"""Task A1: provenance machinery. Spec II.10 and spec IV shared building blocks.

Every test here is written against the public surface of ``backend.api.provenance``
and against the frozen schemas in ``tests/contract/schemas``, which are the source
of truth under Seam 2 and are never edited from here.
"""

from __future__ import annotations

import copy
import datetime as dt
import json
import re
from pathlib import Path
from typing import Any

import pytest

from backend.api import provenance
from backend.api.config import Settings
from backend.api.errors import UnknownResourceError
from backend.api.provenance import (
    CONSTANT_NAMES,
    REQUIRED_CONSTANTS_FIELDS,
    REQUIRED_PROVENANCE_FIELDS,
    ProvenanceIncomplete,
    assert_complete,
    build_constants_block,
    build_provenance_block,
    canonical_json,
    config_hash,
    load_constants,
    make_citation_id,
    stamp_provenance,
)
from backend.api.schemas import errors_for, load_validator

API_DIR = Path(__file__).resolve().parents[1]

SPEC_VALUES = {
    "J2": 1.08262668e-3,
    "GM": 3.986004418e14,
    "R_e": 6378137.0,
    "omega_sid_rad_s": 7.292115e-5,
    "gmst_model": "IAU_1982",
}


def api_source_files() -> list[Path]:
    """Every module the service ships, excluding the tests themselves."""
    return sorted(
        path
        for path in API_DIR.rglob("*.py")
        if "tests" not in path.relative_to(API_DIR).parts
    )


# --------------------------------------------------------------------------
# constants_block
# --------------------------------------------------------------------------


def test_constants_block_carries_every_constant_with_a_source() -> None:
    constants = load_constants()
    block = build_constants_block(constants, citation_id="run_20261005_0123456789ab")

    assert list(block) == [*CONSTANT_NAMES, "citation_id", "source"]
    for name, expected in SPEC_VALUES.items():
        assert block[name] == expected, name
    assert block["citation_id"] == "run_20261005_0123456789ab"
    assert set(block["source"]) == set(CONSTANT_NAMES)
    for name, source in block["source"].items():
        assert isinstance(source, str) and source.strip(), name


def test_constants_block_validates_against_the_frozen_schema() -> None:
    block = build_constants_block(load_constants(), citation_id="run_20261005_0123456789ab")
    assert errors_for("constants_block", block) == []


def test_no_physical_constant_is_hard_coded_in_service_source() -> None:
    """Spec II.10: constants are configuration, never literals in source."""
    literals = (
        "1.08262668e-3",
        "0.00108262668",
        "3.986004418e14",
        "398600441800000",
        "6378137",
        "7.292115e-5",
        "0.00007292115",
        "IAU_1982",
    )
    offenders: list[str] = []
    for path in api_source_files():
        text = path.read_text(encoding="utf-8")
        for literal in literals:
            if literal in text:
                offenders.append(f"{path.relative_to(API_DIR)} contains {literal}")
    assert not offenders, offenders


def test_no_site_or_target_value_is_hard_coded_in_service_source() -> None:
    """Spec II.10 spirit: site, vehicle and target values are configuration too."""
    literals = ("45.3", "45.1", "87.9", "98.1", "674", "602.43", "602.44")
    offenders: list[str] = []
    for path in api_source_files():
        text = path.read_text(encoding="utf-8")
        for literal in literals:
            if re.search(rf"(?<![\d.]){re.escape(literal)}(?![\d])", text):
                offenders.append(f"{path.relative_to(API_DIR)} contains {literal}")
    assert not offenders, offenders


def test_constants_come_from_the_config_file_on_disk() -> None:
    on_disk = json.loads((API_DIR / "data" / "constants.json").read_text(encoding="utf-8"))
    constants = load_constants()
    for name in CONSTANT_NAMES:
        assert constants.values[name] == on_disk["values"][name], name
        assert constants.sources[name] == on_disk["sources"][name], name
    assert constants.config_path == API_DIR / "data" / "constants.json"


# --------------------------------------------------------------------------
# provenance_block
# --------------------------------------------------------------------------


def build_sample_provenance(settings: Settings, site: str = "canso") -> dict[str, Any]:
    site_doc = settings.site_document(site)
    return build_provenance_block(
        site=site_doc["name"],
        site_document=site_doc,
        corridor_override=None,
        criteria_version="v1",
        vehicle_profile_id="cyclone4m",
        source_files=["backend/api/data/service.json"],
    )


def test_provenance_block_has_every_required_field(settings: Settings) -> None:
    block = build_sample_provenance(settings)
    assert set(block) == set(REQUIRED_PROVENANCE_FIELDS)
    assert block["criteria_version"] == "v1"
    assert block["vehicle_profile_id"] == "cyclone4m"
    assert block["source_files"] == ["backend/api/data/service.json"]


def test_provenance_block_is_populated_from_what_was_read(settings: Settings) -> None:
    site_doc = settings.site_document("canso")
    block = build_sample_provenance(settings)

    assert block["site"]["phi_s_deg"] == site_doc["phi_s_deg"]
    assert block["site"]["lambda_s_deg"] == site_doc["lambda_s_deg"]
    assert block["corridor"]["A_min_deg"] == site_doc["corridor"]["A_min_deg"]
    assert block["corridor"]["A_max_deg"] == site_doc["corridor"]["A_max_deg"]
    assert block["row_flags"] == site_doc["row_flags"]


def test_provenance_source_files_are_files_that_were_actually_read(settings: Settings) -> None:
    block = build_sample_provenance(settings)
    for relative in block["source_files"]:
        assert (settings.root / relative).is_file(), relative


def test_corridor_override_is_reflected_and_flagged_as_unsourced(settings: Settings) -> None:
    site_doc = settings.site_document("canso")
    block = build_provenance_block(
        site=site_doc["name"],
        site_document=site_doc,
        corridor_override={"A_min_deg": 120.0, "A_max_deg": None},
        criteria_version="v1",
        vehicle_profile_id="cyclone4m",
        source_files=["backend/api/data/service.json"],
    )
    assert block["corridor"]["A_min_deg"] == 120.0
    assert block["corridor"]["A_max_deg"] == site_doc["corridor"]["A_max_deg"]
    assert block["row_flags"]["corridor_A_min_deg"] == "UNSOURCED_REQUEST_OVERRIDE"
    assert block["row_flags"]["corridor_A_max_deg"] == site_doc["row_flags"]["corridor_A_max_deg"]


def test_provenance_block_validates_against_the_frozen_schema(settings: Settings) -> None:
    assert errors_for("provenance_block", build_sample_provenance(settings)) == []


# --------------------------------------------------------------------------
# citation_id determinism
# --------------------------------------------------------------------------


def test_citation_id_is_run_date_plus_twelve_hex_digits() -> None:
    citation = make_citation_id(
        effective_request={"date_range": {"start": "2027-03-01", "end": "2027-03-02"}},
        constants_payload={"values": SPEC_VALUES},
        config_payload={"service": {"default_site": "canso"}},
        date_start="2027-03-01",
    )
    assert re.fullmatch(r"run_20270301_[0-9a-f]{12}", citation), citation


def test_citation_date_part_comes_from_the_request_not_from_today() -> None:
    constants_payload = {"values": SPEC_VALUES}
    config_payload = {"service": {"default_site": "canso"}}
    start = "2027-03-01"
    citation = make_citation_id(
        effective_request={"date_range": {"start": start, "end": "2027-03-02"}},
        constants_payload=constants_payload,
        config_payload=config_payload,
        date_start=start,
    )
    today = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%d")
    assert not citation.startswith(f"run_{today}_")
    assert citation.startswith("run_20270301_")


def test_same_request_gives_the_same_citation_id() -> None:
    request = {"target": {"type": "SSO", "h_t_km": 674.0}, "site": "canso"}
    kwargs = {
        "effective_request": request,
        "constants_payload": {"values": SPEC_VALUES},
        "config_payload": {"service": {"default_site": "canso"}},
        "date_start": "2026-10-05",
    }
    assert make_citation_id(**kwargs) == make_citation_id(**kwargs)
    assert make_citation_id(**{**kwargs, "effective_request": copy.deepcopy(request)}) == make_citation_id(**kwargs)


def test_a_different_criteria_version_gives_a_different_citation_id() -> None:
    base = {
        "constants_payload": {"values": SPEC_VALUES},
        "config_payload": {"service": {"default_site": "canso"}},
        "date_start": "2026-10-05",
    }
    first = make_citation_id(effective_request={"criteria_version": "v1"}, **base)
    second = make_citation_id(effective_request={"criteria_version": "v2"}, **base)
    assert first != second


def test_citation_id_changes_with_the_constants_and_with_the_config() -> None:
    base = {
        "effective_request": {"criteria_version": "v1"},
        "config_payload": {"service": {"default_site": "canso"}},
        "date_start": "2026-10-05",
    }
    constants_payload = {"values": SPEC_VALUES}
    baseline = make_citation_id(constants_payload=constants_payload, **base)

    changed_constants = copy.deepcopy(constants_payload)
    changed_constants["values"]["J2"] = 1.08263e-3
    assert make_citation_id(constants_payload=changed_constants, **base) != baseline

    changed_config = copy.deepcopy(base["config_payload"])
    changed_config["service"]["default_site"] = "other"
    assert make_citation_id(constants_payload=constants_payload, **{**base, "config_payload": changed_config}) != baseline


def test_canonical_json_is_key_order_independent() -> None:
    assert canonical_json({"b": 1, "a": {"d": 2, "c": 3}}) == canonical_json({"a": {"c": 3, "d": 2}, "b": 1})
    assert canonical_json({"b": 1, "a": 2}) == '{"a":2,"b":1}'


def test_config_hash_is_stable_and_sensitive() -> None:
    payload = {"service": {"default_site": "canso"}, "fixtures": {"windows": "a.json"}}
    assert config_hash(payload) == config_hash(copy.deepcopy(payload))
    assert config_hash(payload) != config_hash({**payload, "fixtures": {"windows": "b.json"}})
    assert re.fullmatch(r"[0-9a-f]{64}", config_hash(payload))


def test_citation_id_is_not_a_uuid() -> None:
    citation = make_citation_id(
        effective_request={"site": "canso"},
        constants_payload={"values": SPEC_VALUES},
        config_payload={"service": {}},
        date_start="2026-10-05",
    )
    assert re.fullmatch(r"run_\d{8}_[0-9a-f]{12}", citation)
    assert provenance.citation_id_prefix == "run_"


# --------------------------------------------------------------------------
# stamping a response, and the completeness assertion
# --------------------------------------------------------------------------


def test_stamp_provenance_writes_both_blocks_onto_a_response(settings: Settings) -> None:
    effective_request = {
        "target": {"type": "SSO", "h_t_km": 674.0},
        "site": "canso",
        "date_range": {"start": "2026-10-05", "end": "2026-10-15"},
        "vehicle_profile_id": "cyclone4m",
        "criteria_version": "v1",
    }
    stamped, sources = stamp_provenance(
        {"reachable": True, "windows": [], "engine_version": "stub"},
        settings=settings,
        effective_request=effective_request,
        source_files=["backend/fixtures/windows.json"],
    )

    assert stamped["constants_block"]["citation_id"].startswith("run_20261005_")
    assert stamped["provenance_block"]["criteria_version"] == "v1"
    assert stamped["provenance_block"]["vehicle_profile_id"] == "cyclone4m"
    assert "backend/fixtures/windows.json" in stamped["provenance_block"]["source_files"]
    assert sources == stamped["provenance_block"]["source_files"]
    assert errors_for("constants_block", stamped["constants_block"]) == []
    assert errors_for("provenance_block", stamped["provenance_block"]) == []


def test_stamp_provenance_is_deterministic(settings: Settings) -> None:
    effective_request = {
        "target": {"type": "SSO", "h_t_km": 674.0},
        "site": "canso",
        "date_range": {"start": "2026-10-05", "end": "2026-10-15"},
        "vehicle_profile_id": "cyclone4m",
        "criteria_version": "v1",
    }
    engine_body = {"reachable": True, "windows": [], "engine_version": "stub"}
    first, _ = stamp_provenance(
        copy.deepcopy(engine_body), settings=settings, effective_request=effective_request
    )
    second, _ = stamp_provenance(
        copy.deepcopy(engine_body), settings=settings, effective_request=effective_request
    )
    assert canonical_json(first) == canonical_json(second)


def test_stamp_provenance_fails_on_an_unknown_site(settings: Settings) -> None:
    with pytest.raises(UnknownResourceError) as caught:
        stamp_provenance(
            {"reachable": True, "windows": [], "engine_version": "stub"},
            settings=settings,
            effective_request={
                "target": {"type": "SSO"},
                "site": "not-a-site",
                "date_range": {"start": "2026-10-05", "end": "2026-10-15"},
                "vehicle_profile_id": "cyclone4m",
            },
        )
    assert caught.value.status_code == 404
    assert caught.value.resource_kind == "site"
    assert "not-a-site" in caught.value.detail


@pytest.mark.parametrize("missing", REQUIRED_CONSTANTS_FIELDS + REQUIRED_PROVENANCE_FIELDS)
def test_a_response_missing_any_provenance_field_fails_the_assertion_suite(
    settings: Settings, missing: str
) -> None:
    stamped, _ = stamp_provenance(
        {"reachable": True, "windows": [], "engine_version": "stub"},
        settings=settings,
        effective_request={
            "target": {"type": "SSO"},
            "site": "canso",
            "date_range": {"start": "2026-10-05", "end": "2026-10-15"},
            "vehicle_profile_id": "cyclone4m",
        },
    )
    assert_complete(stamped)

    block = "constants_block" if missing in REQUIRED_CONSTANTS_FIELDS else "provenance_block"
    damaged = copy.deepcopy(stamped)
    damaged[block].pop(missing)
    with pytest.raises(ProvenanceIncomplete, match=missing):
        assert_complete(damaged)


def test_a_response_without_the_blocks_fails_the_assertion_suite() -> None:
    with pytest.raises(ProvenanceIncomplete):
        assert_complete({"reachable": True, "windows": []})
    with pytest.raises(ProvenanceIncomplete):
        assert_complete({"constants_block": {}, "provenance_block": {}})


def test_constants_and_provenance_blocks_are_the_frozen_shared_objects() -> None:
    schemas = load_validator("windows_response").schema
    assert schemas["properties"]["constants_block"] == {"$ref": "constants_block.json"}
    assert schemas["properties"]["provenance_block"] == {"$ref": "provenance_block.json"}