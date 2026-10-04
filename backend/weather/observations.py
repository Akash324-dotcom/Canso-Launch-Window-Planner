"""The verification outcome: was a past day launchable under a criteria version (seam for issue #7).

The observed fields are the ERA5 hourly archive. The rows, the evaluation window and the evaluator are the
ones the forecast side uses, so a forecast probability and its outcome refer to the same event L(d).
"""

from __future__ import annotations

from . import climatology, config, criteria, ensemble


def observed_launchable(date_iso: str, criteria_version: str | None = None, site: str = "canso") -> int | None:
    """1 if every evaluated criterion held at every window hour of the date, 0 if any was violated.

    Returns None when the archive does not cover the whole window or a needed value is missing, so that the
    caller excludes the day from its sample and counts the exclusion.
    """
    day = config.parse_date(date_iso)
    site_cfg = config.load_site(site)
    rows = climatology.evaluated_rows(site, criteria.load_criteria(criteria_version))
    archive = climatology.load_hourly_archive(site)
    labels = config.window_times(day, site_cfg)
    index = archive["index"]
    if any(label not in index for label in labels):
        return None
    ensemble.check_units(archive["units"], rows)
    hours = [{row["parameter"]: archive["columns"][row["parameter"]][index[label]] for row in rows}
             for label in labels]
    return criteria.window_launchable(rows, hours)
