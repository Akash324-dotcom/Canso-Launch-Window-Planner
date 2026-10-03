"""Reachability from the pad (spec II.2).

Claim (ii) of spec II.9 is PROVED and algebraic, and this module is where it
lives:

    Direct ascent from site latitude phi_s reaches inclination i if and only if
    i lies in [phi_s, 180 deg - phi_s], because the ascent plane is spanned by
    the site position and the liftoff velocity, whose component algebra gives

        cos(i) = cos(phi_s) * sin(beta)                                        (II.2)

    and solving for beta needs |cos(i)/cos(phi_s)| <= 1.

The corridor of (II.3) is a separate, configured restriction on beta applied on
top of that algebraic bound. Both predicates are exposed separately so a caller
can say which one failed.
"""

from __future__ import annotations

import math
from typing import Any, Mapping

from backend.engine import provenance

DEG = math.pi / 180.0
RAD = 180.0 / math.pi


def _corridor(corridor: Mapping[str, Any] | None) -> tuple[float, float]:
    if corridor is None:
        raise ValueError("a corridor configuration is required")
    a_min = corridor.get("A_min_deg")
    a_max = corridor.get("A_max_deg")
    if a_min is None or a_max is None:
        raise ValueError("corridor requires numeric A_min_deg and A_max_deg")
    return float(a_min), float(a_max)


# --- Azimuth (spec II.2) -----------------------------------------------------


def launch_azimuth_deg(i_t_deg: float, lat_deg: float) -> float | None:
    """Southbound launch azimuth for a target inclination, or None if impossible.

    ``beta = 180 - asin(cos(i)/cos(phi_s))`` on the southbound branch, which runs
    continuously from due east at i = phi_s, through due south at i = 90 deg, to
    the retrograde azimuths beyond. Returns None when |sin(beta)| would exceed 1,
    which is exactly the advertised-LEO impossibility case.
    """
    cos_lat = math.cos(lat_deg * DEG)
    if abs(cos_lat) < 1.0e-15:
        raise ValueError("reachability is undefined at the pole")
    ratio = math.cos(i_t_deg * DEG) / cos_lat
    if ratio > 1.0 + 1.0e-12 or ratio < -1.0 - 1.0e-12:
        return None
    return (180.0 - math.degrees(math.asin(max(-1.0, min(1.0, ratio))))) % 360.0


def northbound_partner_deg(beta_south_deg: float) -> float:
    """The prograde partner azimuth, 180 - beta on the northbound branch (spec II.2)."""
    return (180.0 - beta_south_deg) % 360.0


# --- Predicates --------------------------------------------------------------


def geometric_inclination_bounds(lat_deg: float) -> tuple[float, float]:
    """Inclinations a direct ascent can reach, [phi_s, 180 - phi_s]."""
    return lat_deg, 180.0 - lat_deg


def reachable(i_t_deg: float, lat_deg: float) -> bool:
    """Claim (ii), PROVED: geometric reachability, corridor not applied."""
    low, high = geometric_inclination_bounds(lat_deg)
    return low - 1.0e-9 <= i_t_deg <= high + 1.0e-9


def azimuth_in_corridor(beta_deg: float, corridor: Mapping[str, Any] | None) -> bool:
    a_min, a_max = _corridor(corridor)
    return a_min - 1.0e-9 <= beta_deg <= a_max + 1.0e-9


def corridor_inclination_bounds(
    lat_deg: float, corridor: Mapping[str, Any] | None
) -> tuple[float, float]:
    """Inclinations admitted by the corridor, [i(A_max), i(A_min)] (spec II.2).

    ``i(beta) = arccos(cos(phi_s) sin(beta))`` is monotone on the southbound
    branch, so the image of the closed azimuth interval is a closed interval.
    """
    a_min, a_max = _corridor(corridor)
    cos_lat = math.cos(lat_deg * DEG)
    at_min = math.degrees(math.acos(max(-1.0, min(1.0, cos_lat * math.sin(a_min * DEG)))))
    at_max = math.degrees(math.acos(max(-1.0, min(1.0, cos_lat * math.sin(a_max * DEG)))))
    return min(at_min, at_max), max(at_min, at_max)


def reachable_in_corridor(
    i_t_deg: float, lat_deg: float, corridor: Mapping[str, Any] | None
) -> bool:
    """Spec (II.4), the first gate: reachability WITH the corridor applied."""
    if not reachable(i_t_deg, lat_deg):
        return False
    beta = launch_azimuth_deg(i_t_deg, lat_deg)
    return beta is not None and azimuth_in_corridor(beta, corridor)


# --- Plane-change penalty (spec II.5) ----------------------------------------


def circular_speed_ms(altitude_km: float) -> float:
    """Circular orbital speed at a target altitude, sqrt(GM / (R_e + h))."""
    return math.sqrt(provenance.GM / (provenance.R_E + altitude_km * 1000.0))


def plane_change_dv_ms(i_t_deg: float, lat_deg: float, altitude_km: float) -> float:
    """Delta-v = 2 v_c sin(Delta_i / 2), the cost of closing the gap to reach i_t.

    Spec (II.5) prices one case, the advertised 45.1 deg target below the 45.3 N
    pad. Both unreachable cases are handled symmetrically:

    * i_t below phi_s. The direct-ascent floor is the pad latitude, so the
      lateral maneuver has to take out Delta_i = phi_s - i_t. This is the
      advertised case, and the Cyclone-4M guide documents exactly this
      equatorial lateral maneuver for inclinations under 45.1 deg.
    * i_t above 180 - phi_s. The ceiling is the supplement, and the maneuver has
      to take out Delta_i = i_t - (180 - phi_s).

    Any inclination strictly inside [phi_s, 180 - phi_s] is reached by choosing
    the azimuth, so the penalty is exactly zero. Reporting a non-zero cost for a
    reachable target would be inventing a constraint that does not exist.
    """
    low, high = geometric_inclination_bounds(lat_deg)
    if low <= i_t_deg <= high:
        return 0.0
    delta_i_deg = low - i_t_deg if i_t_deg < low else i_t_deg - high
    return 2.0 * circular_speed_ms(altitude_km) * math.sin(abs(delta_i_deg) * DEG / 2.0)