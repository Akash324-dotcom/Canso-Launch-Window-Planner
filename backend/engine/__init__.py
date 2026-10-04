"""Launch window decision engine for Spaceport Nova Scotia (Canso).

Frozen seam (integration contract, Seam 1). The engine returns the spec IV.1
response body MINUS the fields the API composes: ``p_success``,
``p_success_components.weather``, ``horizon_label``, ``forecast_issue_time``,
``constants_block`` and ``provenance_block``.

Pure function. No network. The only file I/O is reads from ``backend/engine/data/``.

The API composes the response from three importable pieces:

    compute_windows(request)          the engine's share of the response body
    provenance.constants_block(run)   the constants block
    provenance.build_provenance_block(request)   the provenance block

Claim status follows spec II.9 without exception: the injection-consistent
fixed point and reachability are PROVED, the chance-constrained window and the
decision layer are SKETCHED, and forecast skill at this site remains a
CONJECTURE. Nothing here upgrades a claim.
"""

from __future__ import annotations

import time
from typing import Any, Mapping

from backend.engine import frames, injection, j2, provenance, reachability, screens, sso, target, window
from backend.engine.engine import compose

ENGINE_VERSION = "engine-0.1.0"

__all__ = [
    "ENGINE_VERSION",
    "compute_windows",
    "compose",
    "frames",
    "injection",
    "j2",
    "provenance",
    "reachability",
    "screens",
    "sso",
    "target",
    "window",
]


def compute_windows(request: Mapping[str, Any]) -> dict[str, Any]:
    """Turn a spec IV.1 request into launch windows, or an honest refusal.

    Returns the engine's share of the spec IV.1 response body. An unreachable
    target is a domain answer with HTTP 200 semantics (spec IV.7), never an
    exception: the response carries ``reachable: false`` together with the
    computed plane-change penalty where one is computable.
    """
    started = time.perf_counter()
    result = compose(request)
    result["engine_version"] = ENGINE_VERSION
    result["computation_ms"] = (time.perf_counter() - started) * 1.0e3
    return result