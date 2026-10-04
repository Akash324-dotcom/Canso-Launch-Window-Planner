"""Every window row carries the weather of its own date. BROWSER_WALK.md, B3.

The window route asked the weather layer once per response, for the first day of the
date range, and wrote that answer on every row. With the real layer a request starting
on 2026-10-05, a day whose forecast probability is 0.0, returned 0.0 and FORECAST on all
rows up to 2026-10-15, while the layer itself gave 0.706 for the 6th and 0.980 for the
7th and would have labelled the last days CLIMATOLOGY. ``p_success`` was not the
date-resolved probability the specification describes.

The date of a row is the UTC date of its ``t_liftoff_utc``: the date the page asks
``GET /v1/weather/probability`` for when that row is selected, so the row and the
weather panel show the same number. The answers are cached per date under the key the
weather endpoint uses.

The offline path is unchanged: with no weather layer, the one recorded forecast of
``backend/fixtures/weather.json`` serves every row, as ``test_weather.py`` asserts.
"""

from __future__ import annotations

import sys
import types
from typing import Any

import pytest
from fastapi.testclient import TestClient

from backend.api.config import Settings
from backend.api.schemas import errors_for

pytestmark = pytest.mark.live_layers

WINDOWS_SCHEMA = "windows_response"


def request_for(start: str, end: str) -> dict[str, Any]:
    return {
        "target": {"type": "SSO", "h_t_km": 674.0},
        "site": "canso",
        "date_range": {"start": start, "end": end},
        "vehicle_profile_id": "cyclone4m",
        "include_weather": True,
    }


def date_of(row: dict[str, Any]) -> str:
    return row["t_liftoff_utc"][:10]


def test_each_row_carries_the_answer_of_the_layer_for_its_own_date(
    client: TestClient, settings: Settings
) -> None:
    from backend import weather

    body = client.post("/v1/windows", json=request_for("2026-10-05", "2026-10-08")).json()

    assert errors_for(WINDOWS_SCHEMA, body) == []
    dates = sorted({date_of(row) for row in body["windows"]})
    assert len(dates) >= 4
    expected = {
        day: weather.probability(date_iso=day, site="canso", criteria_version=settings.default_criteria_version)
        for day in dates
    }
    for row in body["windows"]:
        answer = expected[date_of(row)]
        components = row["p_success_components"]
        assert components["weather"] == answer["p_launch"], row["t_liftoff_utc"]
        assert row["horizon_label"] == answer["horizon_label"]
        assert row["forecast_issue_time"] == answer["forecast_issue_time"]
        assert row["p_success"] == pytest.approx(answer["p_launch"] * components["range"] * components["conjunction"])
    assert len({expected[day]["p_launch"] for day in dates}) > 1, (
        "the committed forecast differs from day to day, so identical rows would mean one answer was reused"
    )


def test_a_row_past_the_forecast_horizon_is_labelled_climatology(client: TestClient) -> None:
    """The first day's label must not be written on a row the forecast does not reach."""
    body = client.post("/v1/windows", json=request_for("2026-10-05", "2026-10-25")).json()
    by_date = {date_of(row): row for row in body["windows"]}

    assert by_date["2026-10-05"]["horizon_label"] == "FORECAST"
    assert by_date["2026-10-05"]["forecast_issue_time"] is not None
    assert by_date["2026-10-25"]["horizon_label"] == "CLIMATOLOGY"
    assert by_date["2026-10-25"]["forecast_issue_time"] is None


def test_a_row_shows_what_the_weather_endpoint_answers_for_its_date(client: TestClient) -> None:
    """The page asks the weather endpoint for the date of the selected row; the two must agree."""
    body = client.post("/v1/windows", json=request_for("2026-10-05", "2026-10-07")).json()

    for row in body["windows"]:
        panel = client.get("/v1/weather/probability", params={"date": date_of(row), "site": "canso"}).json()
        assert row["p_success_components"]["weather"] == panel["p_launch"]
        assert row["horizon_label"] == panel["horizon_label"]


def stand_in_weather(monkeypatch: pytest.MonkeyPatch, answers: dict[str, Any], calls: list[str]) -> None:
    """A weather layer that answers per date, with the real engine left in place."""

    def probability(date_iso: str, site: str, criteria_version: str | None = None) -> dict[str, Any]:
        calls.append(date_iso)
        answer = answers.get(date_iso, answers.get("*"))
        if isinstance(answer, Exception):
            raise answer
        return {
            "date": date_iso,
            "site": site,
            "criteria_version": "criteria_v1",
            "p_launch": answer,
            "horizon_label": "FORECAST",
            "forecast_issue_time": "2026-10-04T00:00:00Z",
            "ensemble_size": 82,
            "components": [],
            "source": "open_meteo",
        }

    module = types.ModuleType("backend.weather")
    module.probability = probability
    monkeypatch.setitem(sys.modules, "backend.weather", module)


def test_the_layer_is_asked_once_for_each_date_and_not_once_for_each_row(
    settings: Settings, client_for: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[str] = []
    stand_in_weather(monkeypatch, {"*": 0.5}, calls)
    uncached = settings.with_service_overrides("cache", windows_ttl_s=0, weather_ttl_s=0, reads_ttl_s=0)

    with client_for(uncached) as fresh:
        body = fresh.post("/v1/windows", json=request_for("2026-10-05", "2026-10-07")).json()

    dates = sorted({date_of(row) for row in body["windows"]})
    assert len(body["windows"]) > len(dates), "two crossings a day, so rows outnumber dates"
    assert sorted(calls) == dates


def test_a_date_the_layer_fails_on_is_neutral_and_the_other_dates_keep_their_answers(
    settings: Settings, client_for: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[str] = []
    stand_in_weather(
        monkeypatch,
        {"2026-10-05": 0.25, "2026-10-06": RuntimeError("the layer is down for this date"), "*": 0.75},
        calls,
    )
    uncached = settings.with_service_overrides("cache", windows_ttl_s=0, weather_ttl_s=0, reads_ttl_s=0)

    with client_for(uncached) as fresh:
        response = fresh.post("/v1/windows", json=request_for("2026-10-05", "2026-10-07"))

    assert response.status_code == 200, response.text
    body = response.json()
    assert errors_for(WINDOWS_SCHEMA, body) == []
    for row in body["windows"]:
        weather_component = row["p_success_components"]["weather"]
        if date_of(row) == "2026-10-05":
            assert weather_component == 0.25
        elif date_of(row) == "2026-10-06":
            assert weather_component == 1.0, "the neutral value the schema admits"
            assert row["forecast_issue_time"] is None
            assert row["horizon_label"] == "CLIMATOLOGY"
        else:
            assert weather_component == 0.75


def test_excluding_the_weather_layer_asks_for_nothing(
    settings: Settings, client_for: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[str] = []
    stand_in_weather(monkeypatch, {"*": 0.5}, calls)

    with client_for(settings) as fresh:
        body = fresh.post(
            "/v1/windows", json={**request_for("2026-10-05", "2026-10-07"), "include_weather": False}
        ).json()

    assert calls == []
    assert all(row["p_success_components"]["weather"] == 1.0 for row in body["windows"])
    assert all(row["forecast_issue_time"] is None for row in body["windows"])


def test_a_second_request_reads_each_date_from_the_weather_cache(
    settings: Settings, client_for: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[str] = []
    stand_in_weather(monkeypatch, {"*": 0.5}, calls)
    only_weather_cache = settings.with_service_overrides("cache", windows_ttl_s=0, reads_ttl_s=0)

    with client_for(only_weather_cache) as warm:
        first = warm.post("/v1/windows", json=request_for("2026-10-05", "2026-10-07")).json()
        asked = len(calls)
        second = warm.post("/v1/windows", json=request_for("2026-10-05", "2026-10-07")).json()

    assert len(calls) == asked, "the second request made no call to the layer"
    assert [row["p_success"] for row in second["windows"]] == [row["p_success"] for row in first["windows"]]
