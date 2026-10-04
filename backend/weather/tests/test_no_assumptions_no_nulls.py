"""Owner rules for the whole layer: no assumed value in any configuration, no null in any stored data or answer."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

import pytest

from backend.weather import config, fetch, service

from .conftest import Upstream, load_fixture

NOW = datetime(2026, 10, 3, 22, 30, tzinfo=timezone.utc)
CONFIG_FILES = ["sites.json", "sources.json", "skill_horizon.json", "criteria_v1.json"]


@pytest.mark.parametrize("name", CONFIG_FILES)
def test_no_configuration_value_is_flagged_as_an_assumption(name):
    document = json.loads((config.DATA_DIR / name).read_text(encoding="utf-8"))

    def flagged(node):
        if isinstance(node, dict):
            return any(str(value).upper() == "ASSUMPTION" for value in node.values()) or any(
                flagged(value) for value in node.values())
        if isinstance(node, list):
            return any(flagged(value) for value in node)
        return False

    assert not flagged(document), f"{name} still carries a value flagged ASSUMPTION"


def test_the_evaluation_window_is_the_one_the_canso_assessment_states():
    window = config.load_site("canso")["evaluation_window_local"]

    assert (window["start_hour"], window["end_hour"]) == (7, 12)
    assert "The majority of launches will be conducted between the hours of 7:00 a.m. and 12:00 p.m." in window["source_quote"]
    assert window["source_url"].startswith("https://www.novascotia.ca/")


def test_run_metadata_is_trusted_by_its_own_validity_period_not_by_a_tolerance_we_picked():
    """A metadata record whose own data_end_time has passed describes an old run and is not trusted."""
    request = config.load_sources()["request"]
    assert "max_issue_age_hours" not in request

    fresh = load_fixture("meta_ncep_gfs013.json")
    expired = dict(fresh, data_end_time=int((NOW - timedelta(hours=1)).timestamp()))
    Upstream(meta={"ncep_gfs013": expired}).install()

    forecast = fetch.fetch_forecast("canso", chain="deterministic", now=NOW)

    assert forecast["issue_time_basis"] == "fetch_time"
    assert forecast["forecast_issue_time"] == "2026-10-03T22:00:00Z"


def test_the_minimum_ensemble_size_is_the_documented_rule_that_one_member_is_not_a_probability():
    settings = config.load_sources()["ensemble"]

    assert settings["min_members"] == 2
    assert "not a probability" in settings["basis"]
    assert settings["require_complete_members"] is True


def test_a_forecast_with_a_missing_value_in_the_window_is_not_used():
    """One ECMWF member has a null gust inside the window. No member is dropped quietly: climatology answers."""
    payload = load_fixture("open_meteo_ensemble_canso.json")
    index = payload["hourly"]["time"].index("2026-10-04T12:00")
    payload["hourly"]["wind_gusts_10m_member07"][index] = None
    Upstream(payloads={"ecmwf_ifs025": payload}).install()

    result = service.compute("2026-10-04", "canso", now=NOW)

    assert result["horizon_label"] == "CLIMATOLOGY"
    assert result["p_launch"] is not None


def test_a_second_ensemble_with_a_missing_value_in_the_window_is_not_used_either():
    payload = load_fixture("open_meteo_gefs_ensemble_canso.json")
    index = payload["hourly"]["time"].index("2026-10-04T12:00")
    payload["hourly"]["visibility_member03"][index] = None
    Upstream(payloads={"gfs05": payload}).install()

    result = service.compute("2026-10-04", "canso", now=NOW)

    assert result["horizon_label"] == "CLIMATOLOGY"


def test_the_committed_test_fixtures_of_both_ensembles_hold_no_missing_value():
    for name in ("open_meteo_ensemble_canso.json", "open_meteo_gefs_ensemble_canso.json"):
        hourly = load_fixture(name)["hourly"]
        missing = sum(1 for key, column in hourly.items() if key != "time" for value in column if value is None)
        assert missing == 0, name
