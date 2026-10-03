"""SSO specifics: LTAN-RAAN coupling, and why 98.1 deg is altitude-specific.

Spec II.6. An LTAN requirement is a date-indexed RAAN requirement:

    Omega_required = alpha_sun + 15 deg * (T_LT - 12 h)                       (II.19)

WHICH SUN, AND WHY IT WAS DECIDED BY MEASUREMENT. The spec describes alpha_sun
as advancing at 0.9856 deg/day, which is the MEAN sun. A published LTAN is
referenced to the Sun as actually observed, so the two differ by the equation of
time, which reaches about 4 deg. Four degrees is 16 minutes of launch time, which
would put the engine outside its own 5-minute credibility gate.

Rather than argue this out, both conventions were run against three published
launches with published inclination and published node time (see
data/published_windows.json and tests/test_reproduce_published_windows.py):

    convention        Sentinel-1C    EarthCARE    Sentinel-5P
    mean longitude         +7.51 min    -717.94 min   +14.73 min
    apparent Sun (used)    -1.55 min      -0.55 min    +0.91 min

So the apparent Sun is used. The three residuals are the gate, not a preference.

Accuracy of the series is about 0.01 deg, which is 0.04 s of launch time. It is
recorded as a modelling choice in the README, not hidden.

BRANCH. "Local time of the descending node" differs from the ascending node time
by 12 h. Requests carry the branch explicitly because conflating them moves
every window half a day, not minutes.
"""

from __future__ import annotations

import math
from typing import Any

from backend.engine import frames, j2, provenance

# A request is consistent when its inclination is within this of the value the
# altitude demands. Set to the spec's own stated band: it quotes 98.1 deg at
# 674 km alongside 98.08 to 98.19 at the same altitude.
INCLINATION_TOLERANCE_DEG = 0.15

ASCENDING = "ascending"
DESCENDING = "descending"

DEG = math.pi / 180.0
_J2000_JD = 2451545.0
_CENTURY_DAYS = 36525.0


def _obliquity_deg(t: float, omega_deg: float) -> float:
    mean_obliquity = (
        23.439291
        - 0.0130042 * t
        - 1.64e-7 * t * t
        + 5.04e-7 * t * t * t
    )
    return mean_obliquity + 0.00256 * math.cos(omega_deg * DEG)


def sun_right_ascension_deg(jd_ut1: float) -> float:
    """Apparent right ascension of the Sun, degrees on [0, 360).

    Low-precision solar coordinates: mean longitude plus the equation of centre,
    corrected for aberration and nutation, then projected onto the true equator
    of date. Accurate to roughly 0.01 deg.

    Two independent anchors are asserted in tests/test_sso.py: alpha_sun is 0 deg
    at the March equinox and 270 deg at the December solstice. Both agree to
    0.005 deg.
    """
    t = (jd_ut1 - _J2000_JD) / _CENTURY_DAYS

    mean_longitude = 280.46646 + 36000.76983 * t + 0.0003032 * t * t
    mean_anomaly = 357.52911 + 35999.05029 * t - 0.0001537 * t * t

    m = mean_anomaly * DEG
    centre = (
        (1.914602 - 0.004817 * t - 0.000014 * t * t) * math.sin(m)
        + (0.019993 - 0.000101 * t) * math.sin(2.0 * m)
        + 0.000289 * math.sin(3.0 * m)
    )
    true_longitude = mean_longitude + centre

    omega = 125.04 - 1934.136 * t
    apparent_longitude = true_longitude - 0.00569 - 0.00478 * math.sin(omega * DEG)
    return _project_to_equator(apparent_longitude, _obliquity_deg(t, omega))


def _project_to_equator(longitude_deg: float, obliquity_deg: float) -> float:
    """Ecliptic longitude to right ascension on the true equator of date."""
    lam = longitude_deg * DEG
    eps = obliquity_deg * DEG
    return math.degrees(math.atan2(math.cos(eps) * math.sin(lam), math.cos(lam))) % 360.0


def raan_for_ltan_deg(jd_ut1: float, ltan_hours: float, branch: str = ASCENDING) -> float:
    """(II.19): the RAAN that puts the node at a given local solar time.

    ``ltan_hours`` is decimal local solar time, 10.5 for 10:30. A descending
    node is 180 deg of RAAN away from the ascending one.
    """
    raan = sun_right_ascension_deg(jd_ut1) + 15.0 * (ltan_hours - 12.0)
    if branch == DESCENDING:
        raan += 180.0
    return raan % 360.0


def ltan_for_raan_deg(jd_ut1: float, raan_deg: float, branch: str = ASCENDING) -> float:
    """Inverse of :func:`raan_for_ltan_deg`, decimal local solar hours on [0, 24)."""
    offset = raan_deg - sun_right_ascension_deg(jd_ut1)
    if branch == DESCENDING:
        offset -= 180.0
    return (offset / 15.0 + 12.0) % 24.0


def required_inclination_deg(altitude_km: float) -> float:
    """The SSO inclination an altitude demands, spec II.6.

    Delegates to the J2 module so the table has exactly one definition.
    """
    return j2.sso_inclination_deg(altitude_km)


def consistency_warning(
    i_t_deg: float | None,
    altitude_km: float | None,
    ltan_hours: float | None = None,
    orbit_class: str = "CUSTOM",
) -> dict[str, Any] | None:
    """Warn when an SSO request asks for an inclination its altitude cannot hold.

    Spec II.6 consequence (a): a request for i = 98.1 deg at 600 km is
    inconsistent, because 600 km requires about 97.79 deg. The node would
    precess at the wrong rate and LTAN drift would accumulate. Returns None when
    the request is consistent, so a caller can simply test for truthiness.
    """
    if orbit_class != "SSO" or altitude_km is None:
        return None

    required = required_inclination_deg(altitude_km)

    if i_t_deg is None or abs(i_t_deg - required) <= INCLINATION_TOLERANCE_DEG:
        return None

    drift_per_year = j2.ltan_drift_deg_per_year(altitude_km, i_t_deg)
    return {
        "requested_inclination_deg": float(i_t_deg),
        "required_inclination_deg": required,
        "altitude_km": float(altitude_km),
        "tolerance_deg": INCLINATION_TOLERANCE_DEG,
        "sso_target_rate_deg_per_day": provenance.SSO_TARGET_RATE_DEG_PER_DAY,
        "node_rate_deg_per_day": j2.nodal_rate_deg_per_day(altitude_km, i_t_deg),
        "ltan_drift_deg_per_year": drift_per_year,
        "ltan_hours": ltan_hours,
        "J2": provenance.J2,
        "reason": (
            f"An SSO at {altitude_km:g} km requires an inclination of {required:.2f} deg "
            f"(spec II.6, (II.7) at +{provenance.SSO_TARGET_RATE_DEG_PER_DAY} deg/day). The "
            f"requested {i_t_deg:.2f} deg precesses at "
            f"{j2.nodal_rate_deg_per_day(altitude_km, i_t_deg):+.4f} deg/day, so the node "
            f"holds its local time only to {abs(drift_per_year) * 4.0:.1f} minutes of LTAN "
            f"per year. 98.1 deg is the SSO inclination near 650 to 700 km and is not "
            "portable across altitudes."
        ),
    }