"""Climatological probability of a launchable hour or day from the ERA5 hourly archive (spec II.22).

P_clim(L | month, hour) is the fraction of historical hours in that month and UTC hour at which every
evaluated criterion held. The same criteria rows and the same evaluator as the forecast side are used, so the
climatology, the forecast and the verification outcome share one event definition.
"""

from __future__ import annotations

import csv
import gzip
import io
import json
from datetime import date, timedelta
from functools import lru_cache

from . import config, criteria, units
from .errors import WeatherDataError

SOURCE = "era5_climatology"


# The hourly archive ----------------------------------------------------------------------------------------

def archive_metadata(site: str) -> dict:
    """Provenance of the committed hourly archive: source, period, grid cell, units and checksum."""
    config.load_site(site)
    path = config.DATA_DIR / f"era5_{site}_hourly.meta.json"
    if not path.is_file():
        raise WeatherDataError(f"no hourly archive metadata for site {site!r} at {path}")
    return json.loads(path.read_text(encoding="utf-8"))


@lru_cache(maxsize=None)
def load_hourly_archive(site: str) -> dict:
    """The ERA5 hourly archive in evaluation units: times, columns per parameter, units and an index by time."""
    meta = archive_metadata(site)
    raw = gzip.decompress((config.DATA_DIR / meta["file"]).read_bytes()).decode("utf-8")
    reader = csv.reader(io.StringIO(raw))
    header = next(reader)
    fields = header[1:]
    target = {field: units.canonical_unit(meta["source_units"][field]) for field in fields}
    times: list[str] = []
    columns: dict[str, list] = {field: [] for field in fields}
    for record in reader:
        times.append(record[0])
        for field, text in zip(fields, record[1:]):
            value = None if text == "" else units.convert(float(text), meta["source_units"][field], target[field])
            columns[field].append(value)
    return {"times": times, "columns": columns, "units": target,
            "index": {label: position for position, label in enumerate(times)}, "meta": meta}


# Building --------------------------------------------------------------------------------------------------

def _entry(n: int, launchable: int, violated: dict[str, int], min_samples: int) -> dict:
    """One bin. A bin below the sample floor, or with a frequency of exactly 0 or 1, is flagged."""
    p_launch = launchable / n if n else None
    reasons = []
    if n < min_samples:
        reasons.append(f"n = {n} is below the floor of {min_samples} samples")
    if p_launch in (0.0, 1.0):
        reasons.append(f"empirical frequency is exactly {p_launch:g}, which a finite sample cannot establish")
    entry = {
        "n": n,
        "n_launchable": launchable,
        "p_launch": p_launch,
        "p_violation": {key: (count / n if n else None) for key, count in violated.items()},
        "low_confidence": bool(reasons),
    }
    if reasons:
        entry["flag_reason"] = "; ".join(reasons)
    return entry


def build_bins(archive: dict, rows: list[dict], site_cfg: dict, min_samples: int) -> dict:
    """Bin the archive by (month, UTC hour) and by month for the daily evaluation window.

    An hour with a missing value for any evaluated field is excluded and counted. A day with a missing value
    inside its window is excluded and counted.
    """
    for row in rows:
        if archive["units"].get(row["parameter"]) != row["unit"]:
            raise WeatherDataError(
                f"unit mismatch for {row['criterion_id']}: archive {row['parameter']} is in "
                f"{archive['units'].get(row['parameter'])!r}, the criterion limit is in {row['unit']!r}"
            )
    ids = [row["criterion_id"] for row in rows]
    times = archive["times"]
    columns = archive["columns"]
    index = archive.get("index") or {label: position for position, label in enumerate(times)}

    def hour_values(position: int) -> dict:
        return {row["parameter"]: columns[row["parameter"]][position] for row in rows}

    counts = {(month, hour): [0, 0, dict.fromkeys(ids, 0)] for month in range(1, 13) for hour in range(24)}
    excluded_hours = 0
    for position, label in enumerate(times):
        verdict = criteria.window_violations(rows, [hour_values(position)])
        if any(v is None for v in verdict.values()):
            excluded_hours += 1
            continue
        cell = counts[(int(label[5:7]), int(label[11:13]))]
        cell[0] += 1
        cell[1] += not any(verdict.values())
        for key in ids:
            cell[2][key] += verdict[key]

    daily = {month: [0, 0, dict.fromkeys(ids, 0)] for month in range(1, 13)}
    excluded_days = 0
    days_total = 0
    if times:
        day = date.fromisoformat(times[0][:10])
        last = date.fromisoformat(times[-1][:10])
        while day <= last:
            labels = config.window_times(day, site_cfg)
            if all(label in index for label in labels):
                days_total += 1
                verdict = criteria.window_violations(rows, [hour_values(index[label]) for label in labels])
                if any(v is None for v in verdict.values()):
                    excluded_days += 1
                else:
                    cell = daily[day.month]
                    cell[0] += 1
                    cell[1] += not any(verdict.values())
                    for key in ids:
                        cell[2][key] += verdict[key]
            day += timedelta(days=1)

    return {
        "bins": [{"month": month, "hour_utc": hour, **_entry(*counts[(month, hour)], min_samples)}
                 for month in range(1, 13) for hour in range(24)],
        "daily_window": [{"month": month, **_entry(*daily[month], min_samples)} for month in range(1, 13)],
        "hours_total": len(times),
        "hours_excluded_missing": excluded_hours,
        "days_total": days_total,
        "days_excluded_missing": excluded_days,
    }


def evaluated_rows(site: str, table: dict) -> list[dict]:
    """The criteria rows that enter P(L|d) for a site: those whose field the hourly archive carries.

    The forecast side evaluates exactly these rows, so forecast, climatology and verification share one event.
    """
    return criteria.rows_with_fields(table, load_hourly_archive(site)["columns"])


def split_rows(site: str, table: dict) -> dict[str, list[dict]]:
    """How the evaluated rows are divided between the two forecast ensembles (data/sources.json, 'supplement').

    'all' is every evaluated row. 'primary' is what the primary ensemble evaluates: every row except those on a
    supplement field. 'supplement_only' is the rows on a supplement field. 'supplement' is what the second
    ensemble evaluates: the supplement rows plus every row whose field both ensembles carry.
    """
    rows = evaluated_rows(site, table)
    settings = config.load_sources()["supplement"]
    supplement_fields = set(settings["fields"])
    primary_only = set(settings["primary_only_fields"])
    supplement_only = [row for row in rows if row["parameter"] in supplement_fields]
    return {
        "all": rows,
        "primary": [row for row in rows if row["parameter"] not in supplement_fields],
        "supplement_only": supplement_only,
        "supplement": [row for row in rows if row["parameter"] not in primary_only] if supplement_only else [],
    }


def not_evaluable(site: str, table: dict) -> list[dict]:
    """The criteria rows that cannot be evaluated for a site, each with the reason."""
    archive = load_hourly_archive(site)
    acquisition = archive["meta"]["acquisition"]
    return [{"criterion_id": row["criterion_id"], "parameter": row["parameter"],
             "reason": f"no field '{row['parameter']}' in the hourly archive (acquisition: {acquisition})"}
            for row in table["criteria"] if row["parameter"] not in archive["columns"]]


def build_climatology(site: str, table: dict, generated_at: str) -> dict:
    """The full climatology document for one site and criteria version, with provenance."""
    site_cfg = config.load_site(site)
    archive = load_hourly_archive(site)
    meta = archive["meta"]
    rows = evaluated_rows(site, table)
    sources = config.load_sources()
    settings = sources["climatology"]
    period = sources["climatology_archive"]
    start = f"{period['first_year']}-01-01T00:00"
    end = f"{period['last_year']}-12-31T23:00"
    if start not in archive["index"] or end not in archive["index"]:
        raise WeatherDataError(f"the hourly archive does not cover the climatology period {start} to {end}")
    first, last = archive["index"][start], archive["index"][end] + 1
    span = {"times": archive["times"][first:last], "units": archive["units"],
            "columns": {field: column[first:last] for field, column in archive["columns"].items()}}
    built = build_bins(span, rows, site_cfg, settings["min_samples_per_bin"])
    return {
        "site": site,
        "source": SOURCE,
        "source_description": meta["source"],
        "archive_acquisition": meta["acquisition"],
        "field_sources": meta["field_sources"],
        "gap_filled": {field: {"hours": gap["hours"], "source": gap["source"]}
                       for field, gap in meta.get("gap_filled", {}).items()},
        "missing_values": meta["missing_values"],
        "period_start": start[:10],
        "period_end": end[:10],
        "archive_period": {"start": meta["period_start"], "end": meta["period_end"]},
        "criteria_version_used": table["criteria_version"],
        "generated_at": generated_at,
        "generated_by": f"python -m backend.weather.scripts.build_climatology {site}",
        "archive_file": meta["file"],
        "archive_sha256": meta["csv_sha256"],
        "archive_retrieved_at": meta["retrieved_at"],
        "grid_cell": meta["grid_cell"],
        "hour_basis": "UTC",
        "min_samples_per_bin": settings["min_samples_per_bin"],
        "method": (
            "bins: for each (month, UTC hour), n is the number of archive hours with every evaluated field "
            "present, and p_launch is the fraction of them at which no evaluated criterion was violated. "
            "daily_window: for each month, n is the number of local days whose whole evaluation window is "
            "present, and p_launch is the fraction of them with no violation at any window hour, which is the "
            "event L(d) the forecast evaluates. p_violation is the per-criterion violation frequency. A bin is "
            "flagged low_confidence when n is below min_samples_per_bin or when the frequency is exactly 0 or 1."
        ),
        "evaluation_window_local": site_cfg["evaluation_window_local"],
        "criteria_evaluated": [row["criterion_id"] for row in rows],
        "criteria_not_evaluable": not_evaluable(site, table),
        **built,
    }


# Reading ---------------------------------------------------------------------------------------------------

@lru_cache(maxsize=None)
def load_climatology(site: str) -> dict:
    """The committed climatology file for a site (data/climatology_<site>.json)."""
    config.load_site(site)
    path = config.DATA_DIR / f"climatology_{site}.json"
    if not path.is_file():
        raise WeatherDataError(f"no climatology file for site {site!r} at {path}")
    return json.loads(path.read_text(encoding="utf-8"))


@lru_cache(maxsize=None)
def _for_version(site: str, criteria_version: str) -> dict:
    committed = load_climatology(site)
    if committed["criteria_version_used"] == criteria_version:
        return committed
    table = criteria.load_criteria(criteria_version)
    return build_climatology(site, table, generated_at="built on request from the hourly archive")


def climatology_table(site: str, criteria_version: str | None = None) -> dict:
    """The climatology for a criteria version: the committed file if it matches, else built from the archive."""
    return _for_version(site, criteria.canonical_version(criteria_version))


def climatology(month: int, hour: int, site: str = "canso", criteria_version: str | None = None) -> dict:
    """P(L | month, hour): one bin, with n, p_launch, p_violation and low_confidence. The hour is UTC."""
    if not isinstance(month, int) or not 1 <= month <= 12:
        raise ValueError(f"month must be 1 to 12, got {month!r}")
    if not isinstance(hour, int) or not 0 <= hour <= 23:
        raise ValueError(f"hour must be 0 to 23 (UTC), got {hour!r}")
    table = climatology_table(site, criteria_version)
    return next(entry for entry in table["bins"] if entry["month"] == month and entry["hour_utc"] == hour)


def daily_window(month: int, site: str = "canso", criteria_version: str | None = None) -> dict:
    """P(L | month) for the daily evaluation window, the event the forecast side evaluates."""
    table = climatology_table(site, criteria_version)
    return next(entry for entry in table["daily_window"] if entry["month"] == month)


# The contract names both a module climatology.py and an exported function climatology(). A package attribute
# can hold only one of them, so this module is made callable: backend.weather.climatology(month, hour) returns
# the bin, and backend.weather.climatology.build_bins and the other functions stay reachable as usual.
import sys as _sys
import types as _types


class _CallableModule(_types.ModuleType):
    def __call__(self, month: int, hour: int, site: str = "canso", criteria_version: str | None = None) -> dict:
        return climatology(month, hour, site, criteria_version)


_sys.modules[__name__].__class__ = _CallableModule
