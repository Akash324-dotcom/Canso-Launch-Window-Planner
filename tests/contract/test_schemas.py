"""Contract tests for the frozen /v1 JSON Schemas, gate G0 of issue #1.

Every schema in ``schemas/`` is transcribed from spec Part IV. Each good example
in ``examples/good/`` must validate against the schema its filename names, and
each bad example in ``examples/bad/`` must be rejected. Examples are discovered
by filename prefix, so adding a file adds a test without editing this module.
"""

from __future__ import annotations

import datetime as dt
import json
import re
from functools import lru_cache
from pathlib import Path
from typing import Any, Iterator

import pytest
from jsonschema import Draft202012Validator, FormatChecker
from referencing import Registry, Resource

CONTRACT_DIR = Path(__file__).resolve().parent
SCHEMA_DIR = CONTRACT_DIR / "schemas"
GOOD_DIR = CONTRACT_DIR / "examples" / "good"
BAD_DIR = CONTRACT_DIR / "examples" / "bad"

FROZEN_SCHEMAS = (
    "constants_block",
    "ephemeris_response",
    "provenance_block",
    "site_response",
    "skill_response",
    "weather_probability_response",
    "windows_request",
    "windows_response",
)

MINIMUM_GOOD_EXAMPLES = 2
MINIMUM_BAD_EXAMPLES = 3

SHARED_BLOCK_REFS = {
    "constants_block": "constants_block.json",
    "provenance_block": "provenance_block.json",
}
SHARED_BLOCK_FIELDS = ("J2", "GM", "R_e", "omega_sid_rad_s", "gmst_model", "citation_id")

RFC3339_DATE_TIME = re.compile(
    r"^\d{4}-\d{2}-\d{2}[Tt]\d{2}:\d{2}:\d{2}(\.\d+)?([Zz]|[+-]\d{2}:\d{2})$"
)


def check_rfc3339_date_time(value: object) -> bool:
    """Reject anything that is not ISO-8601 with a Z or numeric offset suffix."""
    if not isinstance(value, str):
        return True
    if not RFC3339_DATE_TIME.match(value):
        raise ValueError(f"{value!r} is not ISO-8601 date-time with a Z or numeric offset suffix")
    dt.datetime.fromisoformat(value.replace("Z", "+00:00").replace("z", "+00:00"))
    return True


@lru_cache(maxsize=1)
def format_checker() -> FormatChecker:
    """Format checker that actually enforces the ISO formats the schemas declare.

    The ``date`` checker ships with jsonschema. The ``date-time`` checker needs
    the optional rfc3339-validator package, which is not installed here and
    cannot be installed, so an equivalent check is registered on the instance.
    """
    checker = FormatChecker()
    if "date-time" not in checker.checkers:
        checker.checks("date-time", raises=ValueError)(check_rfc3339_date_time)
    return checker


@lru_cache(maxsize=1)
def load_schemas() -> tuple[dict[str, Any], Registry]:
    """Load every schema file into a referencing registry keyed by file name."""
    schemas: dict[str, Any] = {}
    resources: list[tuple[str, Resource]] = []
    for path in sorted(SCHEMA_DIR.glob("*.json")):
        contents = json.loads(path.read_text(encoding="utf-8"))
        schemas[path.stem] = contents
        resource = Resource.from_contents(contents)
        resources.append((path.stem, resource))
        identifier = contents.get("$id")
        if isinstance(identifier, str):
            resources.append((identifier, resource))
    return schemas, Registry().with_resources(resources)


@lru_cache(maxsize=None)
def validator_for(schema_name: str) -> Draft202012Validator:
    schemas, registry = load_schemas()
    return Draft202012Validator(
        schemas[schema_name],
        registry=registry,
        format_checker=format_checker(),
    )


def load_example(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def schema_name_for(filename: str, schema_names: list[str]) -> str | None:
    matches = [name for name in schema_names if filename.startswith(f"{name}_")]
    return max(matches, key=len) if matches else None


def example_cases(directory: Path) -> list[pytest.ParameterSet]:
    schemas, _ = load_schemas()
    schema_names = sorted(schemas)
    return [
        pytest.param(path, schema_name_for(path.name, schema_names), id=path.stem)
        for path in sorted(directory.glob("*.json"))
    ]


def describe(errors: list[Any]) -> str:
    return "\n".join(
        f"  at /{'/'.join(str(part) for part in error.absolute_path)}: {error.message}"
        for error in errors
    )


def walk(node: Any) -> Iterator[dict[str, Any]]:
    if isinstance(node, dict):
        yield node
        for value in node.values():
            yield from walk(value)
    elif isinstance(node, list):
        for value in node:
            yield from walk(value)


def test_every_frozen_schema_file_is_present() -> None:
    schemas, _ = load_schemas()
    missing = sorted(set(FROZEN_SCHEMAS) - set(schemas))
    assert not missing, f"schemas missing from {SCHEMA_DIR.name}: {missing}"


def test_every_schema_is_a_valid_draft_2020_12_schema() -> None:
    schemas, _ = load_schemas()
    for name, schema in sorted(schemas.items()):
        Draft202012Validator.check_schema(schema)
        assert schema["$schema"] == "https://json-schema.org/draft/2020-12/schema", name


def test_shared_objects_are_referenced_and_never_copied() -> None:
    schemas, _ = load_schemas()
    consumers: list[str] = []
    for name, schema in sorted(schemas.items()):
        if name in SHARED_BLOCK_REFS:
            continue
        for block, reference in SHARED_BLOCK_REFS.items():
            if block in schema.get("properties", {}):
                assert schema["properties"][block] == {"$ref": reference}, f"{name}.{block}"
                consumers.append(f"{name}.{block}")
        for subschema in walk(schema):
            declared = subschema.get("properties")
            if isinstance(declared, dict):
                copied = sorted(set(declared) & set(SHARED_BLOCK_FIELDS))
                assert not copied, f"{name} inlines shared fields {copied}"
    assert len(consumers) >= 4, f"expected several consumers of the shared blocks, found {consumers}"


def test_every_schema_has_two_good_and_three_bad_examples() -> None:
    schemas, _ = load_schemas()
    for name in sorted(schemas):
        good = sorted(GOOD_DIR.glob(f"{name}_*.json"))
        bad = sorted(BAD_DIR.glob(f"{name}_*.json"))
        assert len(good) >= MINIMUM_GOOD_EXAMPLES, f"{name} needs {MINIMUM_GOOD_EXAMPLES} good examples, has {len(good)}"
        assert len(bad) >= MINIMUM_BAD_EXAMPLES, f"{name} needs {MINIMUM_BAD_EXAMPLES} bad examples, has {len(bad)}"


@pytest.mark.parametrize(("path", "schema_name"), example_cases(GOOD_DIR))
def test_good_example_validates(path: Path, schema_name: str | None) -> None:
    assert schema_name is not None, f"{path.name} does not name a schema in {SCHEMA_DIR.name}"
    errors = sorted(validator_for(schema_name).iter_errors(load_example(path)), key=lambda error: list(error.absolute_path))
    assert not errors, f"{path.name} must be valid against {schema_name}.json:\n{describe(errors)}"


@pytest.mark.parametrize(("path", "schema_name"), example_cases(BAD_DIR))
def test_bad_example_is_rejected(path: Path, schema_name: str | None) -> None:
    assert schema_name is not None, f"{path.name} does not name a schema in {SCHEMA_DIR.name}"
    errors = list(validator_for(schema_name).iter_errors(load_example(path)))
    assert errors, f"{path.name} must be rejected by {schema_name}.json but validated"


def test_empty_windows_with_reachable_true_is_a_valid_result() -> None:
    """Spec IV.1: no crossing in the date range within tolerance is not an error."""
    example = load_example(GOOD_DIR / "windows_response_good_reachable_no_windows.json")
    assert example["reachable"] is True
    assert example["windows"] == []
    assert not list(validator_for("windows_response").iter_errors(example))


def test_stub_responses_are_distinguishable() -> None:
    """Issue rule: stub output carries engine_version "stub"."""
    example = load_example(GOOD_DIR / "windows_response_good_stub.json")
    assert example["engine_version"] == "stub"
    assert not list(validator_for("windows_response").iter_errors(example))


def test_climatology_weather_has_null_ensemble_size() -> None:
    """Spec IV.3: ensemble_size is null in CLIMATOLOGY mode."""
    example = load_example(GOOD_DIR / "weather_probability_response_good_climatology_ensemble_null.json")
    assert example["horizon_label"] == "CLIMATOLOGY"
    assert example["ensemble_size"] is None
    assert not list(validator_for("weather_probability_response").iter_errors(example))