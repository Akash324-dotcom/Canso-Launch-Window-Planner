"""The service against the real ``backend.engine`` and ``backend.weather``.

Every other file of this suite runs the offline path or a stand-in module (see
``conftest.layers``). The tests here run the two real modules through the routes, so a
mismatch at a seam shows up as a failing test and not as a silently neutral number.
Each of them records a defect that was found when ENGINE and WEATHER landed:

* the service default ``criteria_version`` was refused by the weather layer, the window
  route swallowed the refusal and every window was served with the weather factor 1.0;
* an unknown site reached the engine and came back as an unhandled ``ValueError``;
* ``lead_max`` changed the reliability bins of the skill endpoint on the live path and
  only the series on the recorded path.

The weather layer runs with ``LAUNCHWIN_WEATHER_OFFLINE=1`` and an empty private cache,
so it answers from the committed snapshot and climatology and never from the network.
Expected weather values are taken from the weather layer in the same process, not typed
here, so the tests do not depend on the day they run.
"""

from __future__ import annotations

import copy
from typing import Any, Callable

import pytest
from fastapi.testclient import TestClient

from backend.api.config import Settings
from backend.api.request_model import effective_request
from backend.api.schemas import errors_for

pytestmark = pytest.mark.live_layers

WINDOWS_SCHEMA = "windows_response"
WEATHER_SCHEMA = "weather_probability_response"
SKILL_SCHEMA = "skill_response"


def engine_answer_for(request: dict[str, Any], settings: Settings) -> dict[str, Any]:
    """The same-process engine answer a live route response must agree with."""
    from backend import engine

    return engine.compute_windows(copy.deepcopy(effective_request(request, settings)))


def test_windows_come_from_the_real_engine_and_say_so(
    client: TestClient, settings: Settings, sso_request: dict[str, Any]
) -> None:
    from backend import engine

    body = client.post("/v1/windows", json=sso_request).json()
    direct = engine.compute_windows(copy.deepcopy(effective_request(sso_request, settings)))

    assert errors_for(WINDOWS_SCHEMA, body) == []
    assert body["engine_version"] == engine.ENGINE_VERSION
    assert body["reachable"] is direct["reachable"] is True
    assert [row["t_liftoff_utc"] for row in body["windows"]] == [
        row["t_liftoff_utc"] for row in direct["windows"]
    ]
    assert body["windows"]
    sources = body["provenance_block"]["source_files"]
    assert settings.relative(settings.fixture_path("windows")) not in sources


def test_every_window_carries_the_real_weather_answer_for_the_request(
    client: TestClient, settings: Settings, sso_request: dict[str, Any]
) -> None:
    """The defect: the weather factor was the neutral 1.0 on every row of every response."""
    from backend import weather

    # The route asks the weather layer once per response, for the first day of the range.
    # 2026-10-06 is used because the committed forecast gives it a probability strictly
    # between 0 and 1, so neither a neutral 1.0 nor a dropped factor could pass.
    request = {**sso_request, "date_range": {"start": "2026-10-06", "end": "2026-10-15"}}
    expected = weather.probability(
        date_iso=request["date_range"]["start"],
        site=request["site"],
        criteria_version=settings.default_criteria_version,
    )
    body = client.post("/v1/windows", json=request).json()

    assert body["windows"]

    assert 0.0 < expected["p_launch"] < 1.0, "a neutral 1.0 would hide the defect this test is for"
    for row in body["windows"]:
        components = row["p_success_components"]
        assert components["weather"] == expected["p_launch"]
        assert row["p_success"] == pytest.approx(
            expected["p_launch"] * components["range"] * components["conjunction"]
        )
        assert row["horizon_label"] == expected["horizon_label"]
        assert row["forecast_issue_time"] == expected["forecast_issue_time"]


def test_the_service_default_criteria_version_names_a_table_the_weather_layer_has(
    settings: Settings,
) -> None:
    from backend.weather import criteria

    assert criteria.canonical_version(settings.default_criteria_version) in criteria.available_versions()


def test_an_unknown_criteria_version_fires_a_constraint_on_every_row(
    client: TestClient, sso_request: dict[str, Any]
) -> None:
    """Spec IV.7 rule 3 and the enumeration of spec IV.1: the outcome is in the body, not hidden."""
    response = client.post("/v1/windows", json={**sso_request, "criteria_version": "v99"})

    assert response.status_code == 200, response.text
    body = response.json()
    assert errors_for(WINDOWS_SCHEMA, body) == []
    assert body["windows"]
    for row in body["windows"]:
        assert row["constraint_fired"] == "criteria_version_missing"
        assert row["forecast_issue_time"] is None
        assert row["p_success_components"]["weather"] == 1.0


def test_an_unknown_criteria_version_does_not_overwrite_a_constraint_the_engine_fired(
    client: TestClient, sso_request: dict[str, Any]
) -> None:
    blocked = {
        **sso_request,
        "corridor": {"A_min_deg": 90.0, "A_max_deg": 150.0},
        "criteria_version": "v99",
    }
    body = client.post("/v1/windows", json=blocked).json()

    assert body["reachable"] is False
    assert {row["constraint_fired"] for row in body["windows"]} == {"hazard_area"}


def test_a_corridor_blocked_target_keeps_its_rows_with_the_constraint_that_stopped_them(
    client: TestClient, sso_request: dict[str, Any]
) -> None:
    """The engine's documented answer: unreachable, rows kept, each naming the corridor."""
    body = client.post(
        "/v1/windows", json={**sso_request, "corridor": {"A_min_deg": 90.0, "A_max_deg": 150.0}}
    ).json()

    assert errors_for(WINDOWS_SCHEMA, body) == []
    assert body["reachable"] is False
    assert body["windows"] and all(row["constraint_fired"] == "hazard_area" for row in body["windows"])


def test_polar_rows_reach_the_canso_polar_inclination(
    client: TestClient, settings: Settings
) -> None:
    """87.9 deg is geometrically reachable from Canso, so every POLAR row reaches it."""
    from backend import engine

    request = {
        "target": {"type": "POLAR"},
        "site": "canso",
        "date_range": {"start": "2026-10-05", "end": "2026-10-15"},
        "vehicle_profile_id": "cyclone4m",
        "include_weather": False,
    }
    body = client.post("/v1/windows", json=request).json()
    direct = engine_answer_for(request, settings)

    assert errors_for(WINDOWS_SCHEMA, body) == []
    assert body["reachable"] is True
    assert body["windows"]
    for row in body["windows"]:
        assert row["reached_inclination_deg"] == pytest.approx(87.9, abs=0.5)
    assert [row["reached_inclination_deg"] for row in body["windows"]] == [
        row["reached_inclination_deg"] for row in direct["windows"]
    ]


def test_sso_consistency_warning_pins_the_required_inclination_and_altitude(
    client: TestClient, settings: Settings
) -> None:
    """The J2 justification of spec II.6 (II.7): 600 km needs 97.79 deg, and the altitude echoes."""
    request = {
        "target": {"type": "SSO", "h_t_km": 600.0, "i_t_deg": 98.1},
        "site": "canso",
        "date_range": {"start": "2026-10-05", "end": "2026-10-15"},
        "vehicle_profile_id": "cyclone4m",
        "include_weather": False,
    }
    body = client.post("/v1/windows", json=request).json()
    direct = engine_answer_for(request, settings)

    assert errors_for(WINDOWS_SCHEMA, body) == []
    warning = body["sso_consistency_warning"]
    assert warning is not None
    assert warning["requested_inclination_deg"] == 98.1
    assert warning["required_inclination_deg"] == pytest.approx(97.79, abs=0.05)
    assert warning["altitude_km"] == 600.0
    assert warning == direct["sso_consistency_warning"]


def test_corridor_blocked_rows_carry_no_gap_pricing(
    client: TestClient, sso_request: dict[str, Any]
) -> None:
    """Spec II.5 prices a gap to the reachable interval, not a corridor violation."""
    body = client.post(
        "/v1/windows", json={**sso_request, "corridor": {"A_min_deg": 90.0, "A_max_deg": 150.0}}
    ).json()

    assert errors_for(WINDOWS_SCHEMA, body) == []
    assert body["reachable"] is False
    assert body["windows"]
    assert body["plane_change_dv_ms"] is None


def test_advertised_leo_is_200_with_empty_windows_and_a_penalty(
    client: TestClient, leo_request: dict[str, Any]
) -> None:
    """Spec IV.7 rule 1: geometrically unreachable is still a 200 physics answer."""
    response = client.post("/v1/windows", json=leo_request)

    assert response.status_code == 200, response.text
    body = response.json()
    assert errors_for(WINDOWS_SCHEMA, body) == []
    assert body["windows"] == []
    assert body["reachable"] is False
    assert body["plane_change_dv_ms"] is not None


def test_a_dead_weather_layer_on_the_live_path_names_the_engine_vehicle_profile(
    settings: Settings,
    client_for: Callable[[Settings], Any],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The live run reads the engine vehicle profile, not the stub windows fixture."""
    from backend.api import weather as weather_layer

    def unreachable(**kwargs: Any) -> dict[str, Any]:
        raise RuntimeError(f"the weather layer is unreachable: {sorted(kwargs)}")

    monkeypatch.setattr(weather_layer, "live_probability", lambda: unreachable)
    monkeypatch.setattr(weather_layer, "live_hindcast", lambda: unreachable)
    uncached = settings.with_service_overrides("cache", windows_ttl_s=0, weather_ttl_s=0, reads_ttl_s=0)
    request = {
        "target": {"type": "SSO", "h_t_km": 674.0},
        "site": "canso",
        "date_range": {"start": "2026-10-05", "end": "2026-10-15"},
        "vehicle_profile_id": "cyclone4m",
        "include_weather": True,
    }
    with client_for(uncached) as degraded:
        body = degraded.post("/v1/windows", json=request).json()

    assert errors_for(WINDOWS_SCHEMA, body) == []
    sources = body["provenance_block"]["source_files"]
    assert settings.relative(settings.fixture_path("weather")) not in sources
    assert settings.relative(settings.fixture_path("windows")) not in sources
    assert settings.relative(settings.vehicle_profile_path("cyclone4m")) in sources
    assert body["windows"]
    for row in body["windows"]:
        assert row["forecast_issue_time"] is None


def test_an_unknown_site_is_a_404_before_the_engine_is_asked(
    client: TestClient, sso_request: dict[str, Any]
) -> None:
    response = client.post("/v1/windows", json={**sso_request, "site": "not-a-site"})

    assert response.status_code == 404, response.text
    assert "not-a-site" in response.json()["detail"]


def test_weather_probability_is_the_answer_of_the_real_layer(
    client: TestClient, settings: Settings
) -> None:
    from backend import weather

    for date_iso in ("2026-10-06", "2027-01-15"):
        expected = weather.probability(date_iso=date_iso, site="canso", criteria_version=None)
        response = client.get("/v1/weather/probability", params={"date": date_iso})

        assert response.status_code == 200, response.text
        assert errors_for(WEATHER_SCHEMA, response.json()) == []
        assert response.json() == expected


def test_skill_is_the_real_hindcast_and_lead_max_only_truncates_the_series(
    client: TestClient,
) -> None:
    from backend import weather
    from backend.weather.hindcast import longest_period

    start, end = longest_period("canso")
    period = {"period_start": start, "period_end": end}
    expected = weather.hindcast(period_start=start, period_end=end)

    full = client.get("/v1/validation/skill", params=period).json()
    limited = client.get("/v1/validation/skill", params={**period, "lead_max": 5}).json()

    assert errors_for(SKILL_SCHEMA, full) == [] and errors_for(SKILL_SCHEMA, limited) == []
    for field in ("base_rate", "skill_series", "reliability_bins", "roc_points", "skill_horizon_measured_days"):
        assert full[field] == expected[field], field
    assert [row["lead_time_days"] for row in limited["skill_series"]] == [1, 2, 3, 4, 5]
    assert limited["skill_series"] == full["skill_series"][:5]
    assert limited["reliability_bins"] == full["reliability_bins"]
    assert limited["skill_horizon_measured_days"] == full["skill_horizon_measured_days"]
