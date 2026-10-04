"""The versioned launch-weather criteria table and its evaluator (spec II.7, II.10).

Limits live in data/criteria_v*.json, never in this module. The same functions evaluate ensemble members,
reanalysis hours and observed days, so forecast, climatology and verification share one event definition.
"""

from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path

from .errors import CriteriaVersionMissingError

DATA_DIR = Path(__file__).resolve().parent / "data"

REQUIRED_ROW_KEYS = ("criterion_id", "parameter", "limit", "unit", "source_citation", "flag", "comparison")
FLAGS = ("VERIFIED", "PROXY")
COMPARISONS = ("lt", "gt", "between")
VERIFIED_EVIDENCE_KEYS = ("source_citation", "source_url", "source_quote", "source_accessed")

_VERSION_FILE = re.compile(r"^criteria_v(\d+)\.json$")


def available_versions() -> list[str]:
    """Every criteria version with a table in data/, oldest first."""
    found = []
    for path in DATA_DIR.glob("criteria_v*.json"):
        match = _VERSION_FILE.match(path.name)
        if match:
            found.append((int(match.group(1)), path.stem))
    return [name for _, name in sorted(found)]


def current_criteria_version() -> str:
    """The default version: the highest numbered table in data/ (spec IV.1, 'current data/criteria_v*.json')."""
    versions = available_versions()
    if not versions:
        raise CriteriaVersionMissingError("criteria_v*", versions)
    return versions[-1]


_SHORT_VERSION = re.compile(r"^v(\d+)$")


def canonical_version(criteria_version: str | None) -> str:
    """The name of the table a version string refers to. None means the current default version.

    Two exact forms are accepted: the file stem ('criteria_v1') and its short form ('v1'), which is what the
    contract examples and the API default use for data/criteria_v1.json. Anything else, and any version without
    a table, raises CriteriaVersionMissingError under the name that was given.
    """
    if criteria_version is None:
        return current_criteria_version()
    versions = available_versions()
    short = _SHORT_VERSION.match(criteria_version)
    name = f"criteria_v{short.group(1)}" if short else criteria_version
    if name not in versions:
        raise CriteriaVersionMissingError(criteria_version, versions)
    return name


def validate_table(table: dict) -> None:
    """Raise ValueError if the table breaks a structural rule, including the VERIFIED evidence rule."""
    seen = set()
    for row in table.get("criteria", []):
        name = row.get("criterion_id", "<no id>")
        missing = [key for key in REQUIRED_ROW_KEYS if key not in row]
        if missing:
            raise ValueError(f"criterion {name} lacks {missing}")
        if name in seen:
            raise ValueError(f"criterion id {name} appears twice")
        seen.add(name)
        if row["flag"] not in FLAGS:
            raise ValueError(f"criterion {name} has flag {row['flag']!r}, expected one of {FLAGS}")
        if row["comparison"] not in COMPARISONS:
            raise ValueError(f"criterion {name} has comparison {row['comparison']!r}")
        _check_limit(row)
        if not str(row["source_citation"]).strip():
            raise ValueError(f"criterion {name} has an empty source_citation")
        if row["flag"] == "VERIFIED":
            empty = [key for key in VERIFIED_EVIDENCE_KEYS if not str(row.get(key, "")).strip()]
            if empty:
                raise ValueError(
                    f"criterion {name} is flagged VERIFIED without {empty}; "
                    "a row without a verifiable source must be PROXY"
                )
    for entry in table.get("not_assessed", []):
        if not all(str(entry.get(key, "")).strip() for key in ("inventory_row", "label", "reason")):
            raise ValueError(f"not_assessed entry {entry} lacks its inventory row, label or reason")


def _check_limit(row: dict) -> None:
    limit = row["limit"]
    if row["comparison"] == "between":
        valid = isinstance(limit, list) and len(limit) == 2 and all(_is_number(v) for v in limit)
    else:
        valid = _is_number(limit)
    if not valid:
        raise ValueError(f"criterion {row['criterion_id']} states no usable numeric limit")


def _is_number(value: object) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


@lru_cache(maxsize=None)
def _load(version: str) -> dict:
    path = DATA_DIR / f"{version}.json"
    if not _VERSION_FILE.match(path.name) or not path.is_file():
        raise CriteriaVersionMissingError(version, available_versions())
    table = json.loads(path.read_text(encoding="utf-8"))
    if table.get("criteria_version") != version:
        raise ValueError(f"{path.name} declares criteria_version {table.get('criteria_version')!r}")
    validate_table(table)
    return table


def load_criteria(criteria_version: str | None = None) -> dict:
    """Load one criteria table. None means the current default version.

    Raises CriteriaVersionMissingError for a version with no table.
    """
    return _load(canonical_version(criteria_version))


def rows_with_fields(table: dict, fields) -> list[dict]:
    """The rows whose parameter is among the given data fields, in table order."""
    available = set(fields)
    return [row for row in table["criteria"] if row["parameter"] in available]


def required_parameters(rows: list[dict]) -> list[str]:
    """The data-source fields needed to evaluate the given rows, without duplicates, in table order."""
    return list(dict.fromkeys(row["parameter"] for row in rows))


def is_violated(row: dict, value: float | None) -> bool | None:
    """True if the value violates the row, False if it satisfies it, None if there is no value to judge."""
    if value is None:
        return None
    limit = row["limit"]
    if row["comparison"] == "gt":
        return value > limit
    if row["comparison"] == "lt":
        return value < limit
    return limit[0] <= value <= limit[1]


def window_violations(rows: list[dict], hours: list[dict]) -> dict[str, bool | None]:
    """Per criterion: was it violated at any hour of the window (worst-case excursion, spec II.21).

    ``hours`` holds one mapping of parameter to value per hour. The answer is True as soon as one hour violates,
    None if no hour violates but at least one value is missing, and False only when every hour is known and
    satisfies the row.
    """
    result: dict[str, bool | None] = {}
    for row in rows:
        verdicts = [is_violated(row, hour.get(row["parameter"])) for hour in hours]
        if any(v is True for v in verdicts):
            result[row["criterion_id"]] = True
        elif not verdicts or any(v is None for v in verdicts):
            result[row["criterion_id"]] = None
        else:
            result[row["criterion_id"]] = False
    return result


def window_launchable(rows: list[dict], hours: list[dict]) -> int | None:
    """The event L of spec II.20 for one window: 1, 0, or None when it cannot be decided."""
    verdicts = window_violations(rows, hours).values()
    if any(v is True for v in verdicts):
        return 0
    if not hours or any(v is None for v in verdicts):
        return None
    return 1
