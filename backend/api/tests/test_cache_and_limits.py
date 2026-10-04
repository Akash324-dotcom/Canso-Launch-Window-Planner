"""Task A7: caching and rate limits, spec IV.8.

Two mechanisms, both configured rather than coded: an in-memory TTL cache, and a
per-client request budget. The tests assert behaviour a client can observe, and the
counters the cache and the limiter keep, rather than wall-clock timings, because a
timing assertion is flaky on a loaded machine and the counter is the same statement
made deterministically.

Determinism is the load-bearing property here. Spec III.6 test 6 asks for identical
numbers after a cache flush, so a flush test that compares every numeric field except
``computation_ms``, the one field a replay cannot reproduce, is the honest form of
that assertion. Interpretation 42 of the G0 log already recorded the exclusion.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

import pytest
from fastapi.testclient import TestClient

from backend.api.cache import CacheRegistry, TtlCache, cache_key
from backend.api.config import Settings
from backend.api.limits import RateLimiter, client_key
from backend.api.provenance import canonical_json

SSO_REQUEST = {
    "target": {"type": "SSO", "h_t_km": 674.0},
    "site": "canso",
    "date_range": {"start": "2026-10-05", "end": "2026-10-15"},
    "vehicle_profile_id": "cyclone4m",
    "include_weather": True,
}

READ_PATHS = (
    "/v1/site",
    "/v1/validation/skill?period_start=2026-05-01&period_end=2026-08-31",
    "/v1/weather/probability?date=2026-10-06",
    "/v1/orbits/sso981/ephemeris?start=2026-10-05T13:40:00Z&end=2026-10-05T15:40:00Z&step_s=900",
)


def without_timing(body: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in body.items() if key != "computation_ms"}


def api_source_text() -> str:
    api_dir = Path(__file__).resolve().parents[1]
    return "\n".join(
        path.read_text(encoding="utf-8")
        for path in sorted(api_dir.rglob("*.py"))
        if "tests" not in path.relative_to(api_dir).parts
    )


def limited(settings: Settings, **values: Any) -> Settings:
    return settings.with_service_overrides("rate_limit", **values)


# --------------------------------------------------------------------------
# The cache keys and the cache itself
# --------------------------------------------------------------------------


def test_a_cache_key_is_stable_and_sensitive() -> None:
    payload = {"target": {"type": "SSO"}, "site": "canso"}
    assert cache_key("windows", payload) == cache_key("windows", dict(payload))
    assert cache_key("windows", payload) != cache_key("windows", {**payload, "site": "other"})
    assert cache_key("windows", payload) != cache_key("weather", payload)


def test_an_entry_expires_after_its_lifetime() -> None:
    clock = {"now": 100.0}
    cache = TtlCache("probe", ttl_s=30.0, clock=lambda: clock["now"])
    cache.put("k", {"value": 1})
    assert cache.get("k") is not None
    clock["now"] = 129.9
    assert cache.get("k") is not None
    clock["now"] = 130.0
    assert cache.get("k") is None
    assert len(cache) == 0


def test_a_zero_lifetime_switches_a_cache_off() -> None:
    cache = TtlCache("probe", ttl_s=0.0)
    assert cache.enabled is False
    cache.put("k", {"value": 1})
    assert cache.get("k") is None
    assert len(cache) == 0


def test_an_entry_remembers_the_forecast_issue_time_it_was_stored_with() -> None:
    cache = TtlCache("probe", ttl_s=60.0)
    cache.put("k", {"p_launch": 0.4}, forecast_issue_time="2026-10-06T06:00:00Z")
    assert cache.get("k").forecast_issue_time == "2026-10-06T06:00:00Z"


def test_a_flush_drops_every_entry_and_keeps_the_counters() -> None:
    cache = TtlCache("probe", ttl_s=60.0)
    cache.put("k", 1)
    cache.get("k")
    assert cache.flush() == 1
    assert len(cache) == 0
    assert cache.hits == 1


def test_the_registry_is_built_from_configuration() -> None:
    registry = CacheRegistry({"windows_ttl_s": 10, "weather_ttl_s": 20, "reads_ttl_s": 30})
    assert registry.names() == ["windows", "weather", "reads"]
    assert [cache.ttl_s for cache in registry] == [10.0, 20.0, 30.0]


def test_the_registry_refuses_a_configuration_without_a_lifetime() -> None:
    with pytest.raises(ValueError, match="weather"):
        CacheRegistry({"windows_ttl_s": 10, "reads_ttl_s": 30})


# --------------------------------------------------------------------------
# The window cache on POST /v1/windows
# --------------------------------------------------------------------------


def test_two_identical_posts_hit_the_cache(
    settings: Settings, client_for: Callable[[Settings], TestClient]
) -> None:
    with client_for(settings) as warm:
        first = warm.post("/v1/windows", json=SSO_REQUEST).json()
        windows_cache = warm.app.state.cache_registry["windows"]
        assert len(windows_cache) == 1
        assert windows_cache.misses == 1

        second = warm.post("/v1/windows", json=SSO_REQUEST)

    assert second.status_code == 200, second.text
    assert warm.app.state.cache_registry["windows"].hits == 1
    assert without_timing(second.json()) == without_timing(first)


def test_a_cached_replay_is_byte_identical_including_the_timing_field(
    settings: Settings, client_for: Callable[[Settings], TestClient]
) -> None:
    with client_for(settings) as warm:
        first = warm.post("/v1/windows", json=SSO_REQUEST).json()
        second = warm.post("/v1/windows", json=SSO_REQUEST).json()
    assert canonical_json(first) == canonical_json(second)


def test_a_flushed_cache_changes_no_number(
    settings: Settings, client_for: Callable[[Settings], TestClient]
) -> None:
    """Spec III.6 test 6: a cache flush must not change the answer."""
    with client_for(settings) as warm:
        first = warm.post("/v1/windows", json=SSO_REQUEST).json()
        registry = warm.app.state.cache_registry
        assert registry.flush()["windows"] == 1
        assert len(registry["windows"]) == 0
        second = warm.post("/v1/windows", json=SSO_REQUEST).json()
    assert without_timing(second) == without_timing(first)


def test_a_different_request_is_not_served_from_the_cache(
    settings: Settings, client_for: Callable[[Settings], TestClient]
) -> None:
    with client_for(settings) as warm:
        warm.post("/v1/windows", json=SSO_REQUEST)
        warm.post(
            "/v1/windows",
            json={**SSO_REQUEST, "date_range": {"start": "2026-10-06", "end": "2026-10-16"}},
        )
        assert len(warm.app.state.cache_registry["windows"]) == 2


def test_a_request_spelled_with_the_defaults_hits_the_same_cache_entry(
    settings: Settings, client_for: Callable[[Settings], TestClient]
) -> None:
    with client_for(settings) as warm:
        warm.post("/v1/windows", json=SSO_REQUEST)
        warm.post(
            "/v1/windows",
            json={key: value for key, value in SSO_REQUEST.items() if key != "site"},
        )
        assert len(warm.app.state.cache_registry["windows"]) == 1


def test_the_window_cache_ttl_is_the_specified_twenty_four_hours(settings: Settings) -> None:
    assert settings.cache_config["windows_ttl_s"] == 86400
    assert settings.cache_config["windows_ttl_source"]


def test_a_zero_window_ttl_serves_every_request_fresh(
    settings: Settings, client_for: Callable[[Settings], TestClient]
) -> None:
    off = settings.with_service_overrides("cache", windows_ttl_s=0)
    with client_for(off) as warm:
        warm.post("/v1/windows", json=SSO_REQUEST)
        warm.post("/v1/windows", json=SSO_REQUEST)
        cache = warm.app.state.cache_registry["windows"]
        assert cache.enabled is False
        assert cache.hits == 0
        assert cache.misses == 2


def test_a_run_is_recorded_even_when_the_answer_comes_from_the_cache(
    settings: Settings, client_for: Callable[[Settings], TestClient]
) -> None:
    with client_for(settings) as warm:
        first = warm.post("/v1/windows", json=SSO_REQUEST).json()
        warm.post("/v1/windows", json=SSO_REQUEST)
    assert settings.run_record_path(first["constants_block"]["citation_id"]).is_file()


# --------------------------------------------------------------------------
# The read cache
# --------------------------------------------------------------------------


@pytest.mark.parametrize("path", READ_PATHS)
def test_repeated_reads_hit_the_read_cache(
    settings: Settings, client_for: Callable[[Settings], TestClient], path: str
) -> None:
    with client_for(settings) as warm:
        first = warm.get(path)
        assert first.status_code == 200, first.text
        assert len(warm.app.state.cache_registry["reads"]) == 1
        second = warm.get(path)
    assert second.status_code == 200
    assert canonical_json(second.json()) == canonical_json(first.json())


def test_two_different_reads_do_not_share_a_cache_entry(
    settings: Settings, client_for: Callable[[Settings], TestClient]
) -> None:
    with client_for(settings) as warm:
        warm.get("/v1/site")
        warm.get("/v1/site?site=canso")
        assert len(warm.app.state.cache_registry["reads"]) == 2


def test_a_flush_changes_no_read_number(
    settings: Settings, client_for: Callable[[Settings], TestClient]
) -> None:
    with client_for(settings) as warm:
        first = warm.get("/v1/site").json()
        assert warm.app.state.cache_registry.flush()["reads"] == 1
        second = warm.get("/v1/site").json()
    assert second == first


# --------------------------------------------------------------------------
# The rate limiter
# --------------------------------------------------------------------------


def test_the_shipped_limits_are_the_ones_spec_iv_8_gives(settings: Settings) -> None:
    limits = settings.rate_limit_config
    assert limits["window_s"] == 60
    assert limits["post_windows_per_window"] == 60
    assert limits["reads_per_window"] == 120
    assert limits["retry_after_s"] > 0
    assert limits["source"]


def test_no_cache_lifetime_or_limit_value_is_a_literal_in_the_modules_that_would_hold_one() -> None:
    """A TTL or a budget written into code would make service.json decorative.

    The scan covers the cache, the limiter, the plumbing and the routes, which is
    where such a literal would live. ``ephemeris.py`` is excluded because it converts
    days to seconds, which is a unit and not a lifetime. The configuration key names
    are checked separately, and only where they have no business: the limiter reads
    them because it is the reader of that file, a route must not name one.
    """
    api_dir = Path(__file__).resolve().parents[1]
    modules = [
        api_dir / "cache.py",
        api_dir / "limits.py",
        api_dir / "middleware.py",
        api_dir / "app.py",
        *(api_dir / "routes").glob("*.py"),
    ]
    scanned = "\n".join(path.read_text(encoding="utf-8") for path in sorted(modules))
    for value in ("86400", "1800"):
        assert value not in scanned, value

    routes = "\n".join(path.read_text(encoding="utf-8") for path in sorted((api_dir / "routes").glob("*.py")))
    for key in ("ttl_s", "per_window", "window_s"):
        assert key not in routes, key


def test_exceeding_the_post_budget_is_429_with_retry_after(
    settings: Settings, client_for: Callable[[Settings], TestClient]
) -> None:
    tight = limited(settings, post_windows_per_window=2)
    with client_for(tight) as budgeted:
        assert budgeted.post("/v1/windows", json=SSO_REQUEST).status_code == 200
        assert budgeted.post("/v1/windows", json=SSO_REQUEST).status_code == 200
        response = budgeted.post("/v1/windows", json=SSO_REQUEST)
    assert response.status_code == 429, response.text
    assert int(response.headers["retry-after"]) > 0
    assert response.json()["error"] == "rate_limit_exceeded"
    assert response.json()["retry_after_s"] == int(response.headers["retry-after"])


def test_the_read_budget_is_separate_from_the_post_budget(
    settings: Settings, client_for: Callable[[Settings], TestClient]
) -> None:
    tight = limited(settings, post_windows_per_window=1, reads_per_window=1)
    with client_for(tight) as budgeted:
        assert budgeted.post("/v1/windows", json=SSO_REQUEST).status_code == 200
        assert budgeted.get("/v1/site").status_code == 200
        assert budgeted.post("/v1/windows", json=SSO_REQUEST).status_code == 429
        assert budgeted.get("/v1/site").status_code == 429


@pytest.mark.parametrize("path", ["/v1/site", "/v1/citation?id=run_19700101_deadbeefcafe"])
def test_a_breached_read_budget_is_429_with_retry_after(
    settings: Settings, client_for: Callable[[Settings], TestClient], path: str
) -> None:
    tight = limited(settings, reads_per_window=1)
    with client_for(tight) as budgeted:
        budgeted.get(path)
        response = budgeted.get(path)
    assert response.status_code == 429, response.text
    assert int(response.headers["retry-after"]) > 0


def test_the_limiter_is_disabled_by_configuration(
    settings: Settings, client_for: Callable[[Settings], TestClient]
) -> None:
    off = limited(settings, enabled=False, reads_per_window=1, post_windows_per_window=1)
    with client_for(off) as unbudgeted:
        for _ in range(5):
            assert unbudgeted.get("/v1/site").status_code == 200
            assert unbudgeted.post("/v1/windows", json=SSO_REQUEST).status_code == 200
    assert unbudgeted.app.state.rate_limiter.rejections == 0


def test_the_openapi_document_is_not_charged_against_the_budget(
    settings: Settings, client_for: Callable[[Settings], TestClient]
) -> None:
    """A client fetching the contract must not spend its own budget doing so."""
    tight = limited(settings, reads_per_window=1)
    with client_for(tight) as budgeted:
        assert budgeted.get("/v1/openapi.json").status_code == 200
        assert budgeted.get("/v1/health").status_code == 200
        assert budgeted.get("/v1/site").status_code == 200
        assert budgeted.get("/v1/site").status_code == 429


def test_the_budget_recovers_once_the_window_has_passed(
    settings: Settings, client_for: Callable[[Settings], TestClient]
) -> None:
    """The window slides, so a budget spent is not spent for ever."""
    tight = limited(settings, reads_per_window=1, window_s=1)
    with client_for(tight) as budgeted:
        assert budgeted.get("/v1/site").status_code == 200
        assert budgeted.get("/v1/site").status_code == 429
    import time

    time.sleep(1.05)
    with client_for(tight) as later:
        assert later.get("/v1/site").status_code == 200


def test_the_retry_after_names_the_whole_configured_window(
    settings: Settings, client_for: Callable[[Settings], TestClient]
) -> None:
    """The configured duration is what a client is told to wait when nothing else applies."""
    tight = limited(settings, reads_per_window=1, window_s=60, retry_after_s=60)
    with client_for(tight) as budgeted:
        budgeted.get("/v1/site")
        response = budgeted.get("/v1/site")
    assert response.status_code == 429
    assert int(response.headers["retry-after"]) == 60


def test_a_forwarded_client_address_is_a_separate_budget(
    settings: Settings, client_for: Callable[[Settings], TestClient]
) -> None:
    tight = limited(settings, reads_per_window=1)
    with client_for(tight) as budgeted:
        first = budgeted.get("/v1/site", headers={"x-forwarded-for": "203.0.113.7"})
        second = budgeted.get("/v1/site", headers={"x-forwarded-for": "203.0.113.8"})
    assert first.status_code == 200
    assert second.status_code == 200


def test_a_breached_budget_never_becomes_a_500(
    settings: Settings, client_for: Callable[[Settings], TestClient]
) -> None:
    tight = limited(settings, reads_per_window=1, post_windows_per_window=1)
    with client_for(tight) as budgeted:
        budgeted.post("/v1/windows", json=SSO_REQUEST)
        budgeted.get("/v1/site")
        for path in ("/v1/site", "/v1/weather/probability?date=2026-10-06"):
            assert budgeted.get(path).status_code < 500
        assert budgeted.post("/v1/windows", json=SSO_REQUEST).status_code == 429


# --------------------------------------------------------------------------
# The limiter in isolation
# --------------------------------------------------------------------------


def build_limiter(**overrides: Any) -> RateLimiter:
    clock = {"now": 1000.0}
    config = {
        "enabled": True,
        "window_s": 60,
        "post_windows_per_window": 3,
        "reads_per_window": 3,
        "retry_after_s": 60,
    }
    config.update(overrides)
    return RateLimiter(config, clock=lambda: clock["now"])


def test_the_limiter_counts_within_its_window_and_forgets_after_it() -> None:
    clock = {"now": 1000.0}
    limiter = RateLimiter(
        {"enabled": True, "window_s": 10, "post_windows_per_window": 2, "reads_per_window": 2,
         "retry_after_s": 10},
        clock=lambda: clock["now"],
    )
    limiter.check("read", "a")
    limiter.check("read", "a")
    with pytest.raises(Exception) as caught:
        limiter.check("read", "a")
    assert caught.value.status_code == 429
    clock["now"] += 10.0
    limiter.check("read", "a")


def test_the_limiter_keeps_one_budget_per_client() -> None:
    limiter = build_limiter()
    for _ in range(3):
        limiter.check("read", "a")
    limiter.check("read", "b")
    assert limiter.spent("read", "a") == 3
    assert limiter.spent("read", "b") == 1


def test_the_limiter_refuses_a_bucket_it_was_not_configured_for() -> None:
    limiter = build_limiter()
    with pytest.raises(ValueError, match="write_windows"):
        limiter.check("write_windows", "a")


def test_the_client_key_falls_back_when_there_is_no_peer() -> None:
    class Peerless:
        headers: dict[str, str] = {}
        client = None

    assert client_key(Peerless()) == "unknown"


def test_the_client_key_prefers_the_forwarded_address() -> None:
    class Forwarded:
        headers = {"x-forwarded-for": "203.0.113.7, 198.51.100.2"}
        client = type("Peer", (), {"host": "10.0.0.1"})()

    assert client_key(Forwarded()) == "203.0.113.7"