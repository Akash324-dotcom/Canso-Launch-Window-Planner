"""E8 Range and conjunction screens. Spec II.8.

Three screens, and the spec is explicit that all three are PRE-SCREENS:

* Hazard area. The footprint model is in the vehicle profile and the corridor in
  the site configuration. Output is a deterministic pass or fail, feeding
  P_range_clear as 0 or 1. It is not a probability.
* Conjunction. At request time the engine fetches TLEs from CelesTrak. TESTS
  NEVER TOUCH THE NETWORK: they read the committed fixture in
  data/tle_fixture.json, which records its own fetch time and source.
* NOTAM. Display only, a stub returning "none" while keeping the field present.
  The spec is explicit that a NOTAM never gates a window.

The response marks the constraint source as screen_level: pre_screen.
"""

from __future__ import annotations

import math

import pytest

from backend.engine import provenance, screens

SITE = provenance.load_json("site_canso.json")
PROFILE = provenance.load_json("vehicles/cyclone4m.json")
FIXTURE = provenance.load_json("tle_fixture.json")
FIXTURE_PATH = "backend/engine/data/tle_fixture.json"


# --- The committed fixture (E8 data task) -----------------------------------


def test_fixture_records_its_fetch_time_and_source():
    assert FIXTURE["fetched_utc"].endswith("Z")
    assert isinstance(FIXTURE["source"], str) and "celestrak.org" in FIXTURE["source"].lower()


def test_fixture_holds_exactly_three_real_tles():
    assert len(FIXTURE["satellites"]) == 3
    for satellite in FIXTURE["satellites"]:
        assert satellite["name"]
        assert satellite["norad_id"].isdigit()
        assert satellite["tle_line1"].startswith("1 ")
        assert satellite["tle_line2"].startswith("2 ")
        assert len(satellite["tle_line2"].rstrip()) >= 60


def test_fixture_tle_lines_are_self_consistent():
    """The checksum columns of lines 1 and 2 must agree modulo 10."""
    for satellite in FIXTURE["satellites"]:
        assert _tle_checksum(satellite["tle_line1"]) == satellite["tle_line1"][68]
        assert _tle_checksum(satellite["tle_line2"]) == satellite["tle_line2"][68]


def _tle_checksum(line: str) -> str:
    """NORAD TLE modulo-10 checksum: digits count, '-' counts as 1, else 0."""
    total = 0
    for character in line[:68]:
        if character.isdigit():
            total += int(character)
        elif character == "-":
            total += 1
    return str(total % 10)


def test_fixture_covers_three_altitude_bands():
    bands = {satellite["altitude_band"] for satellite in FIXTURE["satellites"]}
    assert bands == {"400-550", "550-700", "700-1000"}


# --- Hazard screen -----------------------------------------------------------


def test_a_trajectory_inside_the_corridor_passes_the_hazard_screen():
    verdict = screens.hazard_screen(azimuth_deg=177.0, corridor=SITE["corridor"], profile=PROFILE)
    assert verdict.hazard == "pass"
    assert verdict.constraint_fired is None


def test_a_trajectory_outside_the_corridor_fails_the_hazard_screen():
    verdict = screens.hazard_screen(azimuth_deg=201.6, corridor=SITE["corridor"], profile=PROFILE)
    assert verdict.hazard == "fail"
    assert verdict.constraint_fired == "hazard_area"


def test_hazard_screen_is_deterministic():
    first = screens.hazard_screen(201.6, SITE["corridor"], PROFILE)
    second = screens.hazard_screen(201.6, SITE["corridor"], PROFILE)
    assert first.hazard == second.hazard
    assert first.reason == second.reason


def test_hazard_screen_reports_the_range_screen_as_zero_or_one():
    verdict = screens.hazard_screen(201.6, SITE["corridor"], PROFILE)
    assert verdict.p_range in (0, 1)
    assert verdict.p_range == 0
    assert screens.hazard_screen(177.0, SITE["corridor"], PROFILE).p_range == 1


def test_hazard_screen_honours_a_corridor_override():
    narrow = {"A_min_deg": 100.0, "A_max_deg": 140.0}
    assert screens.hazard_screen(177.0, narrow, PROFILE).hazard == "fail"
    assert screens.hazard_screen(120.0, narrow, PROFILE).hazard == "pass"


def test_hazard_screen_uses_the_southbound_branch_only():
    """The environmental assessment admits only southbound trajectories."""
    northbound_partner = 180.0 - 177.0
    verdict = screens.hazard_screen(northbound_partner, SITE["corridor"], PROFILE)
    assert verdict.hazard == "fail"
    assert "southbound" in verdict.reason


def test_every_hazard_screen_verdict_marks_itself_a_pre_screen():
    verdict = screens.hazard_screen(177.0, SITE["corridor"], PROFILE)
    assert verdict.constraint_source == "screen_level: pre_screen"


# --- Conjunction screen ------------------------------------------------------


def test_conjunction_screen_is_deterministic_over_the_fixture():
    target = {"altitude_km": 420.0, "i_t_deg": 51.6, "raan_deg": 120.0}
    first = screens.conjunction_screen(target, FIXTURE)
    second = screens.conjunction_screen(target, FIXTURE)
    assert first.conjunction == second.conjunction
    assert first.worst_miss_km == second.worst_miss_km
    assert first.considerations == second.considerations


def test_conjunction_screen_returns_clear_or_flagged_and_nothing_else():
    target = {"altitude_km": 420.0, "i_t_deg": 51.6, "raan_deg": 120.0}
    assert screens.conjunction_screen(target, FIXTURE).conjunction in {"clear", "flagged"}


def test_conjunction_screen_flags_a_target_sharing_an_altitude_band_with_a_fixture_object():
    """ISS is at 426.8 km; a 430 km target must be considered against it."""
    target = {"altitude_km": 430.0, "i_t_deg": 51.6, "raan_deg": 120.0}
    verdict = screens.conjunction_screen(target, FIXTURE)
    assert verdict.conjunction == "flagged"
    assert verdict.worst_miss_km < verdict.threshold_km
    assert any(item["norad_id"] == "25544" for item in verdict.considerations)


def test_conjunction_screen_clears_a_target_far_from_every_fixture_band():
    """No fixture object is anywhere near 1500 km."""
    target = {"altitude_km": 1500.0, "i_t_deg": 97.5, "raan_deg": 10.0}
    verdict = screens.conjunction_screen(target, FIXTURE)
    assert verdict.conjunction == "clear"
    assert verdict.worst_miss_km > verdict.threshold_km


def test_conjunction_screen_reports_the_worst_miss_distance():
    target = {"altitude_km": 420.0, "i_t_deg": 51.6, "raan_deg": 120.0}
    verdict = screens.conjunction_screen(target, FIXTURE)
    assert math.isfinite(verdict.worst_miss_km)
    assert verdict.worst_miss_km >= 0.0
    assert verdict.p_conjunction in (0, 1)


def test_conjunction_screen_carries_its_threshold_and_its_flag():
    verdict = screens.conjunction_screen(
        {"altitude_km": 420.0, "i_t_deg": 51.6, "raan_deg": 120.0}, FIXTURE
    )
    assert verdict.threshold_km > 0.0
    assert verdict.threshold_flag in {"VERIFIED", "ASSUMPTION"}
    assert verdict.constraint_source == "screen_level: pre_screen"


def test_conjunction_screen_names_its_source_and_is_honest_about_fidelity():
    verdict = screens.conjunction_screen(
        {"altitude_km": 420.0, "i_t_deg": 51.6, "raan_deg": 120.0}, FIXTURE
    )
    assert "celestrak" in verdict.source.lower()
    assert "pre_screen" in verdict.fidelity


def test_conjunction_screen_does_not_reach_the_network():
    """The fixture is the only source the tests can see."""
    verdict = screens.conjunction_screen(
        {"altitude_km": 420.0, "i_t_deg": 51.6, "raan_deg": 120.0}, FIXTURE
    )
    assert verdict.fetched_utc == FIXTURE["fetched_utc"]


# --- NOTAM screen ------------------------------------------------------------


def test_notam_screen_is_a_stub_that_keeps_the_field_present():
    verdict = screens.notam_screen()
    assert verdict.notam == "none"
    assert verdict.constraint_fired is None


def test_notam_screen_does_not_gate_a_window():
    """Spec II.8: display only, never used to gate a window."""
    verdict = screens.notam_screen()
    assert verdict.p_notam is None
    assert verdict.constraint_source == "display_only"


def test_notam_screen_reports_its_own_stub_status():
    verdict = screens.notam_screen()
    assert "stub" in verdict.reason.lower()
    assert "navcanada" in verdict.source.lower()


# --- The combined screen object ----------------------------------------------


def test_screen_result_carries_exactly_the_contract_fields():
    result = screens.evaluate(
        azimuth_deg=177.0,
        corridor=SITE["corridor"],
        profile=PROFILE,
        target={"altitude_km": 420.0, "i_t_deg": 51.6, "raan_deg": 120.0},
        tle_fixture=FIXTURE,
    )
    assert set(result.to_contract_fields()) == {"hazard", "conjunction", "notam"}


def test_screen_result_never_sets_a_constraint_for_a_clear_everything_case():
    result = screens.evaluate(
        177.0,
        SITE["corridor"],
        PROFILE,
        {"altitude_km": 1500.0, "i_t_deg": 97.5, "raan_deg": 10.0},
        FIXTURE,
    )
    assert result.constraint_fired is None


def test_screen_result_sets_conjunction_flagged_when_that_screen_flags():
    result = screens.evaluate(
        177.0,
        SITE["corridor"],
        PROFILE,
        {"altitude_km": 430.0, "i_t_deg": 51.6, "raan_deg": 120.0},
        FIXTURE,
    )
    assert result.conjunction == "flagged"
    assert result.constraint_fired == "conjunction_flagged"


def test_hazard_failure_outranks_conjunction_in_the_constraint():
    """Both stop the row; the deterministic screen is reported as the reason."""
    result = screens.evaluate(
        201.6,
        SITE["corridor"],
        PROFILE,
        {"altitude_km": 430.0, "i_t_deg": 51.6, "raan_deg": 120.0},
        FIXTURE,
    )
    assert result.hazard == "fail"
    assert result.constraint_fired == "hazard_area"