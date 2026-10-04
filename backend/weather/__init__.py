"""Probabilistic launch-weather layer for Spaceport Nova Scotia (contract Seam 1).

Exports:
    probability(date_iso, site, criteria_version=None)   the GET /v1/weather/probability body, spec IV.3
    climatology(month, hour, site, criteria_version)     P(L | month, UTC hour) from the ERA5 archive
    criteria_version()                                   the current default criteria version
    observed_launchable(date_iso, criteria_version, site)  the verification outcome, for issue #7

    hindcast(period_start, period_end, lead_max=10)      the GET /v1/validation/skill body, spec IV.4
"""

from __future__ import annotations

from . import climatology, hindcast, service
from .criteria import current_criteria_version as criteria_version
from .errors import CriteriaVersionMissingError, UnknownSiteError, WeatherDataError, WeatherError
from .observations import observed_launchable

__all__ = [
    "probability",
    "climatology",
    "hindcast",
    "criteria_version",
    "observed_launchable",
    "CriteriaVersionMissingError",
    "UnknownSiteError",
    "WeatherDataError",
    "WeatherError",
]


def probability(date_iso: str, site: str, criteria_version: str | None = None) -> dict:
    """Return the GET /v1/weather/probability body (spec IV.3). May use cache/."""
    return service.compute(date_iso, site, criteria_version)
