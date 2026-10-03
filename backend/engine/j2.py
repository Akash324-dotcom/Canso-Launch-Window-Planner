"""Secular J2 nodal dynamics (spec II.3).

The window core propagates the target plane by secular J2 nodal regression and
by nothing else, per spec I.4. No other perturbation enters the window search.

    Omega_targ_dot = -(3/2) J2 n (R_e/p)^2 cos(i)     [rad/s]                (II.7)

    n = sqrt(GM/a^3),  p = a(1 - e^2); for a circular orbit p = a.

Every constant is read from :mod:`backend.engine.provenance`. No drift constant
is stored here: the commonly quoted 3.99 deg/day is rejected by spec II.3 and by
``tests/test_j2.py``, which back-solves the inclination that would produce it.
"""

from __future__ import annotations

import math

from backend.engine.provenance import GM, J2, R_E, SSO_TARGET_RATE_DEG_PER_DAY

DEG = math.pi / 180.0
RAD = 180.0 / math.pi
SECONDS_PER_DAY = 86400.0


def semi_major_axis_m(altitude_km: float) -> float:
    """a = R_e + h for a circular target orbit (spec II.0)."""
    return R_E + altitude_km * 1000.0


def mean_motion_rad_s(altitude_km: float, eccentricity: float = 0.0) -> float:
    """n = sqrt(GM / a^3), rad/s."""
    return math.sqrt(GM / semi_major_axis_m(altitude_km) ** 3)


def nodal_rate_rad_s(altitude_km: float, inclination_deg: float, eccentricity: float = 0.0) -> float:
    """Secular nodal regression in rad/s, (II.7).

    Sign convention (spec II.3): prograde orbits, cos(i) > 0, regress and give a
    negative rate; retrograde orbits advance and give a positive rate.
    """
    a = semi_major_axis_m(altitude_km)
    n = math.sqrt(GM / a**3)
    p_over_a = 1.0 - eccentricity * eccentricity
    return -1.5 * J2 * n * (R_E / a) ** 2 * math.cos(inclination_deg * DEG) / p_over_a**2


def nodal_rate_deg_per_day(
    altitude_km: float, inclination_deg: float, eccentricity: float = 0.0
) -> float:
    """(II.7) converted to deg/day, the unit the window code carries."""
    return nodal_rate_rad_s(altitude_km, inclination_deg, eccentricity) * RAD * SECONDS_PER_DAY


def sso_inclination_deg(altitude_km: float) -> float:
    """The sun-synchronous inclination at an altitude (spec II.6).

    Solves (II.7) for i at the fixed target rate of +0.9856 deg/day. This is the
    reason 98.1 deg is altitude-specific: it is the value near 650 to 700 km and
    carries no meaning at 600 km.
    """
    a = semi_major_axis_m(altitude_km)
    n = math.sqrt(GM / a**3)
    scale = 1.5 * J2 * n * (R_E / a) ** 2
    target_rad_s = SSO_TARGET_RATE_DEG_PER_DAY / RAD / SECONDS_PER_DAY
    cos_i = -target_rad_s / scale
    if not -1.0 <= cos_i <= 1.0:
        raise ValueError(
            f"no sun-synchronous inclination exists at {altitude_km} km"
        )
    return math.degrees(math.acos(cos_i))


def ltan_drift_deg_per_year(
    altitude_km: float, inclination_deg: float
) -> float:
    """LTAN drift from an inclination error, spec II.6 consequence (b).

    The node precesses at a rate set by inclination; any mismatch with the mean
    Sun's 0.9856 deg/day shows up as accumulated LTAN drift.
    """
    rate = nodal_rate_deg_per_day(altitude_km, inclination_deg)
    return (rate - SSO_TARGET_RATE_DEG_PER_DAY) * 365.25