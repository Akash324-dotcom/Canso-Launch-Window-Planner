"""Task A6: ``GET /v1/citation`` and the stored run records of spec IV.6.

A run record is written on every ``POST /v1/windows``, and the citation endpoint
reproduces it. The tests below are the contract for that endpoint, field by field,
because gate G0 froze ``tests/contract/schemas`` without a citation schema (G0
interpretation 23) and that directory is not edited from here. The proposal for a
frozen ``citation_response.json`` is recorded in ``docs/log/api.md``.

What a researcher gets is the spec II.10 table serialised, plus the constants, the
configuration hash, the criteria version, the vehicle rows with their flags, the
source files, the engine version and the request. A vehicle row that was never read
is reported as absent rather than invented, which is what spec II.10 requires.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient

from backend.api import citation as run_store
from backend.api.config import Settings

SPEC_IV_6_FIELDS = {"run_id", "engine_version", "generated_at", "items", "bibtex"}
ITEM_FIELDS = {
    "item",
    "value_or_source",
    "hard_coded_or_dynamic",
    "file_or_endpoint",
    "citation",
}
TASK_REQUIRED_FIELDS = {
    "constants",
    "config_hash",
    "criteria_version",
    "vehicle_rows",
    "source_files",
    "engine_version",
    "request",
}

SSO_REQUEST = {
    "target": {"type": "SSO", "h_t_km": 674.0},
    "site": "canso",
    "date_range": {"start": "2026-10-05", "end": "2026-10-15"},
    "vehicle_profile_id": "cyclone4m",
    "include_weather": True,
}


def run_a(client: TestClient, body: dict[str, Any] | None = None) -> dict[str, Any]:
    response = client.post("/v1/windows", json=body or SSO_REQUEST)
    assert response.status_code == 200, response.text
    return response.json()


def citation_of(client: TestClient, citation_id: str) -> dict[str, Any]:
    response = client.get("/v1/citation", params={"id": citation_id})
    assert response.status_code == 200, response.text
    return response.json()


# --------------------------------------------------------------------------
# Storage on every POST
# --------------------------------------------------------------------------


def test_every_post_writes_a_record_named_by_its_citation_id(
    client: TestClient, settings: Settings
) -> None:
    body = run_a(client)
    citation_id = body["constants_block"]["citation_id"]
    path = settings.run_record_path(citation_id)
    assert path.is_file(), path
    assert json.loads(path.read_text(encoding="utf-8"))["citation_id"] == citation_id


def test_the_store_writes_to_the_configured_directory(settings: Settings) -> None:
    assert settings.service["runs_dir"] == "backend/api/data/runs"
    assert Settings.load().runs_dir == settings.root / "backend" / "api" / "data" / "runs"


def test_two_posts_of_the_same_request_write_one_record(
    settings: Settings, client_for: Any, runs_dir: Path
) -> None:
    """The identifier is a hash, so a repeat overwrites rather than accumulates."""
    fresh = settings.with_runs_dir(runs_dir / "one-record")
    with client_for(fresh) as isolated:
        assert not list(fresh.runs_dir.glob("*.json")) if fresh.runs_dir.is_dir() else True
        first = run_a(isolated)
        after_first = sorted(path.name for path in fresh.runs_dir.glob("*.json"))
        second = run_a(isolated)
        after_second = sorted(path.name for path in fresh.runs_dir.glob("*.json"))

    citation_id = first["constants_block"]["citation_id"]
    assert first["constants_block"]["citation_id"] == second["constants_block"]["citation_id"]
    assert after_first == [f"{citation_id}.json"]
    assert after_second == after_first


def test_a_different_criteria_version_writes_a_different_record(
    client: TestClient, settings: Settings
) -> None:
    first = run_a(client, {**SSO_REQUEST, "criteria_version": "v1"})
    second = run_a(client, {**SSO_REQUEST, "criteria_version": "v2"})
    first_id = first["constants_block"]["citation_id"]
    second_id = second["constants_block"]["citation_id"]
    assert first_id != second_id
    assert settings.run_record_path(first_id).is_file()
    assert settings.run_record_path(second_id).is_file()
    assert json.loads(settings.run_record_path(second_id).read_text(encoding="utf-8"))[
        "criteria_version"
    ] == "v2"


def test_the_record_is_json_with_no_trailing_content(
    client: TestClient, settings: Settings
) -> None:
    citation_id = run_a(client)["constants_block"]["citation_id"]
    text = settings.run_record_path(citation_id).read_text(encoding="utf-8")
    assert isinstance(json.loads(text), dict)
    assert text.endswith("\n")


def test_a_run_that_fails_to_validate_writes_nothing(
    client: TestClient, settings: Settings
) -> None:
    before = sorted(path.name for path in settings.runs_dir.glob("*.json"))
    assert client.post("/v1/windows", json={}).status_code == 422
    assert sorted(path.name for path in settings.runs_dir.glob("*.json")) == before


# --------------------------------------------------------------------------
# What the citation endpoint returns
# --------------------------------------------------------------------------


def test_the_citation_carries_every_field_spec_iv_6_names(
    client: TestClient, settings: Settings
) -> None:
    citation_id = run_a(client)["constants_block"]["citation_id"]
    body = citation_of(client, citation_id)
    assert SPEC_IV_6_FIELDS <= set(body)
    assert body["run_id"] == citation_id
    assert body["engine_version"] == "stub"
    assert re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z", body["generated_at"])
    assert isinstance(body["bibtex"], str) and body["bibtex"].strip()


def test_the_citation_carries_every_field_the_task_requires(
    client: TestClient, settings: Settings
) -> None:
    citation_id = run_a(client)["constants_block"]["citation_id"]
    body = citation_of(client, citation_id)
    assert TASK_REQUIRED_FIELDS <= set(body)
    assert re.fullmatch(r"[0-9a-f]{64}", body["config_hash"])
    assert body["criteria_version"] == settings.default_criteria_version
    assert isinstance(body["vehicle_rows"], list)
    assert body["source_files"]
    assert body["request"]["date_range"] == {"start": "2026-10-05", "end": "2026-10-15"}


def test_the_items_are_the_serialised_spec_ii_10_table(
    client: TestClient, settings: Settings
) -> None:
    citation_id = run_a(client)["constants_block"]["citation_id"]
    body = citation_of(client, citation_id)
    assert body["items"]
    for item in body["items"]:
        assert set(item) == ITEM_FIELDS, item["item"]
        assert isinstance(item["item"], str) and item["item"].strip()
        assert isinstance(item["citation"], str) and item["citation"].strip()
        assert isinstance(item["file_or_endpoint"], str) and item["file_or_endpoint"].strip()
        assert item["value_or_source"] is not None
    named = {item["item"] for item in body["items"]}
    for required in ("J2", "GM (mu)", "R_e", "omega_sid", "GMST model"):
        assert required in named, required


def test_the_constants_of_a_citation_are_the_constants_of_the_run(
    client: TestClient, settings: Settings
) -> None:
    """Spec III.6 test 6 clause (c): the citation reproduces the constants exactly."""
    run = run_a(client)
    citation = citation_of(client, run["constants_block"]["citation_id"])
    assert citation["constants_block"] == run["constants_block"]
    assert citation["constants"] == {
        name: run["constants_block"][name]
        for name in ("J2", "GM", "R_e", "omega_sid_rad_s", "gmst_model")
    }


def test_the_citation_reproduces_the_source_files_the_run_read(
    client: TestClient, settings: Settings
) -> None:
    run = run_a(client)
    citation = citation_of(client, run["constants_block"]["citation_id"])
    assert citation["source_files"] == run["provenance_block"]["source_files"]


def test_every_source_file_a_citation_names_exists(
    client: TestClient, settings: Settings
) -> None:
    citation_id = run_a(client)["constants_block"]["citation_id"]
    for relative in citation_of(client, citation_id)["source_files"]:
        assert (settings.root / relative).is_file(), relative


def test_the_config_hash_changes_with_the_configuration(
    client: TestClient, settings: Settings, client_for: Any
) -> None:
    citation_id = run_a(client)["constants_block"]["citation_id"]
    baseline = citation_of(client, citation_id)["config_hash"]
    moved = settings.with_service_overrides("site", launch_rate_cap_per_year=9)
    with client_for(moved) as elsewhere:
        assert run_store.config_hash(moved) != baseline


def test_no_vehicle_row_is_invented_while_engine_has_not_landed(
    client: TestClient, settings: Settings
) -> None:
    citation_id = run_a(client)["constants_block"]["citation_id"]
    body = citation_of(client, citation_id)
    assert body["vehicle_rows"] == []
    assert body["vehicle_profile_id"] == "cyclone4m"
    assert not settings.vehicle_profile_path("cyclone4m").is_file()
    assert settings.relative(settings.vehicle_profile_path("cyclone4m")) not in body["source_files"]


def test_the_request_is_stored_as_effective_and_as_received(
    client: TestClient, settings: Settings
) -> None:
    body = {key: value for key, value in SSO_REQUEST.items() if key != "site"}
    citation_id = run_a(client, body)["constants_block"]["citation_id"]
    stored = citation_of(client, citation_id)
    assert stored["request_body"] == body
    assert stored["request"]["site"] == settings.default_site


def test_the_bibtex_entry_names_no_external_identifier(
    client: TestClient, settings: Settings
) -> None:
    """No DOI was resolved by title for this project, so none may be written here."""
    citation_id = run_a(client)["constants_block"]["citation_id"]
    bibtex = citation_of(client, citation_id)["bibtex"].lower()
    assert "doi" not in bibtex
    assert citation_id in citation_of(client, citation_id)["bibtex"]


# --------------------------------------------------------------------------
# Unknown identifiers
# --------------------------------------------------------------------------


def test_an_unknown_citation_id_is_404_that_says_the_run_was_not_found(
    client: TestClient, settings: Settings
) -> None:
    response = client.get("/v1/citation", params={"id": "run_19700101_deadbeefcafe"})
    assert response.status_code == 404, response.text
    body = response.json()
    assert body["error"] == "unknown_resource"
    assert body["resource_kind"] == "run"
    assert body["resource_id"] == "run_19700101_deadbeefcafe"
    assert "was not found" in body["detail"]


def test_a_citation_id_that_is_not_a_run_id_is_404(client: TestClient) -> None:
    response = client.get("/v1/citation", params={"id": "not-a-run"})
    assert response.status_code == 404, response.text
    assert "was not found" in response.json()["detail"]


def test_a_missing_id_is_422_not_500(client: TestClient) -> None:
    assert client.get("/v1/citation").status_code == 422


def test_an_empty_id_is_422(client: TestClient) -> None:
    assert client.get("/v1/citation", params={"id": ""}).status_code == 422


def test_a_path_traversal_id_is_refused_before_the_filesystem_is_touched(
    client: TestClient, settings: Settings
) -> None:
    """The store is looked up by path, so an identifier is checked before it is used."""
    response = client.get("/v1/citation", params={"id": "../../../etc/passwd"})
    assert response.status_code == 422, response.text
    assert response.json()["error"] == "request_schema_violation"


def test_an_identifier_outside_the_run_store_shape_is_404_not_a_read(
    client: TestClient, settings: Settings
) -> None:
    response = client.get("/v1/citation", params={"id": "not-a-run"})
    assert response.status_code == 404, response.text
    assert "was not found" in response.json()["detail"]


def test_the_citation_endpoint_reaches_the_record_across_a_restart(
    settings: Settings, client_for: Any
) -> None:
    with client_for(settings) as first_process:
        citation_id = run_a(first_process)["constants_block"]["citation_id"]
    with client_for(settings) as second_process:
        assert citation_of(second_process, citation_id)["run_id"] == citation_id


# --------------------------------------------------------------------------
# The store itself
# --------------------------------------------------------------------------


def test_the_store_creates_its_directory(settings: Settings, runs_dir: Path) -> None:
    empty = runs_dir / "not-created-yet" / "deeper"
    assert not empty.exists()
    record = {"citation_id": "run_20261005_000000000000"}
    run_store.write_run(settings.with_runs_dir(empty), record)
    assert (empty / "run_20261005_000000000000.json").is_file()


def test_stored_orbits_ignores_the_preset_classes(client: TestClient, settings: Settings) -> None:
    run_a(client)
    assert [orbit.orbit_id for orbit in run_store.stored_orbits(settings)] == []