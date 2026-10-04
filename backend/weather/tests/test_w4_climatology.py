"""W4 climatology: P(L | month, hour) from the ERA5 archive, the sample floor, flags and provenance."""

from __future__ import annotations

from datetime import date, datetime, timedelta

import pytest

from backend.weather import climatology, config, criteria

GUST = {"criterion_id": "gust", "parameter": "wind_gusts_10m", "comparison": "gt", "limit": 17.0,
        "unit": "m/s", "flag": "VERIFIED"}
SITE = {"timezone": "America/Halifax", "evaluation_window_local": {"start_hour": 7, "end_hour": 12}}


def synthetic_archive() -> dict:
    """Two Januaries of hourly gusts. Calm (5 m/s) except 20 m/s at 15:00 UTC on days 1 to 10 of each year.

    One value is missing: 2021-01-20T13:00.
    Hand counts for January, with 31 + 31 = 62 samples per hour of day:
      hour 15: 20 violations, so P(L | Jan, 15 UTC) = 42/62.
      hour 13: one missing sample, so n = 61, and no violation, so the frequency is exactly 1.
      hour 03: n = 62, no violation, frequency exactly 1.
    Daily window, local 07:00 to 12:00 in AST = 11:00 to 16:00 UTC: 62 days, 1 excluded for the missing hour,
    20 of the remaining 61 contain the 15:00 violation, so P(L | Jan window) = 41/61.
    """
    times, gusts = [], []
    for year in (2021, 2022):
        moment = datetime(year, 1, 1, 0)
        while moment.month == 1:
            times.append(moment.strftime("%Y-%m-%dT%H:00"))
            gusts.append(20.0 if moment.hour == 15 and moment.day <= 10 else 5.0)
            moment += timedelta(hours=1)
    gusts[times.index("2021-01-20T13:00")] = None
    return {"times": times, "columns": {"wind_gusts_10m": gusts}, "units": {"wind_gusts_10m": "m/s"}}


def bin_of(built, month, hour):
    return next(b for b in built["bins"] if b["month"] == month and b["hour_utc"] == hour)


def test_each_bin_is_the_fraction_of_historical_hours_that_satisfied_every_criterion():
    built = climatology.build_bins(synthetic_archive(), [GUST], SITE, min_samples=30)

    january_15 = bin_of(built, 1, 15)
    assert january_15["n"] == 62
    assert january_15["n_launchable"] == 42
    assert january_15["p_launch"] == pytest.approx(42 / 62)
    assert january_15["p_violation"] == {"gust": pytest.approx(20 / 62)}
    assert january_15["low_confidence"] is False
    assert len(built["bins"]) == 12 * 24


def test_hours_with_a_missing_value_are_excluded_and_counted():
    built = climatology.build_bins(synthetic_archive(), [GUST], SITE, min_samples=30)

    assert bin_of(built, 1, 13)["n"] == 61
    assert built["hours_total"] == 2 * 31 * 24
    assert built["hours_excluded_missing"] == 1


def test_a_thin_bin_is_flagged_low_confidence_and_is_not_presented_as_a_probability():
    built = climatology.build_bins(synthetic_archive(), [GUST], SITE, min_samples=100)

    january_15 = bin_of(built, 1, 15)
    assert january_15["n"] == 62
    assert january_15["low_confidence"] is True
    assert "below" in january_15["flag_reason"]


def test_a_zero_sample_bin_is_not_zero_probability():
    built = climatology.build_bins(synthetic_archive(), [GUST], SITE, min_samples=30)

    july = bin_of(built, 7, 12)
    assert july["n"] == 0
    assert july["p_launch"] is None
    assert july["low_confidence"] is True


def test_a_frequency_of_exactly_zero_or_one_is_flagged():
    built = climatology.build_bins(synthetic_archive(), [GUST], SITE, min_samples=30)

    never_violated = bin_of(built, 1, 3)
    assert never_violated["p_launch"] == 1.0
    assert never_violated["low_confidence"] is True
    assert "exactly" in never_violated["flag_reason"]


def test_the_daily_window_bin_uses_the_same_event_as_the_forecast():
    built = climatology.build_bins(synthetic_archive(), [GUST], SITE, min_samples=30)

    january = next(b for b in built["daily_window"] if b["month"] == 1)
    assert january["n"] == 61
    assert january["n_launchable"] == 41
    assert january["p_launch"] == pytest.approx(41 / 61)
    assert built["days_excluded_missing"] == 1
    assert len(built["daily_window"]) == 12


# The committed climatology ---------------------------------------------------------------------------------

@pytest.fixture(scope="module")
def committed() -> dict:
    return climatology.load_climatology("canso")


def test_the_committed_file_carries_its_provenance(committed):
    for key in ("source", "period_start", "period_end", "criteria_version_used", "generated_at"):
        assert committed[key], key
    assert committed["source"] == "era5_climatology"
    assert committed["criteria_version_used"] == criteria.current_criteria_version()
    assert committed["hour_basis"] == "UTC"


def test_the_period_is_at_least_three_full_years_and_is_stated(committed):
    start = date.fromisoformat(committed["period_start"])
    end = date.fromisoformat(committed["period_end"])
    assert (start.month, start.day) == (1, 1)
    assert (end.month, end.day) == (12, 31)
    assert end.year - start.year + 1 >= 3


def test_every_bin_carries_n_and_passes_the_sample_floor_or_is_flagged(committed):
    floor = committed["min_samples_per_bin"]
    assert floor == config.load_sources()["climatology"]["min_samples_per_bin"] == 30
    assert len(committed["bins"]) == 288 and len(committed["daily_window"]) == 12
    for entry in committed["bins"] + committed["daily_window"]:
        assert isinstance(entry["n"], int)
        assert entry["n"] >= floor or entry["low_confidence"] is True


def test_no_bin_is_exactly_zero_or_one_without_a_flag(committed):
    for entry in committed["bins"] + committed["daily_window"]:
        if entry["p_launch"] in (0.0, 1.0, None):
            assert entry["low_confidence"] is True, entry


def test_the_committed_file_evaluates_every_row_the_archive_can_and_names_the_rest_with_reasons(committed):
    table = criteria.load_criteria(committed["criteria_version_used"])
    evaluated = [row["criterion_id"] for row in climatology.evaluated_rows("canso", table)]

    assert committed["criteria_evaluated"] == evaluated
    for entry in committed["bins"] + committed["daily_window"]:
        assert list(entry["p_violation"]) == evaluated
    named = [entry["criterion_id"] for entry in committed["criteria_not_evaluable"]]
    assert sorted(evaluated + named) == sorted(row["criterion_id"] for row in table["criteria"])
    assert all(entry["reason"].strip() for entry in committed["criteria_not_evaluable"])


def test_every_criterion_of_the_table_is_evaluated_and_none_lacks_data(committed):
    """No row of the criteria table is without data: the archive carries a field for each of them."""
    table = criteria.load_criteria(committed["criteria_version_used"])

    assert committed["criteria_not_evaluable"] == []
    assert committed["criteria_evaluated"] == [row["criterion_id"] for row in table["criteria"]]
    assert "visibility" in committed["criteria_evaluated"]


def test_the_archive_has_no_missing_value_and_names_the_source_of_every_field(committed):
    archive = climatology.load_hourly_archive("canso")
    meta = archive["meta"]

    for field, column in archive["columns"].items():
        assert all(value is not None for value in column), field
    assert set(meta["missing_values"].values()) == {0}
    assert committed["hours_excluded_missing"] == 0 and committed["days_excluded_missing"] == 0
    assert set(meta["field_sources"]) == set(archive["columns"])
    for field, source in meta["field_sources"].items():
        expected = "observed at" if field == "visibility" else "era5"
        assert source.startswith(expected), f"{field}: {source}"


def test_every_gap_filled_hour_is_listed_with_its_source(committed):
    gap = climatology.archive_metadata("canso")["gap_filled"]["visibility"]

    assert gap["hours"] == len(gap["times"]) == committed["gap_filled"]["visibility"]["hours"]
    assert gap["source"].strip()
    assert gap["hours"] < 0.05 * committed["hours_total"], "the station record must supply nearly every hour"


def test_rebuilding_from_the_committed_archive_reproduces_the_committed_numbers(committed):
    """Provenance (spec II.10): every number in the file is recomputable from the archive next to it."""
    rebuilt = climatology.build_climatology("canso", criteria.load_criteria(None), generated_at="rebuilt")

    for key in ("bins", "daily_window", "hours_total", "hours_excluded_missing", "period_start",
                "period_end", "archive_sha256", "archive_acquisition", "field_sources", "gap_filled",
                "criteria_evaluated", "criteria_not_evaluable"):
        assert rebuilt[key] == committed[key], key


def test_loading_and_sampling_the_climatology_works(committed):
    sampled = climatology.climatology(10, 14)

    assert sampled == next(b for b in committed["bins"] if b["month"] == 10 and b["hour_utc"] == 14)
    assert 0.0 < sampled["p_launch"] < 1.0
    with pytest.raises(ValueError):
        climatology.climatology(13, 0)
    with pytest.raises(ValueError):
        climatology.climatology(1, 24)


def test_the_archive_metadata_matches_the_archive_file():
    import gzip
    import hashlib

    meta = climatology.archive_metadata("canso")
    raw = gzip.decompress((config.DATA_DIR / meta["file"]).read_bytes())

    assert hashlib.sha256(raw).hexdigest() == meta["csv_sha256"]
    assert meta["acquisition"] in {"era5_cds", "open_data"}
    assert set(meta["field_sources"]) == set(meta["fields"]) == set(meta["source_units"])


def test_every_evaluated_field_in_the_archive_is_a_real_field_that_varies():
    """A field served as one constant value for the whole period is not data, even though it is not null.

    Written after the Open-Meteo 'showers' field was found to be 0.0 in all 87,672 archive hours.
    """
    archive = climatology.load_hourly_archive("canso")
    rows = climatology.evaluated_rows("canso", criteria.load_criteria(None))
    assert rows

    for parameter in criteria.required_parameters(rows):
        assert parameter in archive["columns"], parameter
        assert len(set(archive["columns"][parameter])) > 1, f"{parameter} is constant over the whole archive"
