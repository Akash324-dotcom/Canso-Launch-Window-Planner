"""Errors raised by the weather layer. API maps them onto the spec IV.7 error model."""

from __future__ import annotations


class WeatherError(Exception):
    """Base class for every error this layer raises on purpose."""


class CriteriaVersionMissingError(WeatherError):
    """The requested criteria version has no table in data/.

    API maps this to the body value ``constraint_fired: "criteria_version_missing"`` (spec IV.1), never to an
    HTTP error, because it is a domain outcome.
    """

    constraint_fired = "criteria_version_missing"

    def __init__(self, criteria_version: str, available: list[str]):
        self.criteria_version = criteria_version
        self.available = available
        super().__init__(
            f"criteria version {criteria_version!r} not found; available versions: {', '.join(available) or 'none'}"
        )


class UnknownSiteError(WeatherError):
    """The site id is not configured in data/sites.json. API maps this to HTTP 404 (spec IV.7 rule 2)."""

    def __init__(self, site: str, available: list[str]):
        self.site = site
        self.available = available
        super().__init__(f"unknown site {site!r}; configured sites: {', '.join(available) or 'none'}")


class WeatherDataError(WeatherError):
    """A data file or a source payload is missing, malformed or lacks a field the criteria need."""
