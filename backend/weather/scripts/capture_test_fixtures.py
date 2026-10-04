"""Capture the Open-Meteo responses that the tests replay, so that no fixture is typed by hand.

    python -m backend.weather.scripts.capture_test_fixtures canso

Writes, under backend/weather/tests/fixtures/:
    open_meteo_forecast_canso.json   GFS deterministic forecast, 48 hours
    open_meteo_gdps_canso.json       ECCC GEM global deterministic forecast, 48 hours
    open_meteo_ensemble_canso.json   ECMWF IFS ensemble, 51 members, 72 hours
    open_meteo_gefs_ensemble_canso.json   NCEP GEFS ensemble, 31 members, 72 hours
    meta_<model>.json                the run-metadata response of each of the three models

Each source is asked for the fields its chain supplies for the current criteria version; the deterministic
forecasts also carry visibility and total cloud cover for the parsing tests. Each data window starts on the UTC date of the model run reported by the metadata, so the
fixtures stay consistent with their own issue times. Run from the repository root. Needs the network.
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import httpx

from backend.weather import config, fetch

FIXTURE_DIR = Path(__file__).resolve().parents[1] / "tests" / "fixtures"
EXTRA_DETERMINISTIC_FIELDS = ["visibility", "cloud_cover"]
CAPTURES = [
    ("open_meteo_gfs", "deterministic", "open_meteo_forecast_canso.json", 2, True),
    ("open_meteo_gdps", "deterministic", "open_meteo_gdps_canso.json", 2, True),
    ("open_meteo_ecmwf_ens", "ensemble", "open_meteo_ensemble_canso.json", 3, False),
    ("open_meteo_gefs_ens", "ensemble_supplement", "open_meteo_gefs_ensemble_canso.json", 3, False),
]


def main(site: str) -> None:
    site_cfg = config.load_site(site)
    sources = config.load_sources()["sources"]
    FIXTURE_DIR.mkdir(parents=True, exist_ok=True)
    reference_run = None
    with httpx.Client(timeout=90) as client:
        for source_id, chain, file_name, days, deterministic in CAPTURES:
            source = sources[source_id]
            fields = fetch.default_parameters(site, chain)
            meta = client.get(source["meta_url"]).raise_for_status().json()
            meta.pop("crs_wkt", None)
            model_name = source["meta_url"].split("/data/")[1].split("/")[0]
            (FIXTURE_DIR / f"meta_{model_name}.json").write_text(json.dumps(meta, indent=1) + "\n")
            run = datetime.fromtimestamp(meta["last_run_initialisation_time"], timezone.utc)
            if reference_run is None or datetime.now(timezone.utc) - run < timedelta(hours=48):
                reference_run = reference_run or run
                start = run.date()
            else:
                start = reference_run.date()   # stale metadata: use the first model's run date for the data window
            wanted = list(dict.fromkeys(fields + (EXTRA_DETERMINISTIC_FIELDS if deterministic else [])))
            params = {
                "latitude": site_cfg["latitude_deg"], "longitude": site_cfg["longitude_deg"],
                "hourly": ",".join(wanted), "models": source["model"],
                "start_date": start.isoformat(), "end_date": (start + timedelta(days=days - 1)).isoformat(),
                "timezone": "GMT",
            }
            body = client.get(source["url"], params=params).raise_for_status().json()
            text = json.dumps(body, indent=1) if deterministic else json.dumps(body, separators=(",", ":"))
            (FIXTURE_DIR / file_name).write_text(text + "\n")
            hourly = body["hourly"]
            empty = sorted({key.split("_member")[0] for key, values in hourly.items()
                            if key != "time" and all(value is None for value in values)})
            print(f"{file_name}: model run {run:%Y-%m-%dT%H:%MZ}, {len(hourly['time'])} hours from "
                  f"{hourly['time'][0]}, {len(hourly) - 1} columns, {len(text)} bytes, entirely null: {empty}")


if __name__ == "__main__":
    main(sys.argv[1])
