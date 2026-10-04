"""Generate the offline weather fixture backend/fixtures/weather.json from committed data. Nothing in it is typed by hand.

    python -m backend.weather.scripts.build_weather_fixture canso [YYYY-MM-DD]

The fixture is one spec IV.3 response, for the given date or else the date in data/sources.json under
'fixture', which is the date the API's offline record is asked for. Inputs are the committed snapshot (backend/weather/data/snapshot/), the committed climatology and the
criteria table. The local cache is ignored and no request is made, so the output is reproducible byte for byte.
A stored forecast is labelled source 'snapshot_cache' and keeps its issue time. Run from the repository root.
"""

from __future__ import annotations

import json
import os
import sys
from contextlib import contextmanager
from pathlib import Path

from backend.weather import config, fetch, service

FIXTURE_DIR = Path(__file__).resolve().parents[2] / "fixtures"
FIXTURE_NAME = "weather.json"


@contextmanager
def committed_data_only():
    """Offline, with the local cache hidden, so only committed files are read."""
    previous_env = os.environ.get(fetch.OFFLINE_ENV)
    previous_cache = fetch.CACHE_DIR
    os.environ[fetch.OFFLINE_ENV] = "1"
    fetch.CACHE_DIR = fetch.SNAPSHOT_DIR / "_no_local_cache"
    fetch.clear_memo()
    service.clear_memo()
    try:
        yield
    finally:
        fetch.CACHE_DIR = previous_cache
        if previous_env is None:
            os.environ.pop(fetch.OFFLINE_ENV, None)
        else:
            os.environ[fetch.OFFLINE_ENV] = previous_env
        fetch.clear_memo()
        service.clear_memo()


def build(site: str, date_iso: str | None = None) -> str:
    """Return the text of the fixture file."""
    with committed_data_only():
        snapshot = fetch.fetch_forecast(site, "ensemble")
        if snapshot is None:
            raise SystemExit(f"no committed forecast snapshot for {site}; run refresh_snapshot first")
        retrieved = fetch.parse_iso_z(snapshot["retrieved_at"])
        single = date_iso or config.load_sources()["fixture"]["date"]
        body = service.compute(single, site, None, now=retrieved)
    return json.dumps(body, indent=1, ensure_ascii=False) + "\n"


def main(site: str, date_iso: str | None = None) -> None:
    FIXTURE_DIR.mkdir(parents=True, exist_ok=True)
    text = build(site, date_iso)
    (FIXTURE_DIR / FIXTURE_NAME).write_text(text, encoding="utf-8")
    print(f"wrote backend/fixtures/{FIXTURE_NAME} ({len(text)} bytes)")
    print(text)


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2] if len(sys.argv) > 2 else None)
