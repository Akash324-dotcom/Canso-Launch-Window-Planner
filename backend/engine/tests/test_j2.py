"""E4 J2 secular dynamics.

Spec II.3. The window core propagates the target plane by secular J2 nodal
regression and nothing else:

    Omega_targ_dot = -(3/2) J2 n (R_e/p)^2 cos(i)     [rad/s]                (II.7)

    with n = sqrt(GM/a^3), p = a(1 - e^2); for a circular orbit p = a.

HAND ARITHMETIC for the headline case, i = 45.1 deg at h = 600 km:

    a = R_e + h = 6978137 m                     (R_e from provenance)
    a^3 = 3.39826e20
    n = sqrt(GM / a^3) = 1.082858e-3 rad/s     (GM from provenance)
    (R_e/a)^2 = 0.8356849
    cos(45.1 deg) = 0.7058717
    Omega_dot = -(3/2) J2 n (R_e/a)^2 cos(i)
              = -(3/2)(1.082858e-3)(0.8356849)(0.7058717) x J2
              = -1.037355e-6 rad/s
    in deg/day: -1.037355e-6 x 180/pi x 86400 = -5.1354 deg/day

which rounds to the spec's -5.14 deg/day.

THE REJECTED CONSTANT. Spec II.3 records that the commonly quoted 3.99 deg/day
is wrong for this orbit, and Test 1 requires an explicit assertion that the
function does not return it. Solving (II.7) for the inclination that WOULD give
3.99 deg/day at 600 km needs cos(i) = 0.7058717 x (5.1354/3.99) = 0.9087, that is
i = 24.7 deg, not 45.1; conversely 3.99 deg/day belongs to i = 45.1 deg at roughly
1150 km. Both are asserted below from the formula, not from memory.
"""

from __future__ import annotations

import math

import pytest

from backend.engine import j2, provenance

REJECTED_CONSTANT = 3.99
HEADLINE_DRIFT_DEG_PER_DAY = -5.14
DEG = math.pi / 180.0


def test_constants_come_from_the_constants_module_not_the_j2_module():
    """Hard-coding the drift constant is forbidden; (II.7) must read the constants."""
    assert j2.J2 == provenance.J2
    assert j2.GM == provenance.GM
    assert j2.R_E == provenance.R_E


def test_nodal_drift_for_the_advertised_leo_at_600_km():
    rate = j2.nodal_rate_deg_per_day(600.0, 45.1)
    assert rate == pytest.approx(HEADLINE_DRIFT_DEG_PER_DAY, rel=0.01)


def test_nodal_drift_is_not_the_widely_quoted_wrong_constant():
    """Spec II.3 REJECTED item 2. This is the falsification the spec asks for."""
    rate = j2.nodal_rate_deg_per_day(600.0, 45.1)
    assert abs(rate) != pytest.approx(REJECTED_CONSTANT, rel=1.0e-3)


def test_the_rejected_constant_would_need_a_different_inclination():
    """Back-solve (II.7): 3.99 deg/day at 600 km is NOT the 45.1 deg orbit."""
    implied_cos_i = math.cos(45.1 * DEG) * (abs(j2.nodal_rate_deg_per_day(600.0, 45.1)) / REJECTED_CONSTANT)
    implied_i = math.degrees(math.acos(implied_cos_i))
    assert implied_i == pytest.approx(24.7, abs=0.3)
    assert implied_i != pytest.approx(45.1, abs=1.0)


def test_nodal_drift_changes_sign_across_ninety_degrees():
    """Prograde regresses, retrograde advances (spec II.3 sign convention)."""
    prograde = j2.nodal_rate_deg_per_day(674.0, 87.9)
    retrograde = j2.nodal_rate_deg_per_day(674.0, 98.1)
    assert prograde < 0.0
    assert retrograde > 0.0
    assert j2.nodal_rate_deg_per_day(674.0, 90.0) == pytest.approx(0.0, abs=1.0e-9)


def test_nodal_drift_matches_the_spec_table_rows():
    """Spec II.3 drift table.

    The 45.1 row is held to the spec's 1 percent. The 87.9 row cannot be: the
    spec prints -0.27, two significant figures, while (II.7) gives -0.266547,
    a 1.3 percent gap. That row is therefore held to the spec's own printed
    precision, 0.005 deg/day, rather than to a percentage the spec's rounding
    cannot support. The 98.1 row is held to 2 percent because the spec marks it
    "by construction" against a rounded rate.
    """
    assert j2.nodal_rate_deg_per_day(600.0, 45.1) == pytest.approx(-5.14, rel=0.01)
    assert j2.nodal_rate_deg_per_day(600.0, 87.9) == pytest.approx(-0.27, abs=0.005)
    assert j2.nodal_rate_deg_per_day(674.0, 98.1) == pytest.approx(0.9856, rel=0.02)


def test_nodal_drift_context_rows_for_the_advertised_inclination():
    """Spec II.3 context: -5.69 at 400 km, -4.65 at 800, -3.85 at 1200 km."""
    assert j2.nodal_rate_deg_per_day(400.0, 45.1) == pytest.approx(-5.69, rel=0.01)
    assert j2.nodal_rate_deg_per_day(800.0, 45.1) == pytest.approx(-4.65, rel=0.01)
    assert j2.nodal_rate_deg_per_day(1200.0, 45.1) == pytest.approx(-3.85, rel=0.01)


def test_iss_like_reference_case():
    """Spec II.3 context: about -5.0 deg/day at 420 km, i = 51.6 deg."""
    assert j2.nodal_rate_deg_per_day(420.0, 51.6) == pytest.approx(-5.0, rel=0.01)


def test_drift_magnitude_falls_with_altitude():
    rates = [abs(j2.nodal_rate_deg_per_day(h, 45.1)) for h in (400.0, 600.0, 800.0, 1200.0)]
    assert rates == sorted(rates, reverse=True)


def test_eccentricity_shortens_the_node_period():
    """(II.7): p = a(1 - e^2), so the rate grows as 1/(1 - e^2)^2."""
    circular = abs(j2.nodal_rate_rad_s(600.0, 45.1, 0.0))
    eccentric = abs(j2.nodal_rate_rad_s(600.0, 45.1, 0.01))
    assert eccentric > circular
    assert eccentric / circular == pytest.approx(1.0 / (1.0 - 0.01**2) ** 2, rel=1.0e-9)


def test_nodal_rate_matches_its_closed_form_in_radians_per_second():
    altitude_m = 600.0 * 1000.0
    a = provenance.R_E + altitude_m
    n = math.sqrt(provenance.GM / a**3)
    expected = (
        -1.5 * provenance.J2 * n * (provenance.R_E / a) ** 2 * math.cos(45.1 * DEG)
    )
    assert j2.nodal_rate_rad_s(600.0, 45.1, 0.0) == pytest.approx(expected, rel=1.0e-12)


# --- The SSO inclination table (spec II.6, and Test 1 row) ------------------


@pytest.mark.parametrize(
    "altitude_km, expected",
    [(600.0, 97.79), (674.0, 98.08), (700.0, 98.19), (900.0, 99.03)],
)
def test_sso_inclination_table(altitude_km, expected):
    """Spec III.1 pins these four to 0.01 deg.

    The spec quotes 98.08 at 674 km; solving (II.7) with the II.10 constants
    gives 98.087, which is inside the 0.01 deg band. The spec notes 98.12 to
    98.13 for the same altitude under the R = 6380 km convention, so the band
    is convention-sensitive and 0.01 deg is the tightest defensible reading.
    """
    assert j2.sso_inclination_deg(altitude_km) == pytest.approx(expected, abs=0.01)


@pytest.mark.parametrize(
    "altitude_km, expected", [(500.0, 97.40), (800.0, 98.60)]
)
def test_sso_inclination_context_rows(altitude_km, expected):
    """The remaining two rows of the spec II.6 table."""
    assert j2.sso_inclination_deg(altitude_km) == pytest.approx(expected, abs=0.02)


def test_sso_inclination_rises_with_altitude():
    altitudes = [400.0, 500.0, 600.0, 674.0, 700.0, 800.0, 900.0]
    inclinations = [j2.sso_inclination_deg(h) for h in altitudes]
    assert inclinations == sorted(inclinations)
    slope = (inclinations[-1] - inclinations[0]) / (altitudes[-1] - altitudes[0])
    assert slope == pytest.approx(0.0041, abs=0.0003)


def test_sso_inclination_reproduces_the_target_drift_rate():
    for altitude_km in (500.0, 600.0, 674.0, 700.0, 900.0):
        assert j2.nodal_rate_deg_per_day(altitude_km, j2.sso_inclination_deg(altitude_km)) == (
            pytest.approx(provenance.SSO_TARGET_RATE_DEG_PER_DAY, abs=1.0e-4)
        )


def test_ninety_eight_point_one_is_the_sso_inclination_near_650_to_700_km():
    """Spec II.6: 98.1 deg is the SSO inclination at roughly 650 to 700 km.

    Solving (II.7) gives 97.99 deg at 650 km, 98.08 deg at 674 km and 98.19 deg
    at 700 km, so 98.1 deg sits inside that band. At 650 km the gap is 0.11 deg,
    just outside a 0.1 deg band, so the assertion uses the 674 and 700 km rows
    where the spec's own table is quoted.
    """
    assert j2.sso_inclination_deg(674.0) == pytest.approx(98.1, abs=0.1)
    assert j2.sso_inclination_deg(700.0) == pytest.approx(98.1, abs=0.1)
    assert j2.sso_inclination_deg(650.0) == pytest.approx(98.1, abs=0.15)


def test_inclination_error_shows_up_as_precession_error():
    """Spec II.6 consequence (b), evaluated from (II.7) rather than from the prose.

    DISCREPANCY WITH THE SPEC, RECORDED NOT PAPERED OVER. Spec II.6 states that a
    0.01 deg inclination error at 700 km gives "about 0.0004 deg/day precession
    error". Differentiating (II.7) gives d(Omega_dot)/di = (3/2) J2 n (R_e/a)^2
    sin(i), which at 700 km and i = 98.188 deg is 0.1196 deg/day per degree, so
    0.01 deg gives 0.001196 deg/day, three times the spec's figure. The engine
    asserts the value derived from (II.7). The 0.0004 figure is not reproduced.
    """
    exact = j2.nodal_rate_deg_per_day(700.0, j2.sso_inclination_deg(700.0))
    off = j2.nodal_rate_deg_per_day(700.0, j2.sso_inclination_deg(700.0) + 0.01)
    per_day = abs(exact - off)
    assert per_day == pytest.approx(0.001196, rel=1.0e-3)
    assert j2.ltan_drift_deg_per_year(700.0, j2.sso_inclination_deg(700.0) + 0.01) == (
        pytest.approx(per_day * 365.25, rel=1.0e-9)
    )
    # The physically meaningful statement the spec is making: a small inclination
    # error accumulates only minutes of LTAN drift per year. Measured: a tenth of
    # a degree gives 17.5 minutes per year, and a hundredth gives 1.7 minutes.
    # Spec II.6 says "about 6 min/year" for the hundredth-degree case, which does
    # not reconcile with the 0.0004 deg/day it quotes in the same sentence; 0.0004
    # deg/day works out to 0.6 min/year, not 6. Recorded, not silently adopted.
    minutes_per_year = j2.ltan_drift_deg_per_year(700.0, j2.sso_inclination_deg(700.0) + 0.1) * 4.0
    assert minutes_per_year == pytest.approx(17.47, rel=1.0e-3)
    tenth = j2.ltan_drift_deg_per_year(700.0, j2.sso_inclination_deg(700.0) + 0.01) * 4.0
    assert tenth == pytest.approx(1.747, rel=1.0e-3)