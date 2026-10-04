"""E3 Reachability, including the honesty case.

Spec II.2. Direct-ascent plane geometry gives cos(i) = cos(phi_s) sin(beta), the
corridor test of (II.3), and the plane-change penalty of (II.5).

HAND ARITHMETIC FOR THE SPEC TABLE (spec II.2), with phi_s read from
data/site_canso.json rather than written here:

    cos(phi_s)          = cos(45.3 deg)  = 0.70330278
    i = 45.1: cos(45.1) = 0.70587167  ->  sin(beta) = 1.00365 > 1  -> NO REAL SOLUTION
    i = 87.9: cos(87.9) = 0.03664350  ->  sin(beta) = 0.0521016
            beta_southbound = 180 - asin(0.0521016) = 180 - 2.98619 = 177.0138  -> 177.0
    i = 90.0: cos(90.0) = 0            ->  sin(beta) = 0
            beta_southbound = 180 - asin(0)          = 180.0000                -> 180.0
    i = 98.1: cos(98.1) = -0.14090109 ->  sin(beta) = -0.200347
            beta_southbound = 180 - asin(-0.200347) = 180 + 11.5620 = 191.5620 -> 191.6

The branch is unified as beta = 180 - asin(cos(i)/cos(phi_s)) on the southbound
side, which runs continuously from due east (i = phi_s, beta = 90) through due
south (i = 90, beta = 180) to the retrograde azimuths.

PLANE-CHANGE PENALTY (spec II.5), Delta-v = 2 v_c sin(Delta_i / 2):

    The spec quotes v_c = 7.67 km/s at its reference case. Inverting
    v_c = sqrt(GM / (R_e + h)) for that speed gives R_e + h = 6.7766e6 m, that
    is h = 396.9 km. So the reference case is a 400 km circular target, where

        v_c        = sqrt(GM / 6778137) = 7666.05 m/s   (GM from provenance)
        Delta_i    = phi_s - i_t = 45.3 - 45.1 = 0.2 deg
        Delta-v    = 2 * 7666.05 * sin(0.1 deg)     = 26.76 m/s

    which is the spec's 26.8 m/s. The 600 km figure elsewhere in the spec
    belongs to the nodal-drift table, not to this penalty: at 600 km the same
    formula gives 25.15 m/s, which is why the penalty is quoted against a
    400 km target.
"""

from __future__ import annotations

import math

import pytest

from backend.engine import compute_windows, provenance, reachability

SITE = provenance.load_json("site_canso.json")
PHI_S = SITE["latitude_deg"]

SPEC_AZIMUTH_DEG = {
    87.9: 177.0,
    90.0: 180.0,
    98.1: 191.6,
}
PENALTY_REFERENCE_ALTITUDE_KM = 400.0
PENALTY_SPEC_MS = 26.8


def test_site_configuration_carries_the_spec_coordinates():
    assert SITE["latitude_deg"] == pytest.approx(45.3, abs=1e-9)
    assert SITE["longitude_deg"] == pytest.approx(-61.0, abs=1e-9)
    assert SITE["altitude_m"] == pytest.approx(0.0, abs=1e-9)


def test_site_corridor_bounds_are_flagged_with_their_source():
    corridor = SITE["corridor"]
    assert corridor["A_min_deg"] is not None
    assert corridor["A_max_deg"] is not None
    assert corridor["A_min_deg"] < corridor["A_max_deg"]
    assert isinstance(corridor["source"], str) and len(corridor["source"]) > 5
    for bound in ("A_min_deg", "A_max_deg"):
        assert corridor["flags"][bound] in {"VERIFIED", "ASSUMPTION"}


def test_site_config_records_cars_references_and_operating_hours():
    assert SITE["car_references"] == ["602.43", "602.44"]
    assert SITE["operating_hours"]


# --- Azimuth (spec II.2) -----------------------------------------------------


@pytest.mark.parametrize("i_t, expected", sorted(SPEC_AZIMUTH_DEG.items()))
def test_southbound_azimuth_matches_the_spec_table(i_t, expected):
    beta = reachability.launch_azimuth_deg(i_t, PHI_S)
    assert beta is not None
    assert beta == pytest.approx(expected, abs=0.1)


def test_polar_launch_is_three_degrees_east_of_due_south():
    beta = reachability.launch_azimuth_deg(87.9, PHI_S)
    assert 180.0 - beta == pytest.approx(3.0, abs=0.1)


def test_retrograde_launch_is_eleven_point_six_degrees_west_of_due_south():
    beta = reachability.launch_azimuth_deg(98.1, PHI_S)
    assert beta - 180.0 == pytest.approx(11.6, abs=0.1)
    assert beta > 180.0


def test_site_latitude_is_the_minimum_reachable_inclination():
    """Due east from the pad reaches exactly the pad latitude (spec II.2 table)."""
    assert reachability.launch_azimuth_deg(PHI_S, PHI_S) == pytest.approx(90.0, abs=1e-9)
    assert reachability.launch_azimuth_deg(PHI_S - 0.2, PHI_S) is None


def test_northbound_partner_is_the_mirror_of_the_southbound_branch():
    south = reachability.launch_azimuth_deg(87.9, PHI_S)
    north = reachability.northbound_partner_deg(south)
    assert north == pytest.approx(180.0 - south, abs=1e-9)


# --- Reachability predicate (spec II.4, claim ii PROVED) ---------------------


def test_advertised_leo_inclination_is_not_reachable():
    assert reachability.reachable(45.1, PHI_S) is False
    assert reachability.launch_azimuth_deg(45.1, PHI_S) is None


def test_geometric_reachability_interval_is_latitude_to_supplement():
    lo, hi = reachability.geometric_inclination_bounds(PHI_S)
    assert lo == pytest.approx(PHI_S, abs=1e-9)
    assert hi == pytest.approx(180.0 - PHI_S, abs=1e-9)
    assert reachability.reachable(87.9, PHI_S) is True
    assert reachability.reachable(98.1, PHI_S) is True
    assert reachability.reachable(135.0, PHI_S) is False


def test_azimuth_runs_up_to_the_ninety_four_degree_supplement():
    top = reachability.geometric_inclination_bounds(PHI_S)[1]
    assert reachability.launch_azimuth_deg(top, PHI_S) == pytest.approx(270.0, abs=0.1)


# --- Corridor (spec II.3) ----------------------------------------------------


def test_corridor_bounds_bracket_the_advertised_inclinations():
    assert reachability.azimuth_in_corridor(
        reachability.launch_azimuth_deg(98.1, PHI_S), SITE["corridor"]
    )
    assert not reachability.azimuth_in_corridor(
        reachability.launch_azimuth_deg(105.0, PHI_S), SITE["corridor"]
    )


def test_corridor_caps_the_maximum_reachable_inclination():
    """Spec II.2: A_max = 200 deg caps the reachable inclination at about 104 deg."""
    _, capped = reachability.corridor_inclination_bounds(PHI_S, SITE["corridor"])
    assert capped == pytest.approx(103.92, abs=0.1)
    assert reachability.reachable_in_corridor(105.0, PHI_S, SITE["corridor"]) is False
    assert reachability.reachable_in_corridor(98.1, PHI_S, SITE["corridor"]) is True


# --- Plane-change penalty (spec II.5) ----------------------------------------


def test_plane_change_penalty_for_the_advertised_leo_is_the_spec_value():
    dv = reachability.plane_change_dv_ms(45.1, PHI_S, PENALTY_REFERENCE_ALTITUDE_KM)
    assert dv == pytest.approx(PENALTY_SPEC_MS, abs=1.0)


def test_plane_change_penalty_matches_its_closed_form():
    """Delta-v = 2 v_c sin(Delta_i/2), evaluated independently in the test."""
    height_m = PENALTY_REFERENCE_ALTITUDE_KM * 1000.0
    v_c = math.sqrt(provenance.GM / (provenance.R_E + height_m))
    delta_i = math.radians(0.2)
    expected = 2.0 * v_c * math.sin(delta_i / 2.0)
    assert reachability.plane_change_dv_ms(45.1, PHI_S, PENALTY_REFERENCE_ALTITUDE_KM) == (
        pytest.approx(expected, abs=1e-9)
    )


def test_plane_change_penalty_is_zero_for_a_reachable_inclination():
    assert reachability.plane_change_dv_ms(98.1, PHI_S, 674.0) == pytest.approx(0.0, abs=1e-12)


# --- End to end through the frozen seam --------------------------------------


def _request(i_t_deg, h_t_km=400.0, corridor=None):
    body = {
        "target": {"type": "CUSTOM", "h_t_km": h_t_km, "i_t_deg": i_t_deg},
        "site": "canso",
        "date_range": {"start": "2026-10-05", "end": "2026-10-06"},
        "vehicle_profile_id": "cyclone4m",
    }
    if corridor is not None:
        body["corridor"] = corridor
    return body


def test_unreachable_target_returns_false_with_the_penalty_not_an_error():
    response = compute_windows(_request(45.1))
    assert response["reachable"] is False
    assert response["plane_change_dv_ms"] == pytest.approx(PENALTY_SPEC_MS, abs=1.0)
    assert response["windows"] == []


def test_out_of_corridor_azimuth_sets_constraint_fired_hazard_area():
    """i = 105 deg is geometrically reachable but its azimuth exceeds A_max."""
    beta = reachability.launch_azimuth_deg(105.0, PHI_S)
    assert beta > SITE["corridor"]["A_max_deg"]
    response = compute_windows(_request(105.0, h_t_km=600.0))
    assert response["reachable"] is False
    assert response["plane_change_dv_ms"] is None
    assert response["windows"], "the geometric window is still reported, with its reason"
    fired = {row["constraint_fired"] for row in response["windows"]}
    assert fired == {"hazard_area"}
    assert all(row["screens"]["hazard"] == "fail" for row in response["windows"])
    # p_success is composed by the API; the engine's own contribution is the
    # deterministic 0/1 range screen of spec II.8.
    assert all(row["p_success_components"]["range"] == 0.0 for row in response["windows"])
    assert "p_success" not in response["windows"][0]


def test_corridor_override_in_the_request_is_honoured():
    """The contract makes the corridor an optional override; changing it changes reachability."""
    narrow = {"A_min_deg": 100.0, "A_max_deg": 140.0}
    assert compute_windows(_request(98.1, corridor=narrow))["reachable"] is False
    assert compute_windows(_request(98.1))["reachable"] is True