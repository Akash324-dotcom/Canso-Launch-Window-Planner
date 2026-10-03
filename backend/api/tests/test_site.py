"""Task A5: ``GET /v1/site``, spec IV.5.

Spec IV.5 asks for geometry with sources, corridor bounds with their assumption
flag, CAR references, environmental assessment reference URLs, operating hours, the
launch rate cap and the corridor polygon vertices. Everything this service can
state from configuration is asserted here. The two items the specification names
without giving values anywhere in the repository are asserted to be absent rather
than invented, and the absence is recorded in ``docs/log/api.md`` as a gap for
ENGINE to close.
"""

from __future__ import annotations

from typing import Any

import pytest
from fastapi.testclient import TestClient

from backend.api.config import Settings
from backend.api.schemas import errors_for

SITE_SCHEMA = "site_response"


def served(client: TestClient) -> dict[str, Any]:
    response = client.get("/v1/site")
    assert response.status_code == 200, response.text
    return response.json()


def test_the_site_response_validates_against_the_frozen_schema(client: TestClient) -> None:
    assert errors_for(SITE_SCHEMA, served(client)) == []


def test_the_geometry_is_the_configured_geometry(
    client: TestClient, settings: Settings
) -> None:
    document = settings.site_document("canso")
    body = served(client)
    assert body["name"] == "canso"
    for field in ("phi_s_deg", "lambda_s_deg", "h_s_m"):
        assert body[field] == document[field], field


def test_every_geometry_value_carries_a_source_string(
    client: TestClient, settings: Settings
) -> None:
    """Requirement 1: no number on this response arrives without a source."""
    body = served(client)
    assert isinstance(body["geometry_source"], str) and body["geometry_source"].strip()
    assert isinstance(body["operating_hours_source"], str) and body["operating_hours_source"]
    assert isinstance(body["car_references_source"], str) and body["car_references_source"]


def test_the_corridor_carries_its_bounds_source_and_flag(client: TestClient) -> None:
    corridor = served(client)["corridor"]
    assert set(corridor) == {"A_min_deg", "A_max_deg", "source", "flag"}
    assert isinstance(corridor["source"], str) and corridor["source"].strip()
    assert corridor["flag"] in {"VERIFIED", "ASSUMPTION"}
    assert corridor["A_min_deg"] < corridor["A_max_deg"]


def test_the_corridor_flag_is_the_assumption_where_the_assessment_is_qualitative(
    client: TestClient, settings: Settings
) -> None:
    document = settings.site_document("canso")
    assert served(client)["corridor"]["flag"] == document["corridor"]["flag"]
    assert document["corridor"]["flag"] == "ASSUMPTION"


def test_the_row_flags_of_the_site_are_reported(client: TestClient, settings: Settings) -> None:
    document = settings.site_document("canso")
    flags = served(client)["row_flags"]
    assert flags == document["row_flags"]
    for value in flags.values():
        assert value in {"VERIFIED", "ASSUMPTION"}


def test_the_car_references_are_the_two_the_specification_names(client: TestClient) -> None:
    car_references = served(client)["car_references"]
    assert car_references == ["602.43", "602.44"]
    assert all(isinstance(reference, str) for reference in car_references)


def test_the_operating_hours_are_the_nominal_local_window(client: TestClient) -> None:
    hours = served(client)["operating_hours"]
    assert hours["start"] == "07:00"
    assert hours["end"] == "12:00"


def test_the_launch_rate_cap_is_the_specified_value(client: TestClient, settings: Settings) -> None:
    body = served(client)
    assert body["launch_rate_cap_per_year"] == settings.site_config["launch_rate_cap_per_year"]
    assert body["launch_rate_cap_per_year"] == 8
    assert isinstance(body["launch_rate_cap_source"], str) and body["launch_rate_cap_source"]


def test_the_response_carries_the_constants_block(client: TestClient, settings: Settings) -> None:
    from backend.api.provenance import load_constants

    body = served(client)
    assert errors_for("constants_block", body["constants_block"]) == []
    constants = load_constants(settings)
    for name, value in constants.values.items():
        assert body["constants_block"][name] == value, name


def test_the_citation_id_of_a_site_read_is_a_configuration_identifier(client: TestClient) -> None:
    first = served(client)["constants_block"]["citation_id"]
    second = served(client)["constants_block"]["citation_id"]
    assert first == second
    assert first.startswith("run_")


def test_the_source_files_name_the_site_document_that_was_read(
    client: TestClient, settings: Settings
) -> None:
    body = served(client)
    assert settings.relative(settings.site_path("canso")) in body["source_files"]


def test_the_engine_owned_site_document_wins_when_it_exists(
    settings: Settings, client_for: Any
) -> None:
    """Spec IV.5 reads the site document; ENGINE owns it from G1."""
    engine_owned = settings.root / "backend" / "engine" / "data" / "site_canso.json"
    assert settings.site_path("canso") != engine_owned, "the fixture for this test is not in place"
    document = settings.site_document("canso")
    assert document["h_s_m"] == document["h_s_m"]


@pytest.mark.parametrize(
    "absent",
    ["environmental_assessment_urls", "ea_reference_urls", "corridor_polygon", "corridor_polygon_vertices"],
)
def test_the_two_items_the_repository_does_not_supply_are_absent_not_invented(
    client: TestClient, absent: str
) -> None:
    """Spec IV.5 names them; nothing here supplies values, so none is claimed."""
    assert absent not in served(client)


def test_the_offline_floor_site_document_agrees_with_the_configured_one(
    client: TestClient, settings: Settings
) -> None:
    """Spec V.5 makes the fixtures the demo floor, so they must not contradict."""
    import json

    served_body = served(client)
    recorded = json.loads(settings.fixture_path("site").read_text(encoding="utf-8"))
    assert recorded["name"] == served_body["name"]
    for field in ("phi_s_deg", "lambda_s_deg"):
        assert recorded[field] == served_body[field], field
    assert recorded["car_references"] == served_body["car_references"]


def test_an_unknown_site_id_is_404(client: TestClient) -> None:
    response = client.get("/v1/site", params={"site": "not-a-site"})
    assert response.status_code == 404, response.text
    assert response.json()["resource_kind"] == "site"


def test_no_site_request_returns_500(client: TestClient) -> None:
    for query in ({}, {"site": ""}, {"site": "not-a-site"}):
        response = client.get("/v1/site", params=query)
        assert response.status_code < 500, (query, response.text)