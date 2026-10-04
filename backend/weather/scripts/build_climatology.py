"""Build data/climatology_<site>.json from the committed ERA5 hourly archive and the current criteria version.

    python -m backend.weather.scripts.build_climatology canso

Run from the repository root. No network is needed: the archive is data/era5_<site>_hourly.csv.gz.
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone

from backend.weather import climatology, config, criteria


def main(site: str) -> None:
    table = criteria.load_criteria(None)
    generated_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    document = climatology.build_climatology(site, table, generated_at)
    path = config.DATA_DIR / f"climatology_{site}.json"
    path.write_text(json.dumps(document, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    flagged = sum(1 for entry in document["bins"] if entry["low_confidence"])
    print(f"wrote {path.name}: {document['period_start']} to {document['period_end']}, "
          f"{document['hours_total']} hours ({document['hours_excluded_missing']} excluded), "
          f"{document['days_total']} days ({document['days_excluded_missing']} excluded), "
          f"{flagged} of {len(document['bins'])} hourly bins flagged")
    print("month  n_days  P(L | window)   per-criterion violation frequency")
    for entry in document["daily_window"]:
        parts = ", ".join(f"{key}={value:.3f}" for key, value in entry["p_violation"].items())
        print(f"{entry['month']:5d}  {entry['n']:6d}  {entry['p_launch']:.3f}           {parts}")


if __name__ == "__main__":
    main(sys.argv[1])
