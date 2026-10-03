"""State and frames (spec II.1).

Three jobs, all pure:

1. Julian date and ISO-8601 UTC conversion.
2. Greenwich mean sidereal time under the IAU 1982 model.
3. Geodetic to ECEF on the WGS84 ellipsoid, and the ECEF/ECI rotation that
   relates the fixed and quasi-inertial frames by GMST alone.

Conventions (spec II.0): angles are carried in degrees at the interface and in
radians internally; longitude is east-positive.
"""

from __future__ import annotations

import math
from typing import Iterable

from backend.engine import provenance

DEG = math.pi / 180.0
RAD = 180.0 / math.pi

# IAU 1982 GMST series, seconds.
_GMST_C0 = 67310.54841
_GMST_C1 = 876600.0 * 3600.0 + 8640184.812866
_GMST_C2 = 0.093104
_GMST_C3 = -6.2e-6
_J2000_JD = 2451545.0
_CENTURY_DAYS = 36525.0


# --- Time --------------------------------------------------------------------


def julian_date(year: int, month: int, day: int, hour: int = 0, minute: int = 0,
                second: float = 0.0) -> float:
    """Julian Date for a proleptic Gregorian calendar UTC instant."""
    if month <= 2:
        year -= 1
        month += 12
    a = year // 100
    b = 2 - a + a // 4
    day_fraction = (hour + minute / 60.0 + second / 3600.0) / 24.0
    return (
        math.floor(365.25 * (year + 4716))
        + math.floor(30.6001 * (month + 1))
        + day
        + day_fraction
        + b
        - 1524.5
    )


def julian_date_from_iso(iso: str) -> float:
    """Julian Date from an ISO-8601 instant. Only the ``Z`` form is accepted."""
    if not iso.endswith("Z"):
        raise ValueError("timestamps must be ISO-8601 UTC with a Z suffix")
    date_part, _, time_part = iso[:-1].partition("T")
    year, month, day = (int(part) for part in date_part.split("-"))
    if not time_part:
        return julian_date(year, month, day)
    pieces = time_part.split(":")
    hour = int(pieces[0])
    minute = int(pieces[1]) if len(pieces) > 1 else 0
    second = float(pieces[2]) if len(pieces) > 2 else 0.0
    return julian_date(year, month, day, hour, minute, second)


def _jd_to_calendar(jd: float) -> tuple[int, int, int, int, int, float]:
    shifted = jd + 0.5
    z = math.floor(shifted)
    fraction = shifted - z
    alpha = math.floor((z - 1867216.25) / 36524.25)
    a = z + 1 + alpha - alpha // 4
    b = a + 1524
    c = math.floor((b - 122.1) / 365.25)
    d = math.floor(365.25 * c)
    e = math.floor((b - d) / 30.6001)
    day = b - d - math.floor(30.6001 * e)
    month = e - 1 if e < 14 else e - 13
    year = c - 4716 if month > 2 else c - 4715
    seconds_of_day = fraction * 86400.0
    seconds_of_day = min(seconds_of_day, 86399.999999)
    hour = int(seconds_of_day // 3600.0)
    minute = int((seconds_of_day - hour * 3600.0) // 60.0)
    second = seconds_of_day - hour * 3600.0 - minute * 60.0
    return int(year), int(month), int(day), hour, minute, second


def iso_from_julian_date(jd: float, decimals: int = 0) -> str:
    """ISO-8601 UTC instant with a ``Z`` suffix, truncated to whole seconds by default."""
    year, month, day, hour, minute, second = _jd_to_calendar(jd)
    if decimals == 0:
        whole = int(second)
        if whole >= 60:
            whole = 59
        return f"{year:04d}-{month:02d}-{day:02d}T{hour:02d}:{minute:02d}:{whole:02d}Z"
    return (
        f"{year:04d}-{month:02d}-{day:02d}T"
        f"{hour:02d}:{minute:02d}:{second:0{decimals + 3}.{decimals}f}Z"
    )


# --- Sidereal time -----------------------------------------------------------


def gmst_seconds(jd_ut1: float) -> float:
    """Greenwich mean sidereal time in seconds, IAU 1982, reduced to [0, 86400)."""
    return gmst_seconds_unwrapped(jd_ut1) % 86400.0


def gmst_seconds_unwrapped(jd_ut1: float) -> float:
    """The same series with no reduction, so the result is continuous in t.

    ``gmst_seconds`` jumps by exactly 86400 s each time sidereal time crosses
    zero. That is harmless for reporting but fatal for a root finder, which
    needs a residual that is continuous and monotone. Magnitude grows about
    0.9856 deg/day, so double precision holds far below a microsecond of
    rotation over any date range this engine searches.
    """
    t = (jd_ut1 - _J2000_JD) / _CENTURY_DAYS
    return _GMST_C0 + _GMST_C1 * t + _GMST_C2 * t * t + _GMST_C3 * t * t * t


def gmst_degrees(jd_ut1: float) -> float:
    """GMST in degrees on [0, 360)."""
    return gmst_seconds(jd_ut1) / 240.0


def gmst_degrees_unwrapped(jd_ut1: float) -> float:
    """GMST in degrees with no reduction: continuous and increasing in t."""
    return gmst_seconds_unwrapped(jd_ut1) / 240.0


def sidereal_day_seconds() -> float:
    """Length of one sidereal day, 2 pi / omega_sid, about 86164.1 s."""
    return 2.0 * math.pi / provenance.OMEGA_SID_RAD_S


def site_right_ascension_deg(jd_ut1: float, longitude_deg: float) -> float:
    """Spec II.1 eq. A6: RA_site(t) = GMST(t) + lambda_s."""
    return (gmst_degrees(jd_ut1) + longitude_deg) % 360.0


# --- Geodetic <-> ECEF -------------------------------------------------------


def _ellipsoid() -> tuple[float, float]:
    a = provenance.R_E
    f = provenance.WGS84_FLATTENING
    return a, a * (1.0 - f)


def geodetic_to_ecef(lat_deg: float, lon_deg: float, height_m: float) -> tuple[float, float, float]:
    """Geodetic latitude/longitude/height (deg, deg, m) to ECEF metres."""
    a, b = _ellipsoid()
    lat = lat_deg * DEG
    lon = lon_deg * DEG
    e2 = 1.0 - (b * b) / (a * a)
    sin_lat = math.sin(lat)
    n = a / math.sqrt(1.0 - e2 * sin_lat * sin_lat)
    x = (n + height_m) * math.cos(lat) * math.cos(lon)
    y = (n + height_m) * math.cos(lat) * math.sin(lon)
    z = (n * (1.0 - e2) + height_m) * sin_lat
    return x, y, z


def ecef_to_geodetic(x: float, y: float, z: float) -> tuple[float, float, float]:
    """ECEF metres to geodetic latitude, east-positive longitude and height.

    Bowring's method followed by a short fixed-point polish, so the result
    satisfies the round-trip requirement of spec III.1 to 1e-9 deg.
    """
    a, b = _ellipsoid()
    e2 = 1.0 - (b * b) / (a * a)
    ep2 = (a * a - b * b) / (b * b)
    longitude = math.atan2(y, x)
    horizontal = math.hypot(x, y)
    if horizontal < 1.0e-9:
        latitude = math.copysign(math.pi / 2.0, z)
        height = abs(z) - b
        return latitude * RAD, longitude * RAD, height

    theta = math.atan2(z * a, horizontal * b)
    lat = math.atan2(z + ep2 * b * math.sin(theta) ** 3, horizontal - e2 * a * math.cos(theta) ** 3)
    for _ in range(8):
        sin_lat = math.sin(lat)
        n = a / math.sqrt(1.0 - e2 * sin_lat * sin_lat)
        height = horizontal / math.cos(lat) - n
        lat_new = math.atan2(z, horizontal * (1.0 - e2 * n / (n + height)))
        if abs(lat_new - lat) < 1.0e-16:
            lat = lat_new
            break
        lat = lat_new
    sin_lat = math.sin(lat)
    n = a / math.sqrt(1.0 - e2 * sin_lat * sin_lat)
    height = horizontal / math.cos(lat) - n
    return lat * RAD, longitude * RAD, height


# --- ECI <-> ECEF ------------------------------------------------------------


def ecef_to_eci(vector: Iterable[float], jd_ut1: float) -> tuple[float, float, float]:
    """Rotate an ECEF vector into the quasi-inertial frame by GMST about the polar axis."""
    x, y, z = vector
    theta = gmst_seconds(jd_ut1) * (2.0 * math.pi / 86400.0)
    cos_t, sin_t = math.cos(theta), math.sin(theta)
    return (
        x * cos_t + y * sin_t,
        -x * sin_t + y * cos_t,
        z,
    )


def eci_to_ecef(vector: Iterable[float], jd_ut1: float) -> tuple[float, float, float]:
    """Inverse of :func:`ecef_to_eci`."""
    x, y, z = vector
    theta = gmst_seconds(jd_ut1) * (2.0 * math.pi / 86400.0)
    cos_t, sin_t = math.cos(theta), math.sin(theta)
    return (
        x * cos_t - y * sin_t,
        x * sin_t + y * cos_t,
        z,
    )


# --- Rotating-frame azimuth (spec II.6) --------------------------------------


def equatorial_speed(lat_deg: float, height_m: float = 0.0) -> float:
    """Speed of the ground point due to Earth rotation, omega_sid (R_e + h) cos(phi)."""
    return provenance.OMEGA_SID_RAD_S * (provenance.R_E + height_m) * math.cos(lat_deg * DEG)


def orbital_speed(height_m: float = 0.0) -> float:
    """Circular orbital speed at a height above the equatorial radius."""
    return math.sqrt(provenance.GM / (provenance.R_E + height_m))


def launch_azimuth_compass(beta_deg: float, lat_deg: float, height_m: float = 0.0) -> float:
    """Azimuth in the rotating (ground-relative) frame, spec II.6 eq. A2.

    The inertial azimuth ``beta`` is resolved into east and north components and
    the site's own eastward velocity is removed from the east component.
    """
    beta = beta_deg * DEG
    v_orb = orbital_speed(height_m)
    east = v_orb * math.sin(beta) - equatorial_speed(lat_deg, height_m)
    north = v_orb * math.cos(beta)
    return math.degrees(math.atan2(east, north)) % 360.0


def azimuth_correction_deg(beta_deg: float, lat_deg: float, height_m: float = 0.0) -> float:
    """Difference ``beta_rot - beta`` between the rotating and inertial azimuths."""
    return (launch_azimuth_compass(beta_deg, lat_deg, height_m) - beta_deg + 180.0) % 360.0 - 180.0