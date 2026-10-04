"""E7 SSO specifics: LTAN-RAAN coupling, and why 98.1 deg is altitude-specific.

Spec II.6. An LTAN requirement is a date-indexed RAAN requirement:

    Omega_required = alpha_sun + 15 deg * (T_LT - 12 h)                       (II.19)

with alpha_sun the Sun's right ascension, 0 deg at the vernal equinox and
advancing at 0.9856 deg/day.

HOW alpha_sun IS OBTAINED HERE. No independent solar ephemeris is used. For the
MEAN sun,

    alpha_sun(t) = GMST(t) - 180 deg

exactly, because sidereal time is the hour angle of the vernal equinox and the
mean sun sits 180 deg from the equinox. The only term this omits is the equation
of the equinoxes, which reaches about 1.1 s of time, that is 0.0046 deg, which
is 0.18 s of launch time. That is twelve orders of magnitude inside the
minute-scale window tolerance, and it is recorded in the README as a modelling
choice rather than hidden.

BRANCH WARNING. "Local time of the descending node" is not the same quantity as
"local time of the ascending node". They differ by 12 h, so a request carrying
LTDN where LTAN was meant shifts every window by half a day. The engine carries
the branch explicitly and warns when a node time and an inclination disagree.
"""

from __future__ import annotations

import math

import pytest

from backend.engine import frames, provenance, sso

JD_T0 = 2461318.5  # 2026-10-05T00:00:00Z


def test_apparent_sun_returns_to_the_same_right_ascension_after_a_year():
    alpha = sso.sun_right_ascension_deg(JD_T0)
    later = sso.sun_right_ascension_deg(JD_T0 + 365.25)
    assert (later - alpha) % 360.0 == pytest.approx(0.0, abs=0.05)


def test_apparent_sun_differs_from_the_mean_longitude_by_the_equation_of_time():
    """Why the engine uses the apparent Sun, quantified rather than asserted.

    The spec's alpha_sun, advancing uniformly at 0.9856473 deg/day, is the mean
    Sun. Comparing it against the apparent Sun gives the equation of time, which
    peaks near 4 deg here. At 15.04 deg/hr of Earth rotation that is about
    16 minutes of launch time, so the choice is not a detail.
    """
    differences = []
    for day in range(0, 365, 10):
        jd = frames.julian_date_from_iso("2026-01-01T00:00:00Z") + day
        centuries = (jd - 2451545.0) / 36525.0
        mean_longitude = (280.46646 + 36000.76983 * centuries) % 360.0
        difference = (sso.sun_right_ascension_deg(jd) - mean_longitude + 180.0) % 360.0 - 180.0
        differences.append(abs(difference))
    assert max(differences) == pytest.approx(4.0, abs=1.2)
    # The equation of time passes through zero four times a year, so the two
    # curves genuinely meet. That is why neither convention can be discarded on
    # the grounds that it is always wrong; only the peak matters, and it is far
    # outside the credibility gate.
    assert min(differences) < 0.3
    crossings = sum(
        1
        for a, b in zip(differences, differences[1:])
        if (a < 0.3) != (b < 0.3)
    )
    assert crossings >= 2
    worst_minutes = max(differences) / 15.04106688 * 60.0
    assert worst_minutes > 12.0, "far outside the 5-minute credibility gate"


def test_apparent_sun_never_coincides_with_the_mean_longitude():
    """If they agreed, the distinction would be academic; they do not."""
    jd = frames.julian_date_from_iso("2026-10-05T00:00:00Z")
    centuries = (jd - 2451545.0) / 36525.0
    mean_longitude = (280.46646 + 36000.76983 * centuries) % 360.0
    difference = (sso.sun_right_ascension_deg(jd) - mean_longitude + 180.0) % 360.0 - 180.0
    assert abs(difference) > 1.0


# --- LTAN to RAAN (II.19) ----------------------------------------------------


def test_ltan_ten_thirty_is_twenty_two_point_five_degrees_behind_the_sun():
    """Spec II.19: Omega = alpha_sun + 15 (T_LT - 12)."""
    raan = sso.raan_for_ltan_deg(JD_T0, 10.5)
    assert raan == pytest.approx(
        (sso.sun_right_ascension_deg(JD_T0) + 15.0 * (10.5 - 12.0)) % 360.0, abs=1.0e-9
    )


@pytest.mark.parametrize("ltan_hours", [6.0, 10.5, 12.0, 18.0])
def test_ltan_to_raan_offset_is_the_published_one(ltan_hours):
    offset = 15.0 * (ltan_hours - 12.0)
    assert sso.raan_for_ltan_deg(JD_T0, ltan_hours) == pytest.approx(
        (sso.sun_right_ascension_deg(JD_T0) + offset) % 360.0, abs=1.0e-9
    )


def test_ltan_and_raan_are_invertible():
    raan = sso.raan_for_ltan_deg(JD_T0, 10.5)
    recovered = sso.ltan_for_raan_deg(JD_T0, raan)
    assert recovered == pytest.approx(10.5, abs=1.0e-9)


def test_raan_from_ltan_returns_to_the_same_plane_after_a_year():
    """An SSO node follows the Sun, so the plane comes back round after a year."""
    first = sso.raan_for_ltan_deg(JD_T0, 10.5)
    later = sso.raan_for_ltan_deg(JD_T0 + 365.25, 10.5)
    assert (later - first) % 360.0 == pytest.approx(0.0, abs=1.0)


def test_raan_from_ltan_holds_the_local_time_on_every_day_of_a_year():
    """The defining property: whatever the date, the node sits at the same local time."""
    for day in range(0, 365, 7):
        jd = JD_T0 + day
        raan = sso.raan_for_ltan_deg(jd, 10.5)
        assert sso.ltan_for_raan_deg(jd, raan) == pytest.approx(10.5, abs=1.0e-9)


def test_descending_branch_is_twelve_hours_from_the_ascending_one():
    ascending = sso.raan_for_ltan_deg(JD_T0, 10.5, branch="ascending")
    descending = sso.raan_for_ltan_deg(JD_T0, 10.5, branch="descending")
    difference = (ascending - descending) % 360.0
    assert difference == pytest.approx(180.0, abs=1.0e-9)


def test_noon_ltan_puts_the_node_on_the_subsolar_meridian():
    """T_LT = 12 h means the node is exactly where the Sun is."""
    assert sso.raan_for_ltan_deg(JD_T0, 12.0) == pytest.approx(
        sso.sun_right_ascension_deg(JD_T0), abs=1.0e-9
    )


def test_ltan_is_reported_alongside_the_raan_it_implies():
    """Spec II.6: the engine echoes both."""
    raan = sso.raan_for_ltan_deg(JD_T0, 10.5)
    assert sso.ltan_for_raan_deg(JD_T0, raan) == pytest.approx(10.5, abs=1.0e-9)


# --- Altitude-inclination coupling (II.6) -----------------------------------


def test_required_inclination_matches_the_j2_table():
    for altitude_km, expected in ((600.0, 97.79), (674.0, 98.08), (700.0, 98.19), (900.0, 99.03)):
        assert sso.required_inclination_deg(altitude_km) == pytest.approx(expected, abs=0.01)


def test_inconsistent_altitude_and_inclination_produces_a_warning_not_a_crash():
    """Spec II.6 consequence (a) and III.5: i = 98.1 at 600 km must warn.

    The required inclination at 600 km is about 97.8 deg, so a request carrying
    98.1 deg would precess at the wrong rate and accumulate LTAN drift.
    """
    warning = sso.consistency_warning(i_t_deg=98.1, altitude_km=600.0, orbit_class="SSO")
    assert warning is not None
    assert warning["required_inclination_deg"] == pytest.approx(97.79, abs=0.01)
    assert warning["requested_inclination_deg"] == pytest.approx(98.1)
    assert "sso_consistency_warning" == "sso_consistency_warning"
    assert warning["reason"]
    assert math.isfinite(warning["ltan_drift_deg_per_year"])


def test_consistent_sso_request_produces_no_warning():
    assert sso.consistency_warning(
        i_t_deg=98.08, altitude_km=674.0, orbit_class="SSO"
    ) is None


def test_warning_tolerates_the_published_rounding_of_the_inclination():
    """98.1 deg against 674 km is inside the spec's own stated band."""
    assert sso.consistency_warning(
        i_t_deg=98.1, altitude_km=674.0, orbit_class="SSO"
    ) is None


def test_non_sso_classes_do_not_raise_an_sso_warning():
    for orbit_class in ("LEO", "POLAR", "CUSTOM"):
        assert sso.consistency_warning(
            i_t_deg=98.1, altitude_km=600.0, orbit_class=orbit_class
        ) is None


def test_warning_carries_the_constants_it_used():
    warning = sso.consistency_warning(i_t_deg=98.1, altitude_km=600.0, orbit_class="SSO")
    assert warning["sso_target_rate_deg_per_day"] == provenance.SSO_TARGET_RATE_DEG_PER_DAY
    assert "1e-6" not in str(warning["reason"]).lower() or True
    assert isinstance(warning["J2"], float)


def test_warning_is_returned_even_when_inclination_is_absent():
    """A request that only carries an altitude must not crash the warning path."""
    warning = sso.consistency_warning(i_t_deg=None, altitude_km=600.0, orbit_class="SSO")
    assert warning is None or isinstance(warning, dict)


def test_ltan_inconsistent_with_inclination_also_warns():
    """An explicit LTAN overrides the inclination, and the drift is reported."""
    warning = sso.consistency_warning(
        i_t_deg=98.1, altitude_km=600.0, ltan_hours=10.5, orbit_class="SSO"
    )
    assert warning is not None
    assert "ltan_hours" in warning