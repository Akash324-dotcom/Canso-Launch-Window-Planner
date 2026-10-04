"""E11 Provenance echo. Spec II.10 and III.6(b).

Two obligations:

1. ``provenance_block.source_files`` lists EVERY config and data file actually
   read for that run, and no others. Spec II.10: "any number that appears in a
   result and is not computed from this table is a bug".
2. Re-reading those files reproduces the numbers. If a value can change without
   any file changing, or if a number arrives from somewhere the files do not
   name, the provenance chain is broken.

Spec III.6 also requires the response to carry the constants block, the site and
corridor values used, the criteria version and the vehicle profile id with row
flags. The API composes the block, so the engine's obligation is to expose every
piece of it through an importable helper. ``build_provenance_block`` is that
helper, and these tests are the engine's half of the obligation.
"""

from __future__ import annotations

import json

import pytest

from backend.engine import compute_windows, provenance

REQUEST = {
    "target": {"type": "SSO", "h_t_km": 674.0},
    "site": "canso",
    "date_range": {"start": "2026-10-05", "end": "2026-10-09"},
    "vehicle_profile_id": "cyclone4m",
    "criteria_version": "v1",
}

BLOCK_FILES = {
    "backend/engine/data/site_canso.json",
    "backend/engine/data/vehicles/cyclone4m.json",
}
# compose() additionally reads the conjunction fixture, which the block does not.
RUN_FILES = BLOCK_FILES | {"backend/engine/data/tle_fixture.json"}


def test_build_provenance_block_has_exactly_the_contract_fields():
    block = provenance.build_provenance_block(REQUEST)
    assert set(block) == {
        "site",
        "corridor",
        "criteria_version",
        "vehicle_profile_id",
        "row_flags",
        "source_files",
    }


def test_source_files_lists_every_file_the_block_actually_read():
    provenance.reset_source_files()
    block = provenance.build_provenance_block(REQUEST)
    assert set(block["source_files"]) == BLOCK_FILES


def test_source_files_names_files_that_actually_exist_and_parse():
    for relative in provenance.build_provenance_block(REQUEST)["source_files"]:
        path = provenance.DATA_DIR.parent.parent.parent / relative
        assert path.is_file(), f"{relative} does not exist on disk"
        json.loads(path.read_text(encoding="utf-8"))


def test_the_tracker_is_not_leaking_files_from_other_runs():
    """A run that reads no vehicle file must not inherit one from a previous run."""
    provenance.reset_source_files()
    provenance.load_json("site_canso.json")
    assert provenance.source_files() == ["backend/engine/data/site_canso.json"]


def test_build_provenance_block_does_not_reset_a_tracker_the_caller_owns():
    """compose() resets; the block builder must not, or it would lose its reads."""
    provenance.reset_source_files()
    provenance.load_json("site_canso.json")
    provenance.build_provenance_block(REQUEST)
    assert "backend/engine/data/site_canso.json" in provenance.source_files()


def test_compute_windows_records_the_files_it_read():
    provenance.reset_source_files()
    compute_windows(REQUEST)
    assert set(provenance.source_files()) == RUN_FILES


def test_a_different_vehicle_profile_changes_the_files_listed():
    request = dict(REQUEST, vehicle_profile_id="cyclone4m_coast")
    provenance.reset_source_files()
    block = provenance.build_provenance_block(request)
    assert "backend/engine/data/vehicles/cyclone4m_coast.json" in block["source_files"]
    assert "backend/engine/data/vehicles/cyclone4m.json" not in block["source_files"]


def test_the_block_echoes_the_site_and_corridor_actually_used():
    block = provenance.build_provenance_block(REQUEST)
    site = provenance.load_json("site_canso.json")
    assert block["site"]["name"] == site["name"]
    assert block["site"]["latitude_deg"] == site["latitude_deg"]
    assert block["site"]["longitude_deg"] == site["longitude_deg"]
    assert block["corridor"] == site["corridor"]


def test_a_corridor_override_is_echoed_rather_than_the_site_default():
    override = {"A_min_deg": 100.0, "A_max_deg": 140.0}
    provenance.reset_source_files()
    block = provenance.build_provenance_block(dict(REQUEST, corridor=override))
    assert block["corridor"]["A_min_deg"] == 100.0
    assert block["corridor"]["A_max_deg"] == 140.0
    assert block["corridor"]["flags"], "the flags still describe the overridden bounds"
    assert block["corridor"]["assumptions"], "and so do the assumptions"


def test_the_block_echoes_the_criteria_version_and_vehicle_id():
    block = provenance.build_provenance_block(REQUEST)
    assert block["criteria_version"] == "v1"
    assert block["vehicle_profile_id"] == "cyclone4m"


def test_the_block_echoes_the_row_flags_verbatim():
    """Spec III.6(b): the vehicle profile id WITH row flags."""
    block = provenance.build_provenance_block(REQUEST)
    assert block["row_flags"]
    for key, flag in block["row_flags"].items():
        assert flag in {"VERIFIED", "ASSUMPTION"}, f"{key} carries {flag!r}"


def test_row_flags_cover_the_vehicle_and_the_corridor_bounds():
    block = provenance.build_provenance_block(REQUEST)
    assert any(key.startswith("cyclone4m.") for key in block["row_flags"])
    assert "corridor.A_min_deg" in block["row_flags"]
    assert "corridor.A_max_deg" in block["row_flags"]


def test_corridor_bounds_are_reported_as_assumption_until_the_ea_figure_is_read():
    block = provenance.build_provenance_block(REQUEST)
    assert block["row_flags"]["corridor.A_min_deg"] == "ASSUMPTION"
    assert block["row_flags"]["corridor.A_max_deg"] == "ASSUMPTION"


def test_re_reading_the_files_reproduces_the_numbers():
    """Spec II.10 rule of construction: a value must trace to a named row."""
    provenance.reset_source_files()
    first = provenance.build_provenance_block(REQUEST)
    for relative in first["source_files"]:
        json.loads((provenance.DATA_DIR.parent.parent.parent / relative).read_text())
    second = provenance.build_provenance_block(REQUEST)
    assert first == second


def test_recomputing_a_window_twice_from_the_same_files_gives_identical_numbers():
    """Spec III.6(a): byte-compare all numeric fields on a repeated request.

    ``computation_ms`` is a measured wall-clock duration and is excluded: it is
    the one field that cannot be deterministic, and hiding it would defeat the
    purpose of the test rather than satisfy it. Everything else, including every
    window row and every geometric quantity, must match exactly.
    """
    provenance.reset_source_files()
    first = compute_windows(REQUEST)
    provenance.reset_source_files()
    second = compute_windows(REQUEST)
    assert set(first) == set(second)
    for key in first:
        if key == "computation_ms":
            continue
        assert first[key] == second[key], f"{key} is not reproducible"
    assert first["computation_ms"] >= 0.0 and second["computation_ms"] >= 0.0


def test_constants_block_is_built_from_the_constants_module():
    block = provenance.constants_block("run_20261003_deadbeef")
    assert block["J2"] == provenance.J2
    assert block["source"]["J2"]
    assert block["citation_id"] == "run_20261003_deadbeef"


def test_a_corridor_override_that_is_not_a_dict_is_rejected():
    with pytest.raises((ValueError, TypeError, AttributeError)):
        provenance.build_provenance_block(dict(REQUEST, corridor=[90.0, 200.0]))


def test_an_unknown_site_is_rejected_rather_than_defaulted_silently():
    with pytest.raises(ValueError):
        provenance.build_provenance_block(dict(REQUEST, site="baikonur"))