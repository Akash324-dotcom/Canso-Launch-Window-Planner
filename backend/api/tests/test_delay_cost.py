"""``GET /v1/decision/delay-cost``, the optional analysis endpoint of spec II.9 (iv)."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from backend.api import app as app_module
from backend.api.config import Settings


pytestmark = pytest.mark.live_layers


@pytest.fixture()
def client(settings: Settings) -> TestClient:
    with TestClient(app_module.create_app(settings)) as built:
        yield built


def test_a_series_gets_the_expected_extra_days_and_no_cost_without_c_day(client: TestClient) -> None:
    response = client.get("/v1/decision/delay-cost", params={"p": "0.5,0.5,0.5"})

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["expected_extra_days"] == pytest.approx(0.75)
    assert body["p_no_success_in_horizon"] == pytest.approx(0.125)
    assert body["bound"] == "lower"
    assert body["expected_cost"] is None and body["c_day"] is None
    assert body["status"] == "SKETCHED"


def test_a_supplied_c_day_is_multiplied_and_flagged_as_user_supplied(client: TestClient) -> None:
    body = client.get("/v1/decision/delay-cost", params={"p": "0.5,0.5,0.5", "c_day": "2000"}).json()

    assert body["expected_cost"] == pytest.approx(1500.0)
    assert body["c_day_flag"] == "USER_SUPPLIED"


@pytest.mark.parametrize(
    "params",
    [
        {"p": ""},
        {"p": "0.5,,0.2"},
        {"p": "0.5,abc"},
        {"p": "0.5,1.5"},
        {"p": "0.5,-0.1"},
        {"p": "0.5", "c_day": "-1"},
    ],
)
def test_a_bad_request_is_a_422_with_a_message_and_never_a_500(client: TestClient, params: dict) -> None:
    response = client.get("/v1/decision/delay-cost", params=params)

    assert response.status_code == 422, response.text
    assert response.json()["detail"]


def test_a_missing_p_is_a_422(client: TestClient) -> None:
    assert client.get("/v1/decision/delay-cost").status_code == 422


def test_the_window_response_is_not_changed_by_the_extension(client: TestClient) -> None:
    body = client.post(
        "/v1/windows",
        json={
            "target": {"type": "SSO", "h_t_km": 674.0},
            "site": "canso",
            "date_range": {"start": "2026-10-05", "end": "2026-10-06"},
            "vehicle_profile_id": "cyclone4m",
            "include_weather": False,
        },
    ).json()

    assert "expected_cost" not in body and "expected_extra_days" not in body
