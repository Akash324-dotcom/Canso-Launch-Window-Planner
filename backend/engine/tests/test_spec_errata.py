"""Spec errata closure for issue #13. Pins the recomputed figures.

Issue #13 raised two defects in docs/spec/C2_framework_and_build_spec.md that the
engine's own worked examples had exposed:

  1. The two delta(i, phi_s) fixture cells were mutually inconsistent. The pair
     (87.9, +2.37) and (98.1, -8.16) inverts to site latitudes 48.44 N and
     44.92 N respectively, so no single phi_s reproduces both and a reader
     implementing the Test 1 table could not satisfy it. Fixed by naming the
     canonical Canso latitude 45.3 N and recomputing both cells.

  2. window_width_s was half width in one place and full width in another. Fixed
     by stating once, in (II.12) and in the contract schema description, that the
     field carries the FULL width W_window = 2 tau_half.

These tests read the spec text and the contract schema, not the engine constants,
because the defect was in the documentation. A comment that documents the wrong
number is exactly what these catch.

The physics behind the delta figures is derived and proved separately in
docs/physics/ii10_delta.md and backend/engine/tests/test_ii10_delta_derivation.py.
"""

from __future__ import annotations

import json
import math
import pathlib
import re

import pytest

from backend.engine import window

ROOT = pathlib.Path(__file__).resolve().parents[3]
SPEC_PATH = ROOT / "docs" / "spec" / "C2_framework_and_build_spec.md"
SCHEMA_PATH = ROOT / "tests" / "contract" / "schemas" / "windows_response.json"

CANSO_PHI_S_DEG = 45.3
RECOMPUTED = {87.9: 2.12354, 98.1: -8.26891}


@pytest.fixture(scope="module")
def spec_text() -> str:
    return SPEC_PATH.read_text()


def _implied_latitude(inclination_deg: float, delta_deg: float) -> float:
    """The phi_s a delta cell implies, by inverting (II.10) with sin not tan."""
    ratio = math.sin(math.radians(delta_deg)) * math.tan(math.radians(inclination_deg))
    return math.degrees(math.atan(ratio))


# --- 1. delta fixture cells --------------------------------------------------


def test_both_delta_cells_imply_the_one_stated_site_latitude():
    """The acceptance criterion: one phi_s reproduces both cells."""
    latitudes = [_implied_latitude(i, d) for i, d in RECOMPUTED.items()]
    # The cells are published to five decimals, so they agree to about 1e-4 deg
    # rather than bit-exactly. The defect being guarded was a 3.5 deg split.
    spread = max(latitudes) - min(latitudes)
    assert spread < 0.001, (
        f"the delta cells still imply different site latitudes: {latitudes} "
        f"(spread {spread:.4f} deg)"
    )
    mean_latitude = sum(latitudes) / len(latitudes)
    assert mean_latitude == pytest.approx(CANSO_PHI_S_DEG, abs=0.01), (
        f"the cells imply phi_s = {mean_latitude:.4f}, not the stated Canso {CANSO_PHI_S_DEG}"
    )


def test_the_recomputed_cells_match_the_shipped_equation_ii_10():
    """Guard against a future hand edit drifting from window.py."""
    for inclination_deg, expected in RECOMPUTED.items():
        shipped = window.site_node_offset_deg(inclination_deg, CANSO_PHI_S_DEG)
        assert shipped == pytest.approx(expected, abs=0.01), (
            f"spec says delta({inclination_deg}, {CANSO_PHI_S_DEG}) = {expected}, "
            f"engine computes {shipped}"
        )


def test_the_spec_states_phi_s_beside_the_delta_cells(spec_text):
    for inclination_deg, expected in RECOMPUTED.items():
        assert f"{expected:.5f}" in spec_text, (
            f"the recomputed delta {expected:.5f} for i = {inclination_deg} is absent from the spec"
        )
    assert f"phi_s = {CANSO_PHI_S_DEG} N" in spec_text, (
        "the spec must name the site latitude beside the delta cells"
    )


def test_the_superseded_pair_is_not_presented_as_a_live_fixture(spec_text):
    """The old numbers may appear as history, never as the active fixture row."""
    for stale in ("delta = 2.37 deg", "delta = -8.16 deg"):
        assert stale not in spec_text, f"a stale live fixture reads {stale!r}"
    table_rows = [
        line for line in spec_text.splitlines()
        if line.startswith("| delta(i, phi_s) offsets")
    ]
    assert table_rows, "the Test 1 delta row is missing"
    for row in table_rows:
        assert "phi_s = 45.3 N" in row, f"the Test 1 delta row does not state phi_s: {row}"
        assert "2.37" not in row and "-8.16" not in row


def test_the_spec_records_that_the_superseded_pair_was_unsatisfiable(spec_text):
    """A correction with no record reads as an unexplained edit."""
    assert "48.44" in spec_text and "44.92" in spec_text, (
        "the spec must show which latitudes the superseded cells implied"
    )
    assert "issue #13" in spec_text


# --- 2. window width convention ----------------------------------------------


def test_the_spec_states_the_full_width_convention_once_in_ii_12(spec_text):
    assert "WIDTH CONVENTION" in spec_text, "spec (II.12) carries no width convention note"
    convention_paragraph = [
        line for line in spec_text.splitlines() if "WIDTH CONVENTION" in line
    ]
    assert len(convention_paragraph) == 1, "the convention must be stated once, not twice"
    text = spec_text
    assert "window_width_s` is the FULL width" in text
    assert "window_half_width_s" in text, "the half-width field name must be given"
    assert "never the half width tau_half" in text


def test_the_contract_schema_description_states_the_full_width_convention():
    schema = json.loads(SCHEMA_PATH.read_text())
    description = schema["$defs"]["window"]["properties"]["window_width_s"]["description"]
    assert "FULL width" in description
    assert "2 tau_half" in description
    assert "not the half width" in description, (
        "the schema description must state plainly which half is being shipped, "
        "which is the whole point of issue #13"
    )


def test_the_spec_schema_block_flags_the_convention_at_the_point_of_use(spec_text):
    block = re.search(r'"window_width_s": number,(.*)', spec_text)
    assert block, "the spec's inline schema block no longer declares window_width_s"
    assert "FULL width" in block.group(1), (
        "the inline schema comment must carry the convention where a reader meets the field"
    )


def test_the_engine_ships_the_full_width_in_the_named_field():
    """The code already did this; the test exists so the doc and the code agree."""
    tolerance_deg, nodal_rate = 0.1, 0.0
    half = window.window_half_width_s(tolerance_deg, nodal_rate)
    full = window.window_width_s(tolerance_deg, nodal_rate)
    assert full == pytest.approx(2.0 * half, rel=1.0e-12)
    assert half == pytest.approx(23.9345, abs=0.01), "the Test 1 hand case moved"
    assert full == pytest.approx(47.8689, abs=0.02)


def test_the_test_1_width_rows_separate_the_half_from_the_full():
    """The old row said 'Window width' and gave the half, which was the ambiguity."""
    rows = [
        line for line in SPEC_PATH.read_text().splitlines()
        if line.startswith("| Window HALF width") or line.startswith("| Window FULL width")
    ]
    assert len(rows) == 2, f"expected separate half and full rows, found {len(rows)}"
    assert any("tau_half = 23.9345" in row for row in rows)
    assert any("2 tau_half" in row for row in rows)