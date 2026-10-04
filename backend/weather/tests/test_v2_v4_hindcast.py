"""Issue #7, V2 to V4: the forecast archive loader, the outcomes, the hindcast loop and its disk cache."""

from __future__ import annotations

import json
from datetime import date, timedelta
from pathlib import Path

import pytest

from backend.weather import config, hindcast

FIXTURES = Path(__file__).resolve().parent / "fixtures"
SOURCE_UNITS = {"wind_speed_10m": "km/h", "wind_gusts_10m": "km/h", "wind_direction_10m": "°", "visibility": "m",
                "snowfall": "cm", "precipitation": "mm", "cloud_cover_low": "%", "temperature_2m": "°C",
                "cape": "J/kg", "cloud_cover_mid": "%"}
RUN_HOURS = [0, 6, 12, 18]
GUST = {"criterion_id": "gust", "parameter": "wind_gusts_10m", "comparison": "gt", "limit": 17.0,
        "unit": "m/s", "flag": "VERIFIED"}
SITE = {"timezone": "America/Halifax", "evaluation_window_local": {"start_hour": 7, "end_hour": 12}}


# V2: the loader ----------------------------------------------------------------------------------------------

@pytest.fixture(scope="module")
def sample() -> dict:
    text = (FIXTURES / "hindcast_runs_sample.csv").read_text(encoding="utf-8")
    return hindcast.parse_runs(text, SOURCE_UNITS)


def test_the_loader_parses_the_archive_into_issue_time_valid_time_and_fields(sample):
    """First row of the committed sample: run 2026-04-02T00:00, valid 2026-04-03T10:00, wind 16.6 km/h, -1.7 degC."""
    records = sample["records"]

    assert len(records) == 480
    first = records[0]
    assert (first["issue_time"], first["valid_time"]) == ("2026-04-02T00:00", "2026-04-03T10:00")
    assert first["fields"]["wind_speed_10m"] == pytest.approx(16.6 / 3.6)
    assert first["fields"]["temperature_2m"] == -1.7
    assert first["fields"]["visibility"] == 24140.0
    assert sample["units"]["wind_speed_10m"] == "m/s" and sample["units"]["precipitation"] == "mm/h"
    assert set(first["fields"]) == set(SOURCE_UNITS)


def test_an_empty_cell_is_a_missing_value_not_a_zero():
    text = "run_time_utc,valid_time_utc,wind_gusts_10m\n2026-04-02T00:00,2026-04-03T10:00,\n"

    parsed = hindcast.parse_runs(text, {"wind_gusts_10m": "km/h"})

    assert parsed["records"][0]["fields"]["wind_gusts_10m"] is None


def test_issue_dates_with_every_run_are_complete_and_gaps_are_reported_as_a_count(sample):
    by_run = hindcast.index_runs(sample["records"])

    whole = hindcast.coverage(by_run, RUN_HOURS, date(2026, 4, 2), date(2026, 4, 3))
    with_gap = hindcast.coverage(by_run, RUN_HOURS, date(2026, 4, 2), date(2026, 4, 5))

    assert whole == {"issue_dates_expected": 2, "issue_dates_complete": 2, "runs_expected": 8, "runs_missing": 0,
                     "issue_dates_incomplete": []}
    assert with_gap["issue_dates_expected"] == 4 and with_gap["issue_dates_complete"] == 2
    assert with_gap["runs_missing"] == 8
    assert with_gap["issue_dates_incomplete"] == ["2026-04-04", "2026-04-05"]


def test_the_sample_supports_every_lead_from_one_to_ten(sample):
    by_run = hindcast.index_runs(sample["records"])
    run = by_run["2026-04-02T00:00"]

    valid_dates = sorted({label[:10] for label in run})

    assert valid_dates == [(date(2026, 4, 2) + timedelta(days=lead)).isoformat() for lead in range(1, 11)]
    assert all(len([label for label in run if label[:10] == day]) == 6 for day in valid_dates)


# V4: the loop ------------------------------------------------------------------------------------------------

def synthetic_runs(issue: date, gusty_runs: int, leads=(1, 2), runs=4, hole=False) -> dict:
    """Runs of one issue date. The first `gusty_runs` runs have a 20 m/s gust at one window hour of every lead."""
    by_run = {}
    for number in range(runs):
        hours = {}
        for lead in leads:
            labels = config.window_times(issue + timedelta(days=lead), SITE)
            for position, label in enumerate(labels):
                gust = 20.0 if number < gusty_runs and position == 2 else 5.0
                hours[label] = {"wind_gusts_10m": None if hole and number == 0 and position == 0 else gust}
        by_run[f"{issue.isoformat()}T{RUN_HOURS[number]:02d}:00"] = hours
    return by_run


def run_pairs(by_run, issue_dates, outcome, lead_max=2):
    return hindcast.build_pairs(by_run, {"wind_gusts_10m": "m/s"}, SITE, [GUST], issue_dates, lead_max,
                                RUN_HOURS, min_members=2, outcome=outcome)


def test_the_loop_gives_one_row_per_issue_date_and_lead_with_p_from_the_runs_and_o_from_the_observation():
    """One of four runs is gusty, so three satisfy the criterion: p = 0.75. The observed day was launchable: o = 1."""
    issue = date(2026, 5, 1)

    result = run_pairs(synthetic_runs(issue, gusty_runs=1), [issue], outcome=lambda day: 1)

    assert result["pairs"] == [
        {"issue_date": "2026-05-01", "lead_time_days": 1, "valid_date": "2026-05-02", "p": 0.75, "o": 1},
        {"issue_date": "2026-05-01", "lead_time_days": 2, "valid_date": "2026-05-03", "p": 0.75, "o": 1},
    ]
    assert result["excluded"] == {"issue_date_without_every_run": 0, "forecast_with_missing_value": 0,
                                  "outcome_missing": 0}


def test_an_issue_date_without_every_run_is_excluded_and_counted():
    issue = date(2026, 5, 1)

    result = run_pairs(synthetic_runs(issue, gusty_runs=0, runs=3), [issue], outcome=lambda day: 1)

    assert result["pairs"] == []
    assert result["excluded"]["issue_date_without_every_run"] == 1


def test_a_forecast_with_a_missing_value_is_excluded_and_counted_not_evaluated_on_fewer_runs():
    issue = date(2026, 5, 1)

    result = run_pairs(synthetic_runs(issue, gusty_runs=0, hole=True), [issue], outcome=lambda day: 1)

    assert result["pairs"] == []
    assert result["excluded"]["forecast_with_missing_value"] == 2          # one per lead


def test_a_day_with_missing_observations_is_excluded_and_counted():
    issue = date(2026, 5, 1)
    outcomes = {"2026-05-02": None, "2026-05-03": 0}

    result = run_pairs(synthetic_runs(issue, gusty_runs=4), [issue], outcome=lambda day: outcomes[day])

    assert [(row["lead_time_days"], row["p"], row["o"]) for row in result["pairs"]] == [(2, 0.0, 0)]
    assert result["excluded"]["outcome_missing"] == 1


def test_the_forecast_side_uses_the_same_evaluator_as_the_operational_layer(monkeypatch):
    from backend.weather import ensemble

    calls = []
    real = ensemble.ensemble_probability

    def spy(forecast, window, rows, min_members):
        calls.append((len(forecast["members"]), [row["criterion_id"] for row in rows]))
        return real(forecast, window, rows, min_members)

    monkeypatch.setattr(ensemble, "ensemble_probability", spy)
    issue = date(2026, 5, 1)

    run_pairs(synthetic_runs(issue, gusty_runs=1), [issue], outcome=lambda day: 1, lead_max=1)

    assert calls == [(4, ["gust"])]


# V4: scoring the pairs ---------------------------------------------------------------------------------------

PAIRS = [
    {"issue_date": "2026-05-01", "lead_time_days": 1, "valid_date": "2026-05-02", "p": 1.0, "o": 1},
    {"issue_date": "2026-05-02", "lead_time_days": 1, "valid_date": "2026-05-03", "p": 0.25, "o": 0},
    {"issue_date": "2026-05-03", "lead_time_days": 1, "valid_date": "2026-05-04", "p": 0.5, "o": 1},
    {"issue_date": "2026-05-04", "lead_time_days": 1, "valid_date": "2026-05-05", "p": 0.0, "o": 0},
    {"issue_date": "2026-04-30", "lead_time_days": 2, "valid_date": "2026-05-02", "p": 0.5, "o": 1},
    {"issue_date": "2026-05-01", "lead_time_days": 2, "valid_date": "2026-05-03", "p": 0.5, "o": 0},
]


def test_the_skill_series_has_one_entry_per_lead_with_hand_checked_values():
    """Lead 1: BS = (0 + 0.0625 + 0.25 + 0) / 4 = 0.078125; base rate 0.5, BS_ref = 0.25; BSS = 0.6875.

    Lead 2: BS = (0.25 + 0.25) / 2 = 0.25; base rate 0.5, BS_ref = 0.25; BSS = 0.
    """
    body = hindcast.score(PAIRS, lead_max=2, members=4, n_bins=10)

    assert body["skill_series"] == [
        {"lead_time_days": 1, "bs": pytest.approx(0.078125), "bs_ref": pytest.approx(0.25),
         "bss": pytest.approx(0.6875), "n_cases": 4},
        {"lead_time_days": 2, "bs": pytest.approx(0.25), "bs_ref": pytest.approx(0.25),
         "bss": pytest.approx(0.0), "n_cases": 2},
    ]


def test_n_cases_is_the_true_count_and_a_lead_without_pairs_is_still_listed_with_zero_cases():
    body = hindcast.score(PAIRS, lead_max=3, members=4, n_bins=10)

    assert [entry["lead_time_days"] for entry in body["skill_series"]] == [1, 2, 3]
    assert [entry["n_cases"] for entry in body["skill_series"]] == [4, 2, 0]
    assert body["skill_series"][2]["bss"] is None


def test_the_base_rate_is_the_launchable_fraction_of_the_verified_days_each_counted_once():
    """Verified days: 2 May (1), 3 May (0), 4 May (1), 5 May (0). Two of four launchable: 0.5.

    2 May and 3 May are verified at two leads; each still counts once.
    """
    body = hindcast.score(PAIRS, lead_max=2, members=4, n_bins=10)

    assert body["base_rate"] == 0.5
    assert body["verified_days"] == 4


def test_reliability_and_roc_use_every_pair_and_the_member_fractions_as_thresholds():
    body = hindcast.score(PAIRS, lead_max=2, members=4, n_bins=10)

    assert sum(entry["n"] for entry in body["reliability_bins"]) == len(PAIRS)
    assert [point["threshold"] for point in body["roc_points"]] == [0.25, 0.5, 0.75, 1.0]


def test_the_measured_horizon_is_the_last_lead_of_the_unbroken_run_of_positive_skill():
    series = lambda values: [{"lead_time_days": lead, "bss": value} for lead, value in enumerate(values, start=1)]

    assert hindcast.measured_horizon(series([0.4, 0.2, 0.1, -0.1, 0.3])) == 3
    assert hindcast.measured_horizon(series([-0.2, 0.3])) is None
    assert hindcast.measured_horizon(series([0.0, 0.3])) is None, "zero skill is not positive skill"
    assert hindcast.measured_horizon(series([0.3, None])) == 1


# V4: the disk cache ------------------------------------------------------------------------------------------

@pytest.fixture
def cached(monkeypatch, tmp_path):
    """compute() on a small synthetic archive, with a counter on the expensive step."""
    issue = date(2026, 5, 1)
    by_run = synthetic_runs(issue, gusty_runs=1)
    counter = {"n": 0}
    real = hindcast.build_pairs

    def counting(*args, **kwargs):
        counter["n"] += 1
        return real(*args, **kwargs)

    monkeypatch.setattr(hindcast, "CACHE_DIR", tmp_path / "hindcast")
    monkeypatch.setattr(hindcast, "build_pairs", counting)
    monkeypatch.setattr(hindcast, "load_inputs", lambda site, version: {
        "by_run": by_run, "units": {"wind_gusts_10m": "m/s"}, "site_cfg": SITE, "rows": [GUST],
        "run_hours": RUN_HOURS, "min_members": 2, "outcome": lambda day: 1, "n_bins": 10,
        "forecast_source": "synthetic_runs", "verification_source": "era5",
        "fingerprint": f"synthetic-{version}", "constants_block": {"citation_id": "run_test"}})
    return counter


def test_an_unchanged_key_is_answered_from_disk_without_recomputing(cached):
    first = hindcast.compute("2026-05-01", "2026-05-01", 2, criteria_version="criteria_v1")
    second = hindcast.compute("2026-05-01", "2026-05-01", 2, criteria_version="criteria_v1")

    assert first == second
    assert cached["n"] == 1


def test_a_changed_criteria_version_period_or_lead_forces_a_recompute(cached):
    hindcast.compute("2026-05-01", "2026-05-01", 2, criteria_version="criteria_v1")
    hindcast.compute("2026-05-01", "2026-05-01", 2, criteria_version="criteria_v2")
    assert cached["n"] == 2, "the cache key includes the criteria version"
    hindcast.compute("2026-05-01", "2026-05-01", 1, criteria_version="criteria_v1")
    hindcast.compute("2026-05-01", "2026-05-02", 2, criteria_version="criteria_v1")
    assert cached["n"] == 4


def test_the_cache_file_is_keyed_and_holds_the_response(cached, tmp_path):
    body = hindcast.compute("2026-05-01", "2026-05-01", 2, criteria_version="criteria_v1")

    files = list((tmp_path / "hindcast").glob("*.json"))
    assert len(files) == 1
    stored = json.loads(files[0].read_text(encoding="utf-8"))
    assert stored["key"] == {"period_start": "2026-05-01", "period_end": "2026-05-01", "lead_max": 2,
                             "site": "canso", "criteria_version": "criteria_v1",
                             "forecast_source": "synthetic_runs", "verification_source": "era5",
                             "fingerprint": "synthetic-criteria_v1"}
    assert stored["result"] == body
