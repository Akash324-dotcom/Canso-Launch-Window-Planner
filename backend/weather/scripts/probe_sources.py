"""Probe every weather endpoint named in the issue and record status and access date in data/sources.json.

    python -m backend.weather.scripts.probe_sources

Only the 'probes' list and 'probed_at' are rewritten. Run it from the repository root. It needs the network.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone

import httpx

from backend.weather import config

SITE = "canso"
ENSEMBLE_FIELDS = "wind_speed_100m,wind_gusts_10m,precipitation,snowfall,temperature_2m,showers,cloud_cover_low,visibility"


def _point(site_cfg: dict) -> dict:
    return {"latitude": site_cfg["latitude_deg"], "longitude": site_cfg["longitude_deg"], "timezone": "GMT"}


def probes(site_cfg: dict) -> list[dict]:
    point = _point(site_cfg)
    ensemble = "https://ensemble-api.open-meteo.com/v1/ensemble"
    return [
        {"name": "open_meteo_forecast", "url": "https://api.open-meteo.com/v1/forecast",
         "params": {**point, "hourly": "temperature_2m,wind_gusts_10m,visibility", "forecast_days": 1},
         "role": "deterministic forecast, primary of the deterministic chain"},
        {"name": "open_meteo_forecast_gdps", "url": "https://api.open-meteo.com/v1/forecast",
         "params": {**point, "hourly": "temperature_2m,wind_gusts_10m,visibility", "models": "gem_global",
                    "forecast_days": 1},
         "role": "ECCC GDPS deterministic forecast through Open-Meteo, second of the deterministic chain"},
        {"name": "open_meteo_gdps_run_metadata", "url": "https://api.open-meteo.com/data/cmc_gem_gdps/static/meta.json",
         "params": {}, "role": "model run time for the GDPS source"},
        {"name": "open_meteo_ensemble", "url": ensemble,
         "params": {**point, "hourly": ENSEMBLE_FIELDS, "models": "ecmwf_ifs025", "forecast_days": 1},
         "role": "ECMWF IFS ensemble, primary of the ensemble chain"},
        {"name": "open_meteo_ensemble_run_metadata",
         "url": "https://ensemble-api.open-meteo.com/data/ecmwf_ifs025_ensemble/static/meta.json",
         "params": {}, "role": "model run time for the primary ensemble"},
        {"name": "open_meteo_ensemble_gefs", "url": ensemble,
         "params": {**point, "hourly": ENSEMBLE_FIELDS, "models": "gfs_seamless", "forecast_days": 1},
         "role": "NCEP GEFS ensemble, probed as a fallback candidate"},
        {"name": "open_meteo_ensemble_gem", "url": ensemble,
         "params": {**point, "hourly": ENSEMBLE_FIELDS, "models": "gem_global", "forecast_days": 1},
         "role": "ECCC GEM global ensemble, probed as a fallback candidate"},
        {"name": "open_meteo_archive_era5", "url": "https://archive-api.open-meteo.com/v1/archive",
         "params": {**point, "hourly": ENSEMBLE_FIELDS, "models": "era5", "start_date": "2024-07-01",
                    "end_date": "2024-07-01"},
         "role": "ERA5 hourly reanalysis for climatology and verification"},
        {"name": "open_meteo_historical_forecast", "url": "https://historical-forecast-api.open-meteo.com/v1/forecast",
         "params": {**point, "hourly": "temperature_2m,wind_gusts_10m", "start_date": "2025-01-01",
                    "end_date": "2025-01-01"},
         "role": "archived forecasts for the hindcast of issue #7"},
        {"name": "eccc_geomet", "url": "https://geo.weather.gc.ca/geomet",
         "params": {"service": "WMS", "version": "1.3.0", "request": "GetCapabilities", "layer": "GDPS.ETA_TT"},
         "role": "official Canadian model through OGC web services"},
        {"name": "eccc_ogc_api", "url": "https://api.weather.gc.ca/collections", "params": {"f": "json"},
         "role": "ECCC OGC API collections"},
        {"name": "eccc_datamart_root", "url": "https://dd.weather.gc.ca/", "params": {},
         "role": "ECCC Datamart root"},
        {"name": "eccc_datamart_model_gem_global", "url": "https://dd.weather.gc.ca/model_gem_global/",
         "params": {}, "role": "ECCC Datamart GDPS path without a date partition"},
        {"name": "eccc_datamart_today_model_gem_global", "url": "https://dd.weather.gc.ca/today/model_gem_global/",
         "params": {}, "role": "ECCC Datamart, old GDPS directory name under the date partition"},
        {"name": "eccc_datamart_today_model_gdps", "url": "https://dd.weather.gc.ca/today/model_gdps/15km/",
         "params": {}, "role": "ECCC Datamart, current GDPS directory under the date partition (GRIB2 files)",
         "note": "The Datamart root lists dated folders (YYYYMMDD/) and today/. The GDPS lives under "
                 "today/model_gdps/15km/ (HTTP 200 on 2026-10-03; HTTP 404 shortly after 00 UTC on 2026-10-04, "
                 "before the first run of the new day is published); the model_gem_global name is gone. The files are GRIB2, which this "
                 "workflow cannot decode without a dependency that pyproject.toml does not carry, so the GDPS "
                 "is read through the Open-Meteo forecast API instead."},
        {"name": "gefs_nomads", "url": "https://nomads.ncep.noaa.gov/cgi-bin/filter_gefs_atmos_0p50a.pl",
         "params": {}, "role": "NCEP GEFS through NOMADS"},
        {"name": "ec_ads", "url": "https://ads.atmosphere.copernicus.eu/", "params": {},
         "role": "the issue's 'EC ADS', read here as the Copernicus Atmosphere Data Store operated by ECMWF"},
        {"name": "ecmwf_open_data", "url": "https://data.ecmwf.int/forecasts/", "params": {},
         "role": "ECMWF open data, the other reading of 'EC ADS'"},
        {"name": "copernicus_cds", "url": "https://cds.climate.copernicus.eu/api/catalogue/v1/collections/reanalysis-era5-single-levels",
         "params": {}, "role": "Copernicus Climate Data Store, ERA5 single levels catalogue entry",
         "note": "Downloads need CDSAPI_KEY. Verified with a real download on 2026-10-04. A request for one quarter "
                 "of ten variables is refused with 'cost limits exceeded'; one month of ten variables is served."},
        {"name": "open_meteo_ensemble_gefs05", "url": ensemble,
         "params": {**point, "hourly": "visibility,wind_gusts_10m,cape,cloud_cover_low", "models": "gfs05",
                    "forecast_days": 1},
         "role": "NCEP GEFS ensemble, the second ensemble: the only open ensemble that carries visibility"},
        {"name": "nsf_ncar_era5_thredds",
         "url": "https://thredds.rda.ucar.edu/thredds/ncss/grid/files/g/d633000/e5.oper.an.sfc/202401/"
                "e5.oper.an.sfc.128_059_cape.ll025sc.2024010100_2024013123.nc/dataset.html",
         "params": {}, "role": "ERA5 CAPE without a key, NSF NCAR dataset d633000, NetCDF Subset Service",
         "note": "Answered 200 and served a month of hourly CAPE in 14 s on 2026-10-03; answered 503 for every "
                 "month on 2026-10-04. Publishes months late. ERA5 pressure-level winds took 57 s per level per "
                 "day there, which is why they are not used."},
        {"name": "eccc_climate_hourly", "url": "https://api.weather.gc.ca/collections/climate-hourly/items",
         "params": {"f": "json", "CLIMATE_IDENTIFIER": "8204495", "limit": 1,
                    "properties": "UTC_DATE,VISIBILITY"},
         "role": "hourly station observations; Port Hawkesbury is the visibility source of the archive"},
        {"name": "nrcan_geographical_names", "url": "https://geogratis.gc.ca/services/geoname/en/geonames.json",
         "params": {"q": "Canso", "province": "12"},
         "role": "coordinates of the communities named by the environmental assessment, for the direction sector"},
        {"name": "open_meteo_single_runs", "url": "https://single-runs-api.open-meteo.com/v1/forecast",
         "params": {**point, "hourly": "temperature_2m,visibility,cloud_cover_low,cape", "models": "gfs_seamless",
                    "run": "2026-09-20T00:00", "forecast_days": 2},
         "role": "archived individual GFS runs, the forecast source of the hindcast",
         "note": "Runs exist from 2026-04-02. No ensemble run is kept by this or by the ensemble API."},
        {"name": "open_meteo_previous_runs", "url": "https://previous-runs-api.open-meteo.com/v1/forecast",
         "params": {**point, "hourly": "temperature_2m_previous_day1,cloud_cover_low_previous_day1,"
                                       "visibility_previous_day1", "models": "gfs_seamless",
                    "start_date": "2025-01-10", "end_date": "2025-01-10"},
         "role": "lead-specific forecast archive, probed for the hindcast",
         "note": "Not used: low and mid-level cloud cover and visibility are null at lead 1 and beyond in all 15 "
                 "models probed."},
        {"name": "nomads_gefs_opendap", "url": "https://nomads.ncep.noaa.gov/dods/gefs", "params": {},
         "follow_redirects": False,
         "role": "NOAA's own decoder-free GEFS feed, probed as a single source for every field",
         "note": "Retired: 'OpenDAP format has been retired. Please see Service Change Notice 25-81'."},
        {"name": "canso_environmental_assessment",
         "url": "https://www.novascotia.ca/nse/EA/canso-spaceport-facility/Registration_document.pdf",
         "params": {}, "role": "the site-specific source of the criteria table and of the site configuration"},
    ]


def _coverage(body: dict) -> str:
    hourly = body.get("hourly", {})
    present, null = [], []
    bases = {}
    for key, values in hourly.items():
        if key == "time":
            continue
        base = key.split("_member")[0]
        bases.setdefault(base, []).extend(values)
    for base, values in bases.items():
        (null if all(v is None for v in values) else present).append(base)
    columns = len(hourly) - 1 if hourly else 0
    text = f"{columns} hourly columns; fields with data: {', '.join(present) or 'none'}"
    if null:
        text += f"; fields entirely null: {', '.join(null)}"
    return text


def run_probe(probe: dict, accessed: str) -> dict:
    record = {"name": probe["name"], "url": probe["url"], "params": probe["params"], "role": probe["role"],
              "accessed": accessed, "http_status": None, "bytes": None}
    try:
        response = httpx.get(probe["url"], params=probe["params"], timeout=60,
                             follow_redirects=probe.get("follow_redirects", True))
    except httpx.HTTPError as error:
        record["finding"] = f"No HTTP response: {type(error).__name__}."
        return record
    record["http_status"] = response.status_code
    record["bytes"] = len(response.content)
    finding = f"HTTP {response.status_code}."
    if response.status_code == 200 and "json" in response.headers.get("content-type", ""):
        try:
            body = response.json()
        except ValueError:
            body = None
        if isinstance(body, dict) and "hourly" in body:
            finding += " " + _coverage(body) + "."
        elif isinstance(body, dict) and "last_run_initialisation_time" in body:
            run = datetime.fromtimestamp(body["last_run_initialisation_time"], timezone.utc)
            finding += f" last_run_initialisation_time {run.strftime('%Y-%m-%dT%H:%MZ')}."
    if probe.get("note"):
        finding += " " + probe["note"]
    record["finding"] = finding
    return record


def main() -> None:
    site_cfg = config.load_site(SITE)
    accessed = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%MZ")
    results = [run_probe(probe, accessed) for probe in probes(site_cfg)]
    path = config.DATA_DIR / "sources.json"
    sources = json.loads(path.read_text(encoding="utf-8"))
    sources["probed_at"] = accessed
    sources["probes"] = results
    path.write_text(json.dumps(sources, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    for record in results:
        print(f"{record['name']:40s} {record['http_status']}  {record['finding'][:150]}")


if __name__ == "__main__":
    main()
