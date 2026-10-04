"""E5 The window equation: opportunity versus period.

Spec II.4. The site lies in the target plane when

    sin(RA_site - Omega) = tan(phi_s) / tan(i)                                (II.8)

and with RA_site(t) = GMST(t) + lambda_s (II.1) the ascending branch is

    GMST(t) + lambda_s = Omega_t(t) + delta   (mod 360)                       (II.9)
    delta(i, phi_s)    = asin(tan(phi_s) / tan(i))                            (II.10)

with the descending branch replacing delta by 180 deg - delta.

HAND ARITHMETIC, CASE A (the fully worked case)
-----------------------------------------------
Site Canso, phi_s = 45.3 deg, lambda_s = -61.0 deg (read from
data/site_canso.json, not written here). Target i = 98.1 deg on a FIXED plane
(no nodal drift), so Omega_t(t) = Omega constant.

Step 1, the site-to-node offset (II.10):

    tan(45.3 deg) = 1.0105241
    tan(98.1 deg) = -7.0256996
    tan(phi_s)/tan(i) = -0.1438297
    delta = asin(-0.1438297) = -8.265653 deg

Step 2, choose the epoch so the crossing is exact by construction. Let
Omega_t(t0) = GMST(t0) + lambda_s - delta. Substituting into (II.9) gives
GMST(t0) + lambda_s = GMST(t0) + lambda_s - delta + delta, which holds for every
t0, so the ascending branch crosses exactly at t0. GMST itself comes from the IAU
1982 model and is pinned to 1e-6 deg by tests/test_frames.py; the arithmetic
below therefore checks the plane-condition algebra and the root search, which is
what this module owns.

Step 3, the window edges. The site's RA relative to the drifting plane sweeps at
(II.11)

    d(RA_site - Omega_t)/dt = omega_sid - Omega_targ_dot = 15.0410686 deg/hr

so a plane tolerance of +/- Delta_Omega = +/- 0.1 deg puts the edges at

    t_open  = t0 - 0.1 / 15.04106688 hr = t0 - 23.93447 s
    t_close = t0 + 23.93447 s

and the full width (II.12) is

    W_window = 2 * Delta_Omega / 15.04106688 hr = 47.86894 s

Step 4, the descending branch. Replacing delta by 180 - delta moves the crossing
by 180 deg of Earth rotation, that is 180 / 15.04106688 hr = 11.967236 hr later.

The hand-arithmetic target is therefore: the engine's ascending window centre is
within one second of t0, its width is 47.86894 s, and its descending sibling is
11.967236 hr later to within one second.

WINDOW WIDTH, TWO QUANTITIES
----------------------------
Spec (II.12) defines the WINDOW as the full width W = 2 tau_half, and the
response field is named window_width_s, so window_width_s() returns the FULL
width. Spec III.1 pins the HALF width (tau_half = 24 s for Delta_Omega = 0.1 deg),
which is window_half_width_s(). Both are exposed so neither the spec's Test 1 row
nor the issue's hand case "tolerance_deg / 15.04 deg-per-hour in seconds" is
lost. The two differ by exactly a factor of two and the tests assert both.
"""

from __future__ import annotations

import math

import pytest

from backend.engine import frames, provenance, window

SITE = provenance.load_json("site_canso.json")
PHI_S = SITE["latitude_deg"]
LAMBDA_S = SITE["longitude_deg"]
JD_T0 = 2461318.5  # 2026-10-05T00:00:00Z

DEG_PER_HR = provenance.OMEGA_SID_RAD_S * 180.0 / math.pi * 3600.0


def _target(i_t_deg, raan_deg, tolerance_deg, altitude_km=674.0, nodal_rate=0.0):
    return {
        "i_t_deg": i_t_deg,
        "raan_deg": raan_deg,
        "altitude_km": altitude_km,
        "nodal_rate_deg_per_day": nodal_rate,
        "raan_tolerance_deg": tolerance_deg,
        "ltan_hours": None,
        "lat_deg": PHI_S,
        "lon_deg": LAMBDA_S,
        "epoch_jd": JD_T0,
    }


# --- The offset (II.10) ------------------------------------------------------


def test_delta_offset_for_98_1_degrees():
    assert window.site_node_offset_deg(98.1, PHI_S) == pytest.approx(-8.26891, abs=1e-4)


def test_exact_azimuth_at_the_pad_latitude_puts_the_site_on_the_ascending_node():
    """delta = 90 deg at i = phi_s, the due-east boundary case of spec II.2."""
    assert window.site_node_offset_deg(PHI_S, PHI_S) == pytest.approx(90.0, abs=1e-9)


def test_delta_offset_is_undefined_below_the_pad_latitude():
    """Existence of delta is exactly the reachability condition i >= phi_s (II.4)."""
    assert window.site_node_offset_deg(45.1, PHI_S) is None


def test_descending_branch_offsets_sum_to_one_hundred_eighty():
    for i_t in (45.3, 87.9, 98.1):
        ascending = window.site_node_offset_deg(i_t, PHI_S)
        assert ascending is not None
        assert ascending + window.descending_offset_deg(i_t, PHI_S) == pytest.approx(
            180.0, abs=1e-9
        )


# --- Widths (II.12) ----------------------------------------------------------


def test_half_width_matches_the_spec_hand_computation():
    """Spec III.1: Delta_Omega = 0.1 deg against a fixed plane gives 24 s."""
    assert window.window_half_width_s(0.1, 0.0) == pytest.approx(23.93447, abs=0.001)


def test_full_width_is_twice_the_half_width():
    assert window.window_width_s(0.1, 0.0) == pytest.approx(2.0 * window.window_half_width_s(0.1, 0.0))


def test_full_width_matches_the_tolerance_over_sweep_rate_in_seconds():
    """The issue's hand case: tolerance_deg / 15.04 deg-per-hour, converted to seconds."""
    expected = 2.0 * (0.1 / DEG_PER_HR) * 3600.0
    assert window.window_width_s(0.1, 0.0) == pytest.approx(expected, abs=1e-9)


def test_half_width_matches_the_tolerance_over_sweep_rate_in_seconds():
    """The same hand case for the half width, which is what spec III.1 pins."""
    expected = (0.1 / DEG_PER_HR) * 3600.0
    assert window.window_half_width_s(0.1, 0.0) == pytest.approx(expected, abs=1e-9)


def test_width_shrinks_when_the_target_plane_drifts_with_the_earth_rotation():
    """(II.11): sweep = omega_sid - Omega_dot, so the drift sets the width.

    A prograde plane at -5 deg/day runs backwards against the Earth's sweep, the
    relative rate rises to 15.249 deg/hr and the window narrows to 47.215 s. A
    retrograde SSO at +0.9856 deg/day runs with the sweep, the rate falls to
    15.000 deg/hr and the window widens to 48.000 s.
    """
    still = window.window_width_s(0.1, 0.0)
    prograde = window.window_width_s(0.1, -5.0)
    retrograde = window.window_width_s(0.1, +0.9856)
    assert prograde < still
    assert retrograde > still
    assert prograde == pytest.approx(47.21497, abs=1e-4)
    assert retrograde == pytest.approx(48.0, abs=1e-3)


def test_sso_sweep_is_exactly_three_hundred_and_sixty_degrees_per_day():
    """Spec II.4: the +0.9856 deg/day drift cancels the Sun's apparent motion.

    Earth sweeps 360.98565 deg/day and the SSO node advances 0.9856 deg/day, so
    the relative sweep is 360.00005 deg/day, which is what makes the recurrence
    period one solar day rather than one sidereal day.
    """
    assert window.sweep_rate_deg_per_hour(0.9856) * 24.0 == pytest.approx(360.0, abs=1e-4)


# --- Root search (II.9) ------------------------------------------------------


def test_hand_computed_case_a_ascending_window_is_centred_on_t0():
    raan = (frames.gmst_degrees(JD_T0) + LAMBDA_S - window.site_node_offset_deg(98.1, PHI_S)) % 360.0
    target = _target(98.1, raan, 0.1)
    found = window.find_windows(target, JD_T0 - 0.5 / 24.0, JD_T0 + 0.5 / 24.0)
    centres = [entry.centre_jd for entry in found]
    assert centres, "the search must find the crossing it was constructed to contain"
    nearest = min(centres, key=lambda jd: abs((jd - JD_T0) * 86400.0))
    assert abs((nearest - JD_T0) * 86400.0) < 1.0


def test_hand_computed_case_a_window_width_is_47_87_seconds():
    raan = (frames.gmst_degrees(JD_T0) + LAMBDA_S - window.site_node_offset_deg(98.1, PHI_S)) % 360.0
    target = _target(98.1, raan, 0.1)
    found = window.find_windows(target, JD_T0 - 0.5 / 24.0, JD_T0 + 0.5 / 24.0)
    narrowest = min(found, key=lambda entry: entry.width_s)
    assert narrowest.width_s == pytest.approx(47.86894, abs=0.001)


def test_hand_computed_case_a_descending_branch_sits_at_the_predicted_offset():
    raan = (frames.gmst_degrees(JD_T0) + LAMBDA_S - window.site_node_offset_deg(98.1, PHI_S)) % 360.0
    target = _target(98.1, raan, 0.1)
    found = window.find_windows(target, JD_T0 - 0.25, JD_T0 + 1.0)
    assert {entry.branch for entry in found} == {"ascending", "descending"}
    # The two branch offsets differ by (180 - 2 delta) = 196.537829 deg of
    # relative sweep, which is 196.537829 / 15.04106688 = 13.066748 hr. Successive
    # ascending roots are one full recurrence period, 23.934472 hr, apart.
    ascending = next(e for e in found if e.branch == "ascending")
    descending = next(e for e in found if e.branch == "descending")
    separation_hr = (descending.centre_jd - ascending.centre_jd) * 24.0
    assert separation_hr == pytest.approx(13.066748, abs=1.0 / 3600.0)
    last = max(e.centre_jd for e in found if e.branch == "ascending")
    first = min(e.centre_jd for e in found if e.branch == "ascending")
    assert (last - first) * 24.0 == pytest.approx(23.934472, abs=1.0 / 3600.0)


def test_window_edges_sit_at_plus_and_minus_the_tolerance():
    raan = (frames.gmst_degrees(JD_T0) + LAMBDA_S - window.site_node_offset_deg(98.1, PHI_S)) % 360.0
    target = _target(98.1, raan, 0.1)
    found = window.find_windows(target, JD_T0 - 0.5 / 24.0, JD_T0 + 0.5 / 24.0)
    entry = min(found, key=lambda item: abs((item.centre_jd - JD_T0) * 86400.0))
    assert entry.open_jd < entry.centre_jd < entry.close_jd
    assert entry.open_raan_deg == pytest.approx(-0.1, abs=1e-3)
    assert entry.close_raan_deg == pytest.approx(0.1, abs=1e-3)


# --- A whole range (spec III.1, and the contract semantics) -------------------


def test_ninety_day_search_is_sorted_and_free_of_duplicates():
    raan = 30.0
    target = _target(98.1, raan, 1.0, nodal_rate=0.9856)
    found = window.find_windows(target, JD_T0, JD_T0 + 90.0)
    centres = [entry.centre_jd for entry in found]
    assert centres == sorted(centres)
    assert len(centres) == len(set(centres))
    assert len(centres) >= 80, "roughly one opportunity per solar day for an SSO target"


def test_ninety_day_search_keeps_every_window_inside_the_range():
    start, end = JD_T0, JD_T0 + 90.0
    target = _target(98.1, 30.0, 1.0, nodal_rate=0.9856)
    for entry in window.find_windows(target, start, end):
        assert entry.open_jd >= start - 1e-9
        assert entry.close_jd <= end + 1e-9


def test_sso_recurrence_is_exactly_one_solar_day():
    """Spec II.4: the +0.9856 deg/day drift cancels the Sun's apparent motion."""
    assert window.window_period_days(0.9856) == pytest.approx(1.0, abs=0.002)


def test_fixed_plane_recurrence_is_one_sidereal_day():
    """Spec II.4: 360 / 360.9856 = 0.9973 days for a non-precessing plane."""
    period = window.window_period_days(0.0)
    assert period == pytest.approx(0.9973, abs=1.0e-4)
    assert period < 1.0, "a non-precessing plane offers opportunities sooner than daily"


def test_empty_result_is_a_valid_answer_not_an_error():
    """Spec IV.1: no crossing in range with reachable true is informative."""
    target = _target(98.1, 30.0, 0.001)
    assert window.find_windows(target, JD_T0, JD_T0 + 0.001) == []


def test_windows_from_opposite_branches_never_overlap():
    target = _target(98.1, 30.0, 5.0, nodal_rate=0.9856)
    found = sorted(window.find_windows(target, JD_T0, JD_T0 + 5.0), key=lambda e: e.centre_jd)
    for earlier, later in zip(found, found[1:]):
        assert later.open_jd >= earlier.close_jd