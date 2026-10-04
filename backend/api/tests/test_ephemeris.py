"""Task A5: the ephemeris endpoint of spec IV.2.

Three named classes are served from recorded offline ground-track segments, and a
custom id is served from the closed-form circular ground track of the target its
POST recorded. Both go through one resampler, so ``step_s`` means the same thing for
every id. The tests below pin the contract, not the stub: ``frame`` is ECEF, the
ground track validity flag follows the three-day horizon, an unknown id is a 404,
and no id is ever served from an invented geometry.
"""

from __future__ import annotations

import datetime as dt
import json
import math
import sys
import types
from typing import Any

import pytest
from fastapi.testclient import TestClient

from backend.api import ephemeris
from backend.api.config import Settings
from backend.api.schemas import errors_for

EPHEMERIS_SCHEMA = "ephemeris_response"

PRESET_IDS = ("leo45", "polar879", "sso981")
RECORDED_EPOCH = "2026-10-05T13:40:00Z"

LIVE_ENGINE_EPHEMERIS = None
try:  # pragma: no cover - depends on whether ENGINE has landed
    from backend import engine as _engine

    LIVE_ENGINE_EPHEMERIS = getattr(_engine, "ephemeris", None)
except ImportError:
    LIVE_ENGINE_EPHEMERIS = None


def recorded(settings: Settings, orbit_id: str) -> dict[str, Any]:
    return json.loads(settings.base_track_path(orbit_id).read_text(encoding="utf-8"))


def one_day_query(**extra: Any) -> dict[str, Any]:
    query: dict[str, Any] = {
        "start": RECORDED_EPOCH,
        "end": "2026-10-06T13:40:00Z",
        "step_s": 900,
    }
    query.update(extra)
    return query


def first_point(body: dict[str, Any]) -> dict[str, Any]:
    assert body["points"], "the endpoint must not answer with an empty track"
    return body["points"][0]


# --------------------------------------------------------------------------
# The three named classes
# --------------------------------------------------------------------------


@pytest.mark.parametrize("orbit_id", PRESET_IDS)
def test_each_named_class_returns_ecef_points(
    client: TestClient, settings: Settings, orbit_id: str
) -> None:
    response = client.get(f"/v1/orbits/{orbit_id}/ephemeris", params=one_day_query())
    assert response.status_code == 200, response.text
    body = response.json()
    assert errors_for(EPHEMERIS_SCHEMA, body) == []
    assert body["orbit_id"] == orbit_id
    assert body["frame"] == "ECEF"
    assert body["points"]


@pytest.mark.parametrize("orbit_id", PRESET_IDS)
def test_the_ground_track_is_valid_within_the_three_day_horizon(
    client: TestClient, settings: Settings, orbit_id: str
) -> None:
    """Spec IV.2: valid within three days of the start."""
    body = client.get(f"/v1/orbits/{orbit_id}/ephemeris", params=one_day_query()).json()
    assert body["ground_track_valid"] is True


@pytest.mark.parametrize("orbit_id", PRESET_IDS)
def test_the_ground_track_is_invalid_beyond_the_three_day_horizon(
    client: TestClient, settings: Settings, orbit_id: str
) -> None:
    body = client.get(
        f"/v1/orbits/{orbit_id}/ephemeris",
        params={"start": RECORDED_EPOCH, "end": "2026-10-09T13:40:00Z", "step_s": 3600},
    ).json()
    assert body["ground_track_valid"] is False
    assert body["points"]
    assert errors_for(EPHEMERIS_SCHEMA, body) == []


def test_the_horizon_is_measured_from_the_requested_start(
    client: TestClient, settings: Settings
) -> None:
    """Exactly three days is inside the horizon; a second more is outside it."""
    horizon_days = settings.ephemeris_config["ground_track_horizon_days"]
    start = dt.datetime.fromisoformat(RECORDED_EPOCH.replace("Z", "+00:00"))
    inside = start + dt.timedelta(days=horizon_days)
    outside = inside + dt.timedelta(seconds=1)
    for moment, expected in ((inside, True), (outside, False)):
        body = client.get(
            "/v1/orbits/sso981/ephemeris",
            params={
                "start": RECORDED_EPOCH,
                "end": moment.isoformat().replace("+00:00", "Z"),
                "step_s": 3600,
            },
        ).json()
        assert body["ground_track_valid"] is expected, moment


@pytest.mark.parametrize("orbit_id", PRESET_IDS)
def test_every_response_carries_the_constants_block(
    client: TestClient, settings: Settings, orbit_id: str
) -> None:
    from backend.api.provenance import load_constants

    body = client.get(f"/v1/orbits/{orbit_id}/ephemeris", params=one_day_query()).json()
    constants = load_constants(settings)
    assert errors_for("constants_block", body["constants_block"]) == []
    for name, value in constants.values.items():
        assert body["constants_block"][name] == value, name


def test_the_citation_id_of_an_ephemeris_read_is_reproducible(
    client: TestClient, settings: Settings
) -> None:
    query = one_day_query()
    first = client.get("/v1/orbits/sso981/ephemeris", params=query).json()
    second = client.get("/v1/orbits/sso981/ephemeris", params=query).json()
    assert first["constants_block"]["citation_id"] == second["constants_block"]["citation_id"]
    assert first["constants_block"]["citation_id"].startswith("run_20261005_")


def test_a_different_step_gives_a_different_run_identifier(
    client: TestClient, settings: Settings
) -> None:
    coarse = client.get("/v1/orbits/sso981/ephemeris", params=one_day_query()).json()
    fine = client.get(
        "/v1/orbits/sso981/ephemeris", params=one_day_query(step_s=300)
    ).json()
    assert coarse["constants_block"]["citation_id"] != fine["constants_block"]["citation_id"]


# --------------------------------------------------------------------------
# step_s and the query contract
# --------------------------------------------------------------------------


@pytest.mark.parametrize("step_s", [300, 600, 900, 1800, 3600])
def test_step_s_is_honoured(client: TestClient, settings: Settings, step_s: int) -> None:
    body = client.get(
        "/v1/orbits/sso981/ephemeris", params=one_day_query(step_s=step_s)
    ).json()
    epochs = [dt.datetime.fromisoformat(point["t_utc"].replace("Z", "+00:00")) for point in body["points"]]
    gaps = {(b - a).total_seconds() for a, b in zip(epochs, epochs[1:])}
    assert gaps == {float(step_s)}, gaps


def test_the_grid_starts_at_the_requested_start(client: TestClient, settings: Settings) -> None:
    body = client.get("/v1/orbits/sso981/ephemeris", params=one_day_query()).json()
    assert first_point(body)["t_utc"] == RECORDED_EPOCH


def test_the_grid_ends_at_or_before_the_requested_end(
    client: TestClient, settings: Settings
) -> None:
    body = client.get("/v1/orbits/sso981/ephemeris", params=one_day_query()).json()
    assert body["points"][-1]["t_utc"] <= "2026-10-06T13:40:00Z"


def test_the_default_step_is_the_configured_one(client: TestClient, settings: Settings) -> None:
    assert settings.ephemeris_config["default_step_s"] == 300
    body = client.get(
        "/v1/orbits/sso981/ephemeris",
        params={"start": RECORDED_EPOCH, "end": "2026-10-05T15:40:00Z"},
    ).json()
    epochs = [dt.datetime.fromisoformat(point["t_utc"].replace("Z", "+00:00")) for point in body["points"]]
    assert {(b - a).total_seconds() for a, b in zip(epochs, epochs[1:])} == {
        float(settings.ephemeris_config["default_step_s"])
    }


def test_a_missing_start_or_end_is_422(client: TestClient) -> None:
    assert client.get("/v1/orbits/sso981/ephemeris").status_code == 422
    assert client.get("/v1/orbits/sso981/ephemeris", params={"start": RECORDED_EPOCH}).status_code == 422


def test_an_end_before_the_start_is_422(client: TestClient) -> None:
    response = client.get(
        "/v1/orbits/sso981/ephemeris",
        params={"start": "2026-10-06T13:40:00Z", "end": RECORDED_EPOCH},
    )
    assert response.status_code == 422, response.text


@pytest.mark.parametrize("step_s", [0, -300])
def test_a_non_positive_step_is_422(client: TestClient, step_s: int) -> None:
    response = client.get(
        "/v1/orbits/sso981/ephemeris", params=one_day_query(step_s=step_s)
    )
    assert response.status_code == 422, response.text


def test_a_non_numeric_step_is_422(client: TestClient) -> None:
    response = client.get("/v1/orbits/sso981/ephemeris", params=one_day_query(step_s="soon"))
    assert response.status_code == 422, response.text


def test_a_request_beyond_the_point_ceiling_is_422_and_says_which_ceiling(
    client: TestClient, settings: Settings
) -> None:
    ceiling = settings.ephemeris_config["max_points"]
    response = client.get(
        "/v1/orbits/sso981/ephemeris",
        params={"start": RECORDED_EPOCH, "end": "2027-10-05T13:40:00Z", "step_s": 300},
    )
    assert response.status_code == 422, response.text
    assert str(ceiling) in response.json()["detail"]


def test_no_ephemeris_request_returns_500(client: TestClient, settings: Settings) -> None:
    queries = [
        {"start": RECORDED_EPOCH, "end": "2026-10-06T13:40:00Z", "step_s": 900},
        {"start": "not-a-date", "end": "2026-10-06T13:40:00Z"},
        {"start": RECORDED_EPOCH, "end": "2026-10-06T13:40:00Z", "step_s": 0},
    ]
    for query in queries:
        response = client.get("/v1/orbits/sso981/ephemeris", params=query)
        assert response.status_code < 500, (query, response.text)


# --------------------------------------------------------------------------
# Unknown and custom ids
# --------------------------------------------------------------------------


def test_an_unknown_orbit_id_is_404(client: TestClient, settings: Settings) -> None:
    response = client.get("/v1/orbits/not-an-orbit/ephemeris", params=one_day_query())
    assert response.status_code == 404, response.text
    body = response.json()
    assert body["error"] == "unknown_resource"
    assert body["resource_kind"] == "orbit"
    assert body["resource_id"] == "not-an-orbit"


def test_a_custom_id_recorded_by_a_window_post_is_not_a_404(
    client: TestClient, settings: Settings
) -> None:
    posted = client.post(
        "/v1/windows",
        json={
            "target": {"type": "CUSTOM", "h_t_km": 500.0, "i_t_deg": 70.0},
            "date_range": {"start": "2026-10-05", "end": "2026-10-15"},
            "vehicle_profile_id": "cyclone4m",
            "include_weather": False,
        },
    )
    assert posted.status_code == 200, posted.text
    orbit_id = "custom-70.0-500.0"

    response = client.get(f"/v1/orbits/{orbit_id}/ephemeris", params=one_day_query())
    assert response.status_code == 200, response.text
    body = response.json()
    assert errors_for(EPHEMERIS_SCHEMA, body) == []
    assert body["orbit_id"] == orbit_id
    assert body["frame"] == "ECEF"
    assert body["points"]


def test_a_custom_id_track_is_the_recorded_target_not_a_preset_track(
    client: TestClient, settings: Settings
) -> None:
    client.post(
        "/v1/windows",
        json={
            "target": {"type": "CUSTOM", "h_t_km": 500.0, "i_t_deg": 70.0},
            "date_range": {"start": "2026-10-05", "end": "2026-10-15"},
            "vehicle_profile_id": "cyclone4m",
            "include_weather": False,
        },
    )
    body = client.get(
        "/v1/orbits/custom-70.0-500.0/ephemeris", params=one_day_query()
    ).json()
    latitudes = [point["lat_deg"] for point in body["points"]]
    assert max(abs(latitude) for latitude in latitudes) <= 70.0 + 1e-6
    assert max(point["alt_km"] for point in body["points"]) == pytest.approx(500.0, abs=1e-6)


def test_a_preset_class_request_uses_the_preset_id_not_a_custom_one(
    client: TestClient, settings: Settings
) -> None:
    client.post(
        "/v1/windows",
        json={
            "target": {"type": "SSO", "h_t_km": 674.0},
            "date_range": {"start": "2026-10-05", "end": "2026-10-15"},
            "vehicle_profile_id": "cyclone4m",
            "include_weather": False,
        },
    )
    assert client.get("/v1/orbits/sso981/ephemeris", params=one_day_query()).status_code == 200


def test_a_custom_id_is_found_in_the_stored_run_record_after_a_restart(
    settings: Settings, client_for: Any
) -> None:
    from backend.api.citation import stored_orbits

    with client_for(settings) as first_process:
        posted = first_process.post(
            "/v1/windows",
            json={
                "target": {"type": "CUSTOM", "h_t_km": 500.0, "i_t_deg": 70.0},
                "date_range": {"start": "2026-10-05", "end": "2026-10-15"},
                "vehicle_profile_id": "cyclone4m",
                "include_weather": False,
            },
        )
        assert posted.status_code == 200, posted.text

    known = {orbit.orbit_id for orbit in stored_orbits(settings)}
    assert "custom-70.0-500.0" in known

    with client_for(settings) as second_process:
        response = second_process.get(
            "/v1/orbits/custom-70.0-500.0/ephemeris", params=one_day_query()
        )
    assert response.status_code == 200, response.text


# --------------------------------------------------------------------------
# The recorded segments and the resampler
# --------------------------------------------------------------------------


@pytest.mark.parametrize("orbit_id", PRESET_IDS)
def test_every_recorded_segment_is_valid_against_the_frozen_schema(
    settings: Settings, orbit_id: str
) -> None:
    document = recorded(settings, orbit_id)
    assert document["orbit_id"] == orbit_id
    assert errors_for(EPHEMERIS_SCHEMA, document) == []


def test_every_base_track_is_a_document_this_workflow_owns(settings: Settings) -> None:
    """``backend/fixtures/`` is FRONTEND's content under contract section 0 and Seam 3.

    The API reads the offline fallback from there, but a record the service resamples and
    repeats is configuration of this workflow, so it lives under ``backend/api/data``.
    """
    for orbit_id in PRESET_IDS:
        relative = settings.relative(settings.base_track_path(orbit_id))
        assert relative.startswith("backend/api/"), (orbit_id, relative)


def test_the_offline_fallback_document_is_still_served_as_the_demo_floor(
    settings: Settings,
) -> None:
    """It stays on disk and stays schema valid; nothing reads it as a base track."""
    fallback = settings.fixture_path("ephemeris")
    assert fallback.is_file()
    assert errors_for(EPHEMERIS_SCHEMA, json.loads(fallback.read_text(encoding="utf-8"))) == []
    assert fallback.resolve() not in {
        settings.base_track_path(orbit_id).resolve() for orbit_id in PRESET_IDS
    }


@pytest.mark.parametrize("orbit_id", PRESET_IDS)
def test_the_resampler_reproduces_a_recorded_segment_exactly(
    settings: Settings, orbit_id: str
) -> None:
    document = recorded(settings, orbit_id)
    points = document["points"]
    epochs = [dt.datetime.fromisoformat(point["t_utc"].replace("Z", "+00:00")) for point in points]
    step = (epochs[1] - epochs[0]).total_seconds()
    resampled = ephemeris.resample(points, epochs[0], epochs[-1], step)
    assert len(resampled) == len(points)
    for served, source in zip(resampled, points):
        assert served["t_utc"] == source["t_utc"]
        assert served["lat_deg"] == pytest.approx(source["lat_deg"], abs=1e-6)
        assert served["lon_deg"] == pytest.approx(source["lon_deg"], abs=1e-6)
        assert served["alt_km"] == pytest.approx(source["alt_km"], abs=1e-6)


def target_class_of(settings: Settings, orbit_id: str) -> str:
    for name, preset_id in settings.ephemeris_config["preset_ids"].items():
        if preset_id == orbit_id:
            return name
    raise AssertionError(f"{orbit_id} is not one of the configured presets")


@pytest.mark.parametrize("orbit_id", PRESET_IDS)
def test_a_recorded_segment_spans_one_revolution(
    settings: Settings, orbit_id: str
) -> None:
    """A repeat beyond the recorded span must not jump most of a track."""
    document = recorded(settings, orbit_id)
    latitudes = [point["lat_deg"] for point in document["points"]]
    assert min(latitudes) < 0.0 < max(latitudes)
    published = float(settings.target_classes[target_class_of(settings, orbit_id)]["i_t_deg"])
    extreme = math.degrees(math.asin(abs(math.sin(math.radians(published)))))
    assert max(abs(latitude) for latitude in latitudes) == pytest.approx(extreme, abs=0.2)


def test_a_retrograde_class_reaches_below_its_inclination(settings: Settings) -> None:
    """The sub-satellite latitude of a retrograde orbit peaks at 180 - i, not at i."""
    latitudes = [point["lat_deg"] for point in recorded(settings, "sso981")["points"]]
    published = float(settings.target_classes["SSO"]["i_t_deg"])
    assert published > 90.0
    assert max(abs(latitude) for latitude in latitudes) == pytest.approx(
        180.0 - published, abs=0.2
    )


def test_a_prograde_class_reaches_its_inclination(settings: Settings) -> None:
    latitudes = [point["lat_deg"] for point in recorded(settings, "leo45")["points"]]
    published = float(settings.target_classes["LEO"]["i_t_deg"])
    assert published < 90.0
    assert max(abs(latitude) for latitude in latitudes) == pytest.approx(published, abs=0.2)


@pytest.mark.parametrize("orbit_id", ["polar879", "sso981"])
def test_a_track_that_can_reach_the_site_passes_over_it(
    settings: Settings, orbit_id: str
) -> None:
    """The southbound pass crosses the site, which is what makes a corridor track."""
    site = settings.site_document("canso")
    site_lat = float(site["phi_s_deg"])
    site_lon = float(site["lambda_s_deg"])
    points = recorded(settings, orbit_id)["points"]
    epochs = [dt.datetime.fromisoformat(point["t_utc"].replace("Z", "+00:00")) for point in points]
    fine = ephemeris.resample(points, epochs[0], epochs[-1], 1.0)
    crossing = min(
        fine,
        key=lambda point: abs(point["lat_deg"] - site_lat) + abs(point["lon_deg"] - site_lon),
    )
    assert abs(crossing["lat_deg"] - site_lat) < 0.2, (orbit_id, crossing)
    assert abs(crossing["lon_deg"] - site_lon) < 0.2, (orbit_id, crossing)


def test_the_leo45_track_cannot_reach_the_site_latitude(settings: Settings) -> None:
    """Spec II.4 reachability, visible in the track: 45.1 deg peaks below 45.3 N."""
    site_lat = float(settings.site_document("canso")["phi_s_deg"])
    latitudes = [point["lat_deg"] for point in recorded(settings, "leo45")["points"]]
    assert max(latitudes) < site_lat
    published = float(settings.target_classes["LEO"]["i_t_deg"])
    assert published < site_lat


def test_the_canso_longitude_is_crossed_by_every_recorded_segment(settings: Settings) -> None:
    """One revolution advances the track once around, less the Earth's rotation."""
    for orbit_id in PRESET_IDS:
        longitudes = [point["lon_deg"] for point in recorded(settings, orbit_id)["points"]]
        gaps = [abs((b - a + 180.0) % 360.0 - 180.0) for a, b in zip(longitudes, longitudes[1:])]
        assert max(gaps) < 30.0, orbit_id
        assert sum(gaps) > 300.0, orbit_id


def test_the_closed_form_track_matches_a_recorded_segment(settings: Settings) -> None:
    """The generator that produced the records is asserted against one of them."""
    orbit_id = "sso981"
    document = recorded(settings, orbit_id)
    orbit = ephemeris.preset_orbit(settings, orbit_id)
    site = settings.site_document("canso")
    generated = ephemeris.closed_form_segment(
        settings,
        orbit,
        first_epoch=document["points"][0]["t_utc"],
        site_latitude_deg=float(site["phi_s_deg"]),
        site_longitude_deg=float(site["lambda_s_deg"]),
    )
    assert len(generated) == len(document["points"])
    for served, source in zip(generated, document["points"]):
        assert served["lat_deg"] == pytest.approx(source["lat_deg"], abs=1e-6)
        assert served["lon_deg"] == pytest.approx(source["lon_deg"], abs=1e-6)
        assert served["alt_km"] == pytest.approx(source["alt_km"], abs=1e-6)


# --------------------------------------------------------------------------
# The propagation seam
# --------------------------------------------------------------------------


def stand_in_engine(monkeypatch: pytest.MonkeyPatch, calls: list[dict[str, Any]]) -> None:
    """Install a ``backend.engine`` whose ephemeris records how it was called."""

    def ephemeris(**kwargs: Any) -> dict[str, Any]:
        calls.append(dict(kwargs))
        return {
            "orbit_id": kwargs["orbit_id"],
            "frame": "ECEF",
            "points": [
                {"t_utc": kwargs["start"], "lat_deg": 10.0, "lon_deg": 20.0, "alt_km": 700.0},
                {"t_utc": kwargs["end"], "lat_deg": 11.0, "lon_deg": 21.0, "alt_km": 701.0},
            ],
        }

    module = types.ModuleType("backend.engine")
    module.ephemeris = ephemeris
    monkeypatch.setitem(sys.modules, "backend.engine", module)


def test_the_ephemeris_endpoint_delegates_to_the_engine_seam_once_it_exists(
    client: TestClient, settings: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[dict[str, Any]] = []
    stand_in_engine(monkeypatch, calls)

    response = client.get("/v1/orbits/sso981/ephemeris", params=one_day_query())

    assert response.status_code == 200, response.text
    body = response.json()
    assert errors_for(EPHEMERIS_SCHEMA, body) == []
    assert body["frame"] == "ECEF"
    assert body["orbit_id"] == "sso981"
    assert body["points"][0]["lat_deg"] == 10.0
    assert len(calls) == 1
    assert calls[0]["orbit_id"] == "sso981"
    assert calls[0]["start"] == RECORDED_EPOCH
    assert calls[0]["step_s"] == 900
    assert calls[0]["site"] == settings.default_site, "the ascent is drawn from the site of the service"


def test_a_seam_answer_that_breaks_the_contract_falls_through_to_the_record(
    client: TestClient, settings: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A live layer that returns something the contract does not describe is worse
    than the offline floor, so the floor answers instead."""

    def broken(**kwargs: Any) -> dict[str, Any]:
        return {"orbit_id": kwargs["orbit_id"], "frame": "ECEF", "points": [{"lat_deg": 1.0}]}

    module = types.ModuleType("backend.engine")
    module.ephemeris = broken
    monkeypatch.setitem(sys.modules, "backend.engine", module)

    body = client.get("/v1/orbits/sso981/ephemeris", params=one_day_query()).json()
    assert errors_for(EPHEMERIS_SCHEMA, body) == []
    assert len(body["points"]) > 2


def test_a_seam_that_raises_falls_through_to_the_record(
    client: TestClient, settings: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    def unreachable(**kwargs: Any) -> dict[str, Any]:
        raise RuntimeError("the propagation seam is unavailable")

    module = types.ModuleType("backend.engine")
    module.ephemeris = unreachable
    monkeypatch.setitem(sys.modules, "backend.engine", module)

    response = client.get("/v1/orbits/sso981/ephemeris", params=one_day_query())
    assert response.status_code == 200, response.text
    assert errors_for(EPHEMERIS_SCHEMA, response.json()) == []


@pytest.mark.skipif(LIVE_ENGINE_EPHEMERIS is None, reason="backend.engine.ephemeris has not landed yet")
def test_the_live_engine_seam_produces_schema_valid_output(
    client: TestClient, settings: Settings
) -> None:
    body = client.get("/v1/orbits/sso981/ephemeris", params=one_day_query()).json()
    assert errors_for(EPHEMERIS_SCHEMA, body) == []