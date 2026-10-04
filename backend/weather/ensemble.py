"""Ensemble probability of a launchable day, spec II.21, and the horizon label of spec II.7.

P_forecast(L | d) = (1/N) * sum over members of 1{member satisfies every evaluated criterion over I(d)}.

A single deterministic run does not yield a probability. The rule chosen for that case (issue W3) is to return
no probability with the reason 'deterministic_only' and to let climatology carry the date. No 0 or 1 is made up.
"""

from __future__ import annotations

from datetime import date

from . import criteria
from .errors import WeatherDataError
from .fetch import parse_iso_z

FORECAST = "FORECAST"
CLIMATOLOGY = "CLIMATOLOGY"


def _no_probability(reason: str, dropped: int = 0) -> dict:
    return {"p_launch": None, "ensemble_size": None, "components": [], "reason": reason,
            "members_dropped": dropped}


def check_units(forecast_units: dict, rows: list[dict]) -> None:
    """Raise if a forecast field is not in the unit its criterion states. Values and limits must match."""
    for row in rows:
        unit = forecast_units.get(row["parameter"])
        if unit != row["unit"]:
            raise WeatherDataError(
                f"unit mismatch for {row['criterion_id']}: forecast {row['parameter']} is in {unit!r}, "
                f"the criterion limit is in {row['unit']!r}"
            )


def ensemble_probability(forecast: dict, window: list[str], rows: list[dict], min_members: int) -> dict:
    """Evaluate every member over the window and return p_launch, ensemble_size and per-criterion fractions.

    A member with a missing value inside the window is dropped and counted in members_dropped; it is never
    assumed to pass. If fewer than min_members remain, no probability is returned and 'reason' says why.
    """
    positions = {label: index for index, label in enumerate(forecast["times"])}
    if not window or any(label not in positions for label in window):
        return _no_probability("window_not_covered")
    check_units(forecast["units"], rows)
    indices = [positions[label] for label in window]

    verdicts = []
    dropped = 0
    for member in forecast["members"]:
        hours = [{row["parameter"]: member[row["parameter"]][index] for row in rows} for index in indices]
        if any(value is None for hour in hours for value in hour.values()):
            dropped += 1
            continue
        verdicts.append(criteria.window_violations(rows, hours))

    size = len(verdicts)
    if len(forecast["members"]) == 1:
        return _no_probability("deterministic_only", dropped)
    if size < min_members:
        return _no_probability("too_few_members", dropped)

    passing = sum(1 for verdict in verdicts if not any(verdict.values()))
    components = [
        {"criterion_id": row["criterion_id"],
         "p_violation": sum(1 for verdict in verdicts if verdict[row["criterion_id"]]) / size,
         "flag": row["flag"]}
        for row in rows
    ]
    return {"p_launch": passing / size, "ensemble_size": size, "components": components, "reason": None,
            "members_dropped": dropped}


def supplement_evaluation(forecast: dict, window: list[str], rows: list[dict], supplement_ids: list[str],
                          min_members: int) -> dict:
    """Evaluate the second ensemble, which carries the rows the primary ensemble cannot evaluate.

    rows are all rows this ensemble evaluates: the supplement rows and the rows both ensembles carry.
    only_supplement_violation is the fraction of members that satisfy every common row and violate a supplement
    row. components holds the plain violation fraction of each supplement row. Members with a missing value in
    the window are dropped and counted. No result is returned for a single run or for too few members.
    """
    empty = {"only_supplement_violation": None, "components": [], "ensemble_size": None, "members_dropped": 0}
    positions = {label: index for index, label in enumerate(forecast["times"])}
    if not window or any(label not in positions for label in window):
        return {**empty, "reason": "window_not_covered"}
    check_units(forecast["units"], rows)
    indices = [positions[label] for label in window]
    verdicts = []
    dropped = 0
    for member in forecast["members"]:
        hours = [{row["parameter"]: member[row["parameter"]][index] for row in rows} for index in indices]
        if any(value is None for hour in hours for value in hour.values()):
            dropped += 1
            continue
        verdicts.append(criteria.window_violations(rows, hours))
    size = len(verdicts)
    if len(forecast["members"]) == 1:
        return {**empty, "members_dropped": dropped, "reason": "deterministic_only"}
    if size < min_members:
        return {**empty, "members_dropped": dropped, "reason": "too_few_members"}
    wanted = set(supplement_ids)
    alone = sum(1 for verdict in verdicts
                if any(verdict[key] for key in wanted) and not any(v for key, v in verdict.items() if key not in wanted))
    components = [{"criterion_id": row["criterion_id"],
                   "p_violation": sum(1 for verdict in verdicts if verdict[row["criterion_id"]]) / size,
                   "flag": row["flag"]} for row in rows if row["criterion_id"] in wanted]
    return {"only_supplement_violation": alone / size, "components": components, "ensemble_size": size,
            "members_dropped": dropped, "reason": None}


def combine(primary_p_launch: float, only_supplement_violation: float) -> float:
    """Lower bound on the probability that every row holds, from two separate ensembles.

    P(A and B) = P(A) - P(A and not B) >= P(A) - P(common rows hold and not B). No dependence assumption is
    made, so the result can understate the launch probability and can never overstate it.
    """
    return max(0.0, primary_p_launch - only_supplement_violation)


def lead_days(day: date, forecast_issue_time: str) -> int:
    """Calendar days from the UTC date of the forecast issue time to the requested date."""
    return (day - parse_iso_z(forecast_issue_time).date()).days


def horizon_label(lead: int, max_forecast_lead_days: int) -> str:
    """FORECAST inside the configured skill horizon, CLIMATOLOGY outside it (and for dates before the issue)."""
    return FORECAST if 0 <= lead <= max_forecast_lead_days else CLIMATOLOGY
