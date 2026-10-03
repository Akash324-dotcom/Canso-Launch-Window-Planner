"""Loader for the frozen /v1 JSON Schemas of gate G0.

Seam 2 of ``docs/00_INTEGRATION_CONTRACT.md`` makes ``tests/contract/schemas``
the source of truth for the whole team and makes it changeable only through
this workflow. The service therefore validates every request and every response
against those same files rather than against a second, drifting copy. The
resolution order for the schema directory is:

1. the ``LAUNCHWIN_CONTRACT_DIR`` environment variable, if set;
2. ``<repository root>/tests/contract/schemas``.

The format checker is built the same way as in ``tests/contract/test_schemas.py``:
the pinned jsonschema in the virtual environment ships a ``date`` checker but no
``date-time`` checker, because that one needs rfc3339-validator, which is absent
and may not be installed, so an equivalent strict check is registered on the
instance only when the built-in checker is missing.
"""

from __future__ import annotations

import json
import os
import re
from functools import lru_cache
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator, FormatChecker
from referencing import Registry, Resource

API_DIR = Path(__file__).resolve().parent
REPO_ROOT = API_DIR.parents[1]
CONTRACT_DIR_ENV = "LAUNCHWIN_CONTRACT_DIR"

RFC3339_DATE_TIME = re.compile(
    r"^\d{4}-\d{2}-\d{2}[Tt]\d{2}:\d{2}:\d{2}(\.\d+)?([Zz]|[+-]\d{2}:\d{2})$"
)


def contract_schema_dir() -> Path:
    """Directory holding the frozen schema files."""
    override = os.environ.get(CONTRACT_DIR_ENV)
    return Path(override) if override else REPO_ROOT / "tests" / "contract" / "schemas"


def check_rfc3339_date_time(value: object) -> bool:
    """Reject anything that is not ISO-8601 with a Z or numeric offset suffix."""
    import datetime as dt

    if not isinstance(value, str):
        return True
    if not RFC3339_DATE_TIME.match(value):
        raise ValueError(f"{value!r} is not ISO-8601 date-time with a Z or numeric offset suffix")
    dt.datetime.fromisoformat(value.replace("Z", "+00:00").replace("z", "+00:00"))
    return True


@lru_cache(maxsize=1)
def format_checker() -> FormatChecker:
    """Format checker that enforces the ISO formats the schemas declare."""
    checker = FormatChecker()
    if "date-time" not in checker.checkers:
        checker.checks("date-time", raises=ValueError)(check_rfc3339_date_time)
    return checker


@lru_cache(maxsize=1)
def load_schemas() -> tuple[dict[str, Any], Registry]:
    """Every frozen schema, plus a registry so that ``$ref`` by file name resolves."""
    directory = contract_schema_dir()
    if not directory.is_dir():
        raise FileNotFoundError(
            f"frozen contract schemas not found at {directory}. "
            f"Set {CONTRACT_DIR_ENV} to the directory that holds them."
        )
    schemas: dict[str, Any] = {}
    resources: list[tuple[str, Resource]] = []
    for path in sorted(directory.glob("*.json")):
        contents = json.loads(path.read_text(encoding="utf-8"))
        schemas[path.stem] = contents
        resource = Resource.from_contents(contents)
        resources.append((path.stem, resource))
        identifier = contents.get("$id")
        if isinstance(identifier, str):
            resources.append((identifier, resource))
    return schemas, Registry().with_resources(resources)


@lru_cache(maxsize=None)
def load_validator(schema_name: str) -> Draft202012Validator:
    """Validator for one frozen schema, by schema file stem."""
    schemas, registry = load_schemas()
    if schema_name not in schemas:
        raise KeyError(f"no frozen schema named {schema_name}; known: {sorted(schemas)}")
    return Draft202012Validator(
        schemas[schema_name],
        registry=registry,
        format_checker=format_checker(),
    )


def describe(errors: list[Any]) -> str:
    """One line per validation error, with its JSON pointer."""
    return "\n".join(
        f"  at /{'/'.join(str(part) for part in error.absolute_path)}: {error.message}"
        for error in errors
    )


def errors_for(schema_name: str, instance: Any) -> list[Any]:
    """Every validation error of ``instance`` against the named frozen schema."""
    return sorted(
        load_validator(schema_name).iter_errors(instance),
        key=lambda error: list(error.absolute_path),
    )


def validation_message(schema_name: str, instance: Any) -> str:
    """A readable message listing why an instance does not satisfy a schema."""
    errors = errors_for(schema_name, instance)
    return f"{schema_name}.json:\n{describe(errors)}"


def assert_valid(schema_name: str, instance: Any) -> None:
    """Raise ``ValueError`` unless the instance satisfies the named frozen schema."""
    errors = errors_for(schema_name, instance)
    if errors:
        raise ValueError(validation_message(schema_name, instance))