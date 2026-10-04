"""The date-resolved launch-weather probability P(L | d) in the shape of spec IV.3.

FORECAST: the requested date lies within the configured skill horizon of the forecast issue time and ensemble
members cover its evaluation window for every evaluated row. Rows on fields the primary ensemble does not carry
are evaluated on a second ensemble, and the two are combined by a rule that needs no assumption (see
ensemble.combine and data/sources.json, 'supplement').
CLIMATOLOGY: every other case, including a deterministic-only forecast, an outage with no snapshot, and a date
the ensembles do not cover. P is the archive frequency of the same event for that month (spec II.22).

A response never carries a null probability and never carries a row without data: if any evaluated row cannot be
computed from a forecast, the whole date is answered from climatology, where every row has data.
"""

from __future__ import annotations

from datetime import datetime, timezone

from . import climatology, config, criteria, ensemble, fetch
from .errors import WeatherDataError

_RESULTS: dict = {}


def clear_memo() -> None:
    """Forget every computed ensemble result."""
    _RESULTS.clear()


def _within_horizon(day, forecast: dict, max_lead: int) -> bool:
    lead = ensemble.lead_days(day, forecast["forecast_issue_time"])
    return ensemble.horizon_label(lead, max_lead) == ensemble.FORECAST


def _forecast_body(day, date_iso: str, site: str, site_cfg: dict, version: str, split: dict, now: datetime,
                   max_lead: int) -> dict | None:
    """The FORECAST fields of the response, or None when a forecast cannot evaluate every row."""
    sources = config.load_sources()
    minimum = sources["ensemble"]["min_members"]
    window = config.window_times(day, site_cfg)

    primary = fetch.fetch_forecast(site, "ensemble", criteria.required_parameters(split["primary"]), now)
    if primary is None or not _within_horizon(day, primary, max_lead):
        return None
    key = (site, primary["forecast_issue_time"], version, date_iso)
    if key not in _RESULTS:
        _RESULTS[key] = ensemble.ensemble_probability(primary, window, split["primary"], minimum)
    result = _RESULTS[key]
    complete_only = sources["ensemble"]["require_complete_members"]
    if result["p_launch"] is None or (complete_only and result["members_dropped"]):
        return None

    p_launch = result["p_launch"]
    size = result["ensemble_size"]
    components = {component["criterion_id"]: dict(component) for component in result["components"]}
    issue_time = primary["forecast_issue_time"]
    stored = primary["source"] == "snapshot_cache"

    if split["supplement_only"]:
        chain = sources["supplement"]["chain"]
        second = fetch.fetch_forecast(site, chain, criteria.required_parameters(split["supplement"]), now)
        if second is None or not _within_horizon(day, second, max_lead):
            return None
        second_key = (site, chain, second["forecast_issue_time"], version, date_iso)
        if second_key not in _RESULTS:
            _RESULTS[second_key] = ensemble.supplement_evaluation(
                second, window, split["supplement"],
                [row["criterion_id"] for row in split["supplement_only"]], minimum)
        extra = _RESULTS[second_key]
        if extra["only_supplement_violation"] is None or (complete_only and extra["members_dropped"]):
            return None
        p_launch = ensemble.combine(p_launch, extra["only_supplement_violation"])
        size += extra["ensemble_size"]
        components.update({component["criterion_id"]: dict(component) for component in extra["components"]})
        issue_time = min(issue_time, second["forecast_issue_time"])
        stored = stored or second["source"] == "snapshot_cache"

    return {"p_launch": p_launch,
            "horizon_label": ensemble.FORECAST,
            "forecast_issue_time": issue_time,
            "ensemble_size": size,
            "components": [components[row["criterion_id"]] for row in split["all"]],
            "source": "snapshot_cache" if stored else primary["source"]}


def _check(body: dict, rows: list[dict]) -> dict:
    """Refuse to return a response with a missing number or a missing row."""
    values = [body["p_launch"]] + [component["p_violation"] for component in body["components"]]
    if any(value is None or not 0.0 <= value <= 1.0 for value in values):
        raise WeatherDataError(f"the response for {body['date']} would carry a missing or out-of-range number")
    if [component["criterion_id"] for component in body["components"]] != [row["criterion_id"] for row in rows]:
        raise WeatherDataError(f"the response for {body['date']} would not carry one component per evaluated row")
    return body


def compute(date_iso: str, site: str, criteria_version: str | None = None, now: datetime | None = None) -> dict:
    """Return the GET /v1/weather/probability body for one date. ``now`` is injectable for tests.

    Raises ValueError for a malformed date, UnknownSiteError for an unconfigured site and
    CriteriaVersionMissingError for a criteria version with no table.
    """
    day = config.parse_date(date_iso)
    site_cfg = config.load_site(site)
    table = criteria.load_criteria(criteria_version)
    version = table["criteria_version"]
    split = climatology.split_rows(site, table)
    rows = split["all"]
    now = now or datetime.now(timezone.utc)
    max_lead = config.load_skill_horizon()["max_forecast_lead_days"]

    body = {"date": date_iso, "site": site, "criteria_version": version}

    # A forecast is issued no later than now, so a date further ahead than the horizon cannot be FORECAST.
    if (day - now.date()).days <= max_lead:
        forecast = _forecast_body(day, date_iso, site, site_cfg, version, split, now, max_lead)
        if forecast is not None:
            return _check({**body, **forecast}, rows)

    entry = climatology.daily_window(day.month, site, version)
    if entry["p_launch"] is None:
        raise WeatherDataError(f"the climatology for {site} has no sample for month {day.month}")
    return _check({**body,
                   "p_launch": entry["p_launch"],
                   "horizon_label": ensemble.CLIMATOLOGY,
                   "forecast_issue_time": None,
                   "ensemble_size": None,
                   "components": [{"criterion_id": row["criterion_id"],
                                   "p_violation": entry["p_violation"][row["criterion_id"]],
                                   "flag": row["flag"]} for row in rows],
                   "source": climatology.SOURCE}, rows)
