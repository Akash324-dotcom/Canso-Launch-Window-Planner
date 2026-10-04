"""Acceptance criterion 2: the frozen schema must validate the engine's output.

`tests/contract/test_engine_schema.py` is listed as this workflow's obligation but
lives in an API-owned directory, so it cannot be written here. This file is the
engine's half of the same obligation and does the part the engine can be held to.

The engine returns the spec IV.1 response MINUS the fields the API composes. So
this test composes those fields the way the API will, validates the RESULT against
the frozen `windows_response.json`, and therefore proves the two halves fit
together. It reads the schema; it never writes to `tests/contract/`.

This is a stronger check than asserting the key set. If the engine ever invents a
field, drops one, or emits a type the schema rejects, this fails.
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

import pytest

jsonschema = pytest.importorskip("jsonschema", reason="jsonschema is a dev dependency")

from jsonschema import Draft202012Validator, FormatChecker  # noqa: E402
from referencing import Registry, Resource  # noqa: E402

from backend.engine import compute_windows, provenance  # noqa: E402

CONTRACT_DIR = Path(__file__).resolve().parents[3] / "tests" / "contract" / "schemas"


@lru_cache(maxsize=None)
def _validator(schema_name: str) -> Draft202012Validator:
    """Build a validator over the frozen schemas, keyed by file name.

    Follows the same registry pattern as the API's own contract tests so the two
    agree on how the shared blocks are referenced.
    """
    resources: list[tuple[str, Resource]] = []
    for path in sorted(CONTRACT_DIR.glob("*.json")):
        contents = json.loads(path.read_text(encoding="utf-8"))
        resource = Resource.from_contents(contents)
        resources.append((path.stem, resource))
        identifier = contents.get("$id")
        if isinstance(identifier, str):
            resources.append((identifier, resource))
    return Draft202012Validator(
        json.loads((CONTRACT_DIR / f"{schema_name}.json").read_text(encoding="utf-8")),
        registry=Registry().with_resources(resources),
        format_checker=FormatChecker(),
    )


# A plausible composition by the API. The values are chosen to exercise the
# schema's constraints, not to make it pass: p_success at both ends of its range,
# and both horizon labels, so that any wrong type or out-of-range value fails.
API_COMPOSITION = {
    "constants_block": provenance.constants_block("run_20261003_abc12345"),
    "provenance_block": None,  # filled per request
}


def _validate(response: dict, request: dict, *, horizon: str, p_success: float) -> None:
    provenance.reset_source_files()
    engine_output = compute_windows(request)
    composed = {
        **engine_output,
        "constants_block": API_COMPOSITION["constants_block"],
        "provenance_block": provenance.build_provenance_block(request),
    }
    for row in composed["windows"]:
        row["p_success"] = p_success
        row["p_success_components"]["weather"] = p_success
        row["horizon_label"] = horizon
        row["forecast_issue_time"] = (
            "2026-10-03T09:00:00Z" if horizon == "FORECAST" else None
        )
    _validator("windows_response").validate(composed)


REQUESTS = {
    "sso_full": {
        "target": {"type": "SSO", "h_t_km": 674.0, "raan_deg": 45.0, "ltan_hours": "10:30"},
        "site": "canso",
        "date_range": {"start": "2026-10-05", "end": "2026-10-15"},
        "vehicle_profile_id": "cyclone4m",
        "corridor": {"A_min_deg": 100.0, "A_max_deg": 140.0},
        "criteria_version": "v1",
        "raan_tolerance_deg": 2.0,
        "include_weather": True,
    },
    "polar_free_raan": {
        "target": {"type": "POLAR", "h_t_km": 600.0, "raan_deg": None},
        "site": "canso",
        "date_range": {"start": "2026-10-05", "end": "2026-10-20"},
        "vehicle_profile_id": "cyclone4m",
    },
    "sso_inconsistent_warning": {
        "target": {"type": "SSO", "h_t_km": 600.0, "i_t_deg": 98.1},
        "site": "canso",
        "date_range": {"start": "2026-10-05", "end": "2026-10-12"},
        "vehicle_profile_id": "cyclone4m",
    },
    "unreachable_honesty_case": {
        "target": {"type": "LEO"},
        "site": "canso",
        "date_range": {"start": "2026-10-05", "end": "2026-10-06"},
        "vehicle_profile_id": "cyclone4m",
    },
    "corridor_blocked": {
        "target": {"type": "CUSTOM", "h_t_km": 600.0, "i_t_deg": 105.0},
        "site": "canso",
        "date_range": {"start": "2026-10-05", "end": "2026-10-06"},
        "vehicle_profile_id": "cyclone4m",
    },
}


@pytest.mark.parametrize("name", sorted(REQUESTS))
def test_composed_response_validates_against_the_frozen_schema(name):
    """The API's fields plus the engine's must satisfy windows_response.json."""
    _validate(REQUESTS[name], REQUESTS[name], horizon="FORECAST", p_success=0.62)


@pytest.mark.parametrize("name", sorted(REQUESTS))
def test_composed_response_validates_in_the_climatology_case(name):
    _validate(REQUESTS[name], REQUESTS[name], horizon="CLIMATOLOGY", p_success=0.41)


@pytest.mark.parametrize("name", sorted(REQUESTS))
def test_composed_response_validates_at_the_range_ends_of_p_success(name):
    """A bad p_success must still be caught by the schema, so prove the check bites."""
    _validate(REQUESTS[name], REQUESTS[name], horizon="FORECAST", p_success=0.0)
    _validate(REQUESTS[name], REQUESTS[name], horizon="FORECAST", p_success=1.0)


@pytest.mark.parametrize("name", sorted(REQUESTS))
def test_engine_output_alone_is_rejected_for_missing_the_api_fields(name):
    """The engine must NOT already carry constants_block or provenance_block."""
    response = compute_windows(REQUESTS[name])
    for key in ("constants_block", "provenance_block"):
        assert key not in response


def test_the_schema_check_actually_bites():
    """Guard against a vacuous test: an unknown top-level field must be rejected."""
    response = compute_windows(REQUESTS["polar_free_raan"])
    composed = {
        **response,
        "constants_block": API_COMPOSITION["constants_block"],
        "provenance_block": provenance.build_provenance_block(REQUESTS["polar_free_raan"]),
        "engine_invented_this_field": 1,
    }
    with pytest.raises(jsonschema.exceptions.ValidationError):
        _validator("windows_response").validate(composed)


def test_every_reachable_case_actually_produces_at_least_one_window():
    """Otherwise the schema check above is vacuously satisfied by an empty list."""
    for name in ("sso_full", "polar_free_raan", "sso_inconsistent_warning", "corridor_blocked"):
        response = compute_windows(REQUESTS[name])
        assert response["windows"], f"{name} produced no window, so the gate is vacuous"


def test_the_honesty_case_produces_no_window_but_does_validate():
    response = compute_windows(REQUESTS["unreachable_honesty_case"])
    assert response["reachable"] is False
    assert response["windows"] == []
    _validate(
        REQUESTS["unreachable_honesty_case"],
        REQUESTS["unreachable_honesty_case"],
        horizon="CLIMATOLOGY",
        p_success=0.0,
    )