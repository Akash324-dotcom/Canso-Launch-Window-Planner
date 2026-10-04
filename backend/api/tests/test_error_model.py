"""Task A2: the app skeleton and the error model of spec IV.7.

Spec IV.7 rule 1 and rule 3 are the load-bearing rules here: a physics answer,
including "unreachable", "no windows" and "constraint fired", is HTTP 200 with a
body, and only the four conditions of rule 2 may produce a 4xx or 5xx. A
malformed body must be 422 and never 500.
"""

from __future__ import annotations

import json
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.api import app as app_module
from backend.api import stubs
from backend.api.config import Settings
from backend.api.errors import RateLimitExceeded, UnknownResourceError, UpstreamUnavailable
from backend.api.schemas import errors_for


def scratch_client() -> TestClient:
    """A client over the real exception handlers with routes that raise them.

    The 404 for an orbit id, the 429 and the 503 belong to endpoints that tasks
    A5, A6 and A7 add. Driving the production handlers directly keeps those
    branches covered now instead of leaving them untested until later.
    """
    scratch = FastAPI(openapi_url=None)
    app_module.register_exception_handlers(scratch)

    @scratch.get("/probe/unknown-orbit/{orbit_id}")
    def unknown_orbit(orbit_id: str) -> None:
        raise UnknownResourceError("orbit", orbit_id)

    @scratch.get("/probe/unknown-run/{run_id}")
    def unknown_run(run_id: str) -> None:
        raise UnknownResourceError("run", run_id)

    @scratch.get("/probe/rate-limit")
    def rate_limit() -> None:
        raise RateLimitExceeded("request budget spent", retry_after_s=60)

    @scratch.get("/probe/upstream-down")
    def upstream_down() -> None:
        raise UpstreamUnavailable(
            "weather layer unreachable; the offline fixture path answers instead",
            retry_after_s=30,
            fixture_path="backend/fixtures/weather.json",
            layer="weather",
        )

    return TestClient(scratch, raise_server_exceptions=False)


# --------------------------------------------------------------------------
# OpenAPI
# --------------------------------------------------------------------------


def test_openapi_is_served_at_the_versioned_path(client: TestClient) -> None:
    response = client.get("/v1/openapi.json")
    assert response.status_code == 200
    document = response.json()
    assert document["openapi"].startswith("3.")
    assert "/v1/windows" in document["paths"]


def test_openapi_request_body_is_the_frozen_request_schema(client: TestClient) -> None:
    document = client.get("/v1/openapi.json").json()
    operation = document["paths"]["/v1/windows"]["post"]
    served = operation["requestBody"]["content"]["application/json"]["schema"]
    frozen = json.loads(
        (app_module.REPO_ROOT / "tests" / "contract" / "schemas" / "windows_request.json").read_text(
            encoding="utf-8"
        )
    )
    assert served == frozen


def test_openapi_success_response_is_the_frozen_response_schema(client: TestClient) -> None:
    document = client.get("/v1/openapi.json").json()
    operation = document["paths"]["/v1/windows"]["post"]
    served = operation["responses"]["200"]["content"]["application/json"]["schema"]
    frozen = json.loads(
        (app_module.REPO_ROOT / "tests" / "contract" / "schemas" / "windows_response.json").read_text(
            encoding="utf-8"
        )
    )
    assert served == frozen


FROZEN_RESPONSE_SCHEMAS = {
    ("/v1/weather/probability", "get"): "weather_probability_response",
    ("/v1/validation/skill", "get"): "skill_response",
    ("/v1/site", "get"): "site_response",
    ("/v1/orbits/{orbit_id}/ephemeris", "get"): "ephemeris_response",
}


def test_every_endpoint_is_served_under_the_versioned_prefix(client: TestClient) -> None:
    document = client.get("/v1/openapi.json").json()
    assert sorted(document["paths"]) == sorted(
        [
            "/v1/citation",
            "/v1/decision/delay-cost",
            "/v1/health",
            "/v1/orbits/{orbit_id}/ephemeris",
            "/v1/site",
            "/v1/validation/skill",
            "/v1/weather/probability",
            "/v1/windows",
        ]
    )


@pytest.mark.parametrize(("path", "method"), sorted(FROZEN_RESPONSE_SCHEMAS))
def test_every_read_endpoint_publishes_its_frozen_schema(
    client: TestClient, path: str, method: str
) -> None:
    """Seam 2 holds for the readers of the OpenAPI document as well."""
    document = client.get("/v1/openapi.json").json()
    served = document["paths"][path][method]["responses"]["200"]["content"]["application/json"]["schema"]
    frozen = json.loads(
        (app_module.REPO_ROOT / "tests" / "contract" / "schemas" / f"{FROZEN_RESPONSE_SCHEMAS[(path, method)]}.json").read_text(
            encoding="utf-8"
        )
    )
    assert served == frozen


def test_every_endpoint_documents_the_four_statuses_of_rule_two(client: TestClient) -> None:
    document = client.get("/v1/openapi.json").json()
    for path, operations in document["paths"].items():
        if path == "/v1/health":
            continue
        for method, operation in operations.items():
            responses = operation["responses"]
            for status in ("404", "422", "429", "503"):
                assert status in responses, (path, method, status)


# --------------------------------------------------------------------------
# Rule 1: physics answers are 200
# --------------------------------------------------------------------------


def test_well_formed_post_returns_200(client: TestClient, sso_request: dict[str, Any]) -> None:
    response = client.post("/v1/windows", json=sso_request)
    assert response.status_code == 200, response.text
    assert errors_for("windows_response", response.json()) == []


def test_unreachable_target_is_200_with_a_computed_plane_change_penalty(
    client: TestClient, leo_request: dict[str, Any]
) -> None:
    """Spec III.5 pass criteria: 200, reachable false, penalty within 1 m/s of (II.5)."""
    response = client.post("/v1/windows", json=leo_request)
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["reachable"] is False
    assert abs(body["plane_change_dv_ms"] - 26.8) <= 1.0, body["plane_change_dv_ms"]
    assert body["constants_block"]["citation_id"]


def test_reachable_with_no_windows_is_200(client: TestClient, sso_request: dict[str, Any]) -> None:
    empty = {"reachable": True, "windows": []}
    original = stubs.load_windows_document
    stubs.load_windows_document = lambda settings: empty  # type: ignore[assignment]
    try:
        response = client.post("/v1/windows", json=sso_request)
    finally:
        stubs.load_windows_document = original
    assert response.status_code == 200, response.text
    assert response.json()["windows"] == []
    assert response.json()["reachable"] is True


def test_constraint_fired_is_200_and_never_an_http_error(
    client: TestClient, sso_request: dict[str, Any]
) -> None:
    original = stubs.load_windows_document
    document = json.loads(
        (Settings.load().fixture_path("windows")).read_text(encoding="utf-8")
    )
    document["windows"][0]["constraint_fired"] = "hazard_area"
    document["windows"][0]["screens"]["hazard"] = "fail"
    stubs.load_windows_document = lambda settings: document  # type: ignore[assignment]
    try:
        response = client.post("/v1/windows", json=sso_request)
    finally:
        stubs.load_windows_document = original
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["windows"][0]["constraint_fired"] == "hazard_area"
    assert body["windows"][0]["screens"]["hazard"] == "fail"
    assert errors_for("windows_response", body) == []


# --------------------------------------------------------------------------
# Rule 2: malformed input is 422, never 500
# --------------------------------------------------------------------------


MALFORMED_BODIES: dict[str, Any] = {
    "empty_object": {},
    "missing_target": {"date_range": {"start": "2026-10-05", "end": "2026-10-15"}, "vehicle_profile_id": "cyclone4m"},
    "missing_date_range": {"target": {"type": "LEO"}, "vehicle_profile_id": "cyclone4m"},
    "missing_vehicle_profile_id": {"target": {"type": "LEO"}, "date_range": {"start": "2026-10-05", "end": "2026-10-15"}},
    "target_without_type": {"target": {}, "date_range": {"start": "2026-10-05", "end": "2026-10-15"}, "vehicle_profile_id": "cyclone4m"},
    "custom_without_inclination": {
        "target": {"type": "CUSTOM", "h_t_km": 600.0},
        "date_range": {"start": "2026-10-05", "end": "2026-10-15"},
        "vehicle_profile_id": "cyclone4m",
    },
    "bad_date_format": {
        "target": {"type": "LEO"},
        "date_range": {"start": "05-10-2026", "end": "2026-10-15"},
        "vehicle_profile_id": "cyclone4m",
    },
    "unknown_target_type": {
        "target": {"type": "GEO"},
        "date_range": {"start": "2026-10-05", "end": "2026-10-15"},
        "vehicle_profile_id": "cyclone4m",
    },
    "unfrozen_extra_field": {
        "target": {"type": "LEO"},
        "date_range": {"start": "2026-10-05", "end": "2026-10-15"},
        "vehicle_profile_id": "cyclone4m",
        "unfrozen": True,
    },
    "include_weather_wrong_type": {
        "target": {"type": "LEO"},
        "date_range": {"start": "2026-10-05", "end": "2026-10-15"},
        "vehicle_profile_id": "cyclone4m",
        "include_weather": "yes",
    },
}


@pytest.mark.parametrize("body", list(MALFORMED_BODIES.values()), ids=list(MALFORMED_BODIES))
def test_malformed_body_returns_422_not_500(client: TestClient, body: Any) -> None:
    response = client.post("/v1/windows", json=body)
    assert response.status_code == 422, response.text
    detail = response.json()["detail"]
    assert isinstance(detail, str) and detail


@pytest.mark.parametrize("raw", ["not json at all", "[1, 2, 3]", "null", '"a string"'])
def test_a_body_that_is_not_a_json_object_returns_422(client: TestClient, raw: str) -> None:
    response = client.post("/v1/windows", content=raw, headers={"content-type": "application/json"})
    assert response.status_code == 422, response.text
    assert response.json()["error"]


def test_validation_error_body_names_the_frozen_schema(client: TestClient) -> None:
    response = client.post("/v1/windows", json={})
    body = response.json()
    assert body["error"] == "request_schema_violation"
    assert body["schema_name"] == "windows_request"
    assert body["violations"]


# --------------------------------------------------------------------------
# Rule 2: 404 for unknown orbit, site and run ids
# --------------------------------------------------------------------------


def test_unknown_site_id_returns_404_with_a_json_detail(client: TestClient, sso_request: dict[str, Any]) -> None:
    response = client.post("/v1/windows", json={**sso_request, "site": "not-a-site"})
    assert response.status_code == 404, response.text
    body = response.json()
    assert body["error"] == "unknown_resource"
    assert body["resource_kind"] == "site"
    assert body["resource_id"] == "not-a-site"
    assert isinstance(body["detail"], str) and body["detail"]


@pytest.mark.parametrize("resource_kind", ["orbit", "run"])
def test_unknown_orbit_and_run_ids_return_404_with_a_json_detail(resource_kind: str) -> None:
    response = scratch_client().get(f"/probe/unknown-{resource_kind}/does-not-exist")
    assert response.status_code == 404, response.text
    body = response.json()
    assert body["error"] == "unknown_resource"
    assert body["resource_kind"] == resource_kind
    assert body["resource_id"] == "does-not-exist"


# --------------------------------------------------------------------------
# Rule 2: 429 and 503 carry Retry-After
# --------------------------------------------------------------------------


def test_rate_limit_returns_429_with_retry_after() -> None:
    response = scratch_client().get("/probe/rate-limit")
    assert response.status_code == 429, response.text
    assert int(response.headers["retry-after"]) > 0
    body = response.json()
    assert body["error"] == "rate_limit_exceeded"
    assert body["retry_after_s"] == int(response.headers["retry-after"])


def test_upstream_outage_returns_503_with_retry_after_and_the_fixture_path_active() -> None:
    response = scratch_client().get("/probe/upstream-down")
    assert response.status_code == 503, response.text
    assert int(response.headers["retry-after"]) > 0
    body = response.json()
    assert body["error"] == "upstream_unavailable"
    assert body["fixture_path_active"] is True
    assert body["offline_fixture_path"] == "backend/fixtures/weather.json"
    assert body["layer"] == "weather"


def test_unreadable_offline_fixture_reports_503_and_names_the_configured_path(settings: Settings) -> None:
    """The outage branch of the real route, not only of the probe."""
    broken = settings.with_fixture_overrides(windows="backend/fixtures/absent-windows.json")
    with TestClient(app_module.create_app(broken)) as client:
        response = client.post(
            "/v1/windows",
            json={
                "target": {"type": "SSO", "h_t_km": 674.0},
                "date_range": {"start": "2026-10-05", "end": "2026-10-15"},
                "vehicle_profile_id": "cyclone4m",
            },
        )
    assert response.status_code == 503, response.text
    body = response.json()
    assert int(response.headers["retry-after"]) > 0
    assert body["fixture_path_active"] is True
    assert body["offline_fixture_path"] == "backend/fixtures/absent-windows.json"


# --------------------------------------------------------------------------
# Nothing becomes a bare 500
# --------------------------------------------------------------------------


def test_an_unexpected_failure_is_reported_as_json_not_as_a_bare_500() -> None:
    scratch = FastAPI(openapi_url=None)
    app_module.register_exception_handlers(scratch)

    @scratch.get("/probe/boom")
    def boom() -> None:
        raise RuntimeError("an unexpected internal failure")

    with TestClient(scratch, raise_server_exceptions=False) as client:
        response = client.get("/probe/boom")
    assert response.status_code == 500
    assert response.json()["error"] == "internal_error"
    assert isinstance(response.json()["detail"], str)


@pytest.mark.parametrize("body", list(MALFORMED_BODIES.values()), ids=list(MALFORMED_BODIES))
def test_no_malformed_body_ever_reaches_500(client: TestClient, body: Any) -> None:
    with TestClient(app_module.create_app(Settings.load()), raise_server_exceptions=False) as strict:
        response = strict.post("/v1/windows", json=body)
    assert response.status_code < 500, response.text