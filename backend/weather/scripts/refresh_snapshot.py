"""Fetch the current ensemble forecasts and store them as the committed offline snapshot.

    python -m backend.weather.scripts.refresh_snapshot canso

Writes backend/weather/data/snapshot/<site>/<source_id>.json for the primary ensemble and for the second
ensemble that supplies the supplement fields. A snapshot keeps the forecast's own issue time, so a stale snapshot
is answered as CLIMATOLOGY once the requested date leaves its horizon. Needs the network.
"""

from __future__ import annotations

import shutil
import sys

from backend.weather import config, fetch


def main(site: str) -> None:
    fetch.clear_memo()
    for chain in ("ensemble", config.load_sources()["supplement"]["chain"]):
        forecast = fetch.fetch_forecast(site, chain)
        if forecast is None or forecast["source"] == "snapshot_cache":
            raise SystemExit(f"no live source answered for the {chain} chain; the snapshot was left unchanged")
        cached = fetch.cache_path(site, forecast["forecast_issue_time"], forecast["source_id"])
        target = fetch.SNAPSHOT_DIR / site / f"{forecast['source_id']}.json"
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(cached, target)
        nulls = sum(1 for member in forecast["members"] for column in member.values() for value in column
                    if value is None)
        print(f"snapshot {target.name}: issued {forecast['forecast_issue_time']} ({forecast['issue_time_basis']}), "
              f"retrieved {forecast['retrieved_at']}, {len(forecast['members'])} members, "
              f"{forecast['times'][0]} to {forecast['times'][-1]}, {target.stat().st_size} bytes, "
              f"{nulls} missing values at the far end of the forecast range")


if __name__ == "__main__":
    main(sys.argv[1])
