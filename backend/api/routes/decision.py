"""``GET /v1/decision/delay-cost``, the optional analysis endpoint of spec II.9 (iv).

Spec II.9 (iv) says the decision layer "ships as an optional analysis endpoint
computing (II.27) from a requested p-series". This is that endpoint. It is an
extension of the seven frozen response schemas, not a change to any of them:
``POST /v1/windows`` and every other route answer exactly as before, and this
route publishes no frozen schema because there is none for it.

The caller sends the daily success probabilities (for example the best usable
``p_success`` of each day of a window response) and, optionally, a daily cost of
delay ``c_day``. The cost is only computed when the caller supplies ``c_day``; the
service writes no default dollar figure. The arithmetic is
``backend.engine.decision`` and is documented there.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Query

from backend.api.errors import UPSTREAM_UNAVAILABLE, ApiError, ContractViolation
from backend.api.limits import READ_BUCKET
from backend.api.middleware import rate_limited
from backend.api.publish import get_query_extra, query_parameter

router = APIRouter(tags=["decision"])

MAX_DAYS = 366


class DecisionLayerAbsent(ApiError):
    """The engine package that holds the decision layer is not importable here."""

    status_code = 503
    error = UPSTREAM_UNAVAILABLE

DESCRIPTION = (
    "Expected extra days until the first successful launch, from a requested "
    "series of daily success probabilities, and the expected delay cost when a "
    "daily cost is supplied. Spec II.9 (iv), status SKETCHED. An extension "
    "endpoint: it has no frozen response schema."
)


def _parse_series(raw: str) -> list[float]:
    pieces = [piece.strip() for piece in raw.split(",")]
    if not raw.strip() or any(piece == "" for piece in pieces):
        raise ContractViolation(
            "p must be a comma separated list of daily probabilities, for example 0.6,0.7,0.5",
            violations=["/p: empty entry"],
        )
    if len(pieces) > MAX_DAYS:
        raise ContractViolation(f"p holds at most {MAX_DAYS} days", violations=["/p: too long"])
    values: list[float] = []
    for index, piece in enumerate(pieces):
        try:
            values.append(float(piece))
        except ValueError:
            raise ContractViolation(
                f"p[{index}] is not a number: {piece!r}", violations=[f"/p/{index}: not a number"]
            ) from None
    return values


@router.get(
    "/decision/delay-cost",
    openapi_extra=get_query_extra(
        [
            query_parameter(
                "p",
                {"type": "string"},
                True,
                "Comma separated daily success probabilities, each in [0, 1], first opportunity first.",
            ),
            query_parameter(
                "c_day",
                {"type": "number", "minimum": 0},
                False,
                "Daily cost of delay, user supplied. No default exists; without it no cost is returned.",
            ),
        ],
        DESCRIPTION,
    ),
    dependencies=[Depends(rate_limited(READ_BUCKET))],
)
def get_delay_cost(
    p: str = Query(...),
    c_day: float | None = Query(None),
) -> dict[str, Any]:
    """The delay summary for one p-series, spec II.9 (iv)."""
    series = _parse_series(p)
    try:
        # Imported here, not at module load: the service must start without the engine.
        from backend.engine import decision
    except ImportError:
        raise DecisionLayerAbsent("the engine decision layer is not available in this deployment") from None
    try:
        return decision.expected_delay_cost(series, c_day=c_day)
    except ValueError as error:
        raise ContractViolation(str(error), violations=[str(error)]) from None
