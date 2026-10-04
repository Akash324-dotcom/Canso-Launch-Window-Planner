"""The opportunity-process decision layer of spec II.9 (iv): expected delay and its cost.

Status: SKETCHED, as the spec marks it. This is a counting argument on independent
daily success probabilities, not a queueing-theorem result. It does not enter the
window equation, ``p_success`` or any ranking; it only summarises the p-series the
engine already produced.

Model. The engine emits one decision per day, taken at the best opportunity of that
day, and the decision succeeds with probability ``p_k`` (II.23). Successes are
independent across days (assumption). Let ``T`` be the index of the first success,
counted from 1 for the first opportunity. The survival expansion is

    E[T] = sum_{j >= 0} P(T > j) = sum_{j >= 0} prod_{s = 1..j} (1 - p_s)

A launch that succeeds at the first opportunity has ``T = 1``, which is the nominal
plan, so the expected number of EXTRA days is

    E[T] - 1 = sum_{j >= 1} prod_{s = 1..j} (1 - p_s)

and the expected cost relative to the nominal plan is ``C_day * (E[T] - 1)`` (II.28).
With a constant ``p`` the sum is ``(1 - p) / p``, the mean of a geometric tail, which
is checked in the tests.

Note on (II.27) as printed in the spec. It writes the summand as
``1 - prod (1 - p)``, which is ``P(T <= j)`` and not ``P(T > j)``. With a constant
``p`` that form grows without bound as the horizon grows (about N - 1/p), so it
cannot be the expected time to next success. The survival form above is the one
whose constant-``p`` case reproduces the geometric mean ``1/p``, and it is the one
implemented here. The correction is recorded in docs/physics/delay_cost.md.

Truncation. The p-series covers a finite number of days ``N``. Beyond it nothing is
known, so nothing is extrapolated: the sum is cut at ``N`` and the result is a LOWER
BOUND on the expected extra days. ``p_no_success_in_horizon`` is the probability mass
left beyond the horizon; when it is 0 the bound is exact.

``C_day`` is a daily cost-of-delay parameter that is supplied by the user. No default
is written here: spec II.9 (iv) lists it as "user-supplied or documented default" and
the genre reference (O'Neill and Davidheiser, J. Spacecraft and Rockets,
doi 10.2514/1.a36618) supplies a cost-model form, not a Canso number. Without it the
function returns the expected delay in days and no cost.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from typing import Any

STATUS = "SKETCHED"
CITATION = "O'Neill and Davidheiser, J. Spacecraft and Rockets, doi 10.2514/1.a36618"


def _checked_series(p_series: Sequence[float]) -> list[float]:
    if isinstance(p_series, (str, bytes)) or not isinstance(p_series, Sequence):
        raise ValueError("p_series must be a list of daily success probabilities")
    if len(p_series) == 0:
        raise ValueError("p_series must hold at least one day")
    checked: list[float] = []
    for index, value in enumerate(p_series):
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ValueError(f"p_series[{index}] must be a number")
        number = float(value)
        if not math.isfinite(number) or not 0.0 <= number <= 1.0:
            raise ValueError(f"p_series[{index}] must lie in [0, 1], got {value!r}")
        checked.append(number)
    return checked


def expected_extra_days(p_series: Sequence[float]) -> dict[str, float]:
    """Expected extra days before the first success, relative to the first opportunity.

    Returns ``expected_extra_days`` (a lower bound unless ``p_no_success_in_horizon``
    is 0) and ``p_no_success_in_horizon``.
    """
    series = _checked_series(p_series)
    survival = 1.0
    extra = 0.0
    # After day j the survival is P(T > j). The truncated sum runs j = 1 .. N - 1.
    for p in series[:-1]:
        survival *= 1.0 - p
        extra += survival
    # One more factor, for the last day, gives the probability of no success in the horizon.
    survival *= 1.0 - series[-1]
    return {"expected_extra_days": extra, "p_no_success_in_horizon": survival}


def expected_delay_cost(
    p_series: Sequence[float], c_day: float | None = None
) -> dict[str, Any]:
    """The decision-layer summary for one p-series, with a cost only if C_day is given."""
    result = expected_extra_days(p_series)
    if c_day is not None:
        if isinstance(c_day, bool) or not isinstance(c_day, (int, float)):
            raise ValueError("c_day must be a number")
        if not math.isfinite(float(c_day)) or float(c_day) < 0.0:
            raise ValueError("c_day must be a finite number that is not negative")
    exact = result["p_no_success_in_horizon"] == 0.0
    body: dict[str, Any] = {
        "status": STATUS,
        "horizon_days": len(list(p_series)),
        "expected_extra_days": result["expected_extra_days"],
        "p_no_success_in_horizon": result["p_no_success_in_horizon"],
        "bound": "exact" if exact else "lower",
        "c_day": None if c_day is None else float(c_day),
        "c_day_flag": "USER_SUPPLIED" if c_day is not None else None,
        "expected_cost": None
        if c_day is None
        else float(c_day) * result["expected_extra_days"],
        "formula": "E[extra days] = sum_{j>=1} prod_{s=1..j} (1 - p_s); E[cost] = C_day * E[extra days]",
        "assumptions": [
            "successes are independent across days",
            "one decision per day, at the best opportunity of that day",
            "the horizon is finite and nothing is extrapolated beyond it, so the days are a lower bound unless the probability of no success in the horizon is 0",
        ],
        "citation": CITATION,
    }
    return body
