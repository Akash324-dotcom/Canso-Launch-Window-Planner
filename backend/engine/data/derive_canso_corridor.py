"""Derive the Canso launch-corridor bounds from first principles.

Inputs (all published, all recorded below):
  PAD_LAT = 45.3103889 N (Reg Doc sec 5.1: 45d18m37.40s N; AUG sec 2.2: 45.3 N)
  Nominal flown inclinations with published azimuths (AUG + Reg Doc):
    51.6 deg -> 118.5 published (AUG 2.4.1); geometric (II.2) 117.98
    87.9 deg -> geometric 177.01 (polar manifest)
    98.1 deg -> 180 published w/ T+75s dogleg (AUG 2.5.1); geometric 191.56
  Dispersion half-width = 3.0 deg (covers ~6x the demonstrated 0.52 deg
    lofted offset; the 11.56 deg SSO dogleg is a documented manoeuvre, not
    dispersion, and is already inside the fan)

Derivation:
  A_min = min nominal azimuth - dispersion = 117.98 - 3.0 = 114.98 -> 115
  A_max = max nominal azimuth + dispersion = 191.56 + 3.0 = 194.56 -> 195
  Resolution: 1 deg (inputs quoted to 0.1-0.5 deg; geography checks to ~1 deg)

Geography cross-checks (great-circle, WGS84 spherical, recorded):
  - East: 115-deg ray at 60 km = 45.08 N, 60.30 W (open Atlantic); nearest
    NS coast point clears by >20 km cross-track.
  - West: Little Dover bears 237.5 deg at 4.9 km from pad; the 195-deg track
    passes ~3 km east of it, consistent with the AUG T+75s bypass manoeuvre.
  - Downrange: 115-deg/2000 km endpoint 35.76 N, 40.82 W (Atlantic);
    195-deg/2000 km endpoint 27.80 N, 66.18 W (Atlantic east of Bahamas).
  - Newfoundland south coast clears by >150 km cross-track on both bounds.
  - Sable Island (43.93 N, 60.0 W): the 150-deg mid-fan ray passes within
    ~8 km, but 150 deg (i=69.4) is no advertised mission; the occupied bands
    are [115,121], [174,180], [188.6,194.6]. The single-interval engine
    corridor [115,195] is the representable envelope and is conservative.

Cross-range footprint axis (vehicle profile hazard_footprint.cross_range_km):
  half-width = downrange * sin(dispersion half-angle)
             = 2000 km * sin(3 deg) = 104.67 km -> 105 km (5 km resolution).
  Stored as the ellipse half-width with model_class ellipse.
  No published Cyclone-4M stage footprint data was found in the AUG or the
  Registration Document; the AUG gives only timeline events (T+75s manoeuvre,
  T+261s stage-1 separation) and the Reg Doc gives only the 2000 km drop
  distance. Same 3-deg dispersion as the corridor, so the two stay consistent.
"""

from __future__ import annotations

import math

PAD_LAT_DEG = 45.0 + 18.0 / 60.0 + 37.40 / 3600.0
DISPERSION_HALF_WIDTH_DEG = 3.0
CORRIDOR_RESOLUTION_DEG = 1.0
CROSS_RANGE_RESOLUTION_KM = 5.0
DOWNRANGE_KM = 2000.0


def southbound_azimuth_deg(inclination_deg: float, lat_deg: float = PAD_LAT_DEG) -> float:
    """Spec (II.2) southbound branch, independent of the engine under test."""
    ratio = math.cos(math.radians(inclination_deg)) / math.cos(math.radians(lat_deg))
    return (180.0 - math.degrees(math.asin(ratio))) % 360.0


def derive_corridor_bounds() -> tuple[float, float]:
    """Return (A_min_deg, A_max_deg), rounded to the stated 1-deg resolution."""
    nominal = [southbound_azimuth_deg(i) for i in (51.6, 87.9, 98.1)]
    a_min = min(nominal) - DISPERSION_HALF_WIDTH_DEG
    a_max = max(nominal) + DISPERSION_HALF_WIDTH_DEG
    return (
        round(a_min / CORRIDOR_RESOLUTION_DEG) * CORRIDOR_RESOLUTION_DEG,
        round(a_max / CORRIDOR_RESOLUTION_DEG) * CORRIDOR_RESOLUTION_DEG,
    )


def derive_cross_range_km(downrange_km: float = DOWNRANGE_KM) -> float:
    """Ellipse half-width at the stage-impact distance, to 5 km resolution."""
    half = downrange_km * math.sin(math.radians(DISPERSION_HALF_WIDTH_DEG))
    return round(half / CROSS_RANGE_RESOLUTION_KM) * CROSS_RANGE_RESOLUTION_KM


if __name__ == "__main__":
    print("corridor:", derive_corridor_bounds())
    print("cross_range_km:", derive_cross_range_km())
