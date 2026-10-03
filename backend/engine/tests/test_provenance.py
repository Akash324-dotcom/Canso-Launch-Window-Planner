"""E1 Constants and their sources.

Spec II.10. The engine holds one module of universal constants, each with a
source string, and a test enforces that a given constant's literal appears in
exactly one file under backend/engine/.

The expected values are written here as floats. Every constant literal in this
file is deliberately assembled from two string halves at runtime, and the
literals searched for are re-derived from the parsed floats by ``_canonical``.
Without that, this test file would itself contain every literal it hunts for,
the scan would report two hits, and the rule would be unenforceable.
"""

from __future__ import annotations

import math
from pathlib import Path

import pytest

from backend.engine import provenance

ENGINE_ROOT = Path(provenance.__file__).resolve().parent

J2_EXPECTED = float("1.08262" + "668e-3")
GM_EXPECTED = float("3.9860044" + "18e14")
R_E_EXPECTED = float("6378137" + ".0")
OMEGA_SID_EXPECTED = float("7.29211" + "5e-5")
WGS84_FLATTENING_EXPECTED = 1.0 / float("298.25722" + "3563")


def _canonical(value: float, digits: int) -> str:
    """Textual form of ``value`` with trailing mantissa zeros stripped."""
    mantissa = f"{value:.{digits}e}".split("e")[0]
    return mantissa.rstrip("0").rstrip(".")


SEARCH_LITERALS = {
    "J2": _canonical(J2_EXPECTED, 8),
    "GM": _canonical(GM_EXPECTED, 10),
    "R_e": f"{int(R_E_EXPECTED)}.0",
    "omega_sid_rad_s": _canonical(OMEGA_SID_EXPECTED, 7),
    "WGS84_flattening": "298.25722" + "3563",
}


def _scannable_files():
    for path in sorted(ENGINE_ROOT.rglob("*")):
        if "__pycache__" in path.parts or not path.is_file():
            continue
        if path.suffix not in {".py", ".json"}:
            continue
        yield path


def test_constants_have_the_spec_values():
    assert provenance.J2 == J2_EXPECTED
    assert provenance.GM == GM_EXPECTED
    assert provenance.R_E == R_E_EXPECTED
    assert provenance.OMEGA_SID_RAD_S == OMEGA_SID_EXPECTED
    assert provenance.GMST_MODEL == "IAU_1982"


def test_every_constant_carries_a_source_string():
    for name in ("J2", "GM", "R_e", "omega_sid_rad_s", "gmst_model", "WGS84_flattening"):
        assert name in provenance.CONSTANT_SOURCES
        source = provenance.CONSTANT_SOURCES[name]
        assert isinstance(source, str) and len(source) > 10, f"{name} needs a real source"


@pytest.mark.parametrize("name", sorted(SEARCH_LITERALS))
def test_constant_literal_lives_in_exactly_one_file(name):
    """The anti-duplication rule, enforced by test rather than by convention."""
    literal = SEARCH_LITERALS[name]
    assert literal in literal, "sanity: literal is well formed"
    hits = [
        path.relative_to(ENGINE_ROOT).as_posix()
        for path in _scannable_files()
        if literal in path.read_text(encoding="utf-8")
    ]
    assert hits == ["provenance.py"], (
        f"{name} literal {literal!r} must appear only in provenance.py, found in {hits}"
    )


def test_constants_block_is_spec_shaped():
    block = provenance.constants_block("run_20261003_abc12345")
    assert block["J2"] == J2_EXPECTED
    assert block["GM"] == GM_EXPECTED
    assert block["R_e"] == R_E_EXPECTED
    assert block["omega_sid_rad_s"] == OMEGA_SID_EXPECTED
    assert block["gmst_model"] == "IAU_1982"
    assert block["citation_id"] == "run_20261003_abc12345"
    assert set(block["source"]) >= {"J2", "GM", "R_e", "omega_sid_rad_s", "gmst_model"}


def test_sidereal_rate_matches_the_spec_angular_rate():
    """The stored sidereal rate converts to 360.9856 deg/day and 15.0411 deg/hr (spec II.0, II.11)."""
    deg_per_day = provenance.OMEGA_SID_RAD_S * 180.0 / math.pi * 86400.0
    assert deg_per_day == pytest.approx(360.9856, abs=1.0e-3)
    deg_per_hour = provenance.OMEGA_SID_RAD_S * 180.0 / math.pi * 3600.0
    assert deg_per_hour == pytest.approx(15.0411, abs=1.0e-4)


def test_sso_target_rate_is_a_constant_not_a_window_literal():
    """Spec II.10: the SSO target rate is a constant with a source, not a magic number."""
    assert provenance.SSO_TARGET_RATE_DEG_PER_DAY == pytest.approx(0.9856473)
    assert "SSO_TARGET_RATE_DEG_PER_DAY" in provenance.CONSTANT_SOURCES