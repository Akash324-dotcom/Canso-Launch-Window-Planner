"""WEATHER's Seam 2 obligation: the output of backend.weather validates against the frozen spec IV.3 schema.

Runs offline. The forecast comes from the committed snapshot in backend/weather/data/snapshot/ and the
climatology from backend/weather/data/, so no test here touches the network.
"""

from __future__ import annotations

import json
from datetime import date, timedelta
from pathlib import Path

import pytest

from test_schemas import describe, load_schemas, validator_for

SCHEMA = "weather_probability_response"
REPO = Path(__file__).resolve().parents[2]
FIXTURES = REPO / "backend" / "fixtures"


@pytest.fixture(autouse=True)
def offline(monkeypatch, tmp_path):
    from backend.weather import fetch, service

    monkeypatch.setenv(fetch.OFFLINE_ENV, "1")
    monkeypatch.setattr(fetch, "CACHE_DIR", tmp_path / "cache")
    fetch.clear_memo()
    service.clear_memo()
    yield
    fetch.clear_memo()
    service.clear_memo()


def snapshot_issue_date() -> date:
    snapshot = REPO / "backend" / "weather" / "data" / "snapshot" / "canso" / "open_meteo_ecmwf_ens.json"
    meta = json.loads(snapshot.read_text(encoding="utf-8"))["meta"]
    return date.fromisoformat(meta["forecast_issue_time"][:10])


def assert_valid(body: dict) -> None:
    errors = list(validator_for(SCHEMA).iter_errors(body))
    assert not errors, describe(errors)


def source_enum() -> set[str]:
    schemas, _ = load_schemas()
    return set(schemas[SCHEMA]["properties"]["source"]["enum"])


def test_forecast_mode_output_validates():
    from backend.weather import probability

    body = probability((snapshot_issue_date() + timedelta(days=1)).isoformat(), "canso")

    assert body["horizon_label"] == "FORECAST"
    assert_valid(body)


def test_climatology_mode_output_validates():
    from backend.weather import probability

    body = probability((snapshot_issue_date() + timedelta(days=60)).isoformat(), "canso")

    assert body["horizon_label"] == "CLIMATOLOGY"
    assert body["ensemble_size"] is None and body["forecast_issue_time"] is None
    assert_valid(body)


def test_every_date_of_a_180_day_sweep_validates_and_uses_only_listed_sources():
    from backend.weather import probability

    start = snapshot_issue_date()
    allowed = source_enum()
    labels = set()
    for offset in range(180):
        body = probability((start + timedelta(days=offset)).isoformat(), "canso")
        assert_valid(body)
        assert body["source"] in allowed
        labels.add(body["horizon_label"])
    assert labels == {"FORECAST", "CLIMATOLOGY"}


def test_every_source_the_layer_can_emit_is_in_the_spec_enum():
    from backend.weather import climatology, config

    sources = config.load_sources()
    emitted = {entry["response_source"] for entry in sources["sources"].values()}
    emitted.add(sources["climatology_archive"]["response_source"])
    emitted.add(climatology.SOURCE)

    assert emitted <= source_enum()


def test_the_weather_fixture_validates():
    assert_valid(json.loads((FIXTURES / "weather.json").read_text(encoding="utf-8")))


# GET /v1/validation/skill (spec IV.4), issue #7 ---------------------------------------------------------------

def assert_valid_skill(body: dict) -> None:
    errors = list(validator_for("skill_response").iter_errors(body))
    assert not errors, describe(errors)


def test_the_hindcast_output_validates_field_for_field(monkeypatch, tmp_path):
    from backend.weather import config, hindcast

    monkeypatch.setattr(hindcast, "CACHE_DIR", tmp_path / "hindcast")
    start, end = hindcast.longest_period("canso")

    lead_max = config.load_sources()["hindcast"]["lead_max_days"]

    body = hindcast(start, end, lead_max)

    assert_valid_skill(body)
    assert len(body["skill_series"]) == lead_max


def test_the_skill_fixture_validates():
    assert_valid_skill(json.loads((FIXTURES / "skill.json").read_text(encoding="utf-8")))

