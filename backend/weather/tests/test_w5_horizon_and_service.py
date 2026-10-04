"""W5 skill horizon as configuration, and probability() end to end in both modes with its fallbacks."""

from __future__ import annotations

import copy
from datetime import datetime, timedelta, timezone

import pytest

from backend.weather import climatology, config, criteria, ensemble, fetch, service
from backend.weather.errors import CriteriaVersionMissingError, UnknownSiteError

from .conftest import Upstream, load_fixture

NOW = datetime(2026, 10, 3, 22, 30, tzinfo=timezone.utc)
# The run time of the committed ECMWF ensemble fixture, read from its own metadata. The fixture covers 3 to 5 October.
ENS_RUN_EPOCH = load_fixture("meta_ecmwf_ifs025_ensemble.json")["last_run_initialisation_time"]
ENS_RUN_TIME = datetime.fromtimestamp(ENS_RUN_EPOCH, timezone.utc)
ENS_RUN = ENS_RUN_TIME.strftime("%Y-%m-%dT%H:%M:%SZ")
SPEC_IV3_KEYS = {"date", "site", "p_launch", "horizon_label", "forecast_issue_time", "ensemble_size",
                 "criteria_version", "components", "source"}


# W5: the boundary is configuration ---------------------------------------------------------------------------

def test_the_skill_horizon_file_states_the_boundary_its_flag_and_its_sources():
    horizon = config.load_skill_horizon()

    assert horizon["prior"]["max_forecast_lead_days"] == 10, "spec II.7, kept as the record of what was replaced"
    assert horizon["max_forecast_lead_days"] == horizon["measured"]["last_lead_with_skill"]["lead_time_days"]
    assert horizon["flag"] == "SKETCHED"
    assert horizon["source"].strip()
    dois = {citation["doi"] for citation in horizon["citations"]}
    assert dois == {"10.1111/j.2153-3490.1982.tb01839.x", "10.3402/tellusa.v65i0.19022", "10.1002/qj.2619"}


@pytest.mark.parametrize("lead, expected", [(-1, "CLIMATOLOGY"), (0, "FORECAST"), (10, "FORECAST"),
                                            (11, "CLIMATOLOGY")])
def test_the_label_is_forecast_within_the_horizon_and_climatology_outside(lead, expected):
    assert ensemble.horizon_label(lead, 10) == expected


def test_lead_is_counted_in_calendar_days_from_the_issue_time():
    assert ensemble.lead_days(config.parse_date("2026-10-13"), "2026-10-03T06:00:00Z") == 10
    assert ensemble.lead_days(config.parse_date("2026-10-03"), "2026-10-03T06:00:00Z") == 0


def test_the_boundary_comes_from_the_config_file_not_from_a_literal_in_code(monkeypatch):
    Upstream().install()
    inside = service.compute("2026-10-05", "canso", now=NOW)
    assert inside["horizon_label"] == "FORECAST"                      # lead 2, horizon 10

    monkeypatch.setattr(config, "load_skill_horizon", lambda: {"max_forecast_lead_days": 1})
    service.clear_memo()
    outside = service.compute("2026-10-05", "canso", now=NOW)
    assert outside["horizon_label"] == "CLIMATOLOGY"                   # lead 2, horizon 1


# FORECAST mode ---------------------------------------------------------------------------------------------

def test_a_date_inside_the_horizon_is_answered_from_the_ensemble():
    Upstream().install()

    result = service.compute("2026-10-04", "canso", now=NOW)

    assert set(result) == SPEC_IV3_KEYS
    assert result["horizon_label"] == "FORECAST"
    assert result["source"] == "open_meteo"
    assert result["forecast_issue_time"] == ENS_RUN
    assert result["ensemble_size"] == 51 + 31, "51 ECMWF members and 31 GEFS members"
    assert result["criteria_version"] == "criteria_v1"
    assert 0.0 <= result["p_launch"] <= 1.0


def test_the_forecast_uses_both_ensembles_and_combines_them_by_the_stated_rule():
    """ECMWF evaluates every row but visibility; GEFS evaluates visibility. p = max(0, P_ecmwf - Q_gefs)."""
    upstream = Upstream().install()
    split = climatology.split_rows("canso", criteria.load_criteria("criteria_v1"))
    window = config.window_times(config.parse_date("2026-10-04"), config.load_site("canso"))
    minimum = config.load_sources()["ensemble"]["min_members"]
    primary = ensemble.ensemble_probability(
        fetch.parse_open_meteo(load_fixture("open_meteo_ensemble_canso.json")), window, split["primary"], minimum)
    second = ensemble.supplement_evaluation(
        fetch.parse_open_meteo(load_fixture("open_meteo_gefs_ensemble_canso.json")), window, split["supplement"],
        ["visibility"], minimum)

    result = service.compute("2026-10-04", "canso", now=NOW)

    assert upstream.data_calls == ["ecmwf_ifs025", "gfs05"]
    assert [row["criterion_id"] for row in split["supplement_only"]] == ["visibility"]
    assert result["p_launch"] == pytest.approx(max(0.0, primary["p_launch"] - second["only_supplement_violation"]))
    assert result["p_launch"] <= primary["p_launch"]
    visibility = next(c for c in result["components"] if c["criterion_id"] == "visibility")
    assert visibility == second["components"][0]


def test_no_response_carries_a_missing_number_or_a_row_without_data():
    Upstream().install()
    rows = climatology.evaluated_rows("canso", criteria.load_criteria("criteria_v1"))

    for date_iso in ("2026-10-03", "2026-10-04", "2026-10-05", "2026-10-09", "2026-11-20", "2027-02-01"):
        result = service.compute(date_iso, "canso", now=NOW)
        assert result["p_launch"] is not None and 0.0 <= result["p_launch"] <= 1.0
        assert [c["criterion_id"] for c in result["components"]] == [row["criterion_id"] for row in rows]
        assert all(c["p_violation"] is not None for c in result["components"])


def test_without_the_second_ensemble_the_date_is_answered_from_climatology_not_with_a_gap(monkeypatch, tmp_path):
    """GEFS down and no stored copy: visibility cannot be forecast, so no forecast probability is issued."""
    monkeypatch.setattr(fetch, "SNAPSHOT_DIR", tmp_path / "no_snapshot")
    Upstream(down={"gfs05"}, meta={"ncep_gefs05": None}).install()

    result = service.compute("2026-10-04", "canso", now=NOW)

    assert result["horizon_label"] == "CLIMATOLOGY"
    assert result["source"] == "era5_climatology"
    assert "visibility" in [c["criterion_id"] for c in result["components"]]


def test_forecast_components_have_one_row_per_evaluated_criterion_with_its_flag():
    Upstream().install()
    rows = climatology.evaluated_rows("canso", criteria.load_criteria("criteria_v1"))
    assert len(rows) >= 10

    result = service.compute("2026-10-04", "canso", now=NOW)

    assert [c["criterion_id"] for c in result["components"]] == [row["criterion_id"] for row in rows]
    assert [c["flag"] for c in result["components"]] == [row["flag"] for row in rows]
    for component in result["components"]:
        assert set(component) == {"criterion_id", "p_violation", "flag"}
        assert 0.0 <= component["p_violation"] <= 1.0


def test_p_launch_is_never_above_what_the_most_violated_criterion_allows():
    Upstream().install()

    result = service.compute("2026-10-04", "canso", now=NOW)

    worst = max(component["p_violation"] for component in result["components"])
    assert result["p_launch"] <= 1.0 - worst + 1e-9


# CLIMATOLOGY mode ------------------------------------------------------------------------------------------

def test_a_date_beyond_the_horizon_is_answered_from_climatology():
    Upstream().install()

    result = service.compute("2026-10-20", "canso", now=NOW)

    assert set(result) == SPEC_IV3_KEYS
    assert result["horizon_label"] == "CLIMATOLOGY"
    assert result["ensemble_size"] is None
    assert result["forecast_issue_time"] is None
    assert result["source"] == "era5_climatology"
    october = climatology.daily_window(10, "canso")
    assert result["p_launch"] == pytest.approx(october["p_launch"])
    assert {c["criterion_id"]: c["p_violation"] for c in result["components"]} == pytest.approx(
        october["p_violation"])


def test_a_far_future_date_makes_no_request_at_all():
    upstream = Upstream().install()

    result = service.compute("2027-03-01", "canso", now=NOW)

    assert result["horizon_label"] == "CLIMATOLOGY"
    assert upstream.calls == 0


def test_a_date_inside_the_horizon_that_the_forecast_does_not_cover_falls_to_climatology():
    """The fixture ends on 5 October. 8 October is lead 5 but has no members, so no probability is invented."""
    Upstream().install()

    result = service.compute("2026-10-08", "canso", now=NOW)

    assert result["horizon_label"] == "CLIMATOLOGY"
    assert result["source"] == "era5_climatology"
    assert result["forecast_issue_time"] is None


def test_a_past_date_is_answered_from_climatology():
    Upstream().install()

    result = service.compute("2026-09-01", "canso", now=NOW)

    assert result["horizon_label"] == "CLIMATOLOGY"
    assert result["p_launch"] == pytest.approx(climatology.daily_window(9, "canso")["p_launch"])


# Fallbacks -------------------------------------------------------------------------------------------------

def test_when_only_a_deterministic_forecast_exists_no_probability_is_fabricated(monkeypatch, tmp_path):
    """Chain reduced to the single-run GFS source: the answer is climatology under its own label."""
    sources = copy.deepcopy(config.load_sources())
    sources["chains"]["ensemble"] = ["open_meteo_gfs"]
    monkeypatch.setattr(config, "load_sources", lambda: sources)
    upstream = Upstream().install()

    result = service.compute("2026-10-04", "canso", now=NOW)

    assert upstream.data_calls == ["gfs_seamless"], "the deterministic source did answer, and nothing else was asked"
    assert result["horizon_label"] == "CLIMATOLOGY"
    assert result["source"] == "era5_climatology"
    assert result["ensemble_size"] is None
    assert result["p_launch"] == pytest.approx(climatology.daily_window(10, "canso")["p_launch"])
    assert result["p_launch"] not in (0.0, 1.0)


def test_primary_down_falls_back_to_the_snapshot_and_the_response_says_so():
    Upstream().install()
    live = service.compute("2026-10-04", "canso", now=NOW)
    fetch.clear_memo()
    service.clear_memo()
    Upstream(down={"ecmwf_ifs025", "gfs05"}, meta={"ecmwf_ifs025_ensemble": None, "ncep_gefs05": None}).install()

    later = datetime(2026, 10, 4, 8, 0, tzinfo=timezone.utc)
    result = service.compute("2026-10-04", "canso", now=later)

    assert result["source"] == "snapshot_cache"
    assert result["horizon_label"] == "FORECAST"
    assert result["forecast_issue_time"] == ENS_RUN
    assert result["p_launch"] == live["p_launch"]


def test_everything_down_and_no_snapshot_is_answered_from_climatology(monkeypatch, tmp_path):
    monkeypatch.setattr(fetch, "SNAPSHOT_DIR", tmp_path / "no_snapshot")
    Upstream(down={"ecmwf_ifs025"}).install()

    result = service.compute("2026-10-04", "canso", now=NOW)

    assert result["horizon_label"] == "CLIMATOLOGY"
    assert result["source"] == "era5_climatology"


# Cache, determinism, errors --------------------------------------------------------------------------------

def test_results_are_cached_on_site_issue_time_and_criteria_version(monkeypatch):
    calls = []
    real = ensemble.ensemble_probability

    def counting(forecast, window, rows, min_members):
        calls.append(forecast["forecast_issue_time"])
        return real(forecast, window, rows, min_members)

    monkeypatch.setattr(ensemble, "ensemble_probability", counting)
    upstream = Upstream().install()

    first = service.compute("2026-10-04", "canso", now=NOW)
    second = service.compute("2026-10-04", "canso", now=NOW)
    assert first == second
    assert calls == [ENS_RUN], "same site, issue time and criteria version must not be recomputed"

    next_run = ENS_RUN_TIME + timedelta(hours=6)
    newer = dict(upstream.meta["ecmwf_ifs025_ensemble"], last_run_initialisation_time=ENS_RUN_EPOCH + 6 * 3600)
    upstream.meta["ecmwf_ifs025_ensemble"] = newer
    fetch.clear_memo()
    service.compute("2026-10-04", "canso", now=next_run + timedelta(hours=3))
    assert calls == [ENS_RUN, next_run.strftime("%Y-%m-%dT%H:%M:%SZ")], "a new issue time invalidates the result"


def test_the_same_request_twice_gives_identical_numbers():
    Upstream().install()
    first = service.compute("2026-10-04", "canso", now=NOW)
    fetch.clear_memo()
    service.clear_memo()

    assert service.compute("2026-10-04", "canso", now=NOW) == first


def test_an_unknown_criteria_version_raises_the_mapped_error():
    with pytest.raises(CriteriaVersionMissingError) as raised:
        service.compute("2026-10-04", "canso", "criteria_v99", now=NOW)
    assert raised.value.constraint_fired == "criteria_version_missing"


def test_an_unknown_site_and_a_malformed_date_are_errors():
    with pytest.raises(UnknownSiteError):
        service.compute("2026-10-04", "atlantis", now=NOW)
    for bad in ("2026-13-01", "04/10/2026", "2026-10-4", ""):
        with pytest.raises(ValueError):
            service.compute(bad, "canso", now=NOW)


def test_the_public_entry_point_answers_offline_from_committed_data():
    """No network and no mock: the committed snapshot and climatology are enough for a valid answer."""
    from backend.weather import probability

    near = probability("2026-10-07", "canso")
    far = probability("2027-02-14", "canso")

    assert set(near) == SPEC_IV3_KEYS and set(far) == SPEC_IV3_KEYS
    assert far["horizon_label"] == "CLIMATOLOGY"
    assert far["p_launch"] == pytest.approx(climatology.daily_window(2, "canso")["p_launch"])
    assert near["source"] in {"snapshot_cache", "era5_climatology"}
