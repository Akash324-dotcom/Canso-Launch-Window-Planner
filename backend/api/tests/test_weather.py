"""Task A4: the weather endpoints, the outage policy and the weather cache.

Spec IV.3 and IV.4 name the two read endpoints. The seam 1 signatures of
``docs/00_INTEGRATION_CONTRACT.md`` say the service calls
``backend.weather.probability`` and ``backend.weather.hindcast`` the moment those
exist and reads ``backend/fixtures`` until then, so both paths are exercised here:
the offline path directly, and the seam through a stand-in module injected into
``sys.modules``, which proves the delegation and the frozen keyword arguments
without waiting for WEATHER.

The chosen outage behaviour is recorded in ``backend/api/README.md`` and in
``docs/log/api.md``: a dead weather layer never fails the window route. A cached
weather answer is served, and a request with no cached answer returns the window
rows with ``forecast_issue_time`` null and the neutral values the frozen schema
admits. Nothing returns 500.
"""

from __future__ import annotations

import json
import sys
import types
from pathlib import Path
from typing import Any, Callable

import pytest
from fastapi.testclient import TestClient

from backend.api import weather as weather_layer
from backend.api.config import Settings
from backend.api.schemas import errors_for

WEATHER_SCHEMA = "weather_probability_response"
SKILL_SCHEMA = "skill_response"
WINDOWS_SCHEMA = "windows_response"

LIVE_WEATHER = None
try:  # pragma: no cover - depends on whether WEATHER has landed
    from backend import weather as _weather

    LIVE_WEATHER = getattr(_weather, "probability", None)
except ImportError:
    LIVE_WEATHER = None

FIXTURE_DIR = Path(__file__).resolve().parents[2] / "fixtures"


def offline_document(settings: Settings, name: str) -> dict[str, Any]:
    return json.loads(settings.fixture_path(name).read_text(encoding="utf-8"))


def snapshot_date(settings: Settings) -> str:
    return str(offline_document(settings, "weather")["date"])


def recorded_period(settings: Settings) -> dict[str, str]:
    period = offline_document(settings, "skill")["period"]
    return {"period_start": str(period["start"]), "period_end": str(period["end"])}


def windows_request() -> dict[str, Any]:
    return {
        "target": {"type": "SSO", "h_t_km": 674.0},
        "site": "canso",
        "date_range": {"start": "2026-10-05", "end": "2026-10-15"},
        "vehicle_profile_id": "cyclone4m",
        "include_weather": True,
    }


def without_timing(body: dict[str, Any]) -> dict[str, Any]:
    """A response body without the one field a cache replay cannot reproduce."""
    return {key: value for key, value in body.items() if key != "computation_ms"}


def api_source_text() -> str:
    api_dir = Path(__file__).resolve().parents[1]
    return "\n".join(
        path.read_text(encoding="utf-8")
        for path in sorted(api_dir.rglob("*.py"))
        if "tests" not in path.relative_to(api_dir).parts
    )


def failing_live_layer(monkeypatch: pytest.MonkeyPatch) -> None:
    """Make the live weather layer raise, which is what an outage looks like."""

    def unreachable(**kwargs: Any) -> dict[str, Any]:
        raise RuntimeError(f"the weather layer is unreachable: {sorted(kwargs)}")

    monkeypatch.setattr(weather_layer, "live_probability", lambda: unreachable)
    monkeypatch.setattr(weather_layer, "live_hindcast", lambda: unreachable)


def stand_in_weather_module(monkeypatch: pytest.MonkeyPatch, calls: list[dict[str, Any]]) -> None:
    """Install a ``backend.weather`` that records how it was called."""

    def probability(date_iso: str, site: str, criteria_version: str | None = None) -> dict[str, Any]:
        calls.append(
            {
                "kind": "probability",
                "kwargs": {
                    "date_iso": date_iso,
                    "site": site,
                    "criteria_version": criteria_version,
                },
            }
        )
        document = json.loads((FIXTURE_DIR / "weather.json").read_text(encoding="utf-8"))
        document["source"] = "open_meteo"
        document["forecast_issue_time"] = "2026-10-06T06:00:00Z"
        return document

    def hindcast(period_start: str, period_end: str, lead_max: int = 10) -> dict[str, Any]:
        calls.append(
            {"kind": "hindcast", "kwargs": {"period_start": period_start, "period_end": period_end}}
        )
        document = json.loads((FIXTURE_DIR / "skill.json").read_text(encoding="utf-8"))
        document["skill_series"] = [
            row for row in document["skill_series"] if row["lead_time_days"] <= lead_max
        ]
        return document

    module = types.ModuleType("backend.weather")
    module.probability = probability
    module.hindcast = hindcast
    monkeypatch.setitem(sys.modules, "backend.weather", module)


def without_response_caches(settings: Settings) -> Settings:
    """Settings whose response caches are off, so the weather path is exercised."""
    return settings.with_service_overrides("cache", windows_ttl_s=0, weather_ttl_s=0, reads_ttl_s=0)


# --------------------------------------------------------------------------
# GET /v1/weather/probability
# --------------------------------------------------------------------------


def test_weather_probability_returns_the_frozen_spec_iv_3_shape(
    client: TestClient, settings: Settings
) -> None:
    response = client.get(
        "/v1/weather/probability", params={"date": snapshot_date(settings), "site": "canso"}
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert errors_for(WEATHER_SCHEMA, body) == []
    assert body == offline_document(settings, "weather")
    assert body["source"] == "snapshot_cache"


def test_weather_probability_carries_the_criteria_version_of_the_rows_it_read(
    client: TestClient, settings: Settings
) -> None:
    body = client.get("/v1/weather/probability", params={"date": snapshot_date(settings)}).json()
    recorded = offline_document(settings, "weather")
    assert body["criteria_version"] == recorded["criteria_version"]
    assert body["components"] == recorded["components"]
    assert body["horizon_label"] == recorded["horizon_label"]
    assert body["forecast_issue_time"] == recorded["forecast_issue_time"]


def test_weather_probability_without_a_date_is_422(client: TestClient) -> None:
    response = client.get("/v1/weather/probability")
    assert response.status_code == 422, response.text


def test_weather_probability_rejects_a_malformed_date(client: TestClient) -> None:
    response = client.get("/v1/weather/probability", params={"date": "05-10-2026"})
    assert response.status_code == 422, response.text
    assert response.json()["error"] == "request_schema_violation"


def test_weather_probability_for_an_unknown_site_is_404(client: TestClient, settings: Settings) -> None:
    response = client.get(
        "/v1/weather/probability", params={"date": snapshot_date(settings), "site": "not-a-site"}
    )
    assert response.status_code == 404, response.text
    body = response.json()
    assert body["error"] == "unknown_resource"
    assert body["resource_kind"] == "site"


def test_weather_probability_for_a_date_the_record_does_not_cover_is_503(
    client: TestClient, settings: Settings
) -> None:
    """The record answers for the day it records and says so for any other day."""
    response = client.get("/v1/weather/probability", params={"date": "2026-11-30"})
    assert response.status_code == 503, response.text
    assert int(response.headers["retry-after"]) > 0
    body = response.json()
    assert body["fixture_path_active"] is True
    assert body["offline_fixture_path"] == settings.relative(settings.fixture_path("weather"))
    assert snapshot_date(settings) in body["detail"]


def test_weather_probability_survives_a_dead_live_layer_with_the_record_active(
    client: TestClient, settings: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    failing_live_layer(monkeypatch)
    response = client.get("/v1/weather/probability", params={"date": snapshot_date(settings)})
    assert response.status_code == 200, response.text
    assert response.json()["source"] == "snapshot_cache"
    assert errors_for(WEATHER_SCHEMA, response.json()) == []


def test_weather_probability_is_503_when_neither_the_layer_nor_the_record_answers(
    settings: Settings, client_for: Callable[[Settings], TestClient]
) -> None:
    dead = settings.with_fixture_overrides(weather="backend/fixtures/absent-weather.json")
    with client_for(dead) as offline_dead:
        response = offline_dead.get("/v1/weather/probability", params={"date": snapshot_date(settings)})
    assert response.status_code == 503, response.text
    assert int(response.headers["retry-after"]) > 0
    assert response.json()["offline_fixture_path"] == "backend/fixtures/absent-weather.json"


# --------------------------------------------------------------------------
# GET /v1/validation/skill
# --------------------------------------------------------------------------


def test_validation_skill_returns_the_frozen_spec_iv_4_shape(
    client: TestClient, settings: Settings
) -> None:
    response = client.get("/v1/validation/skill", params=recorded_period(settings))
    assert response.status_code == 200, response.text
    body = response.json()
    assert errors_for(SKILL_SCHEMA, body) == []
    recorded = offline_document(settings, "skill")
    for field in (
        "verification_source",
        "reference_forecast",
        "base_rate",
        "skill_series",
        "reliability_bins",
        "roc_points",
        "skill_horizon_measured_days",
    ):
        assert body[field] == recorded[field], field


def test_validation_skill_echoes_the_requested_period(client: TestClient, settings: Settings) -> None:
    period = recorded_period(settings)
    body = client.get("/v1/validation/skill", params={**period, "lead_max": 10}).json()
    assert body["period"] == {"start": period["period_start"], "end": period["period_end"]}
    assert errors_for(SKILL_SCHEMA, body) == []


def test_validation_skill_truncates_the_series_to_lead_max(
    client: TestClient, settings: Settings
) -> None:
    period = recorded_period(settings)
    full = client.get("/v1/validation/skill", params=period).json()
    limited = client.get("/v1/validation/skill", params={**period, "lead_max": 5}).json()
    assert limited["skill_series"] == [
        row for row in full["skill_series"] if row["lead_time_days"] <= 5
    ]
    assert limited["skill_series"]
    assert limited["reliability_bins"] == full["reliability_bins"]
    assert errors_for(SKILL_SCHEMA, limited) == []


def test_validation_skill_without_a_period_is_422(client: TestClient) -> None:
    response = client.get("/v1/validation/skill")
    assert response.status_code == 422, response.text


def test_validation_skill_rejects_a_negative_lead_max(client: TestClient, settings: Settings) -> None:
    response = client.get("/v1/validation/skill", params={**recorded_period(settings), "lead_max": -1})
    assert response.status_code == 422, response.text


def test_validation_skill_for_a_period_the_record_does_not_cover_is_503(
    client: TestClient, settings: Settings
) -> None:
    response = client.get(
        "/v1/validation/skill", params={"period_start": "2019-01-01", "period_end": "2019-02-01"}
    )
    assert response.status_code == 503, response.text
    assert int(response.headers["retry-after"]) > 0
    body = response.json()
    assert body["fixture_path_active"] is True
    assert body["offline_fixture_path"] == settings.relative(settings.fixture_path("skill"))


# --------------------------------------------------------------------------
# Delegation to the WEATHER seam
# --------------------------------------------------------------------------


def test_weather_endpoints_delegate_to_the_live_seam_once_it_exists(
    client: TestClient, settings: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[dict[str, Any]] = []
    stand_in_weather_module(monkeypatch, calls)

    probability = client.get(
        "/v1/weather/probability", params={"date": snapshot_date(settings), "site": "canso"}
    )
    skill = client.get("/v1/validation/skill", params={**recorded_period(settings), "lead_max": 10})

    assert probability.status_code == 200, probability.text
    assert skill.status_code == 200, skill.text
    assert errors_for(WEATHER_SCHEMA, probability.json()) == []
    assert errors_for(SKILL_SCHEMA, skill.json()) == []
    assert probability.json()["source"] == "open_meteo"
    assert probability.json()["forecast_issue_time"] == "2026-10-06T06:00:00Z"
    assert [call["kind"] for call in calls] == ["probability", "hindcast"]


def test_the_live_seam_is_called_with_the_frozen_keyword_arguments(
    settings: Settings, client_for: Callable[[Settings], TestClient], monkeypatch: pytest.MonkeyPatch
) -> None:
    """Seam 1 freezes the names, so a call by keyword must be what the seam sees."""
    calls: list[dict[str, Any]] = []
    stand_in_weather_module(monkeypatch, calls)
    period = recorded_period(settings)
    uncached = settings.with_service_overrides("cache", windows_ttl_s=0, weather_ttl_s=0, reads_ttl_s=0)

    with client_for(uncached) as fresh:
        fresh.get("/v1/weather/probability", params={"date": snapshot_date(settings), "site": "canso"})
        fresh.get("/v1/validation/skill", params=period)

    assert calls[0]["kwargs"] == {
        "date_iso": snapshot_date(settings),
        "site": "canso",
        "criteria_version": settings.default_criteria_version,
    }
    assert calls[1]["kwargs"] == {
        "period_start": period["period_start"],
        "period_end": period["period_end"],
    }


def test_a_live_seam_answer_for_a_date_outside_the_record_is_served(
    client: TestClient, settings: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[dict[str, Any]] = []
    stand_in_weather_module(monkeypatch, calls)
    response = client.get("/v1/weather/probability", params={"date": "2026-10-06"})
    assert response.status_code == 200, response.text
    assert errors_for(WEATHER_SCHEMA, response.json()) == []
    assert calls[0]["kwargs"]["date_iso"] == "2026-10-06"


@pytest.mark.skipif(LIVE_WEATHER is None, reason="backend.weather.probability has not landed yet")
def test_the_live_weather_module_is_the_served_source_once_it_lands(
    client: TestClient, settings: Settings
) -> None:
    body = client.get("/v1/weather/probability", params={"date": snapshot_date(settings)}).json()
    assert errors_for(WEATHER_SCHEMA, body) == []


# --------------------------------------------------------------------------
# The chosen outage behaviour on POST /v1/windows
# --------------------------------------------------------------------------


def test_windows_still_return_when_the_weather_layer_raises(
    settings: Settings, client_for: Callable[[Settings], TestClient], monkeypatch: pytest.MonkeyPatch
) -> None:
    failing_live_layer(monkeypatch)
    with client_for(without_response_caches(settings)) as degraded:
        response = degraded.post("/v1/windows", json=windows_request())
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["windows"]
    assert errors_for(WINDOWS_SCHEMA, body) == []


def test_windows_carry_a_null_forecast_issue_time_and_the_neutral_weather_values(
    settings: Settings, client_for: Callable[[Settings], TestClient], monkeypatch: pytest.MonkeyPatch
) -> None:
    """The frozen schema forbids null for three of the four weather fields."""
    failing_live_layer(monkeypatch)
    with client_for(without_response_caches(settings)) as degraded:
        body = degraded.post("/v1/windows", json=windows_request()).json()
    for window in body["windows"]:
        assert window["forecast_issue_time"] is None
        assert window["horizon_label"] == "CLIMATOLOGY"
        assert window["p_success_components"]["weather"] == 1.0
        assert window["p_success"] == pytest.approx(
            window["p_success_components"]["range"] * window["p_success_components"]["conjunction"]
        )


def test_a_dead_weather_layer_is_not_reported_as_a_source_the_run_read(
    settings: Settings, client_for: Callable[[Settings], TestClient], monkeypatch: pytest.MonkeyPatch
) -> None:
    failing_live_layer(monkeypatch)
    with client_for(without_response_caches(settings)) as degraded:
        body = degraded.post("/v1/windows", json=windows_request()).json()
    sources = body["provenance_block"]["source_files"]
    assert settings.relative(settings.fixture_path("weather")) not in sources
    assert settings.relative(settings.fixture_path("windows")) in sources


def test_a_cached_weather_answer_survives_the_outage(
    settings: Settings, client_for: Callable[[Settings], TestClient], monkeypatch: pytest.MonkeyPatch
) -> None:
    """One success, then a dead layer and a dead record: the cache still answers.

    The cache is per application, so both requests go through one client. After the
    first success the live layer is made to raise and the offline record is made
    unreadable, so an implementation that fell through to either would fail rather
    than quietly return the same numbers.
    """
    warm_settings = settings.with_service_overrides("cache", windows_ttl_s=0, reads_ttl_s=0)
    recorded = offline_document(settings, "weather")["forecast_issue_time"]

    with client_for(warm_settings) as warm:
        first = warm.post("/v1/windows", json=windows_request()).json()
        assert first["windows"][0]["forecast_issue_time"] == recorded

        failing_live_layer(monkeypatch)

        def unreadable(settings_argument: Any, layer: str) -> dict[str, Any]:
            raise AssertionError("the offline record must not be read once the cache answers")

        monkeypatch.setattr(weather_layer, "load_weather_document", unreadable)

        response = warm.post("/v1/windows", json=windows_request())

    assert response.status_code == 200, response.text
    body = response.json()
    assert errors_for(WINDOWS_SCHEMA, body) == []
    assert [window["forecast_issue_time"] for window in body["windows"]] == [
        window["forecast_issue_time"] for window in first["windows"]
    ]
    assert [window["p_success_components"]["weather"] for window in body["windows"]] == [
        window["p_success_components"]["weather"] for window in first["windows"]
    ]


def test_the_weather_cache_stores_and_echoes_the_forecast_issue_time(
    settings: Settings, client_for: Callable[[Settings], TestClient]
) -> None:
    warm_settings = settings.with_service_overrides("cache", windows_ttl_s=0, reads_ttl_s=0)
    with client_for(warm_settings) as warm:
        body = warm.post("/v1/windows", json=windows_request()).json()
        entries = warm.app.state.cache_registry["weather"].entries()
    assert len(entries) == 1
    recorded = offline_document(settings, "weather")["forecast_issue_time"]
    assert next(iter(entries.values())).forecast_issue_time == recorded
    assert body["windows"][0]["forecast_issue_time"] == recorded


def test_the_weather_cache_is_not_shared_across_criteria_versions(
    settings: Settings, client_for: Callable[[Settings], TestClient]
) -> None:
    warm_settings = settings.with_service_overrides("cache", windows_ttl_s=0, reads_ttl_s=0)
    with client_for(warm_settings) as warm:
        warm.post("/v1/windows", json={**windows_request(), "criteria_version": "v1"})
        warm.post("/v1/windows", json={**windows_request(), "criteria_version": "v2"})
        assert len(warm.app.state.cache_registry["weather"]) == 2


def test_a_flush_changes_no_window_number(
    settings: Settings, client_for: Callable[[Settings], TestClient]
) -> None:
    with client_for(settings.with_service_overrides("cache", windows_ttl_s=0, reads_ttl_s=0)) as warm:
        first = warm.post("/v1/windows", json=windows_request()).json()
        registry = warm.app.state.cache_registry
        assert len(registry["weather"]) == 1
        assert registry.flush()["weather"] == 1
        second = warm.post("/v1/windows", json=windows_request()).json()
    assert without_timing(second) == without_timing(first)


def test_the_weather_cache_ttl_is_configuration_not_a_literal(settings: Settings) -> None:
    """Spec IV.8 gives 30 minutes for weather; it must arrive through service.json."""
    assert settings.cache_config["weather_ttl_s"] == 1800
    assert settings.cache_config["weather_ttl_source"]
    assert "1800" not in api_source_text()