"""Requests the service used to crash on or to answer although they mean nothing.

Found by the browser walk against the running service and recorded in
frontend/BROWSER_WALK.md, sections B2 and B5:

* a corridor override with one bound gave HTTP 500, and because an unhandled error
  carries no CORS header the browser reported it as a blocked request and the page
  fell back to its fixtures while the user was still typing the second bound;
* ``ltan_hours`` "25:99" and ``raan_tolerance_deg`` 0 were answered with HTTP 200.

Spec IV.7 rule 2: a request the engine cannot interpret is a 422. The frozen request
schema types these fields and does not bound them, so the bounds are checked by the
route, for the live engine and for the offline path alike.
"""

from __future__ import annotations

from typing import Any

import pytest
from fastapi.testclient import TestClient

from backend.api.schemas import errors_for

WINDOWS_SCHEMA = "windows_response"


@pytest.mark.live_layers
@pytest.mark.parametrize("corridor", [{"A_min_deg": 120.0}, {"A_max_deg": 150.0}, {"A_min_deg": None, "A_max_deg": 150.0}])
def test_a_corridor_override_with_one_bound_is_answered_by_the_live_engine(
    client: TestClient, sso_request: dict[str, Any], corridor: dict[str, Any]
) -> None:
    response = client.post("/v1/windows", json={**sso_request, "corridor": corridor})

    assert response.status_code == 200, response.text
    body = response.json()
    assert errors_for(WINDOWS_SCHEMA, body) == []
    assert body["engine_version"] != "stub"


@pytest.mark.live_layers
def test_one_bound_is_completed_with_the_bound_of_the_site(
    client: TestClient, sso_request: dict[str, Any]
) -> None:
    """A_max 150 with the site's lower bound shuts out the southbound SSO azimuth of 191.5 deg."""
    open_corridor = client.post("/v1/windows", json=sso_request).json()
    shut = client.post("/v1/windows", json={**sso_request, "corridor": {"A_max_deg": 150.0}}).json()

    assert open_corridor["reachable"] is True
    assert shut["reachable"] is False
    assert shut["windows"] and all(row["constraint_fired"] == "hazard_area" for row in shut["windows"])


@pytest.mark.parametrize("value", ["25:99", "24:00", "10:60", "noon"])
def test_a_local_time_that_does_not_exist_is_a_422(
    client: TestClient, sso_request: dict[str, Any], value: str
) -> None:
    body = {**sso_request, "target": {"type": "SSO", "ltan_hours": value}}

    response = client.post("/v1/windows", json=body)

    assert response.status_code == 422, response.text
    assert response.json()["error"] == "request_schema_violation"
    assert any("ltan_hours" in violation for violation in response.json()["violations"])


@pytest.mark.parametrize("value", [0, -1.0])
def test_a_plane_tolerance_that_is_not_positive_is_a_422(
    client: TestClient, sso_request: dict[str, Any], value: float
) -> None:
    response = client.post("/v1/windows", json={**sso_request, "raan_tolerance_deg": value})

    assert response.status_code == 422, response.text
    assert any("raan_tolerance_deg" in violation for violation in response.json()["violations"])


@pytest.mark.live_layers
@pytest.mark.parametrize(
    "change",
    [
        {"target": {"type": "SSO", "ltan_hours": "25:99"}},
        {"raan_tolerance_deg": 0},
    ],
)
def test_the_same_requests_are_a_422_with_the_live_engine(
    client: TestClient, sso_request: dict[str, Any], change: dict[str, Any]
) -> None:
    response = client.post("/v1/windows", json={**sso_request, **change})

    assert response.status_code == 422, response.text
    assert "access-control-allow-origin" in {
        key.lower()
        for key in client.post(
            "/v1/windows", json={**sso_request, **change}, headers={"Origin": "http://localhost:5500"}
        ).headers
    }, "a refusal the browser can read, not a blocked request"


@pytest.mark.live_layers
@pytest.mark.parametrize("value", ["00:00", "06:00", "23:59"])
def test_a_valid_local_time_is_still_answered(
    client: TestClient, sso_request: dict[str, Any], value: str
) -> None:
    body = {**sso_request, "target": {"type": "SSO", "ltan_hours": value}}

    assert client.post("/v1/windows", json=body).status_code == 200


@pytest.mark.live_layers
def test_a_positive_tolerance_is_still_answered_and_governs_the_width(
    client: TestClient, sso_request: dict[str, Any]
) -> None:
    one = client.post("/v1/windows", json={**sso_request, "raan_tolerance_deg": 1.0}).json()
    two = client.post("/v1/windows", json={**sso_request, "raan_tolerance_deg": 2.0}).json()

    assert two["windows"][0]["window_width_s"] == pytest.approx(2.0 * one["windows"][0]["window_width_s"], rel=1.0e-6)
