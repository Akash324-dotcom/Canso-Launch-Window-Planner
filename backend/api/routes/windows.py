"""POST /v1/windows, tasks A2 and A3 of issue #4.

The route does four things and nothing else:

1. validates the body against the frozen schema ``windows_request.json``, because
   that file is the contract for everyone under Seam 2;
2. asks the engine seam for the body, which is ``backend.engine.compute_windows``
   once ENGINE lands and the offline stub until then;
3. composes the weather fields that the engine seam does not own;
4. stamps ``constants_block`` and ``provenance_block`` from configuration.

It never converts a physics answer into an HTTP error. Unreachable, no windows and
constraint fired are 200 with a body, per spec IV.7 rules 1 and 3.
"""

from __future__ import annotations

import copy
from typing import Any

from fastapi import APIRouter, Body, Depends

from backend.api import stubs
from backend.api.config import Settings, get_settings
from backend.api.errors import ContractViolation
from backend.api.request_model import effective_request
from backend.api.schemas import load_schemas, validation_message
from backend.api.schemas import errors_for as schema_errors

router = APIRouter(tags=["windows"])

REQUEST_SCHEMA = "windows_request"
RESPONSE_SCHEMA = "windows_response"


def _engine_compute_windows() -> Any:
    """The live engine seam, or None while ENGINE has not landed.

    Spec IV.7 rule 1 does not change with the answer: an unreachable target is an
    answer whether it came from the engine or from a stub, so this function selects a
    source of numbers and never selects an HTTP status.
    """
    try:
        from backend import engine
    except ImportError:
        return None
    return getattr(engine, "compute_windows", None)


def validate_request_body(body: Any) -> dict[str, Any]:
    """Raise ``ContractViolation`` (422) unless the body satisfies the frozen schema."""
    if not isinstance(body, dict):
        raise ContractViolation(
            "the request body must be a JSON object",
            schema_name=REQUEST_SCHEMA,
            violations=["the request body is not an object"],
        )
    violations = [
        f"/{'/'.join(str(part) for part in error.absolute_path)}: {error.message}"
        for error in schema_errors(REQUEST_SCHEMA, body)
    ]
    if violations:
        raise ContractViolation(
            f"the request body does not satisfy the frozen {REQUEST_SCHEMA}.json schema",
            schema_name=REQUEST_SCHEMA,
            violations=violations,
        )
    return body


def windows_openapi_extra() -> dict[str, Any]:
    """Publish the frozen schemas in the OpenAPI document.

    The generated FastAPI schema for this route would describe a free-form object,
    because the frozen contract is the authority. Publishing the frozen files
    themselves keeps a reader of /v1/openapi.json on exactly the same contract as a
    reader of tests/contract.
    """
    schemas, _ = load_schemas()
    return {
        "requestBody": {
            "required": True,
            "content": {"application/json": {"schema": schemas[REQUEST_SCHEMA]}},
        },
        "responses": {
            "200": {
                "description": (
                    "The physics answer for any well formed request, including an "
                    "unreachable target, an empty window list and a fired constraint."
                ),
                "content": {"application/json": {"schema": schemas[RESPONSE_SCHEMA]}},
            },
            "404": {"description": "Unknown orbit, site or run id."},
            "422": {"description": "The body violates the frozen request schema."},
            "429": {"description": "Rate limit exceeded. Retry-After is set."},
            "503": {
                "description": (
                    "An upstream layer is unreachable and the offline fixture path "
                    "answers instead. Retry-After is set and the body names the path."
                )
            },
        },
    }


@router.post("/windows", openapi_extra=windows_openapi_extra())
def create_windows(
    body: dict[str, Any] = Body(...),
    settings: Settings = Depends(get_settings),
) -> dict[str, Any]:
    """Compute launch windows for one target, site, date range and vehicle."""
    validate_request_body(body)
    request = effective_request(body, settings)

    compute_windows = _engine_compute_windows()
    if compute_windows is not None:
        engine_body = copy.deepcopy(compute_windows(copy.deepcopy(request)))
        engine_version = str(engine_body.get("engine_version") or "engine")
        sources: list[str] = []
    else:
        engine_body = stubs.compute_windows(settings, request)
        engine_version = stubs.STUB_ENGINE_VERSION
        sources = stubs.fixture_sources(settings, request, engine_is_live=False)

    composed = compose_response(engine_body, engine_version, request, settings, sources)
    return composed


def compose_response(
    engine_body: dict[str, Any],
    engine_version: str,
    request: dict[str, Any],
    settings: Settings,
    sources: list[str] | None = None,
) -> dict[str, Any]:
    """Compose the full spec IV.1 response from the engine body.

    The weather fields are composed here, not in the engine, because the seam 1
    signature hands them to the API. Then the two shared blocks are stamped from
    configuration, which is the only place the constants and the site record live.
    """
    from backend.api.provenance import stamp_provenance

    body: dict[str, Any] = {
        "reachable": bool(engine_body["reachable"]),
        "plane_change_dv_ms": engine_body.get("plane_change_dv_ms"),
        "sso_consistency_warning": engine_body.get("sso_consistency_warning"),
        "windows": [],
        "engine_version": engine_version,
        "computation_ms": engine_body.get("computation_ms", 0.0),
    }
    for window in engine_body.get("windows", []):
        row = copy.deepcopy(window)
        row.update(stubs.compose_weather(settings, request, window))
        body["windows"].append(row)

    stamped, _ = stamp_provenance(
        {key: value for key, value in body.items() if key != "computation_ms"},
        settings=settings,
        effective_request=request,
        source_files=sources or [],
    )
    body["constants_block"] = stamped["constants_block"]
    body["provenance_block"] = stamped["provenance_block"]
    return body


def assert_response_valid(body: dict[str, Any]) -> None:
    """Raise ``ValueError`` unless the composed body satisfies the frozen schema."""
    violations = schema_errors(RESPONSE_SCHEMA, body)
    if violations:
        raise ValueError(validation_message(RESPONSE_SCHEMA, body))