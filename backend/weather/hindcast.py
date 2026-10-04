"""Hindcast of the launch-weather probability: Brier score, skill against climatology, reliability (spec III.4).

Scoring formulas (spec II.24, II.25):

    BS  = (1/M) * sum (p_m - o_m)^2,  o_m in {0, 1}
    BSS = 1 - BS / BS_ref,            BS_ref computed with p_m = base rate of the sample

The scoring functions in this first part are pure: no file, no network.
"""

from __future__ import annotations

Pair = tuple[float, int]


def brier_score(pairs: list[Pair]) -> float:
    """Mean squared difference between forecast probability and outcome. Undefined for an empty sample."""
    if not pairs:
        raise ValueError("the Brier score of an empty sample is undefined")
    return sum((p - o) ** 2 for p, o in pairs) / len(pairs)


def base_rate(pairs: list[Pair]) -> float:
    """The observed frequency of the event in the sample."""
    if not pairs:
        raise ValueError("the base rate of an empty sample is undefined")
    return sum(o for _, o in pairs) / len(pairs)


def reference_brier_score(pairs: list[Pair]) -> float:
    """The Brier score of the forecast that always issues the base rate of this same sample."""
    rate = base_rate(pairs)
    return sum((rate - o) ** 2 for _, o in pairs) / len(pairs)


def brier_skill_score(bs: float, bs_ref: float) -> float | None:
    """1 - BS / BS_ref. Negative when the forecast is worse than the reference; never clipped.

    None when the reference score is zero, which happens only when the event always or never occurred in the
    sample: the base-rate forecast is then perfect and no skill ratio exists.
    """
    if bs_ref == 0:
        return None
    return 1.0 - bs / bs_ref


def reliability_bins(pairs: list[Pair], n_bins: int = 10) -> list[dict]:
    """Equal-width bins over [0, 1]: centre, observed frequency of the event, and count.

    A probability on a bin edge belongs to the upper bin, and 1.0 belongs to the last bin. Bins that hold no
    forecast are left out: an empty bin has no observed frequency, and showing one as 0 would be false.
    """
    counts = [0] * n_bins
    events = [0] * n_bins
    for p, o in pairs:
        index = min(int(p * n_bins), n_bins - 1)
        counts[index] += 1
        events[index] += o
    return [{"p_center": (index + 0.5) / n_bins, "observed_freq": events[index] / counts[index], "n": counts[index]}
            for index in range(n_bins) if counts[index] > 0]


def roc_points(pairs: list[Pair], thresholds: list[float]) -> list[dict]:
    """Probability of detection and false-alarm rate of the decision 'forecast yes when p >= threshold'.

    pod = hits / (hits + misses). far = false alarms / (false alarms + correct negatives), the false-alarm rate
    of the ROC curve. A threshold for which either rate is undefined is left out.
    """
    points = []
    for threshold in thresholds:
        hits = sum(1 for p, o in pairs if p >= threshold and o == 1)
        misses = sum(1 for p, o in pairs if p < threshold and o == 1)
        false_alarms = sum(1 for p, o in pairs if p >= threshold and o == 0)
        correct_negatives = sum(1 for p, o in pairs if p < threshold and o == 0)
        if hits + misses == 0 or false_alarms + correct_negatives == 0:
            continue
        points.append({"threshold": threshold, "pod": hits / (hits + misses),
                       "far": false_alarms / (false_alarms + correct_negatives)})
    return points


# The forecast archive, the loop and the response ------------------------------------------------------------

import csv
import gzip
import hashlib
import io
import json
from datetime import date, timedelta
from pathlib import Path

from . import climatology, config, criteria, ensemble, observations, units
from .errors import WeatherDataError

HINDCAST_DIR = config.DATA_DIR / "hindcast"
CACHE_DIR = Path(__file__).resolve().parent / "cache" / "hindcast"
VERIFICATION_SOURCE = "era5"
REFERENCE_FORECAST = "climatology_base_rate"


def parse_runs(text: str, source_units: dict[str, str]) -> dict:
    """Parse the forecast archive into records of (issue_time, valid_time, fields) in evaluation units.

    An empty cell is a missing value and stays None; it is never read as zero.
    """
    reader = csv.reader(io.StringIO(text))
    header = next(reader)
    fields = header[2:]
    target = {field: units.canonical_unit(source_units[field]) for field in fields}
    records = []
    for line in reader:
        values = {}
        for field, cell in zip(fields, line[2:]):
            values[field] = None if cell == "" else units.convert(float(cell), source_units[field], target[field])
        records.append({"issue_time": line[0], "valid_time": line[1], "fields": values})
    return {"records": records, "units": target}


def index_runs(records: list[dict]) -> dict[str, dict[str, dict]]:
    """Records grouped as {issue_time: {valid_time: fields}}."""
    by_run: dict[str, dict[str, dict]] = {}
    for record in records:
        by_run.setdefault(record["issue_time"], {})[record["valid_time"]] = record["fields"]
    return by_run


def source_metadata(site: str) -> dict:
    """Where the forecast archive came from, when, and what it lacks (data/hindcast/source.json)."""
    path = HINDCAST_DIR / "source.json"
    if not path.is_file():
        raise WeatherDataError(f"no forecast archive metadata at {path}; run fetch_hindcast_runs first")
    meta = json.loads(path.read_text(encoding="utf-8"))
    if meta["site"] != site:
        raise WeatherDataError(f"the forecast archive is for site {meta['site']!r}, not {site!r}")
    return meta


def load_runs(site: str) -> dict:
    """The committed forecast archive of a site, parsed, with its metadata."""
    meta = source_metadata(site)
    raw = gzip.decompress((HINDCAST_DIR / meta["file"]).read_bytes()).decode("utf-8")
    parsed = parse_runs(raw, meta["source_units"])
    return {**parsed, "by_run": index_runs(parsed["records"]), "meta": meta}


def _issue_dates(first: date, last: date) -> list[date]:
    return [first + timedelta(days=offset) for offset in range((last - first).days + 1)]


def coverage(by_run: dict, run_hours: list[int], first: date, last: date) -> dict:
    """How complete the forecast archive is over a range of issue dates. Gaps are counted, not hidden."""
    incomplete, missing_runs = [], 0
    days = _issue_dates(first, last)
    for day in days:
        absent = [hour for hour in run_hours if f"{day.isoformat()}T{hour:02d}:00" not in by_run]
        missing_runs += len(absent)
        if absent:
            incomplete.append(day.isoformat())
    return {"issue_dates_expected": len(days), "issue_dates_complete": len(days) - len(incomplete),
            "runs_expected": len(days) * len(run_hours), "runs_missing": missing_runs,
            "issue_dates_incomplete": incomplete}


def build_pairs(by_run: dict, field_units: dict, site_cfg: dict, rows: list[dict], issue_dates: list[date],
                lead_max: int, run_hours: list[int], min_members: int, outcome) -> dict:
    """One (p, o) pair per issue date and lead.

    p is the fraction of the runs of the issue date that satisfy every criterion over the evaluation window of
    the valid date, computed by ensemble.ensemble_probability, the function the operational layer uses. o is
    outcome(valid_date): 1, 0, or None when the observation is missing. A pair is produced only when every run
    of the issue date exists, no run has a missing value in the window, and the outcome is known; every other
    case is counted under 'excluded'.
    """
    pairs = []
    excluded = {"issue_date_without_every_run": 0, "forecast_with_missing_value": 0, "outcome_missing": 0}
    parameters = criteria.required_parameters(rows)
    for day in issue_dates:
        runs = [by_run.get(f"{day.isoformat()}T{hour:02d}:00") for hour in run_hours]
        if any(run is None for run in runs):
            excluded["issue_date_without_every_run"] += 1
            continue
        for lead in range(1, lead_max + 1):
            valid = day + timedelta(days=lead)
            window = config.window_times(valid, site_cfg)
            members = [{parameter: [run.get(label, {}).get(parameter) for label in window]
                        for parameter in parameters} for run in runs]
            forecast = {"times": window, "members": members, "units": field_units}
            result = ensemble.ensemble_probability(forecast, window, rows, min_members)
            if result["p_launch"] is None or result["members_dropped"]:
                excluded["forecast_with_missing_value"] += 1
                continue
            observed = outcome(valid.isoformat())
            if observed is None:
                excluded["outcome_missing"] += 1
                continue
            pairs.append({"issue_date": day.isoformat(), "lead_time_days": lead, "valid_date": valid.isoformat(),
                          "p": result["p_launch"], "o": observed})
    return {"pairs": pairs, "excluded": excluded}


def _scores(sample: list[Pair]) -> dict:
    if not sample:
        return {"bs": None, "bs_ref": None, "bss": None, "n_cases": 0}
    bs, bs_ref = brier_score(sample), reference_brier_score(sample)
    return {"bs": bs, "bs_ref": bs_ref, "bss": brier_skill_score(bs, bs_ref), "n_cases": len(sample)}


def _mean_forecast_by_bin(pairs: list[Pair], n_bins: int) -> list[dict]:
    """For each populated reliability bin: the mean forecast probability of the pairs in it."""
    totals: dict[int, list[float]] = {}
    for p, _ in pairs:
        totals.setdefault(min(int(p * n_bins), n_bins - 1), []).append(p)
    return [{"p_center": (index + 0.5) / n_bins, "mean_forecast": sum(values) / len(values)}
            for index, values in sorted(totals.items())]


def measured_horizon(skill_series: list[dict]) -> int | None:
    """The last lead of the unbroken run of leads, starting at lead 1, whose skill is above zero. None if none."""
    horizon = None
    for entry in sorted(skill_series, key=lambda item: item["lead_time_days"]):
        if entry["bss"] is None or entry["bss"] <= 0:
            break
        horizon = entry["lead_time_days"]
    return horizon


def score(pairs: list[dict], lead_max: int, members: int, n_bins: int) -> dict:
    """Skill by lead, base rate, reliability bins and ROC points from the pair rows.

    The reference of each lead is the base rate of that lead's own sample. The base rate reported at the top is
    the launchable fraction of the verified days, each day counted once however many leads verify it. The
    reliability bins and ROC points pool every lead; the ROC thresholds are the possible member fractions.
    """
    series = []
    for lead in range(1, lead_max + 1):
        sample = [(row["p"], row["o"]) for row in pairs if row["lead_time_days"] == lead]
        series.append({"lead_time_days": lead, **_scores(sample)})
    days = {row["valid_date"]: row["o"] for row in pairs}
    pooled = [(row["p"], row["o"]) for row in pairs]
    return {
        "skill_series": series,
        "base_rate": sum(days.values()) / len(days) if days else None,
        "verified_days": len(days),
        "reliability_bins": reliability_bins(pooled, n_bins),
        "reliability_mean_forecast": _mean_forecast_by_bin(pooled, n_bins),
        "roc_points": roc_points(pooled, [number / members for number in range(1, members + 1)]),
        "skill_horizon_measured_days": measured_horizon(series),
    }


def load_inputs(site: str, criteria_version: str) -> dict:
    """Everything compute() needs: the forecast archive, the evaluated rows, the outcome function, the settings."""
    sources = config.load_sources()
    settings = sources["hindcast"]
    table = criteria.load_criteria(criteria_version)
    runs = load_runs(site)
    archive_meta = climatology.archive_metadata(site)
    constants = json.loads((config.DATA_DIR / "constants_block.json").read_text(encoding="utf-8"))
    return {
        "by_run": runs["by_run"],
        "units": runs["units"],
        "site_cfg": config.load_site(site),
        "rows": climatology.evaluated_rows(site, table),
        "run_hours": settings["forecast_source"]["run_hours_utc"],
        "min_members": sources["ensemble"]["min_members"],
        "outcome": lambda day: observations.observed_launchable(day, criteria_version, site),
        "n_bins": settings["reliability_bins"],
        "aggregate_leads": settings["aggregate_leads"],
        "forecast_source": runs["meta"]["forecast_source_id"],
        "verification_source": VERIFICATION_SOURCE,
        "fingerprint": f"runs:{runs['meta']['csv_sha256']} archive:{archive_meta['csv_sha256']}",
        "criteria_sha256": hashlib.sha256(
            (config.DATA_DIR / f"{criteria_version}.json").read_bytes()).hexdigest(),
        "constants_block": {key: value for key, value in constants.items() if not key.startswith("_")},
    }


def compute(period_start: str, period_end: str, lead_max: int = 10, site: str = "canso",
            criteria_version: str | None = None) -> dict:
    """Run the hindcast over the issue dates period_start to period_end and return the full result.

    The result is cached on disk under a key of period, lead_max, site, criteria version, forecast source,
    verification source and the checksums of the two data files. An unchanged key is answered from disk.
    """
    first, last = config.parse_date(period_start), config.parse_date(period_end)
    if last < first:
        raise ValueError("period_end is before period_start")
    if lead_max < 1:
        raise ValueError("lead_max must be at least 1")
    version = criteria_version or criteria.current_criteria_version()
    inputs = load_inputs(site, version)
    key = {"period_start": period_start, "period_end": period_end, "lead_max": lead_max, "site": site,
           "criteria_version": version, "forecast_source": inputs["forecast_source"],
           "verification_source": inputs["verification_source"], "fingerprint": inputs["fingerprint"]}
    digest = hashlib.sha256(json.dumps(key, sort_keys=True).encode("utf-8")).hexdigest()
    path = CACHE_DIR / f"{digest[:16]}.json"
    if path.is_file():
        stored = json.loads(path.read_text(encoding="utf-8"))
        if stored.get("key") == key:
            return stored["result"]

    built = build_pairs(inputs["by_run"], inputs["units"], inputs["site_cfg"], inputs["rows"],
                        _issue_dates(first, last), lead_max, inputs["run_hours"], inputs["min_members"],
                        inputs["outcome"])
    scored = score(built["pairs"], lead_max, len(inputs["run_hours"]), inputs["n_bins"])
    aggregate = None
    if inputs.get("aggregate_leads"):
        low, high = inputs["aggregate_leads"]
        sample = [(row["p"], row["o"]) for row in built["pairs"] if low <= row["lead_time_days"] <= high]
        aggregate = {"leads": [low, high], **_scores(sample)}
    result = {
        "period": {"start": period_start, "end": period_end},
        "lead_max": lead_max,
        "site": site,
        "criteria_version": version,
        "criteria_sha256": inputs.get("criteria_sha256"),
        "criteria_evaluated": [row["criterion_id"] for row in inputs["rows"]],
        "forecast_source": inputs["forecast_source"],
        "verification_source": inputs["verification_source"],
        "reference_forecast": REFERENCE_FORECAST,
        "members_per_issue_date": len(inputs["run_hours"]),
        "coverage": coverage(inputs["by_run"], inputs["run_hours"], first, last),
        "excluded": built["excluded"],
        "pairs": built["pairs"],
        **scored,
        "aggregate": aggregate,
        "constants_block": {**inputs["constants_block"],
                            "citation_id": f"run_{period_end.replace('-', '')}_hindcast_{digest[:8]}"},
    }
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"key": key, "result": result}, separators=(",", ":")), encoding="utf-8")
    return result


def longest_period(site: str) -> tuple[str, str]:
    """The first and last issue date the committed data supports: from the first archived run to the last run
    whose lead-1 valid date is still inside the hourly archive."""
    runs = source_metadata(site)
    archive_end = date.fromisoformat(climatology.archive_metadata(site)["period_end"][:10])
    first = date.fromisoformat(runs["coverage"]["first_run"][:10])
    last = min(date.fromisoformat(runs["coverage"]["last_run"][:10]), archive_end - timedelta(days=1))
    return first.isoformat(), last.isoformat()


def observed_violation_frequency(site: str, criteria_version: str, valid_dates: list[str]) -> dict[str, float]:
    """Per criterion: the fraction of the given days on which the observed fields violated it in the window."""
    archive = climatology.load_hourly_archive(site)
    site_cfg = config.load_site(site)
    rows = climatology.evaluated_rows(site, criteria.load_criteria(criteria_version))
    counts = {row["criterion_id"]: 0 for row in rows}
    for day in valid_dates:
        labels = config.window_times(config.parse_date(day), site_cfg)
        hours = [{row["parameter"]: archive["columns"][row["parameter"]][archive["index"][label]] for row in rows}
                 for label in labels]
        for key, violated in criteria.window_violations(rows, hours).items():
            counts[key] += bool(violated)
    return {key: count / len(valid_dates) for key, count in counts.items()} if valid_dates else {}


def response(result: dict) -> dict:
    """The GET /v1/validation/skill body (spec IV.4) from a hindcast result.

    Raises WeatherDataError if a lead has no pair or no defined skill: the caller must then narrow lead_max
    explicitly. A lead is never padded.
    """
    for entry in result["skill_series"]:
        if entry["n_cases"] == 0 or entry["bss"] is None:
            raise WeatherDataError(
                f"lead {entry['lead_time_days']} has {entry['n_cases']} usable cases and no defined skill for the "
                f"period {result['period']['start']} to {result['period']['end']}; narrow lead_max")
    return {
        "period": result["period"],
        "verification_source": result["verification_source"],
        "reference_forecast": result["reference_forecast"],
        "base_rate": result["base_rate"],
        "skill_series": result["skill_series"],
        "reliability_bins": result["reliability_bins"],
        "roc_points": result["roc_points"],
        "skill_horizon_measured_days": result["skill_horizon_measured_days"],
        "constants_block": result["constants_block"],
    }


def hindcast(period_start: str, period_end: str, lead_max: int = 10) -> dict:
    """Returns the GET /v1/validation/skill body (spec IV.4). Heavy; cached to disk.

    period_start and period_end are the first and last forecast issue dates, YYYY-MM-DD.
    """
    return response(compute(period_start, period_end, lead_max))


# The contract names both a module hindcast.py and an exported function hindcast(). A package attribute can hold
# only one of them, so this module is made callable, as climatology.py is: backend.weather.hindcast(start, end)
# returns the response, and backend.weather.hindcast.brier_score and the other functions stay reachable.
import sys as _sys
import types as _types


class _CallableModule(_types.ModuleType):
    def __call__(self, period_start: str, period_end: str, lead_max: int = 10) -> dict:
        return hindcast(period_start, period_end, lead_max)


_sys.modules[__name__].__class__ = _CallableModule
