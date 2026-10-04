"""Run the hindcast over the longest period the committed data supports and write its outputs.

    python -m backend.weather.scripts.run_hindcast canso

Writes:
    data/hindcast/pairs_<site>.csv     one row per (issue date, lead): forecast probability and observed outcome
    data/hindcast/result_<site>.json   skill by lead, reliability, exclusions, coverage; everything but the pairs
    backend/weather/HINDCAST.md        the report, rendered from the result

No network is needed: the forecast archive and the hourly archive are committed. Run from the repository root.
"""

from __future__ import annotations

import csv
import io
import json
import sys
from pathlib import Path

from backend.weather import climatology, config, criteria, hindcast, hindcast_report

REPORT = Path(__file__).resolve().parents[1] / "HINDCAST.md"


def build(site: str) -> dict[str, str]:
    """Return {path relative to backend/weather: file text} for the three outputs."""
    start, end = hindcast.longest_period(site)
    settings = config.load_sources()["hindcast"]
    result = dict(hindcast.compute(start, end, settings["lead_max_days"], site))
    valid_dates = sorted({row["valid_date"] for row in result["pairs"]})
    result["observed_violation_frequency"] = hindcast.observed_violation_frequency(
        site, result["criteria_version"], valid_dates)
    bootstrap = settings["calibration_bootstrap"]
    result["calibration"] = {
        "gaps": hindcast.calibration_gaps([(row["p"], row["o"]) for row in result["pairs"]],
                                          settings["reliability_bins"]),
        "bootstrap": hindcast.bootstrap_calibration_gap(
            result["pairs"], settings["reliability_bins"], bootstrap["block_days"], bootstrap["replicates"],
            bootstrap["seed"], hindcast_report.MAX_CALIBRATION_GAP, tuple(bootstrap["interval"])),
    }

    text = io.StringIO()
    writer = csv.writer(text, lineterminator="\n")
    writer.writerow(["issue_date", "lead_time_days", "valid_date", "p", "o"])
    for row in result["pairs"]:
        writer.writerow([row["issue_date"], row["lead_time_days"], row["valid_date"], row["p"], row["o"]])

    report = hindcast_report.render(result, hindcast.source_metadata(site), climatology.archive_metadata(site),
                                    criteria.load_criteria(result["criteria_version"]), config.load_skill_horizon(),
                                    review=settings)
    summary = {key: value for key, value in result.items() if key != "pairs"}
    return {
        f"data/hindcast/pairs_{site}.csv": text.getvalue(),
        f"data/hindcast/result_{site}.json": json.dumps(summary, indent=1, ensure_ascii=False) + "\n",
        "HINDCAST.md": report,
    }


def main(site: str) -> None:
    root = Path(__file__).resolve().parents[1]
    for name, text in build(site).items():
        (root / name).write_text(text, encoding="utf-8")
        print(f"wrote backend/weather/{name} ({len(text)} bytes)")
    print((root / "HINDCAST.md").read_text(encoding="utf-8"))


if __name__ == "__main__":
    main(sys.argv[1])
