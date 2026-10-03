"""Request normalisation for POST /v1/windows.

Spec IV.1 gives defaults for ``site``, ``criteria_version``, ``raan_tolerance_deg``
and ``include_weather``. Applying them here, before the citation identifier is
computed, means two requests that differ only by spelling out a default produce the
same run identifier, which is what spec III.6 determinism requires.
"""

from __future__ import annotations

from typing import Any

from backend.api.config import Settings


def effective_request(body: dict[str, Any], settings: Settings) -> dict[str, Any]:
    """The request with every documented default applied, as a fresh document."""
    resolved: dict[str, Any] = {
        "target": dict(body.get("target", {})),
        "date_range": dict(body.get("date_range", {})),
        "vehicle_profile_id": body.get("vehicle_profile_id"),
        "site": body.get("site", settings.default_site),
        "criteria_version": body.get("criteria_version", settings.default_criteria_version),
        "raan_tolerance_deg": body.get("raan_tolerance_deg"),
        "include_weather": body.get("include_weather", settings.default_include_weather),
    }
    corridor = body.get("corridor")
    if corridor is not None:
        resolved["corridor"] = dict(corridor)
    return resolved