"""E2 State and frames.

Spec II.1. Geodetic/ECEF conversion on the WGS84 ellipsoid, and Greenwich mean
sidereal time under the IAU 1982 model.

REFERENCE VALUES AND THEIR SOURCES
-----------------------------------
GMST at J2000.0:
    J2000.0 is Julian Date 2451545.0, that is 2000-01-01 12:00:00 UT1. The IAU
    1982 sidereal-time series is

        GMST = 67310.54841 + (876600 h + 8640184.812866) T + 0.093104 T^2
               - 6.2e-6 T^3   seconds,   T = (JD_UT1 - 2451545.0) / 36525

    whose constant term is by definition GMST at J2000.0, namely
    67310.54841 s = 18 h 41 m 50.54841 s = 280.460618375 deg. So this test
    pins the epoch reference to the model's own definition rather than to a
    remembered almanac page, which is the honest way to state it.
    Source: IAU 1982 GMST model as adopted in Vallado, "Fundamentals of
    Astrodynamics and Applications"; spec II.1 and II.10 name the model.

Canso site coordinates:
    45.3 N, 61.0 W. Spec II.1 takes these from the Cyclone-4M Abbreviated User's
    Guide section 2.2 and marks them VERIFIED (spec F.2). They are configuration
    values, so they are read from data/site_canso.json, not written here.

Rotating-frame azimuth (spec II.6):
    tan(beta_rot) = [v_orb sin(beta) - v_e] / [v_orb cos(beta)] with
    v_e = omega_sid R_e cos(phi_s). At the equator the site latitude factor
    cos(phi_s) is 1 and the due-east boundary launch (beta = 90 deg, the
    azimuth that yields i = 0 from a site on the equator) has zero north
    component, so beta_rot collapses exactly onto beta and the correction
    vanishes. Away from the equator the same algebra leaves a residual.
"""

from __future__ import annotations

import math

import pytest

from backend.engine import frames, provenance

SIDEREAL_DAY_S = frames.sidereal_day_seconds()

GMST_J2000_DEG = 67310.54841 / 240.0  # seconds -> degrees
DEG_PER_RAD = 180.0 / math.pi


def test_julian_date_for_j2000():
    assert frames.julian_date(2000, 1, 1, 12, 0, 0.0) == pytest.approx(2451545.0, abs=1e-9)


@pytest.mark.parametrize(
    "args, expected",
    [
        ((2000, 1, 1, 12, 0, 0.0), 2451545.0),
        ((1970, 1, 1, 0, 0, 0.0), 2440587.5),
        ((1987, 4, 10, 0, 0, 0.0), 2446895.5),
        ((2026, 10, 3, 0, 0, 0.0), 2461316.5),
        ((2026, 10, 4, 13, 30, 0.0), 2461318.0625),
    ],
)
def test_julian_date_known_values(args, expected):
    assert frames.julian_date(*args) == pytest.approx(expected, abs=1e-9)


def test_gmst_at_the_published_epoch():
    """IAU 1982 GMST at J2000.0, to 1e-6 deg."""
    gmst = frames.gmst_degrees(frames.julian_date(2000, 1, 1, 12, 0, 0.0))
    assert gmst == pytest.approx(GMST_J2000_DEG, abs=1.0e-6)


def test_gmst_is_normalised_into_zero_to_360():
    for jd in (2451545.0, 2446895.5, 2461318.5):
        value = frames.gmst_degrees(jd)
        assert 0.0 <= value < 360.0


def test_gmst_advances_by_one_full_turn_per_sidereal_day():
    """The defining property of sidereal time, independent of the epoch value.

    The residual is not zero: the IAU 1982 series and the stored omega_sid
    constant disagree on the sidereal day at the 1e-7 relative level, which is
    0.15 s of Earth rotation per sidereal day.
    """
    start = frames.gmst_degrees(2461316.5)
    later = frames.gmst_degrees(2461316.5 + SIDEREAL_DAY_S / 86400.0)
    delta = (later - start) % 360.0
    assert min(delta, 360.0 - delta) < 1.0e-3


def test_gmst_advances_at_the_sidereal_rate_per_hour():
    """Spec II.11 quotes 15.0411 deg/hr; the series and omega_sid agree to 1e-7."""
    jd = 2461316.5
    one_hour_later = frames.gmst_degrees(jd + 1.0 / 24.0)
    advance = (one_hour_later - frames.gmst_degrees(jd)) % 360.0
    assert advance == pytest.approx(15.0411, abs=1.0e-4)
    from_constant = provenance.OMEGA_SID_RAD_S * DEG_PER_RAD * 3600.0
    assert advance == pytest.approx(from_constant, abs=1.0e-4)


def test_sidereal_day_is_about_23h56m_s():
    assert SIDEREAL_DAY_S == pytest.approx(86164.1, abs=0.1)
    assert SIDEREAL_DAY_S < 86400.0


def test_gmst_of_utc_string_round_trips_through_julian_date():
    jd = frames.julian_date_from_iso("2026-10-04T13:30:00Z")
    assert jd == pytest.approx(2461318.0625, abs=1.0e-9)
    assert frames.iso_from_julian_date(jd) == "2026-10-04T13:30:00Z"


def test_unwrapped_gmst_is_continuous_where_the_reduced_one_jumps():
    """The root solver needs a continuous GMST; the reduced one jumps by 360 deg.

    Locate the instant where sidereal time crosses a whole turn, then step one
    second across it. The reduced evaluation reports the short step, having
    wrapped; the unreduced one reports the same short step as a plain
    difference. The wrapper is what silently breaks a Newton solve, so the two
    behaviours are pinned here rather than discovered later.
    """
    crossing = None
    previous = None
    for index in range(4000):
        jd = 2461318.0 + index * 0.01
        remainder = frames.gmst_degrees_unwrapped(jd) % 360.0
        if previous is not None and previous > 350.0 and remainder < 10.0:
            crossing = jd
            break
        previous = remainder
    assert crossing is not None, "a whole turn is crossed within the sampled window"

    just_below = crossing - 1.0 / 86400.0
    just_above = crossing + 1.0 / 86400.0
    reduced_jump = (frames.gmst_degrees(just_above) - frames.gmst_degrees(just_below)) % 360.0
    # GMST turns 360 deg in one sidereal day, so it advances 15.041 deg per HOUR.
    assert reduced_jump == pytest.approx(2.0 / 3600.0 * 15.04106688, abs=1e-6)

    unwrapped_step = frames.gmst_degrees_unwrapped(just_above) - frames.gmst_degrees_unwrapped(
        just_below
    )
    # Differencing two sidereal times of magnitude 3.5e6 deg leaves about 5e-8 deg
    # of float64 noise, which is 13 microseconds of Earth rotation.
    assert unwrapped_step == pytest.approx(2.0 / 3600.0 * 15.04106688, abs=1.0e-6)
    assert abs(unwrapped_step) < 1.0


def test_unwrapped_gmst_advances_at_the_same_rate():
    unwrapped = frames.gmst_degrees_unwrapped(2461318.5)
    for hours in (1.0, 24.0, 365.0):
        later = frames.gmst_degrees_unwrapped(2461318.5 + hours / 24.0)
        # Relative, not absolute: the IAU 1982 series and omega_sid disagree on
        # the rotation rate at 1.1e-7 relative, which is 6e-4 deg over a year.
        assert later - unwrapped == pytest.approx(
            hours * provenance.OMEGA_SID_RAD_S * DEG_PER_RAD * 3600.0, rel=1.0e-6
        )


def test_unwrapped_gmst_agrees_with_the_reduced_one_modulo_a_turn():
    for jd in (2451545.0, 2461318.5, 2461318.4999):
        difference = (
            frames.gmst_degrees_unwrapped(jd) - frames.gmst_degrees(jd)
        ) % 360.0
        assert min(difference, 360.0 - difference) < 1.0e-6


# --- Geodetic <-> ECEF -------------------------------------------------------


def test_canso_geodetic_to_ecef_and_back_within_1e_9():
    lat, lon, height = 45.3, -61.0, 0.0
    x, y, z = frames.geodetic_to_ecef(lat, lon, height)
    lat2, lon2, height2 = frames.ecef_to_geodetic(x, y, z)
    assert lat2 == pytest.approx(lat, abs=1.0e-9)
    assert lon2 == pytest.approx(lon, abs=1.0e-9)
    assert height2 == pytest.approx(height, abs=1.0e-6)


@pytest.mark.parametrize("lat", [0.0, 45.3, -45.3, 61.0, 89.9])
@pytest.mark.parametrize("lon", [-180.0, -61.0, 0.0, 61.0, 179.0])
def test_geodetic_round_trip_on_a_grid(lat, lon):
    x, y, z = frames.geodetic_to_ecef(lat, lon, 120.0)
    lat2, lon2, height2 = frames.ecef_to_geodetic(x, y, z)
    assert lat2 == pytest.approx(lat, abs=1.0e-9)
    assert lon2 == pytest.approx(lon, abs=1.0e-9)
    assert height2 == pytest.approx(120.0, abs=1.0e-6)


def test_ecef_radius_at_the_equator_is_the_equatorial_radius():
    x, y, z = frames.geodetic_to_ecef(0.0, 0.0, 0.0)
    assert math.hypot(x, y, z) == pytest.approx(provenance.R_E, abs=1.0e-6)


def test_ecef_to_eci_and_back_is_identity_over_one_sidereal_day():
    """Spec III.1 row: ECEF to ECI to ECEF over one sidereal day, within 1e-9 rad."""
    jd = 2461318.5
    jd_later = jd + SIDEREAL_DAY_S / 86400.0
    x, y, z = frames.geodetic_to_ecef(45.3, -61.0, 0.0)
    vector = (x, y, z)
    first = frames.ecef_to_eci(vector, jd)
    back = frames.eci_to_ecef(first, jd)
    assert math.dist(vector, back) / provenance.R_E < 1.0e-9
    second = frames.ecef_to_eci(vector, jd_later)
    turned = frames.eci_to_ecef(second, jd_later)
    assert math.dist(vector, turned) / provenance.R_E < 1.0e-9


# --- Rotating-frame azimuth (spec II.6) --------------------------------------


def test_azimuth_correction_at_canso_has_the_positive_sign():
    """Southbound from 45.3 N: the rotating-frame azimuth exceeds the inertial one.

    The site is moving east at omega_sid R_e cos(phi_s) = 327 m/s at Canso.
    To hold the same inertial azimuth the ground-relative east component must
    drop by that amount, which for a strongly southward velocity turns the
    heading toward 180 deg, so beta_rot > beta.
    """
    lat, beta, height = 45.3, 177.0, 0.0
    correction = frames.azimuth_correction_deg(beta, lat, height)
    assert correction > 0.0
    assert frames.launch_azimuth_compass(beta, lat, height) == pytest.approx(beta + correction)


def test_azimuth_correction_is_zero_at_the_equator_for_the_due_east_boundary():
    """On the equator the reachable azimuth for i = 0 is due east, and it is fixed."""
    correction = frames.azimuth_correction_deg(90.0, 0.0, 0.0)
    assert correction == pytest.approx(0.0, abs=1.0e-12)


def test_azimuth_correction_scales_with_the_site_equatorial_velocity():
    """Same inertial azimuth from a lower site leaves a larger correction.

    The correction grows with v_e = omega_sid R_e cos(phi_s), which is largest at
    the equator and vanishes at the pole. A site at 20 N therefore shows a
    larger rotating-frame shift than the same azimuth from 60 N.
    """
    beta = 150.0
    low = frames.azimuth_correction_deg(beta, 20.0, 0.0)
    high = frames.azimuth_correction_deg(beta, 60.0, 0.0)
    assert low > high > 0.0
    assert frames.equatorial_speed(20.0) > frames.equatorial_speed(60.0)


def test_azimuth_correction_tends_to_zero_at_the_pole():
    """cos(phi_s) vanishes at the pole, so the site's rotational velocity does."""
    assert frames.azimuth_correction_deg(150.0, 89.999, 0.0) < 1.0e-2


def test_azimuth_compass_keeps_the_eastward_sense_of_a_prograde_launch():
    """A due-east launch must stay eastbound in the rotating frame."""
    beta_rot = frames.launch_azimuth_compass(90.0, 45.3, 0.0)
    assert 0.0 < beta_rot < 180.0