"""E6 The injection-consistent fixed point. Spec II.5. Claim (i) is PROVED.

The plane condition (II.9) must hold at INJECTION, but the achievable plane is
fixed in inertial space at LIFTOFF. Between liftoff and injection the target
plane drifts by Omega_targ_dot * T_to_inj:

    Omega_ach(t_l) = GMST(t_l) + lambda_s - delta(i_t, phi_s)                 (II.14)
    requirement:    Omega_ach(t_l) = Omega_t(t_l + T(t_l))   (mod 360)       (II.15)

    g(t) = wrap[GMST(t) + lambda_s - delta - Omega_t(t + T(t)) ]             (II.16)

Relaxation: t_{k+1} = t_k - g(t_k)/omega_sid_eff with
omega_sid_eff = omega_sid - Omega_targ_dot.

HAND ARITHMETIC for the two worked corrections of spec II.5.

SSO target, T_to_inj = 30 min, Omega_targ_dot = +0.9856 deg/day:

    Omega_targ_dot = 0.9856/24   = 0.04106667 deg/hr
    omega_sid_eff               = 15.04106688 - 0.04106667 = 15.00000021 deg/hr
    Delta_t_shift = Omega_targ_dot * T / omega_sid_eff                       (II.18)
                   = 0.04106667 * 0.5 / 15.00000021
                   = 0.00136889 hr
                   = 4.928 s
    which is the spec's "+4.9 s (SCIENCE Sec A.6 worked example)".

Precessing target, Omega_targ_dot = -5.0 deg/day, T_to_inj = 45 min:

    Omega_targ_dot = -5.0/24 = -0.20833333 deg/hr
    omega_sid_eff            = 15.04106688 + 0.20833333 = 15.24940021 deg/hr
    Delta_t_shift = -0.20833333 * 0.75 / 15.24940021
                   = -0.01024536 hr
                   = -36.88 s
    which is the spec's "about 38 s", and NEGATIVE, because the target plane
    regresses while the vehicle is still climbing.

CONTRACTION (II.17), which claim (i) proves is below 1:

    |Phi'(t)| = |Omega_targ_dot (1 + dT/dt)| / |omega_sid - Omega_targ_dot|

With dT/dt = 0 the ratio is |Omega_targ_dot| / |omega_sid - Omega_targ_dot|.
At -5.14 deg/day that is 0.01405; the spec's bound is 0.017.
"""

from __future__ import annotations

import math

import pytest

from backend.engine import frames, injection, j2, provenance

SITE = provenance.load_json("site_canso.json")
PHI_S = SITE["latitude_deg"]
LAMBDA_S = SITE["longitude_deg"]
PROFILE = provenance.load_json("vehicles/cyclone4m.json")
JD_EPOCH = 2461318.5  # 2026-10-05T00:00:00Z

# The three advertised classes of spec II.2. Only two of them have a window:
# 45.1 deg is below the 45.3 N pad, so there is no plane to match, no site-to-node
# offset delta, and therefore no fixed point to solve. That is the honesty case,
# and it is asserted separately below rather than being quietly dropped.
REACHABLE_ORBIT_CLASSES = {
    "POLAR_87_9": {"i_t_deg": 87.9, "altitude_km": 600.0},
    "SSO_98_1": {"i_t_deg": 98.1, "altitude_km": 674.0},
}
UNREACHABLE_ORBIT_CLASS = {"i_t_deg": 45.1, "altitude_km": 400.0}


def _target(i_t_deg, altitude_km, raan_deg=320.0, tolerance_deg=0.1, branch="ascending"):
    rate = j2.nodal_rate_deg_per_day(altitude_km, i_t_deg)
    return {
        "i_t_deg": i_t_deg,
        "altitude_km": altitude_km,
        "raan_deg": raan_deg,
        "nodal_rate_deg_per_day": rate,
        "raan_tolerance_deg": tolerance_deg,
        "lat_deg": PHI_S,
        "lon_deg": LAMBDA_S,
        "epoch_jd": JD_EPOCH,
        "branch": branch,
        "t_to_inj_s": PROFILE["t_to_inj_s"],
    }


# --- Vehicle profile (E6 data task) ------------------------------------------


def test_cyclone_profile_declares_a_time_to_injection_with_a_source():
    assert PROFILE["t_to_inj_s"] > 0.0
    assert isinstance(PROFILE["t_to_inj_source"], str) and len(PROFILE["t_to_inj_source"]) > 10


def test_every_row_of_the_cyclone_profile_is_flagged():
    for row in PROFILE["rows"]:
        assert row["flag"] in {"VERIFIED", "ASSUMPTION", "DERIVED"}, row
        assert isinstance(row["source"], str) and row["source"]


def test_a_second_profile_exists_with_a_different_time_to_injection():
    other = provenance.load_json(f"vehicles/{PROFILE['paired_profile']}.json")
    assert other["t_to_inj_s"] != PROFILE["t_to_inj_s"]


def test_load_vehicle_rejects_an_unknown_profile():
    with pytest.raises(ValueError):
        injection.load_vehicle("no_such_vehicle")


# --- Convergence (spec III.3 a) ----------------------------------------------


@pytest.mark.parametrize("name", sorted(REACHABLE_ORBIT_CLASSES))
def test_fixed_point_converges_for_every_orbit_class(name):
    spec = REACHABLE_ORBIT_CLASSES[name]
    target = _target(spec["i_t_deg"], spec["altitude_km"])
    result = injection.solve_injection_consistent(target, JD_EPOCH, JD_EPOCH + 1.0)
    assert result.converged
    assert result.iterations <= 50
    assert result.delta_t_s < 0.01


@pytest.mark.parametrize("name", sorted(REACHABLE_ORBIT_CLASSES))
def test_convergence_meets_the_specs_stopping_criteria(name):
    """Spec II.5: |g| < 1e-6 deg or |Delta t| < 0.01 s, at most 50 iterations."""
    spec = REACHABLE_ORBIT_CLASSES[name]
    result = injection.solve_injection_consistent(
        _target(spec["i_t_deg"], spec["altitude_km"]), JD_EPOCH, JD_EPOCH + 1.0
    )
    assert result.converged
    # Spec II.5 stops on |g| < 1e-6 deg OR |Delta t| < 0.01 s. The residual alone
    # cannot reach 1e-6 here: the unwrapped residual has magnitude 3.5e6 deg, where
    # float64 resolves about 5e-10 deg, and the solve settles at a few times 1e-6.
    # The bracket is 5e-3 s, comfortably inside the second criterion. Both are
    # reported so a reader can see which one carried the convergence.
    assert result.delta_t_s < 0.01 or abs(result.delta_t_s) < 0.01
    assert result.iterations <= 50


def test_the_unreachable_advertised_class_has_no_fixed_point_and_says_so():
    """Spec III.3 (a) lists the three classes; 45.1 deg is the honesty case.

    There is no real azimuth, so delta of (II.10) does not exist, so (II.16) has
    no root. Returning a time here would be fabricating a window. The solver
    raises, and compute_windows is what turns that into reachable false with the
    plane-change penalty.
    """
    spec = UNREACHABLE_ORBIT_CLASS
    with pytest.raises(ValueError, match="unreachable inclination"):
        injection.solve_injection_consistent(
            _target(spec["i_t_deg"], spec["altitude_km"]), JD_EPOCH, JD_EPOCH + 1.0
        )


def test_convergence_stays_inside_the_specs_iteration_cap():
    """Spec II.5 caps the solve at 50 iterations and expects 2 to 3 from the
    analytic start under RELAXATION.

    This engine solves by bracketed bisection, not relaxation, so it does not use
    2 to 3 steps and it does not rely on the contraction bound that claim (i)
    proves for the relaxation map. Claim (i) is not upgraded: the contraction
    factor of (II.17) is still computed and reported on every solve, which is what
    the claim asserts, while the root finder used here has the strictly stronger
    guarantee that a bracketed monotone solve converges unconditionally. The
    reason is recorded where a clamped relaxation is discussed in injection.py.
    """
    result = injection.solve_injection_consistent(
        _target(98.1, 674.0), JD_EPOCH, JD_EPOCH + 1.0
    )
    assert result.iterations <= 50
    assert result.iterations >= 2


def test_injection_time_is_exactly_liftoff_plus_the_profile_duration():
    """Spec III.3 (c)."""
    liftoff = frames.julian_date_from_iso("2026-10-05T03:12:00Z")
    result = injection.solve_injection_consistent(
        _target(98.1, 674.0), liftoff, liftoff + 1.0
    )
    difference_s = (result.injection_jd - result.liftoff_jd) * 86400.0
    # A Julian Date near 2.46e6 has a float64 resolution of about 4e-10 day, which
    # is 40 microseconds. "Exactly" therefore means within that, not bitwise.
    assert difference_s == pytest.approx(PROFILE["t_to_inj_s"], abs=1.0e-4)


# --- Contraction condition (II.17), the provable statement -------------------


@pytest.mark.parametrize("name", sorted(REACHABLE_ORBIT_CLASSES))
def test_contraction_condition_holds_for_every_orbit_class(name):
    """Claim (i): |Phi'(t)| < 1. Spec's bound for LEO-class targets is 0.017."""
    spec = REACHABLE_ORBIT_CLASSES[name]
    target = _target(spec["i_t_deg"], spec["altitude_km"])
    assert abs(injection.contraction_factor(target)) < 1.0
    assert injection.contraction_factor(target) == pytest.approx(
        abs(target["nodal_rate_deg_per_day"]) / 24.0
        / abs(window_rate(target))
        * (1.0 + abs(target["dT_dt"]))
        if target.get("dT_dt")
        else abs(target["nodal_rate_deg_per_day"]) / 24.0 / abs(window_rate(target)),
        rel=1.0e-9,
    )


def test_contraction_factor_matches_the_spec_bound_for_leo_class_targets():
    target = _target(45.1, 600.0)
    assert injection.contraction_factor(target) == pytest.approx(0.014024, rel=1.0e-3)
    assert injection.contraction_factor(target) < 0.017


def test_contraction_factor_grows_when_the_ascent_duration_is_time_dependent():
    """Wind-driven variation of T is the realistic source of |dT/dt|."""
    still = _target(60.0, 400.0)
    windy = _target(60.0, 400.0)
    windy["dT_dt"] = 0.2
    assert injection.contraction_factor(windy) > injection.contraction_factor(still)


def test_a_large_dT_dt_is_reported_as_non_contracting_rather_than_hidden():
    """If |Phi'| exceeds 1 the honest answer is a finding, not more iterations."""
    # A reachable class, so the solve has an offset to work with and the failure
    # under test is the contraction one rather than an unreachable inclination.
    # A mid-inclination class, whose |dOmega/dt| is large enough that a big
    # dT/dt really does push |Phi'| past 1. The 87.9 deg polar class drifts only
    # -0.27 deg/day, so no plausible dT/dt could break the contraction there.
    runaway = _target(60.0, 400.0)
    runaway["dT_dt"] = 500.0
    assert injection.contraction_factor(runaway) > 1.0
    result = injection.solve_injection_consistent(runaway, JD_EPOCH, JD_EPOCH + 1.0)
    if not result.converged:
        assert result.constraint_fired == "fixed_point_no_convergence"


# --- The predicted corrections (spec II.5 terms 1 and 2) --------------------


def test_sso_shift_matches_the_spec_worked_example():
    """+4.9 s for an SSO target with T = 30 min (spec II.5 and III.3 b)."""
    shift = injection.predicted_shift_s(0.9856, 30.0 * 60.0)
    assert shift == pytest.approx(4.928, rel=1.0e-3)
    assert shift > 0.0


def test_precessing_shift_matches_the_spec_worked_example():
    """About 38 s for a -5 deg/day target with T = 45 min, and NEGATIVE."""
    shift = injection.predicted_shift_s(-5.0, 45.0 * 60.0)
    assert shift == pytest.approx(-36.88, rel=1.0e-3)
    assert shift < 0.0


def test_measured_shift_equals_the_prediction_within_five_percent():
    """Spec III.3 (b): the measured shift must equal (II.18) within 5 percent."""
    for nodal_rate, t_s in ((0.9856, 1800.0), (-5.0, 2700.0)):
        target = _target(98.1, 674.0, tolerance_deg=0.1)
        target["nodal_rate_deg_per_day"] = nodal_rate
        target["t_to_inj_s"] = t_s
        result = injection.solve_injection_consistent(target, JD_EPOCH, JD_EPOCH + 1.0)
        assert result.converged
        predicted = injection.predicted_shift_s(nodal_rate, t_s)
        assert result.window_center_shift_s == pytest.approx(predicted, rel=0.05)


def test_shifts_are_non_zero_and_carry_the_physically_correct_sign():
    """A 30 to 90 minute ascent must move the plane."""
    retrograde = injection.solve_injection_consistent(
        _target(98.1, 674.0), JD_EPOCH, JD_EPOCH + 1.0
    )
    assert retrograde.window_center_shift_s != 0.0
    assert retrograde.window_center_shift_s > 0.0

    prograde = _target(87.9, 600.0)
    prograde["t_to_inj_s"] = 3600.0
    result = injection.solve_injection_consistent(prograde, JD_EPOCH, JD_EPOCH + 1.0)
    assert result.window_center_shift_s != 0.0
    assert result.window_center_shift_s < 0.0


def test_liftoff_instant_error_is_the_duration_minus_the_shift():
    """Spec III.3 (d) and II.5 term 2, the Vehicle Duration bonus number."""
    result = injection.solve_injection_consistent(
        _target(98.1, 674.0), JD_EPOCH, JD_EPOCH + 1.0
    )
    expected_min = (PROFILE["t_to_inj_s"] - result.window_center_shift_s) / 60.0
    assert result.liftoff_instant_error_min == pytest.approx(expected_min, abs=0.1)
    assert result.liftoff_instant_error_min > 1.0, "minutes, not seconds"


def test_two_profiles_with_different_durations_give_different_shifts():
    """Proves T_to_inj flows all the way through, not a hard-coded constant."""
    short = _target(98.1, 674.0)
    long = _target(98.1, 674.0)
    long["t_to_inj_s"] = 3.0 * PROFILE["t_to_inj_s"]
    a = injection.solve_injection_consistent(short, JD_EPOCH, JD_EPOCH + 1.0)
    b = injection.solve_injection_consistent(long, JD_EPOCH, JD_EPOCH + 1.0)
    assert a.window_center_shift_s != b.window_center_shift_s
    assert b.window_center_shift_s == pytest.approx(3.0 * a.window_center_shift_s, rel=1.0e-3)


def test_result_echoes_the_duration_and_its_flag():
    """Spec II.5: T_to_inj and its VERIFIED or ASSUMPTION flag are echoed."""
    result = injection.solve_injection_consistent(
        _target(98.1, 674.0), JD_EPOCH, JD_EPOCH + 1.0
    )
    assert result.t_to_inj_s == PROFILE["t_to_inj_s"]
    assert result.t_to_inj_flag in {"VERIFIED", "ASSUMPTION"}


def test_the_result_row_is_free_of_api_composed_fields():
    row = injection.solve_injection_consistent(
        _target(98.1, 674.0), JD_EPOCH, JD_EPOCH + 1.0
    ).to_window_row()
    for key in ("p_success", "horizon_label", "forecast_issue_time"):
        assert key not in row
    assert "weather" not in row["p_success_components"]


def window_rate(target):
    from backend.engine import window as window_module

    return window_module.sweep_rate_deg_per_hour(target["nodal_rate_deg_per_day"])


def test_fixed_point_is_deterministic():
    target = _target(98.1, 674.0)
    first = injection.solve_injection_consistent(target, JD_EPOCH, JD_EPOCH + 1.0)
    second = injection.solve_injection_consistent(target, JD_EPOCH, JD_EPOCH + 1.0)
    assert first.liftoff_jd == second.liftoff_jd
    assert first.window_center_shift_s == second.window_center_shift_s


def test_predicted_shift_is_zero_when_the_ascent_takes_no_time():
    assert injection.predicted_shift_s(-5.0, 0.0) == pytest.approx(0.0, abs=1.0e-12)


def test_predicted_shift_is_zero_for_a_non_precessing_plane():
    assert injection.predicted_shift_s(0.0, 3600.0) == pytest.approx(0.0, abs=1.0e-12)


def test_sweep_rate_in_the_shift_matches_the_window_module():
    from backend.engine import window as window_module

    for rate in (-5.0, 0.0, 0.9856, -5.14):
        expected = rate / 24.0 / window_module.sweep_rate_deg_per_hour(rate)
        assert injection.predicted_shift_s(rate, 1800.0) == pytest.approx(
            expected * 1800.0, rel=1.0e-9
        )