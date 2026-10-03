"""The public Python client of the service, task A8 of issue #4.

The distributable surface is the single top level module ``launchwin``, which
``pyproject.toml`` maps onto this directory, so that ``import launchwin`` resolves
from any working directory once the distribution has been installed with
``pip install -e .``. This package is the in repository form of the same module:
``backend.client.launchwin`` is that file, and re-exporting it here means the
repository can name the client either way without there being two copies of it.
"""

from __future__ import annotations

from .launchwin import (
    BASE_URL_ENV,
    COMPONENT_COLUMNS,
    DEFAULT_BASE_URL,
    DEFAULT_LEAD_MAX_DAYS,
    DEFAULT_SITE,
    DEFAULT_STEP_S,
    DEFAULT_TIMEOUT_S,
    DEFAULT_VEHICLE_PROFILE_ID,
    POINT_COLUMNS,
    SCREEN_COLUMNS,
    WINDOW_COLUMNS,
    LaunchwinError,
    citation,
    ephemeris,
    resolve_base_url,
    site,
    skill,
    weather,
    windows,
    windows_frame,
)

__all__ = [
    "BASE_URL_ENV",
    "COMPONENT_COLUMNS",
    "DEFAULT_BASE_URL",
    "DEFAULT_LEAD_MAX_DAYS",
    "DEFAULT_SITE",
    "DEFAULT_STEP_S",
    "DEFAULT_TIMEOUT_S",
    "DEFAULT_VEHICLE_PROFILE_ID",
    "POINT_COLUMNS",
    "SCREEN_COLUMNS",
    "WINDOW_COLUMNS",
    "LaunchwinError",
    "citation",
    "ephemeris",
    "resolve_base_url",
    "site",
    "skill",
    "weather",
    "windows",
    "windows_frame",
]