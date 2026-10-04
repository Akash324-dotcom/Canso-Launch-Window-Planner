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
import importlib
from typing import Any

from fastapi import APIRouter, Body, Depends, Request

from backend.api import citation as run_store
from backend.api import stubs
from backend.api.cache import CacheRegistry, cache_key
from backend.api.config import Settings, get_settings
from backend.api.errors import ContractViolation
from backend.api.limits import POST_WINDOWS_BUCKET
from backend.api.middleware import rate_limited
from backend.api.orbits import RegisteredOrbit, orbit_id_for_target
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
        engine = importlib.import_module("backend.engine")
    except ImportError:
        return None
    return getattr(engine, "compute_windows", None)


def _bound_violations(body: dict[str, Any]) -> list[str]:
    """Values the frozen schema types but does not bound, and that mean nothing out of bounds.

    The schema is frozen, so these two bounds live here. Without them the service
    answered ``ltan_hours`` "25:99" with windows for a node time that does not exist,
    and ``raan_tolerance_deg`` 0 with windows of no width (spec II.12: the width is
    twice the tolerance over the sweep rate). Spec IV.7 rule 2 makes both a 422.
    """
    violations: list[str] = []
    target = body.get("target")
    ltan = target.get("ltan_hours") if isinstance(target, dict) else None
    if isinstance(ltan, str):
        text = ltan.strip()
        valid = False
        if ":" in text:
            hours, _, minutes = text.partition(":")
            valid = hours.isdigit() and minutes.isdigit() and int(hours) <= 23 and int(minutes) <= 59
        else:
            try:
                valid = 0.0 <= float(text) < 24.0
            except ValueError:
                valid = False
        if not valid:
            violations.append(
                f"/target/ltan_hours: {ltan!r} is not a local time; expected HH:MM from 00:00 to 23:59"
            )
    tolerance = body.get("raan_tolerance_deg")
    if isinstance(tolerance, (int, float)) and not isinstance(tolerance, bool) and not tolerance > 0:
        violations.append(
            f"/raan_tolerance_deg: {tolerance!r} is not greater than 0; the tolerance governs the window width"
        )
    return violations


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
    out_of_bounds = _bound_violations(body)
    if out_of_bounds:
        raise ContractViolation(
            "the request body is well formed but holds a value the engine cannot interpret",
            schema_name=REQUEST_SCHEMA,
            violations=out_of_bounds,
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


WINDOWS_CACHE = "windows"


@router.post(
    "/windows",
    openapi_extra=windows_openapi_extra(),
    dependencies=[Depends(rate_limited(POST_WINDOWS_BUCKET))],
)
def create_windows(
    body: dict[str, Any] = Body(...),
    http_request: Request = None,  # type: ignore[assignment]
    settings: Settings = Depends(get_settings),
) -> dict[str, Any]:
    """Compute launch windows for one target, site, date range and vehicle."""
    validate_request_body(body)
    request = effective_request(body, settings)
    registry = _cache_registry(http_request)

    key = cache_key(WINDOWS_CACHE, request)
    entry = registry[WINDOWS_CACHE].get(key) if registry is not None else None
    if entry is not None:
        return copy.deepcopy(entry.value)

    # Spec IV.7 rule 2: an unknown site id is a 404. The check is made here so that it
    # holds for the engine as for the stub; the engine raises ValueError for a site it
    # has no file for, which is not an answer a client can read.
    settings.site_path(str(request["site"]))

    compute_windows = _engine_compute_windows()
    if compute_windows is not None:
        engine_body = copy.deepcopy(compute_windows(copy.deepcopy(request)))
        engine_version = str(engine_body.get("engine_version") or "engine")
        engine_is_live = True
    else:
        engine_body = stubs.compute_windows(settings, request)
        engine_version = stubs.STUB_ENGINE_VERSION
        engine_is_live = False

    composed = compose_response(
        engine_body, engine_version, request, settings, registry=registry, engine_is_live=engine_is_live
    )
    store_run(settings, body, request, composed, http_request)
    if registry is not None:
        registry[WINDOWS_CACHE].put(key, composed)
    return composed


def store_run(
    settings: Settings,
    body: dict[str, Any],
    request: dict[str, Any],
    composed: dict[str, Any],
    http_request: Request | None = None,
) -> RegisteredOrbit:
    """Record the run and the orbit id it created, spec IV.6.

    The record is the durable half of the identifier: it is what
    ``GET /v1/citation`` reads and what makes a custom orbit id resolvable after a
    restart, because spec IV.2 expects a POST to create orbit ids implicitly and the
    frozen response schema has no field in which to return one.
    """
    orbit = _record_orbit(settings, request, composed)
    run_store.write_run(
        settings,
        run_store.build_run_record(
            settings=settings,
            body=body,
            effective_request=request,
            constants_block=composed["constants_block"],
            provenance_block=composed["provenance_block"],
            engine_version=composed["engine_version"],
            orbit_id=orbit.orbit_id if orbit is not None else None,
        ),
    )
    if orbit is not None and http_request is not None:
        http_request.app.state.orbits.register(orbit)
    return orbit


def _record_orbit(
    settings: Settings, request: dict[str, Any], composed: dict[str, Any]
) -> RegisteredOrbit | None:
    """The orbit this run describes, or None when the target could not be resolved."""
    try:
        resolved = stubs.resolve_target(settings, request["target"])
    except (KeyError, ValueError, TypeError):
        return None
    return RegisteredOrbit(
        orbit_id=orbit_id_for_target(settings, resolved),
        i_t_deg=float(resolved["i_t_deg"]),
        h_t_km=None if resolved.get("h_t_km") is None else float(resolved["h_t_km"]),
        preset=None,
        citation_id=str(composed["constants_block"]["citation_id"]),
        source_files=tuple(composed["provenance_block"]["source_files"]),
    )


def _cache_registry(request: Request) -> CacheRegistry | None:
    """The application's cache registry, when the application has one."""
    return getattr(request.app.state, "cache_registry", None)


def compose_response(
    engine_body: dict[str, Any],
    engine_version: str,
    request: dict[str, Any],
    settings: Settings,
    registry: CacheRegistry | None = None,
    engine_is_live: bool = False,
    sources: list[str] | None = None,
) -> dict[str, Any]:
    """Compose the full spec IV.1 response from the engine body.

    The weather fields are composed here, not in the engine, because the seam 1
    signature hands them to the API. Then the two shared blocks are stamped from
    configuration, which is the only place the constants and the site record live.
    """
    from backend.api.provenance import stamp_provenance
    from backend.api.weather import CRITERIA_VERSION_MISSING, compose_window_row, window_weather

    body: dict[str, Any] = {
        "reachable": bool(engine_body["reachable"]),
        "plane_change_dv_ms": engine_body.get("plane_change_dv_ms"),
        "sso_consistency_warning": engine_body.get("sso_consistency_warning"),
        "windows": [],
        "engine_version": engine_version,
        "computation_ms": engine_body.get("computation_ms", 0.0),
    }
    document, weather_origin = window_weather(settings, request, registry)
    for window in engine_body.get("windows", []):
        row = copy.deepcopy(window)
        row.update(compose_window_row(document, window))
        if weather_origin == CRITERIA_VERSION_MISSING and row.get("constraint_fired") is None:
            # A constraint the engine fired on the row is kept: it stopped the row first.
            row["constraint_fired"] = CRITERIA_VERSION_MISSING
        body["windows"].append(row)

    if sources is None:
        sources = stubs.fixture_sources(
            settings, request, engine_is_live=engine_is_live, weather_origin=weather_origin
        )

    stamped, _ = stamp_provenance(
        {key: value for key, value in body.items() if key != "computation_ms"},
        settings=settings,
        effective_request=request,
        source_files=sources,
    )
    body["constants_block"] = stamped["constants_block"]
    body["provenance_block"] = stamped["provenance_block"]
    return body


def assert_response_valid(body: dict[str, Any]) -> None:
    """Raise ``ValueError`` unless the composed body satisfies the frozen schema."""
    violations = schema_errors(RESPONSE_SCHEMA, body)
    if violations:
        raise ValueError(validation_message(RESPONSE_SCHEMA, body))