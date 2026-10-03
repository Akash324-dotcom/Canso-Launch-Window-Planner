"""Universal constants and their sources (spec II.10).

This module is the ONLY place in ``backend/engine/`` where a universal physical
constant literal appears. ``tests/test_provenance.py`` enforces that rule by
scanning the package and failing if a literal turns up anywhere else.

Site-, vehicle- and criteria-dependent values do NOT belong here. Those live in
``backend/engine/data/*.json`` and are loaded through :func:`load_json`.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping

DATA_DIR = Path(__file__).resolve().parent / "data"

# --- Universal constants -----------------------------------------------------
# Spec II.10 provenance table. Values are the spec values; the contract notes
# that a corrected constant is not a contract break.

J2 = 1.08262668e-3
GM = 3.986004418e14
R_E = 6378137.0
OMEGA_SID_RAD_S = 7.292115e-5
GMST_MODEL = "IAU_1982"

# WGS84 ellipsoid flattening, used only for the geodetic/ECEF conversion in
# frames.py. Its semi-major axis is R_E above; geodetic and geocentric latitude
# differ on the ellipsoid, so the flattening is required for an exact round trip.
WGS84_FLATTENING = 1.0 / 298.257223563

# Mean apparent motion of the Sun, used as the SSO target nodal drift rate
# (spec II.6 eq. A4, II.10). A constant with a source, never a magic literal in
# the window code.
SSO_TARGET_RATE_DEG_PER_DAY = 0.9856473

CONSTANT_SOURCES: dict[str, str] = {
    "J2": (
        "Earth dynamic flattening coefficient, EGM2008 value; spec II.10 provenance table"
    ),
    "GM": (
        "Earth gravitational parameter, IERS/GM1; spec II.10 provenance table"
    ),
    "R_e": (
        "Earth equatorial radius, EGM2008/WGS84; spec II.10 provenance table"
    ),
    "omega_sid_rad_s": (
        "Earth sidereal rotation rate, 7.292115e-5 rad/s; spec II.10 provenance table"
    ),
    "gmst_model": (
        "Greenwich mean sidereal time, IAU 1982 model, nutation omitted; spec II.1, II.10"
    ),
    "WGS84_flattening": (
        "WGS84 ellipsoid flattening 1/298.257223563; spec II.1 geodetic latitude convention"
    ),
    "SSO_TARGET_RATE_DEG_PER_DAY": (
        "Mean Sun right-ascension motion, 0.9856473 deg/day; spec II.6 eq. A4, II.10"
    ),
}


def constants_block(citation_id: str) -> dict[str, Any]:
    """The spec IV ``constants_block``, including the per-constant source map."""
    return {
        "J2": J2,
        "GM": GM,
        "R_e": R_E,
        "omega_sid_rad_s": OMEGA_SID_RAD_S,
        "gmst_model": GMST_MODEL,
        "citation_id": citation_id,
        "source": dict(CONSTANT_SOURCES),
    }


def load_json(relative_path: str) -> Any:
    """Read a JSON document from ``backend/engine/data/``.

    The only file I/O the engine performs. ``relative_path`` is a literal under
    the package, never caller-supplied text, so there is no traversal surface.
    Every read is recorded so the provenance block can name the files a run
    actually depended on rather than the files that happen to exist.
    """
    path = DATA_DIR / relative_path
    _READ_FILES.add(f"backend/engine/data/{relative_path}")
    return json.loads(path.read_text(encoding="utf-8"))


# --- Provenance echo (spec II.10, III.6) -------------------------------------

_READ_FILES: set[str] = set()


def reset_source_files() -> None:
    """Forget which files have been read. Called at the start of every run."""
    _READ_FILES.clear()


def source_files() -> list[str]:
    """Every data file read since the last reset, as repository-relative paths."""
    return sorted(_READ_FILES)


def build_provenance_block(request: Mapping[str, Any]) -> dict[str, Any]:
    """The spec IV ``provenance_block`` for a request.

    The API composes the block; this exposes every piece it needs so the values
    on the response are the ones the engine actually used, read from the same
    files the numbers came from. ``row_flags`` is the union of the per-row
    VERIFIED and ASSUMPTION flags in the vehicle profile and the corridor.
    """
    site_name = request.get("site") or "canso"
    if site_name != "canso":
        raise ValueError(f"unknown site {site_name!r}; configuration ships for 'canso' only")
    site = load_json("site_canso.json")
    vehicle_id = request.get("vehicle_profile_id") or ""
    profile = load_json(f"vehicles/{vehicle_id}.json") if vehicle_id else {}

    row_flags: dict[str, str] = {}
    override = request.get("corridor")
    # The override replaces the bounds only; the flags, source and assumptions
    # still describe those bounds and must travel with them.
    corridor = {**site["corridor"], **(override or {})}
    for bound in ("A_min_deg", "A_max_deg"):
        flag = corridor.get("flags", {}).get(bound)
        if flag is None:
            flag = site["corridor"]["flags"][bound]
        row_flags[f"corridor.{bound}"] = flag
    for row in profile.get("rows", []):
        row_flags[f"{vehicle_id}.{row['key']}"] = row["flag"]

    return {
        "site": {
            "name": site["name"],
            "latitude_deg": site["latitude_deg"],
            "longitude_deg": site["longitude_deg"],
            "altitude_m": site["altitude_m"],
            "coordinate_source": site["coordinate_source"],
        },
        "corridor": corridor,
        "criteria_version": request.get("criteria_version") or "v1",
        "vehicle_profile_id": vehicle_id,
        "row_flags": row_flags,
        "source_files": source_files(),
    }