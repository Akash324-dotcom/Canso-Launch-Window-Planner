"""Acquisition of the hourly observed archive: every field from a named real source, and no missing value."""

from __future__ import annotations

import gzip
import json

import httpx
import pytest

from backend.weather import config, era5
from backend.weather.errors import WeatherDataError

SITE = {"latitude_deg": 45.310389, "longitude_deg": -60.993292}
TIMES = ["2022-01-01T00:00", "2022-01-01T01:00", "2022-01-01T02:00"]


# Source selection ------------------------------------------------------------------------------------------

def test_the_copernicus_route_is_used_when_the_key_is_real_and_the_packages_are_present():
    assert era5.choose_source("auto", key_status="configured", missing_packages=[])[0] == "era5_cds"


@pytest.mark.parametrize("status", ["placeholder", "missing"])
def test_a_placeholder_or_missing_key_selects_the_open_route_and_says_why(status):
    source, reason = era5.choose_source("auto", key_status=status, missing_packages=[])

    assert source == "open_data"
    assert "CDSAPI_KEY" in reason


def test_a_real_key_without_the_download_packages_selects_the_open_route_and_names_the_packages():
    source, reason = era5.choose_source("auto", key_status="configured", missing_packages=["cdsapi", "xarray"])

    assert source == "open_data"
    assert "cdsapi" in reason and "xarray" in reason


def test_asking_for_copernicus_explicitly_without_a_usable_key_is_an_error():
    with pytest.raises(WeatherDataError, match="CDSAPI_KEY"):
        era5.choose_source("era5_cds", key_status="placeholder", missing_packages=[])
    assert era5.choose_source("open_data", key_status="configured", missing_packages=[])[0] == "open_data"


# The open route: ERA5 surface fields, ERA5 CAPE, observed visibility -----------------------------------------

OPEN = {
    "era5_surface": {"url": "https://archive.test/v1/archive", "model": "era5", "fields": ["temperature_2m"]},
    "era5_cape": {
        "url_template": "https://thredds.test/ncss/e5.oper.an.sfc/{yyyymm}/cape.{yyyymm}0100_{yyyymm}{last_day}23.nc",
        "variable": "CAPE", "field": "cape", "unit": "J/kg", "parallel_requests": 1, "retries": 1,
    },
}
VISIBILITY = {
    "field": "visibility", "unit": "m",
    "station": {"url": "https://eccc.test/collections/climate-hourly/items", "climate_identifier": "8204495",
                "station_name": "PORT HAWKESBURY", "property": "VISIBILITY", "source_unit": "km",
                "page_size": 2},
    "gap_fill": {"url": "https://history.test/v1/forecast", "model": "gfs_seamless", "field": "visibility"},
}


def open_transport(station_values=(16.1, None, 3.2), missing_gap_fill=False, cape_rows=3):
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request.url.host)
        host = request.url.host
        if host == "archive.test":
            return httpx.Response(200, json={
                "latitude": 45.25, "longitude": -61.0, "elevation": 14.0, "utc_offset_seconds": 0,
                "hourly_units": {"time": "iso8601", "temperature_2m": "°C"},
                "hourly": {"time": TIMES, "temperature_2m": [1.5, 2.0, 2.5]}})
        if host == "thredds.test":
            assert request.url.params["var"] == "CAPE" and request.url.params["accept"] == "csv"
            lines = ['time,station,latitude[unit="degrees_north"],longitude[unit="degrees_east"],CAPE[unit="J kg**-1"]']
            values = [7.875, 250.0, 0.0]
            for label, value in list(zip(TIMES, values))[:cape_rows]:
                lines.append(f"{label}:00Z,GridPointRequestedAt[45.250N_61.000W],45.250,-61.000,{value}")
            return httpx.Response(200, text="\n".join(lines) + "\n")
        if host == "eccc.test":
            offset = int(request.url.params.get("offset", 0))
            records = [{"properties": {"UTC_DATE": f"{label}:00", "VISIBILITY": value}}
                       for label, value in zip(TIMES, station_values)]
            return httpx.Response(200, json={"features": records[offset:offset + 2]})
        gap = [9000.0, None if missing_gap_fill else 9500.0, 9900.0]
        return httpx.Response(200, json={
            "latitude": 45.25, "longitude": -61.0, "utc_offset_seconds": 0,
            "hourly_units": {"time": "iso8601", "visibility": "m"},
            "hourly": {"time": TIMES, "visibility": gap}})

    return httpx.MockTransport(handler), calls


def fetch_open(**kwargs):
    transport, calls = open_transport(**kwargs)
    with httpx.Client(transport=transport) as client:
        data = era5.fetch_open_data(SITE, OPEN, 2022, 2022, client, months=[(2022, 1)])
        data = era5.add_observed_visibility(data, SITE, VISIBILITY, client)
    return data, calls


def test_the_open_route_takes_surface_fields_and_cape_from_era5_and_records_where_each_came_from():
    data, _ = fetch_open()

    assert data["times"] == TIMES
    assert data["columns"]["temperature_2m"] == [1.5, 2.0, 2.5]
    assert data["columns"]["cape"] == [7.875, 250.0, 0.0]
    assert data["source_units"]["cape"] == "J/kg"
    assert data["field_sources"]["temperature_2m"].startswith("era5")
    assert "thredds.test" in data["field_sources"]["cape"] and data["field_sources"]["cape"].startswith("era5")


def test_visibility_is_the_station_observation_in_metres_with_gaps_filled_and_counted():
    """Station values 16.1 km, missing, 3.2 km. The missing hour takes the gap-fill value 9500 m."""
    data, _ = fetch_open()

    assert data["columns"]["visibility"] == [pytest.approx(16100.0), 9500.0, pytest.approx(3200.0)]
    assert data["source_units"]["visibility"] == "m"
    assert "PORT HAWKESBURY" in data["field_sources"]["visibility"]
    assert data["gap_filled"]["visibility"] == {"hours": 1, "times": ["2022-01-01T01:00"],
                                               "source": "gfs_seamless via https://history.test/v1/forecast"}


def test_the_gap_fill_request_stays_inside_the_archive_period():
    """Found against the live service on 2026-10-04: a request to the end of the current year is refused (HTTP 400).

    The archive here covers 2022-01-01 only, so the gap-fill request must ask for that day and no other.
    """
    asked = []
    inner, _ = open_transport()

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == "history.test":
            asked.append((request.url.params["start_date"], request.url.params["end_date"]))
        return inner.handle_request(request)

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        data = era5.fetch_open_data(SITE, OPEN, 2022, 2022, client, months=[(2022, 1)])
        era5.add_observed_visibility(data, SITE, VISIBILITY, client)

    assert asked == [("2022-01-01", "2022-01-01")]


def test_a_complete_station_record_needs_no_gap_fill():
    data, _ = fetch_open(station_values=(16.1, 12.0, 3.2))

    assert data["gap_filled"]["visibility"]["hours"] == 0
    assert data["columns"]["visibility"][1] == pytest.approx(12000.0)


def test_an_hour_that_no_source_can_supply_is_an_error_never_a_null_in_the_archive():
    transport, _ = open_transport(missing_gap_fill=True)
    with httpx.Client(transport=transport) as client:
        data = era5.fetch_open_data(SITE, OPEN, 2022, 2022, client, months=[(2022, 1)])
        data = era5.add_observed_visibility(data, SITE, VISIBILITY, client)

    with pytest.raises(WeatherDataError, match="visibility"):
        era5.assert_complete(data)


def test_an_era5_month_with_missing_hours_is_refused():
    transport, _ = open_transport(cape_rows=2)
    with httpx.Client(transport=transport) as client:
        with pytest.raises(WeatherDataError, match="cape"):
            era5.fetch_open_data(SITE, OPEN, 2022, 2022, client, months=[(2022, 1)])


def test_a_complete_archive_passes_the_completeness_check():
    data, _ = fetch_open()

    assert era5.assert_complete(data) is None


def test_a_field_served_as_one_constant_value_is_dropped_and_reported():
    columns = {"temperature_2m": [1.5, 2.0, 2.5], "showers": [0.0, 0.0, 0.0], "cape": [10.0, 250.0, 0.0]}

    kept, dropped = era5.drop_constant_fields(columns)

    assert list(kept) == ["temperature_2m", "cape"]
    assert dropped == ["showers"]


def test_the_written_archive_states_its_sources_period_and_checksum(tmp_path):
    data, _ = fetch_open()

    meta = era5.write_archive("canso", data, acquisition="open_data", reason="CDSAPI_KEY placeholder",
                              dropped=[], directory=tmp_path, retrieved_at="2026-10-04T01:00Z")

    assert meta["acquisition"] == "open_data"
    assert meta["period_start"] == TIMES[0] and meta["period_end"] == TIMES[-1]
    assert meta["missing_values"] == {"temperature_2m": 0, "cape": 0, "visibility": 0}
    assert meta["gap_filled"]["visibility"]["hours"] == 1
    raw = gzip.decompress((tmp_path / meta["file"]).read_bytes()).decode()
    assert raw.splitlines()[0] == "time_utc,temperature_2m,cape,visibility"
    assert raw.splitlines()[2] == "2022-01-01T01:00,2.0,250.0,9500.0"
    assert json.loads((tmp_path / "era5_canso_hourly.meta.json").read_text()) == meta


# The Copernicus route ----------------------------------------------------------------------------------------

def test_cds_values_are_converted_to_the_field_names_and_units_the_criteria_use():
    """Hand values. u10 = 3, v10 = 4 m/s gives 5 m/s. 273.15 K is 0 degC. 0.001 m of rain is 1 mm.

    0.002 m of snow water equivalent is 2 mm, times 0.7 cm per mm is 1.4 cm. A cloud fraction of 0.5 is 50 percent.
    """
    point = {"u10": [3.0, None], "v10": [4.0, 1.0], "fg10": [12.5, 9.0], "t2m": [273.15, 283.15],
             "tp": [0.001, 0.0], "sf": [0.002, 0.0], "tcc": [0.5, 1.0], "lcc": [0.25, 0.0], "mcc": [1.0, 0.0],
             "cape": [150.0, 0.0]}

    columns, units = era5.cds_point_to_columns(point, levels=[], snowfall_cm_per_mm_water=0.7)

    assert columns["wind_speed_10m"] == [5.0, None]
    assert columns["wind_gusts_10m"] == [12.5, 9.0]
    assert columns["temperature_2m"] == [pytest.approx(0.0), pytest.approx(10.0)]
    assert columns["precipitation"] == [pytest.approx(1.0), 0.0]
    assert columns["snowfall"] == [pytest.approx(1.4), 0.0]
    assert columns["cloud_cover_low"] == [25.0, 0.0]
    assert columns["cloud_cover_mid"] == [100.0, 0.0]
    assert columns["cape"] == [150.0, 0.0]
    assert units["wind_speed_10m"] == "m/s" and units["temperature_2m"] == "°C" and units["precipitation"] == "mm"


@pytest.mark.parametrize("u, v, expected", [(0.0, -5.0, 0.0), (-5.0, 0.0, 90.0), (0.0, 5.0, 180.0), (5.0, 0.0, 270.0)])
def test_wind_direction_is_the_direction_the_wind_blows_from(u, v, expected):
    assert era5.wind_direction_from(u, v) == pytest.approx(expected)


def test_the_cds_request_covers_a_quarter_with_the_configured_variables_and_a_cell_around_the_site():
    cfg = config.load_sources()["climatology_archive"]["era5_cds"]

    single = era5.cds_request(cfg, "single", SITE, year=2024, first_month=4)

    assert single["dataset"] == "reanalysis-era5-single-levels"
    assert single["request"]["variable"] == cfg["single_level_variables"]
    assert "convective_available_potential_energy" in single["request"]["variable"]
    assert single["request"]["year"] == ["2024"] and single["request"]["month"] == ["04", "05", "06"]
    north, west, south, east = single["request"]["area"]
    assert south <= 45.310389 <= north and west <= -60.993292 <= east and north > south and east > west
    assert single["request"]["data_format"] == "netcdf"


def test_reading_a_cds_netcdf_file_returns_the_nearest_grid_point_series(tmp_path):
    xarray = pytest.importorskip("xarray")
    pytest.importorskip("netCDF4")
    import numpy

    times = numpy.array(["2024-04-01T00", "2024-04-01T01"], dtype="datetime64[ns]")
    dataset = xarray.Dataset(
        {"t2m": (("valid_time", "latitude", "longitude"), numpy.array([[[273.15, 1.0], [2.0, 3.0]],
                                                                        [[283.15, 1.0], [2.0, 3.0]]]))},
        coords={"valid_time": times, "latitude": [45.25, 45.5], "longitude": [-61.0, -60.75]})
    dataset.to_netcdf(tmp_path / "single.nc")

    labels, point = era5.read_cds_point([tmp_path / "single.nc"], latitude=45.3, longitude=-61.0)

    assert labels == ["2024-04-01T00:00", "2024-04-01T01:00"]
    assert point["t2m"] == [pytest.approx(273.15), pytest.approx(283.15)]


# acquire(): Copernicus when the key is real, the open route otherwise ----------------------------------------

ARCHIVE_CFG = {"first_year": 2022, "last_year": 2025, "era5_cds": {}, "open_data": {},
               "visibility_observed": {}}
SECRET = {"url": "https://cds.test/api", "key": "super-secret-token"}


def run_acquire(preference, key_status, cds_error=None, first_year=None, last_year=None):
    calls = []

    def cds(site_cfg, cfg, first, last, credentials, workdir):
        calls.append(("cds", first, last))
        if cds_error is not None:
            raise cds_error
        return {"marker": "cds"}

    def open_route(site_cfg, cfg, first, last, client, **extra):
        calls.append(("open_data", first, last))
        return {"marker": "open_data"}

    def visibility(data, site_cfg, cfg, client):
        calls.append(("visibility", data["marker"]))
        return {**data, "visibility": True}

    outcome = era5.acquire(SITE, ARCHIVE_CFG, preference, key_status=key_status, credentials=SECRET, missing=[],
                           first_year=first_year, last_year=last_year, workdir=None, client=None,
                           cds_fetcher=cds, open_fetcher=open_route, visibility_fetcher=visibility,
                           completeness_check=lambda data: None)
    return outcome, calls


def test_with_a_real_key_the_era5_fields_come_from_copernicus_and_visibility_from_the_station():
    (data, source, reason), calls = run_acquire("auto", "configured")

    assert source == "era5_cds" and data == {"marker": "cds", "visibility": True}
    assert calls == [("cds", 2022, 2025), ("visibility", "cds")]


def test_with_the_placeholder_key_the_open_route_supplies_the_same_fields():
    (data, source, reason), calls = run_acquire("auto", "placeholder")

    assert source == "open_data" and data == {"marker": "open_data", "visibility": True}
    assert calls == [("open_data", 2022, 2025), ("visibility", "open_data")]
    assert "CDSAPI_KEY" in reason


def test_a_failed_copernicus_download_uses_the_open_route_and_the_reason_never_shows_the_key():
    failure = RuntimeError("401 Unauthorized for token super-secret-token")

    (data, source, reason), calls = run_acquire("auto", "configured", cds_error=failure)

    assert source == "open_data"
    assert [name for name, *_ in calls] == ["cds", "open_data", "visibility"]
    assert "RuntimeError" in reason and "super-secret-token" not in reason


def test_an_explicit_request_for_copernicus_does_not_switch_route_when_the_download_fails():
    with pytest.raises(RuntimeError):
        run_acquire("era5_cds", "configured", cds_error=RuntimeError("queue timeout"))


def test_explicit_years_are_honoured():
    (_, source, _), calls = run_acquire("open_data", "configured", first_year=2023, last_year=2024)

    assert source == "open_data" and calls[0] == ("open_data", 2023, 2024)


# Copernicus precision and period -----------------------------------------------------------------------------

def test_copernicus_precipitation_and_snowfall_are_reported_to_the_precision_of_the_forecast_data():
    """Found against a real download: unrounded ERA5 precipitation is non-zero twice as often as the 0.1 mm data.

    0.00004 m is 0.04 mm and rounds to 0.0 mm; 0.00016 m is 0.16 mm and rounds to 0.2 mm. Snowfall water
    equivalent 0.00004 m rounds to 0.0 mm, so no snow; 0.0003 m is 0.3 mm, times 0.7 is 0.21 cm.
    """
    point = {"u10": [1.0, 1.0], "v10": [1.0, 1.0], "fg10": [2.0, 2.0], "t2m": [280.0, 280.0],
             "tp": [0.00004, 0.00016], "sf": [0.00004, 0.0003], "tcc": [0.1, 0.1], "lcc": [0.1, 0.1],
             "mcc": [0.1, 0.1], "cape": [0.0, 0.0]}

    columns, _ = era5.cds_point_to_columns(point, levels=[], snowfall_cm_per_mm_water=0.7, precision_mm=0.1)

    assert columns["precipitation"] == [0.0, pytest.approx(0.2)]
    assert columns["snowfall"] == [0.0, pytest.approx(0.21)]


def test_the_copernicus_requests_stop_at_the_last_available_day():
    """Quarters up to the month before the end date, then the last month with only its available days."""
    from datetime import date

    tasks = era5.cds_tasks(2025, date(2026, 5, 20))

    assert tasks[:4] == [(2025, [1, 2, 3], None), (2025, [4, 5, 6], None), (2025, [7, 8, 9], None),
                         (2025, [10, 11, 12], None)]
    assert tasks[4:] == [(2026, [1, 2, 3], None), (2026, [4], None), (2026, [5], list(range(1, 21)))]


def test_full_years_are_requested_by_quarter_when_no_end_date_is_given():
    assert era5.cds_tasks(2024, None, last_year=2024) == [(2024, [1, 2, 3], None), (2024, [4, 5, 6], None),
                                                          (2024, [7, 8, 9], None), (2024, [10, 11, 12], None)]


def test_hours_at_the_end_that_a_source_has_not_published_yet_are_trimmed_not_kept_as_nulls():
    data = {"times": ["t1", "t2", "t3", "t4"], "columns": {"a": [1.0, 2.0, 3.0, None], "b": [1.0, 2.0, None, None]},
            "source_units": {}, "field_sources": {}, "grid": {}, "gap_filled": {}}

    trimmed = era5.trim_incomplete_tail(data)

    assert trimmed["times"] == ["t1", "t2"]
    assert trimmed["columns"] == {"a": [1.0, 2.0], "b": [1.0, 2.0]}


# Request size, and CAPE from Copernicus inside the open route ------------------------------------------------

def test_copernicus_requests_can_be_cut_to_any_number_of_months():
    """Found against the live service: a quarter of ten variables is refused with 'cost limits exceeded'."""
    from datetime import date

    monthly = era5.cds_tasks(2026, date(2026, 3, 31), months_per_request=1)
    half_years = era5.cds_tasks(2025, date(2026, 2, 10), months_per_request=6)

    assert monthly == [(2026, [1], None), (2026, [2], None), (2026, [3], None)]
    assert half_years == [(2025, [1, 2, 3, 4, 5, 6], None), (2025, [7, 8, 9, 10, 11, 12], None),
                          (2026, [1], None), (2026, [2], list(range(1, 11)))]
    assert config.load_sources()["climatology_archive"]["era5_cds"]["months_per_request"] == 1


def test_the_open_route_can_take_cape_from_copernicus_and_then_reaches_the_latest_published_day():
    """NCAR publishes ERA5 months late. With a usable key, CAPE comes from Copernicus and the archive extends."""
    from datetime import date

    requested = []

    def handler(request: httpx.Request) -> httpx.Response:
        requested.append((request.url.host, request.url.params.get("start_date"), request.url.params.get("end_date")))
        return httpx.Response(200, json={
            "latitude": 45.25, "longitude": -61.0, "elevation": 14.0, "utc_offset_seconds": 0,
            "hourly_units": {"time": "iso8601", "temperature_2m": "°C"},
            "hourly": {"time": TIMES + ["2022-01-01T03:00"], "temperature_2m": [1.5, 2.0, 2.5, None]}})

    def cape_from_copernicus(first_year, end_date):
        assert (first_year, end_date) == (2022, date(2022, 1, 1))
        return {label: 5.0 for label in TIMES}, "era5 via Copernicus CDS, reanalysis-era5-single-levels"

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        data = era5.fetch_open_data(SITE, OPEN, 2022, 2022, client, end_date=date(2022, 1, 1),
                                    cape_fetcher=cape_from_copernicus)

    assert requested == [("archive.test", "2022-01-01", "2022-01-01")], "no request to the NCAR server"
    assert data["times"] == TIMES, "the hour Open-Meteo has not published yet is trimmed"
    assert data["columns"]["cape"] == [5.0, 5.0, 5.0]
    assert data["field_sources"]["cape"].startswith("era5 via Copernicus CDS")
