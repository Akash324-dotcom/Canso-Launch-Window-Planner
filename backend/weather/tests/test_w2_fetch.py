"""W2 forecast acquisition: parsing, issue time, explicit units, cache, fallback. No test touches the network."""

from __future__ import annotations

import json
from datetime import datetime, timezone

import httpx
import pytest

from backend.weather import config, fetch, units
from backend.weather.errors import UnknownSiteError, WeatherDataError

from .conftest import Upstream, load_fixture

NOW = datetime(2026, 10, 3, 22, 30, tzinfo=timezone.utc)
GFS_RUN = "2026-10-03T18:00:00Z"          # meta_ncep_gfs013.json, last_run_initialisation_time 1791050400
PARSED_FIELDS = ["temperature_2m", "wind_speed_10m", "wind_gusts_10m", "precipitation", "cloud_cover", "visibility"]


# Parsing ---------------------------------------------------------------------------------------------------

def test_parses_the_open_meteo_hourly_fields_from_the_committed_fixture():
    parsed = fetch.parse_open_meteo(load_fixture("open_meteo_forecast_canso.json"))

    assert len(parsed["times"]) == 48
    assert parsed["times"][0] == "2026-10-03T00:00"
    assert len(parsed["members"]) == 1
    for field in PARSED_FIELDS:
        column = parsed["members"][0][field]
        assert len(column) == 48
        assert all(isinstance(value, float) for value in column), field


def test_parses_every_member_of_an_ensemble_payload():
    parsed = fetch.parse_open_meteo(load_fixture("open_meteo_ensemble_canso.json"))

    assert len(parsed["members"]) == 51
    assert parsed["member_labels"][0] == "control"
    assert parsed["member_labels"][-1] == "member50"
    assert {len(member["wind_gusts_10m"]) for member in parsed["members"]} == {72}


def test_unit_conversion_is_explicit_and_one_value_is_checked_end_to_end():
    """Worked value. The fixture gives wind_speed_10m = 18.6 km/h at 2026-10-03T12:00.

    18.6 km/h / 3.6 = 5.166667 m/s, and 5.166667 m/s * 3.6 = 18.6 km/h.
    """
    raw = load_fixture("open_meteo_forecast_canso.json")
    index = raw["hourly"]["time"].index("2026-10-03T12:00")
    assert raw["hourly_units"]["wind_speed_10m"] == "km/h"
    assert raw["hourly"]["wind_speed_10m"][index] == 18.6

    parsed = fetch.parse_open_meteo(raw)

    assert parsed["units"]["wind_speed_10m"] == "m/s"
    in_ms = parsed["members"][0]["wind_speed_10m"][index]
    assert in_ms == pytest.approx(5.166667, abs=1e-6)
    assert units.convert(in_ms, "m/s", "km/h") == pytest.approx(18.6, abs=1e-9)
    assert parsed["units"]["temperature_2m"] == "degC"
    assert parsed["members"][0]["temperature_2m"][index] == 12.5
    assert parsed["units"]["precipitation"] == "mm/h"


@pytest.mark.parametrize(
    "value, source, target, expected",
    [
        (36.0, "km/h", "m/s", 10.0),
        (10.0, "m/s", "km/h", 36.0),
        (33.0, "kn", "m/s", 33 * 1852 / 3600),
        (30.0, "mph", "m/s", 13.4112),
        (99.0, "degF", "degC", 37.2222222),
        (4.0, "NM", "m", 7408.0),
        (0.1, "inch", "mm", 2.54),
    ],
)
def test_unit_conversions_against_hand_values(value, source, target, expected):
    assert units.convert(value, source, target) == pytest.approx(expected, abs=1e-6)


def test_an_unknown_unit_is_an_error_never_a_silent_pass_through():
    with pytest.raises(WeatherDataError):
        units.convert(1.0, "furlong/fortnight", "m/s")
    payload = load_fixture("open_meteo_forecast_canso.json")
    payload["hourly_units"]["wind_speed_10m"] = "furlong/fortnight"
    with pytest.raises(WeatherDataError):
        fetch.parse_open_meteo(payload)


# Issue time ------------------------------------------------------------------------------------------------

def test_every_fetch_result_carries_the_model_run_time_as_forecast_issue_time():
    Upstream().install()

    forecast = fetch.fetch_forecast("canso", chain="deterministic", now=NOW)

    assert forecast["forecast_issue_time"] == GFS_RUN
    assert forecast["issue_time_basis"] == "model_run_initialisation"
    assert forecast["retrieved_at"] == "2026-10-03T22:30:00Z"
    assert forecast["source"] == "open_meteo"
    assert forecast["kind"] == "deterministic"


def test_a_missing_run_time_is_stamped_from_the_fetch_time_and_says_so():
    Upstream(meta={"ncep_gfs013": None}).install()

    forecast = fetch.fetch_forecast("canso", chain="deterministic", now=NOW)

    assert forecast["forecast_issue_time"] == "2026-10-03T22:00:00Z"
    assert forecast["issue_time_basis"] == "fetch_time"


def test_a_stale_run_time_from_the_metadata_endpoint_is_not_trusted():
    """The committed GDPS metadata reports a run in May 2026 although data for October is served."""
    Upstream(down={"gfs_seamless"}).install()

    forecast = fetch.fetch_forecast("canso", chain="deterministic", now=NOW,
                                    parameters=["temperature_2m", "wind_gusts_10m"])

    assert forecast["source"] == "gdps"
    assert forecast["issue_time_basis"] == "fetch_time"
    assert forecast["forecast_issue_time"] == "2026-10-03T22:00:00Z"


# Cache -----------------------------------------------------------------------------------------------------

def test_the_raw_fetch_is_cached_on_disk_keyed_by_site_and_issue_time():
    Upstream().install()

    fetch.fetch_forecast("canso", chain="deterministic", now=NOW)

    path = fetch.cache_path("canso", GFS_RUN, "open_meteo_gfs")
    assert path == fetch.CACHE_DIR / "canso" / "20261003T1800Z" / "open_meteo_gfs.json"
    stored = json.loads(path.read_text(encoding="utf-8"))
    assert stored["meta"]["forecast_issue_time"] == GFS_RUN
    assert stored["payload"]["hourly"]["time"][0] == "2026-10-03T00:00"


def test_an_unchanged_issue_time_is_served_from_disk_and_a_new_one_is_fetched_again():
    upstream = Upstream().install()
    fetch.fetch_forecast("canso", chain="deterministic", now=NOW)
    assert upstream.data_calls == ["gfs_seamless"]

    fetch.clear_memo()
    again = fetch.fetch_forecast("canso", chain="deterministic", now=NOW)
    assert upstream.data_calls == ["gfs_seamless"], "same issue time must not download the data again"
    assert again["forecast_issue_time"] == GFS_RUN

    newer = dict(load_fixture("meta_ncep_gfs013.json"), last_run_initialisation_time=1791050400 + 6 * 3600)
    upstream.meta["ncep_gfs013"] = newer
    fetch.clear_memo()
    after_the_next_run = datetime(2026, 10, 4, 3, 0, tzinfo=timezone.utc)
    refreshed = fetch.fetch_forecast("canso", chain="deterministic", now=after_the_next_run)
    assert upstream.data_calls == ["gfs_seamless", "gfs_seamless"]
    assert refreshed["forecast_issue_time"] == "2026-10-04T00:00:00Z"
    assert fetch.cache_path("canso", "2026-10-04T00:00:00Z", "open_meteo_gfs").is_file()


def test_repeated_calls_inside_the_refresh_interval_make_no_request_at_all():
    upstream = Upstream().install()

    first = fetch.fetch_forecast("canso", chain="deterministic", now=NOW)
    calls = (list(upstream.data_calls), list(upstream.meta_calls))
    second = fetch.fetch_forecast("canso", chain="deterministic", now=NOW)

    assert (upstream.data_calls, upstream.meta_calls) == calls
    assert second is first


# Fallback --------------------------------------------------------------------------------------------------

def test_primary_unreachable_falls_back_to_the_next_source_and_says_which_answered():
    upstream = Upstream(down={"gfs_seamless"}).install()

    forecast = fetch.fetch_forecast("canso", chain="deterministic", now=NOW,
                                    parameters=["temperature_2m", "wind_gusts_10m", "precipitation"])

    assert upstream.data_calls == ["gfs_seamless", "gem_global"]
    assert forecast["source_id"] == "open_meteo_gdps"
    assert forecast["source"] == "gdps"


def test_a_source_that_lacks_a_required_field_is_rejected_not_used():
    """The GDPS fixture has visibility entirely null, so it cannot answer a request that needs visibility."""
    Upstream(down={"gfs_seamless"}).install()

    forecast = fetch.fetch_forecast("canso", chain="deterministic", now=NOW, parameters=["visibility"])

    assert forecast is None


def test_every_live_source_down_falls_back_to_the_snapshot_with_its_original_issue_time():
    Upstream().install()
    fetch.fetch_forecast("canso", chain="deterministic", now=NOW)
    fetch.clear_memo()
    Upstream(down={"gfs_seamless", "gem_global"}, meta={"ncep_gfs013": None, "cmc_gem_gdps": None}).install()

    later = datetime(2026, 10, 4, 9, 0, tzinfo=timezone.utc)
    forecast = fetch.fetch_forecast("canso", chain="deterministic", now=later)

    assert forecast["source"] == "snapshot_cache"
    assert forecast["source_id"] == "open_meteo_gfs"
    assert forecast["forecast_issue_time"] == GFS_RUN, "a snapshot is never presented as a fresh fetch"


def test_no_live_source_and_no_snapshot_returns_none_instead_of_inventing_a_forecast(monkeypatch, tmp_path):
    monkeypatch.setattr(fetch, "SNAPSHOT_DIR", tmp_path / "no_snapshot")
    Upstream(down={"gfs_seamless", "gem_global"}).install()

    assert fetch.fetch_forecast("canso", chain="deterministic", now=NOW) is None


def test_offline_mode_makes_no_request(monkeypatch, tmp_path):
    monkeypatch.setattr(fetch, "SNAPSHOT_DIR", tmp_path / "no_snapshot")
    upstream = Upstream().install()
    monkeypatch.setenv("LAUNCHWIN_WEATHER_OFFLINE", "1")

    assert fetch.fetch_forecast("canso", chain="deterministic", now=NOW) is None
    assert upstream.data_calls == [] and upstream.meta_calls == []


def test_an_unknown_site_is_an_error():
    with pytest.raises(UnknownSiteError):
        fetch.fetch_forecast("atlantis", chain="deterministic", now=NOW)


# sources.json ----------------------------------------------------------------------------------------------

SPEC_SOURCE_ENUM = {"open_meteo", "gdps", "era5_climatology", "snapshot_cache"}


def test_every_chain_entry_is_a_configured_source_with_a_spec_source_value():
    sources = config.load_sources()

    for chain in sources["chains"].values():
        for source_id in chain:
            assert sources["sources"][source_id]["response_source"] in SPEC_SOURCE_ENUM
    assert sources["climatology_archive"]["response_source"] in SPEC_SOURCE_ENUM


def test_sources_json_records_every_probed_endpoint_with_status_and_access_date():
    sources = config.load_sources()

    assert sources["probed_at"]
    names = {probe["name"] for probe in sources["probes"]}
    for required in ("open_meteo_forecast", "open_meteo_ensemble", "eccc_geomet", "eccc_datamart_root",
                     "eccc_datamart_model_gem_global", "eccc_datamart_today_model_gdps", "gefs_nomads",
                     "open_meteo_ensemble_gefs05", "nsf_ncar_era5_thredds", "eccc_climate_hourly",
                     "nrcan_geographical_names", "open_meteo_single_runs", "open_meteo_previous_runs",
                     "nomads_gefs_opendap", "canso_environmental_assessment", "ec_ads", "open_meteo_archive_era5",
                     "copernicus_cds"):
        assert required in names, required
    for probe in sources["probes"]:
        assert probe["url"].startswith("https://")
        assert isinstance(probe["http_status"], int) or probe["http_status"] is None
        assert probe["accessed"]
        assert probe["finding"].strip()


def test_a_snapshot_answer_is_held_only_for_the_failure_retry_interval(monkeypatch):
    """After an outage the live source is tried again after failure_retry_s, not after the full refresh interval."""
    request = config.load_sources()["request"]
    assert request["failure_retry_s"] < request["refresh_ttl_s"]
    clock = {"t": 1000.0}
    monkeypatch.setattr(fetch.time, "monotonic", lambda: clock["t"])

    Upstream().install()
    fetch.fetch_forecast("canso", chain="deterministic", now=NOW)
    fetch.clear_memo()
    Upstream(down={"gfs_seamless", "gem_global"}, meta={"ncep_gfs013": None, "cmc_gem_gdps": None}).install()
    during = fetch.fetch_forecast("canso", chain="deterministic", now=NOW)
    assert during["source"] == "snapshot_cache"

    Upstream().install()
    clock["t"] += request["failure_retry_s"] - 1
    assert fetch.fetch_forecast("canso", chain="deterministic", now=NOW)["source"] == "snapshot_cache"
    clock["t"] += 2
    assert fetch.fetch_forecast("canso", chain="deterministic", now=NOW)["source"] == "open_meteo"
