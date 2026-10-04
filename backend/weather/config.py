"""Configuration loaded from data/*.json. No site value, forecast boundary or source setting lives in source code."""

from __future__ import annotations

import json
from datetime import date, datetime, timedelta, timezone
from functools import lru_cache
from pathlib import Path
from zoneinfo import ZoneInfo

from .errors import UnknownSiteError, WeatherDataError

DATA_DIR = Path(__file__).resolve().parent / "data"


@lru_cache(maxsize=None)
def _read(name: str) -> dict:
    path = DATA_DIR / name
    if not path.is_file():
        raise WeatherDataError(f"configuration file {path} is missing")
    return json.loads(path.read_text(encoding="utf-8"))


def load_sources() -> dict:
    """Sources, fallback chains and request settings (data/sources.json)."""
    return _read("sources.json")


def load_skill_horizon() -> dict:
    """The FORECAST to CLIMATOLOGY boundary and its citations (data/skill_horizon.json)."""
    return _read("skill_horizon.json")


def site_ids() -> list[str]:
    return sorted(key for key in _read("sites.json") if not key.startswith("_"))


def load_site(site: str) -> dict:
    """One site's configuration. Raises UnknownSiteError for an id that is not configured."""
    sites = _read("sites.json")
    if site not in sites or site.startswith("_"):
        raise UnknownSiteError(site, site_ids())
    return sites[site]


def parse_date(date_iso: str) -> date:
    """Parse YYYY-MM-DD strictly. Raises ValueError for anything else."""
    if not isinstance(date_iso, str) or len(date_iso) != 10:
        raise ValueError(f"date must be YYYY-MM-DD, got {date_iso!r}")
    return date.fromisoformat(date_iso)


def window_times(day: date, site_cfg: dict) -> list[str]:
    """The hourly labels of the evaluation window I(d) as UTC strings 'YYYY-MM-DDTHH:00'.

    The window is given in local hours in data/sites.json; both end hours are included. The conversion uses
    the site's time zone, so daylight saving time is handled by the zone database, not by a constant offset.
    """
    window = site_cfg["evaluation_window_local"]
    zone = ZoneInfo(site_cfg["timezone"])
    start = datetime(day.year, day.month, day.day, window["start_hour"], tzinfo=zone)
    count = window["end_hour"] - window["start_hour"] + 1
    labels = []
    for offset in range(count):
        local = start.astimezone(timezone.utc) + timedelta(hours=offset)
        labels.append(local.strftime("%Y-%m-%dT%H:00"))
    return labels
