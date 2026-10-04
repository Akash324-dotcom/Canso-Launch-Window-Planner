"""W8 offline fixture: valid against the contract and produced by the committed script, never hand-typed."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator, FormatChecker

from backend.weather.scripts import build_weather_fixture

REPO = Path(__file__).resolve().parents[3]
FIXTURES = REPO / "backend" / "fixtures"
SCHEMA = REPO / "tests" / "contract" / "schemas" / "weather_probability_response.json"


@pytest.fixture(scope="module")
def validator() -> Draft202012Validator:
    return Draft202012Validator(json.loads(SCHEMA.read_text(encoding="utf-8")), format_checker=FormatChecker())


def test_the_weather_fixture_matches_the_schema(validator):
    body = json.loads((FIXTURES / "weather.json").read_text(encoding="utf-8"))

    assert list(validator.iter_errors(body)) == []
    assert body["site"] == "canso"


def test_the_weather_fixture_is_a_stored_forecast_with_its_own_issue_time():
    body = json.loads((FIXTURES / "weather.json").read_text(encoding="utf-8"))

    assert body["horizon_label"] == "FORECAST"
    assert body["source"] == "snapshot_cache", "a stored forecast is labelled as a snapshot, never as a live fetch"
    assert body["forecast_issue_time"] and body["ensemble_size"] >= 10
    assert all(component["p_violation"] is not None for component in body["components"])
    assert "visibility" in [component["criterion_id"] for component in body["components"]]


def test_the_fixture_is_for_the_date_the_offline_record_is_asked_for():
    """The API reads this file as its offline record and its tests and the frozen window rows use 2026-10-06.

    Found on the merged tree: a fixture for another date makes the offline weather endpoint answer 503.
    """
    from backend.weather import config

    cfg = config.load_sources()["fixture"]
    body = json.loads((FIXTURES / "weather.json").read_text(encoding="utf-8"))

    assert cfg["date"] == "2026-10-06" and cfg["date_basis"].strip()
    assert body["date"] == cfg["date"]


def test_the_committed_snapshots_hold_no_missing_value():
    """Both stored ensembles are complete for every hour they cover, so offline answers never meet a null."""
    from backend.weather import fetch

    files = sorted((fetch.SNAPSHOT_DIR / "canso").glob("*.json"))
    assert [path.stem for path in files] == ["open_meteo_ecmwf_ens", "open_meteo_gefs_ens"]
    for path in files:
        parsed = fetch.parse_open_meteo(json.loads(path.read_text(encoding="utf-8"))["payload"])
        missing = sum(1 for member in parsed["members"] for column in member.values() for value in column
                      if value is None)
        assert missing == 0, f"{path.name} holds {missing} missing values"


def test_running_the_script_again_reproduces_the_committed_fixture_exactly():
    text = build_weather_fixture.build("canso")

    assert (FIXTURES / "weather.json").read_text(encoding="utf-8") == text, "weather.json was not produced by the script"


def test_only_the_fixture_the_issue_names_is_written_by_this_workflow():
    """Issue W8 names weather.json and skill.json. The skill fixture belongs to issue #7."""
    weather_files = sorted(path.name for path in FIXTURES.glob("weather*"))

    assert weather_files == ["weather.json"]
