"""Download the archived forecast runs the hindcast verifies and write them to data/hindcast/.

    python -m backend.weather.scripts.fetch_hindcast_runs canso [--last-date YYYY-MM-DD]

Writes:
    data/hindcast/runs_<site>.csv.gz   one row per (run, valid hour): the fields every criterion needs, as served
    data/hindcast/source.json          source, access date, coverage, units and every run the archive lacks

Only the hours of the evaluation window of each valid date, leads 1 to the configured maximum, are kept. A run the
archive does not hold is recorded as missing, never interpolated. Run from the repository root. Needs the network.
"""

from __future__ import annotations

import argparse
import csv
import gzip
import hashlib
import io
import json
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta, timezone

import httpx

from backend.weather import climatology, config, criteria
from backend.weather.errors import WeatherDataError

NOT_AVAILABLE = "model run is not available"


def fetch_run(client: httpx.Client, source: dict, site_cfg: dict, fields: list[str], run: str) -> dict | None:
    """One archived run as an Open-Meteo payload, or None when the archive does not hold it."""
    params = {"latitude": site_cfg["latitude_deg"], "longitude": site_cfg["longitude_deg"],
              "hourly": ",".join(fields), "models": source["model"], "run": run,
              "forecast_days": source["forecast_days"], "timezone": "GMT"}
    problem = "no attempt made"
    for attempt in range(5):
        try:
            response = client.get(source["url"], params=params)
        except httpx.HTTPError as error:
            problem = type(error).__name__
        else:
            if response.status_code == 200:
                return response.json()
            if response.status_code == 400 and NOT_AVAILABLE in response.text:
                return None
            problem = f"HTTP {response.status_code}"
        time.sleep(20 * (attempt + 1) if "429" in problem else 3 * (attempt + 1))
    raise WeatherDataError(f"run {run} could not be fetched after 5 attempts: {problem}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("site")
    parser.add_argument("--last-date", help="last issue date to fetch; default: the last day of the hourly archive")
    arguments = parser.parse_args()

    site_cfg = config.load_site(arguments.site)
    settings = config.load_sources()["hindcast"]
    source = settings["forecast_source"]
    lead_max = config.load_skill_horizon()["max_forecast_lead_days"]
    table = criteria.load_criteria(None)
    fields = criteria.required_parameters(table["criteria"])
    first = date.fromisoformat(source["first_run_date"])
    archive_end = date.fromisoformat(climatology.archive_metadata(arguments.site)["period_end"][:10])
    last = date.fromisoformat(arguments.last_date) if arguments.last_date else archive_end

    runs = []
    day = first
    while day <= last:
        runs += [f"{day.isoformat()}T{hour:02d}:00" for hour in source["run_hours_utc"]]
        day += timedelta(days=1)

    with httpx.Client(timeout=90) as client:
        with ThreadPoolExecutor(max_workers=4) as pool:
            payloads = list(pool.map(lambda run: fetch_run(client, source, site_cfg, fields, run), runs))

    rows, missing, units = [], [], {}
    for run, payload in zip(runs, payloads):
        if payload is None:
            missing.append(run)
            continue
        hourly = payload["hourly"]
        units = {field: payload["hourly_units"][field] for field in fields}
        position = {label: index for index, label in enumerate(hourly["time"])}
        issue = date.fromisoformat(run[:10])
        for lead in range(1, lead_max + 1):
            for label in config.window_times(issue + timedelta(days=lead), site_cfg):
                if label in position:
                    rows.append([run, label] + [hourly[field][position[label]] for field in fields])

    text = io.StringIO()
    writer = csv.writer(text, lineterminator="\n")
    writer.writerow(["run_time_utc", "valid_time_utc"] + fields)
    for row in rows:
        writer.writerow(["" if value is None else value for value in row])
    raw = text.getvalue().encode("utf-8")
    directory = config.DATA_DIR / "hindcast"
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"runs_{arguments.site}.csv.gz"
    with open(path, "wb") as handle:
        with gzip.GzipFile(filename="", mode="wb", fileobj=handle, mtime=0) as zipped:
            zipped.write(raw)

    nulls = {field: sum(1 for row in rows if row[2 + index] is None) for index, field in enumerate(fields)}
    meta = {
        "site": arguments.site,
        "forecast_source_id": source["id"],
        "description": source["description"],
        "url": source["url"],
        "model": source["model"],
        "licence": source["licence"],
        "accessed": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%MZ"),
        "coverage": {
            "first_run": runs[0], "last_run": runs[-1],
            "runs_expected": len(runs), "runs_present": len(runs) - len(missing),
            "runs_missing": missing,
            "archive_start_note": source["first_run_date_note"],
        },
        "lead_days_kept": [1, lead_max],
        "hours_kept": "the evaluation window of each valid date, " + json.dumps(site_cfg["evaluation_window_local"]["use"]),
        "fields": fields,
        "source_units": units,
        "missing_values": nulls,
        "rows": len(rows),
        "csv_sha256": hashlib.sha256(raw).hexdigest(),
        "file": path.name,
    }
    (directory / "source.json").write_text(json.dumps(meta, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"wrote {path.name}: {len(rows)} rows from {meta['coverage']['runs_present']} of {len(runs)} runs, "
          f"{runs[0]} to {runs[-1]}; missing runs: {missing}; missing values: {nulls}")


if __name__ == "__main__":
    main()
