"""The admissible launch direction is a property of the site, held in its file.

``docs/physics/ii10_delta_hazard_policy.md`` section 9 found that the hazard screen refused every
azimuth outside 90 to 270 deg at every site, by a constant in the code whose reason
cited the Canso environmental assessment. That statement is a fact about Canso. It
now lives in ``site_canso.json`` as ``corridor.direction_policy`` with its source,
and a site whose file states no such policy is judged by its corridor alone.
"""

from __future__ import annotations

import inspect

import pytest

from backend.engine import compute_windows, provenance, reachability, screens

CANSO = provenance.load_json("site_canso.json")
PROFILE = provenance.load_json("vehicles/cyclone4m.json")
GATE_SITES = ("kourou_ela1", "plesetsk_133", "vandenberg_slc4e")


# --- The policy is data --------------------------------------------------------


def test_the_canso_file_states_its_direction_policy_with_a_source():
    policy = CANSO["corridor"]["direction_policy"]

    assert policy["admitted_branch"] == "southbound"
    assert policy["flag"] == "VERIFIED"
    assert "Registration Document" in policy["source"]
    assert "2.2.5" in policy["source"]


def test_the_screen_holds_no_site_in_its_source():
    source = inspect.getsource(screens)

    assert "Canso" not in source
    assert not hasattr(screens, "_is_southbound")


@pytest.mark.parametrize("site", GATE_SITES)
def test_a_gate_site_states_no_direction_policy(site):
    """No published statement on direction was located for the gate sites, so none is written."""
    corridor = provenance.load_json(f"sites/{site}.json")["corridor"]

    assert "direction_policy" not in corridor


# --- Canso: the policy still refuses a northbound azimuth ---------------------


def test_a_northbound_azimuth_at_canso_is_refused_by_the_policy_of_the_site():
    verdict = screens.hazard_screen(348.47, CANSO["corridor"], PROFILE)

    assert verdict.hazard == "fail"
    assert verdict.constraint_fired == "hazard_area"
    assert "southbound" in verdict.reason
    assert CANSO["corridor"]["direction_policy"]["source"] in verdict.reason


def test_a_bounds_override_at_canso_does_not_waive_the_policy():
    """A request may move the bounds. It cannot move the environmental assessment."""
    request = {
        "site": "canso",
        "target": {"type": "SSO", "h_t_km": 674.0, "i_t_deg": 98.1, "ltan_hours": "10:30"},
        "date_range": {"start": "2026-10-05", "end": "2026-10-06"},
        "vehicle_profile_id": "cyclone4m",
        "corridor": {"A_min_deg": 300.0, "A_max_deg": 359.0},
    }
    response = compute_windows(request)

    assert response["windows"]
    assert all(row["screens"]["hazard"] == "fail" for row in response["windows"])
    assert response["reachable"] is False


# --- A site with no policy is judged by its corridor --------------------------


def test_a_northbound_azimuth_passes_where_the_corridor_admits_it_and_no_policy_forbids_it():
    corridor = {"A_min_deg": 340.0, "A_max_deg": 355.0}

    assert screens.hazard_screen(351.79, corridor, PROFILE).hazard == "pass"
    assert screens.hazard_screen(188.58, corridor, PROFILE).hazard == "fail"


def test_a_sector_that_crosses_north_is_read_through_north():
    """A_min greater than A_max is the sector from A_min through 360 to A_max."""
    corridor = {"A_min_deg": 349.5, "A_max_deg": 93.5}

    for inside in (349.5, 351.79, 0.0, 10.0, 93.5):
        assert reachability.azimuth_in_corridor(inside, corridor), inside
        assert screens.hazard_screen(inside, corridor, PROFILE).hazard == "pass", inside
    for outside in (94.0, 188.58, 270.0, 349.0):
        assert not reachability.azimuth_in_corridor(outside, corridor), outside
        assert screens.hazard_screen(outside, corridor, PROFILE).hazard == "fail", outside


def test_the_inclination_bounds_of_a_sector_include_its_turning_points():
    """i(beta) = acos(cos(phi) sin(beta)) turns at 90 and 270 deg, so endpoints alone are not enough."""
    low, high = reachability.corridor_inclination_bounds(
        0.0, {"A_min_deg": 60.0, "A_max_deg": 120.0}
    )
    assert low == pytest.approx(0.0, abs=1.0e-9)
    assert high == pytest.approx(30.0, abs=1.0e-9)

    low, high = reachability.corridor_inclination_bounds(
        0.0, {"A_min_deg": 349.5, "A_max_deg": 93.5}
    )
    assert low == pytest.approx(0.0, abs=1.0e-9)
    assert high == pytest.approx(100.5, abs=1.0e-9)


def test_reachability_admits_the_northbound_crossing_where_the_corridor_does():
    """With no policy, a target whose northbound azimuth lies in the corridor is reachable."""
    north_only = {"A_min_deg": 340.0, "A_max_deg": 355.0}
    south_only = {"A_min_deg": 115.0, "A_max_deg": 195.0}

    assert reachability.reachable_in_corridor(98.18, 5.2392, north_only)
    assert reachability.reachable_in_corridor(98.18, 5.2392, south_only)
    assert not reachability.reachable_in_corridor(98.18, 5.2392, {"A_min_deg": 200.0, "A_max_deg": 300.0})


# --- The reason names the corridor that refused, and how well it is known -----


@pytest.mark.parametrize(
    "site, azimuth", (("kourou_ela1", 351.79), ("plesetsk_133", 340.52))
)
def test_a_refusal_at_a_gate_site_names_its_own_corridor_and_its_flag(site, azimuth):
    corridor = provenance.load_json(f"sites/{site}.json")["corridor"]
    verdict = screens.hazard_screen(azimuth, corridor, PROFILE)

    assert verdict.hazard == "fail"
    assert "Canso" not in verdict.reason
    assert "[90, 260]" in verdict.reason
    assert "ASSUMPTION" in verdict.reason


def test_a_refusal_at_canso_names_the_derived_corridor():
    verdict = screens.hazard_screen(201.6, CANSO["corridor"], PROFILE)

    assert verdict.hazard == "fail"
    assert "[115, 195]" in verdict.reason
    assert "DERIVED" in verdict.reason
