"""The corridor the service reports is the corridor the engine applies. BROWSER_WALK.md, B4.

``GET /v1/site`` and ``provenance_block.corridor`` said 90 to 200 deg, flag ASSUMPTION,
from the API's own site file. The engine reads ``backend/engine/data/site_canso.json``,
whose corridor is 115 to 195 deg, flag DERIVED. The page drew its corridor wedge and ran
its guard from the first while the hazard screen judged rows by the second.

The site record stays the API's. The corridor in it is the engine's whenever the engine
ships a site file, because that is the corridor that decides the answer.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from backend.api.app import create_app
from backend.api.config import Settings
from backend.api.schemas import errors_for

REPO = Path(__file__).resolve().parents[3]
ENGINE_SITE = REPO / "backend" / "engine" / "data" / "site_canso.json"


def engine_corridor() -> dict[str, Any]:
    return json.loads(ENGINE_SITE.read_text(encoding="utf-8"))["corridor"]


def test_the_site_endpoint_reports_the_corridor_of_the_engine_site_file(client: TestClient) -> None:
    engine = engine_corridor()
    body = client.get("/v1/site").json()

    assert errors_for("site_response", body) == []
    assert body["corridor"]["A_min_deg"] == engine["A_min_deg"]
    assert body["corridor"]["A_max_deg"] == engine["A_max_deg"]
    assert body["corridor"]["source"] == engine["source"]
    assert body["corridor"]["flag"] == engine["flags"]["A_min_deg"] == engine["flags"]["A_max_deg"]
    assert body["row_flags"]["corridor_A_min_deg"] == engine["flags"]["A_min_deg"]
    assert body["row_flags"]["corridor_A_max_deg"] == engine["flags"]["A_max_deg"]
    assert "backend/engine/data/site_canso.json" in body["source_files"]


@pytest.mark.live_layers
def test_the_provenance_of_a_window_response_names_the_corridor_the_engine_applied(
    client: TestClient, sso_request: dict[str, Any]
) -> None:
    engine = engine_corridor()
    body = client.post("/v1/windows", json=sso_request).json()
    corridor = body["provenance_block"]["corridor"]

    assert corridor["A_min_deg"] == engine["A_min_deg"]
    assert corridor["A_max_deg"] == engine["A_max_deg"]
    assert corridor["flag"] == engine["flags"]["A_min_deg"]
    assert body["provenance_block"]["row_flags"]["corridor_A_min_deg"] == engine["flags"]["A_min_deg"]
    assert "backend/engine/data/site_canso.json" in body["provenance_block"]["source_files"]
    for row in body["windows"]:
        inside = corridor["A_min_deg"] <= row["azimuth_deg"] <= corridor["A_max_deg"]
        assert (row["screens"]["hazard"] == "pass") == inside, (
            f"azimuth {row['azimuth_deg']}: the screen and the reported corridor must agree"
        )


@pytest.mark.live_layers
def test_a_request_override_still_replaces_the_bound_and_is_flagged(
    client: TestClient, sso_request: dict[str, Any]
) -> None:
    body = client.post("/v1/windows", json={**sso_request, "corridor": {"A_max_deg": 150.0}}).json()
    corridor = body["provenance_block"]["corridor"]

    assert corridor["A_max_deg"] == 150.0
    assert corridor["A_min_deg"] == engine_corridor()["A_min_deg"]
    assert body["provenance_block"]["row_flags"]["corridor_A_max_deg"] == "UNSOURCED_REQUEST_OVERRIDE"


def test_without_an_engine_site_file_the_api_site_record_answers(
    settings: Settings, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """The fallback of the offline floor: the corridor of the API's own record, as before."""
    monkeypatch.setattr(Settings, "engine_site_path", lambda self, site_id: tmp_path / "absent.json")
    own = json.loads(settings.site_path("canso").read_text(encoding="utf-8"))["corridor"]

    with TestClient(create_app(settings)) as client:
        body = client.get("/v1/site").json()

    assert body["corridor"]["A_min_deg"] == own["A_min_deg"]
    assert body["corridor"]["A_max_deg"] == own["A_max_deg"]
    assert body["corridor"]["flag"] == own["flag"]
    assert "backend/engine/data/site_canso.json" not in body["source_files"]
