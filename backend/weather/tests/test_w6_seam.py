"""W6 seam for issue #7: the criteria version and the outcome evaluator are exported and share the forecast's rules."""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest

def synthetic_archive() -> dict:
    """January 2021 hourly gusts: calm, except 20 m/s at 15:00 UTC on days 1 to 10; 2021-01-20T13:00 missing."""
    times, gusts = [], []
    moment = datetime(2021, 1, 1, 0)
    while moment.month == 1:
        times.append(moment.strftime("%Y-%m-%dT%H:00"))
        gusts.append(20.0 if moment.hour == 15 and moment.day <= 10 else 5.0)
        moment += timedelta(hours=1)
    gusts[times.index("2021-01-20T13:00")] = None
    return {"times": times, "columns": {"wind_gusts_10m": gusts}, "units": {"wind_gusts_10m": "m/s"},
            "index": {label: position for position, label in enumerate(times)}}


def test_issue_7_can_import_the_exported_surface():
    from backend.weather import climatology, criteria_version, hindcast, observed_launchable, probability

    assert callable(probability) and callable(climatology) and callable(observed_launchable)
    assert callable(hindcast), "the frozen Seam 1 entry point hindcast(period_start, period_end, lead_max=10)"
    assert criteria_version() == "criteria_v1"


def test_the_hindcast_signature_is_the_frozen_seam_1_signature():
    import inspect

    from backend.weather.hindcast import hindcast

    parameters = inspect.signature(hindcast).parameters
    assert list(parameters) == ["period_start", "period_end", "lead_max"]
    assert parameters["lead_max"].default == 10


def test_observed_launchable_returns_1_0_or_none_from_the_observed_fields(monkeypatch):
    from backend.weather import climatology, observations

    # The synthetic archive carries gusts only, so the gust rows of the real table are the evaluated rows:
    # surface_wind_gust (violated above 16.98 m/s) and ground_operations_wind (above 21.61 m/s).
    monkeypatch.setattr(climatology, "load_hourly_archive", lambda site: synthetic_archive())

    assert observations.observed_launchable("2021-01-05") == 0        # 20 m/s at 15:00 UTC, inside the window
    assert observations.observed_launchable("2021-01-15") == 1        # calm all window
    assert observations.observed_launchable("2021-01-20") is None     # one window hour missing
    assert observations.observed_launchable("2021-03-01") is None     # outside the archive


def test_the_outcome_and_the_forecast_are_judged_by_the_same_function_and_the_same_table(monkeypatch):
    """A mismatch between the two sides would invalidate the hindcast of issue #7."""
    from backend.weather import climatology, config, criteria, ensemble, observations

    seen = []
    real = criteria.window_violations

    def spy(rows, hours):
        seen.append([row["criterion_id"] for row in rows])
        return real(rows, hours)

    monkeypatch.setattr(criteria, "window_violations", spy)
    rows = climatology.evaluated_rows("canso", criteria.load_criteria("criteria_v1"))
    window = config.window_times(config.parse_date("2024-07-01"), config.load_site("canso"))
    members = [{row["parameter"]: [20000.0] * len(window) for row in rows} for _ in range(10)]
    forecast = {"times": window, "members": members, "units": {row["parameter"]: row["unit"] for row in rows}}

    ensemble.ensemble_probability(forecast, window, rows, min_members=10)
    forecast_side = seen[-1]
    observations.observed_launchable("2024-07-01", "criteria_v1")
    observed_side = seen[-1]

    assert forecast_side == observed_side == [row["criterion_id"] for row in rows]


def test_observed_launchable_on_the_committed_archive_agrees_with_the_climatology_counts():
    """Summing the daily outcome over every July day of the archive reproduces the July daily-window bin."""
    from backend.weather import climatology, observations

    table = climatology.load_climatology("canso")
    first_year, last_year = int(table["period_start"][:4]), int(table["period_end"][:4])
    outcomes = [observations.observed_launchable(f"{year}-07-{day:02d}")
                for year in range(first_year, last_year + 1) for day in range(1, 32)]
    july = climatology.daily_window(7, "canso")

    assert None not in outcomes
    assert len(outcomes) == july["n"] == 31 * (last_year - first_year + 1)
    assert sum(outcomes) == july["n_launchable"]


def test_an_unknown_criteria_version_is_refused_on_the_observed_side_too():
    from backend.weather import observations
    from backend.weather.errors import CriteriaVersionMissingError

    with pytest.raises(CriteriaVersionMissingError):
        observations.observed_launchable("2024-07-01", "criteria_v99")
