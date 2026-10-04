"""Range closeout: DERIVED Canso bounds reproduce from the committed derivation.

Task: engine/range-closeout. The corridor bounds and the cross-range footprint
axis are DERIVED from geography plus physics (see
backend/engine/data/derive_canso_corridor.py), not published figures. These
tests assert the committed numbers reproduce the derivation exactly, so a
regression in either the data or the script fails loudly.
"""

from __future__ import annotations

import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from backend.engine import provenance, reachability  # noqa: E402
from backend.engine.data import derive_canso_corridor as derivation  # noqa: E402

SITE = provenance.load_json("site_canso.json")
PROFILE = provenance.load_json("vehicles/cyclone4m.json")
PHI_S = SITE["latitude_deg"]


def test_the_derivation_reproduces_the_committed_corridor_bounds():
    a_min, a_max = derivation.derive_corridor_bounds()
    assert SITE["corridor"]["A_min_deg"] == a_min == 115.0
    assert SITE["corridor"]["A_max_deg"] == a_max == 195.0


def test_the_derivation_reproduces_the_committed_cross_range_axis():
    assert derivation.derive_cross_range_km() == PROFILE["hazard_footprint"]["cross_range_km"] == 105.0


def test_derived_bounds_carry_the_derived_flag_not_verified():
    assert SITE["corridor"]["flags"]["A_min_deg"] == "DERIVED"
    assert SITE["corridor"]["flags"]["A_max_deg"] == "DERIVED"
    assert PROFILE["hazard_footprint"]["flags"]["cross_range_km"] == "DERIVED"
    for bound in ("A_min_deg", "A_max_deg"):
        assert SITE["corridor"]["flags"][bound] not in {"VERIFIED", "ASSUMPTION"}


def test_derived_corridor_still_brackets_the_advertised_missions():
    for inclination in (51.6, 87.9, 98.1):
        beta = reachability.launch_azimuth_deg(inclination, PHI_S)
        assert beta is not None
        assert SITE["corridor"]["A_min_deg"] <= beta <= SITE["corridor"]["A_max_deg"]


def test_derived_corridor_caps_the_maximum_reachable_inclination():
    _, capped = reachability.corridor_inclination_bounds(PHI_S, SITE["corridor"])
    assert capped == derivation_expected_cap_deg() == capped
    assert capped == pytest_approx(100.49, 0.1)


def derivation_expected_cap_deg() -> float:
    cos_lat = math.cos(math.radians(PHI_S))
    return math.degrees(math.acos(cos_lat * math.sin(math.radians(195.0))))


def pytest_approx(expected: float, tolerance: float) -> float:
    """Tiny local approx helper so this file needs no pytest import at module scope."""
    return _Approx(expected, tolerance)


class _Approx:
    def __init__(self, expected: float, tolerance: float) -> None:
        self.expected = expected
        self.tolerance = tolerance

    def __eq__(self, other: object) -> bool:
        return isinstance(other, (int, float)) and abs(other - self.expected) <= self.tolerance


def test_cross_range_is_the_ellipse_half_width_at_stage_impact_distance():
    expected = 2000.0 * math.sin(math.radians(3.0))
    assert PROFILE["hazard_footprint"]["cross_range_km"] == round(expected / 5.0) * 5.0


def test_operating_hours_state_no_published_restriction_with_documents_checked():
    hours = SITE["operating_hours"]
    assert hours["utc_window"] == ["00:00", "23:59"]
    assert hours["restriction"] == "none published; engine treats all hours admissible"
    assert isinstance(hours["documents_checked"], list) and len(hours["documents_checked"]) >= 3
    assert "7:00 a.m. and 12:00 p.m." in hours["assumptions"][0]
