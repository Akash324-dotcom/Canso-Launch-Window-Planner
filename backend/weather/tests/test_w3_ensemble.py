"""W3 ensemble P(L|d): the member fraction of spec II.21, components, ensemble size and the one-member rule."""

from __future__ import annotations

import pytest

from backend.weather import ensemble
from backend.weather.errors import WeatherDataError

GUST = {"criterion_id": "gust", "parameter": "wind_gusts_10m", "comparison": "gt", "limit": 17.0,
        "unit": "m/s", "flag": "VERIFIED"}
RAIN = {"criterion_id": "rain", "parameter": "precipitation", "comparison": "gt", "limit": 0.0,
        "unit": "mm/h", "flag": "PROXY"}
ROWS = [GUST, RAIN]
WINDOW = ["2026-10-07T10:00", "2026-10-07T11:00", "2026-10-07T12:00"]
TIMES = ["2026-10-07T09:00", *WINDOW, "2026-10-07T13:00"]

CALM = ([5.0] * 5, [0.0] * 5)
GUSTY = ([5.0, 5.0, 18.0, 5.0, 5.0], [0.0] * 5)          # violates the gust row at one window hour
WET = ([5.0] * 5, [0.0, 0.0, 0.0, 0.4, 0.0])             # violates the rain row at one window hour
BOTH = ([5.0, 20.0, 5.0, 5.0, 5.0], [0.0, 0.2, 0.0, 0.0, 0.0])
GUSTY_OUTSIDE = ([30.0, 5.0, 5.0, 5.0, 30.0], [0.0] * 5)  # violations only outside the window


def forecast(members, units=None, times=TIMES):
    return {
        "times": times,
        "members": [{"wind_gusts_10m": list(gust), "precipitation": list(rain)} for gust, rain in members],
        "units": units or {"wind_gusts_10m": "m/s", "precipitation": "mm/h"},
    }


def test_p_launch_is_the_fraction_of_members_that_satisfy_every_criterion():
    """Worked example: N = 10, of which 2 gusty, 1 wet, 1 both, so 6 pass. p_launch = 6/10 = 0.6."""
    members = [CALM] * 6 + [GUSTY, GUSTY, WET, BOTH]

    result = ensemble.ensemble_probability(forecast(members), WINDOW, ROWS, min_members=10)

    assert result["p_launch"] == pytest.approx(0.6)
    assert result["ensemble_size"] == 10
    assert result["reason"] is None


def test_components_carry_one_row_per_criterion_with_its_violation_fraction_and_flag():
    members = [CALM] * 6 + [GUSTY, GUSTY, WET, BOTH]

    result = ensemble.ensemble_probability(forecast(members), WINDOW, ROWS, min_members=10)

    assert result["components"] == [
        {"criterion_id": "gust", "p_violation": pytest.approx(0.3), "flag": "VERIFIED"},   # GUSTY, GUSTY, BOTH
        {"criterion_id": "rain", "p_violation": pytest.approx(0.2), "flag": "PROXY"},      # WET, BOTH
    ]


def test_only_the_window_hours_count():
    members = [GUSTY_OUTSIDE] * 10

    result = ensemble.ensemble_probability(forecast(members), WINDOW, ROWS, min_members=10)

    assert result["p_launch"] == 1.0


def test_a_deterministic_forecast_does_not_yield_a_probability():
    """The chosen behaviour for a single run: no probability, with the reason. Nothing is fabricated."""
    for single in (CALM, BOTH):
        result = ensemble.ensemble_probability(forecast([single]), WINDOW, ROWS, min_members=10)

        assert result["p_launch"] is None
        assert result["ensemble_size"] is None
        assert result["components"] == []
        assert result["reason"] == "deterministic_only"


def test_too_few_members_is_not_a_probability_either():
    result = ensemble.ensemble_probability(forecast([CALM] * 9), WINDOW, ROWS, min_members=10)

    assert result["p_launch"] is None
    assert result["reason"] == "too_few_members"


def test_members_with_a_missing_value_in_the_window_are_dropped_and_counted_not_assumed_good():
    hole = ([5.0, 5.0, None, 5.0, 5.0], [0.0] * 5)
    members = [CALM] * 8 + [GUSTY, WET, hole, hole]

    result = ensemble.ensemble_probability(forecast(members), WINDOW, ROWS, min_members=10)

    assert result["ensemble_size"] == 10
    assert result["members_dropped"] == 2
    assert result["p_launch"] == pytest.approx(0.8)


def test_a_forecast_that_does_not_cover_the_window_gives_no_probability():
    result = ensemble.ensemble_probability(forecast([CALM] * 10), ["2026-10-20T10:00"], ROWS, min_members=10)

    assert result["p_launch"] is None
    assert result["reason"] == "window_not_covered"


def test_a_unit_mismatch_between_forecast_and_criteria_is_an_error():
    wrong = forecast([CALM] * 10, units={"wind_gusts_10m": "km/h", "precipitation": "mm/h"})

    with pytest.raises(WeatherDataError, match="unit"):
        ensemble.ensemble_probability(wrong, WINDOW, ROWS, min_members=10)


def test_the_committed_ecmwf_fixture_gives_a_probability_from_51_members():
    from backend.weather import climatology, config, criteria, fetch

    from .conftest import load_fixture

    parsed = fetch.parse_open_meteo(load_fixture("open_meteo_ensemble_canso.json"))
    rows = climatology.split_rows("canso", criteria.load_criteria("criteria_v1"))["primary"]
    window = config.window_times(config.parse_date("2026-10-04"), config.load_site("canso"))
    minimum = config.load_sources()["ensemble"]["min_members"]

    result = ensemble.ensemble_probability(parsed, window, rows, min_members=minimum)

    assert result["ensemble_size"] == 51
    assert 0.0 <= result["p_launch"] <= 1.0
    assert [c["criterion_id"] for c in result["components"]] == [row["criterion_id"] for row in rows]
    assert all(row["parameter"] != "visibility" for row in rows), "the ECMWF ensemble carries no visibility"
    passing = round(result["p_launch"] * 51)
    assert result["p_launch"] == pytest.approx(passing / 51)


def test_the_evaluation_window_follows_local_time_through_daylight_saving():
    from backend.weather import config

    site = config.load_site("canso")

    summer = config.window_times(config.parse_date("2026-10-07"), site)     # ADT, UTC-3
    winter = config.window_times(config.parse_date("2026-12-07"), site)     # AST, UTC-4

    assert summer == [f"2026-10-07T{hour:02d}:00" for hour in range(10, 16)]
    assert winter == [f"2026-12-07T{hour:02d}:00" for hour in range(11, 17)]


# A second ensemble for the rows the first cannot evaluate ----------------------------------------------------

VIS = {"criterion_id": "vis", "parameter": "visibility", "comparison": "lt", "limit": 7408.0, "unit": "m",
       "flag": "VERIFIED"}
SUPPLEMENT_ROWS = [GUST, RAIN, VIS]


def supplement_forecast(members):
    """members: (gust, rain, visibility) constant over the five hours."""
    return {
        "times": TIMES,
        "members": [{"wind_gusts_10m": [gust] * 5, "precipitation": [rain] * 5, "visibility": [vis] * 5}
                    for gust, rain, vis in members],
        "units": {"wind_gusts_10m": "m/s", "precipitation": "mm/h", "visibility": "m"},
    }


CLEAR = (5.0, 0.0, 20000.0)
FOG_ONLY = (5.0, 0.0, 800.0)
FOG_AND_RAIN = (5.0, 0.6, 800.0)
RAIN_ONLY = (5.0, 0.6, 20000.0)


def test_the_supplement_counts_members_that_fail_on_its_own_rows_alone():
    """Worked example, N = 10: 6 clear, 2 fog only, 1 fog with rain, 1 rain only.

    Visibility is violated in 3 members (0.3). It is the only violation in 2 members, so the deduction is 0.2.
    """
    members = [CLEAR] * 6 + [FOG_ONLY] * 2 + [FOG_AND_RAIN, RAIN_ONLY]

    result = ensemble.supplement_evaluation(supplement_forecast(members), WINDOW, SUPPLEMENT_ROWS, ["vis"],
                                            min_members=10)

    assert result["only_supplement_violation"] == pytest.approx(0.2)
    assert result["components"] == [{"criterion_id": "vis", "p_violation": pytest.approx(0.3), "flag": "VERIFIED"}]
    assert result["ensemble_size"] == 10 and result["reason"] is None


def test_the_combined_probability_is_a_lower_bound_that_never_overstates():
    """P(all rows hold) >= P(primary rows hold) - P(common rows hold and a supplement row fails)."""
    assert ensemble.combine(0.6, 0.2) == pytest.approx(0.4)
    assert ensemble.combine(0.6, 0.0) == pytest.approx(0.6)
    assert ensemble.combine(0.1, 0.3) == 0.0
    assert ensemble.combine(1.0, 1.0) == 0.0


def test_a_supplement_with_too_few_members_or_no_coverage_gives_no_result():
    few = ensemble.supplement_evaluation(supplement_forecast([CLEAR] * 9), WINDOW, SUPPLEMENT_ROWS, ["vis"], 10)
    uncovered = ensemble.supplement_evaluation(supplement_forecast([CLEAR] * 10), ["2026-10-20T10:00"],
                                               SUPPLEMENT_ROWS, ["vis"], 10)

    assert few["only_supplement_violation"] is None and few["reason"] == "too_few_members"
    assert uncovered["only_supplement_violation"] is None and uncovered["reason"] == "window_not_covered"


def test_a_supplement_member_with_a_missing_value_is_dropped_not_assumed_clear():
    hole = (5.0, 0.0, None)
    members = [CLEAR] * 9 + [FOG_ONLY] + [hole] * 3

    result = ensemble.supplement_evaluation(supplement_forecast(members), WINDOW, SUPPLEMENT_ROWS, ["vis"], 10)

    assert result["ensemble_size"] == 10 and result["members_dropped"] == 3
    assert result["only_supplement_violation"] == pytest.approx(0.1)
