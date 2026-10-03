#!/usr/bin/env python3
"""Regenerate the two offline fixtures that carry the SSO geometry.

FRONTEND owns the content of ``backend/fixtures/`` (integration contract seam 3),
API owns the directory. This script rewrites ``windows.json`` and ``ephemeris.json``
from one internally consistent geometry and then validates all five fixture files
against the frozen schemas in ``tests/contract/schemas/``.

WHAT THIS IS NOT
----------------
This is a fixture approximation, not the ENGINE. It implements no window search, no
plane-change arithmetic, no J2 secular rates and no injection-consistent fixed point.
It places one circular two-body orbit so that the shipped ground track starts over the
site at the first liftoff instant and runs south over the Atlantic, and it restates the
window rows with an injection instant exactly 600 s after liftoff. ENGINE replaces both
files with a real run at gate G1; nothing in this file is a claim about the engine.

The orbit is the classic two-body ellipse in the inertial equatorial frame, converted
to ECEF with the Greenwich mean sidereal time model that ``constants_block.gmst_model``
names (IAU 1982, nutation omitted) and with the sidereal rotation rate
omega_sid_rad_s = 7.292115e-5 rad/s. The circular orbit is therefore at constant
altitude and the ground track regresses westward by about 24 deg per revolution, which
is the behaviour the viewer sees.

Standard library only: no third party import, no network, no install step.
"""

from __future__ import annotations

import datetime as dt
import json
import math
import re
import sys
from pathlib import Path
from typing import Any, Iterable

REPO_ROOT = Path(__file__).resolve().parents[2]
FIXTURE_DIR = REPO_ROOT / "backend" / "fixtures"
SCHEMA_DIR = REPO_ROOT / "tests" / "contract" / "schemas"

# Target orbit of the shipped fixture. These are the slide values of spec II and the
# SSO preset of frontend/src/config.js ORBIT_PRESETS.
TARGET_INCLINATION_DEG = 98.1
TARGET_ALTITUDE_KM = 550.0
ORBIT_ID = "sso981"

# Sample grid of the ephemeris.
EPHEMERIS_ORBITS = 2
EPHEMERIS_STEP_S = 60

# Vehicle duration of the fixture: injection is exactly this many seconds after
# liftoff. The value is the Vehicle Duration bonus of the slide, quantified as a
# number, and is an ASSUMPTION of this fixture until ENGINE ships a real profile.
INJECTION_OFFSET_S = 600

# Physical constants, identical to the frozen fixtures and to spec II.10.
GM_M3_S2 = 3.986004418e14
R_EARTH_M = 6378137.0
OMEGA_SID_RAD_S = 7.292115e-5
J2000_MS = 946728000000.0
DAY_MS = 86400000.0

# Rounding of the emitted samples. Five decimals of a degree is about one metre.
LAT_LON_DECIMALS = 5
ALT_DECIMALS = 3

SCHEMA_FOR_FIXTURE = {
    "windows.json": "windows_response.json",
    "weather.json": "weather_probability_response.json",
    "skill.json": "skill_response.json",
    "site.json": "site_response.json",
    "ephemeris.json": "ephemeris_response.json",
}

RFC3339_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
RFC3339_DATE_TIME = re.compile(
    r"^\d{4}-\d{2}-\d{2}[Tt]\d{2}:\d{2}:\d{2}(\.\d+)?([Zz]|[+-]\d{2}:\d{2})$"
)


# --------------------------------------------------------------------------------------
# time helpers
# --------------------------------------------------------------------------------------


def parse_instant(text: str) -> dt.datetime:
    return dt.datetime.strptime(text, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=dt.timezone.utc)


def format_instant(instant: dt.datetime) -> str:
    return instant.astimezone(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def epoch_ms(instant: dt.datetime) -> float:
    return instant.timestamp() * 1000.0


def wrap_deg(value: float) -> float:
    return value % 360.0


def wrap_signed_deg(value: float) -> float:
    wrapped = wrap_deg(value)
    return wrapped - 360.0 if wrapped > 180.0 else wrapped


def gmst_deg(epoch: float) -> float:
    """Greenwich mean sidereal time in degrees, IAU 1982, the model the block names.

    Same polynomial as frontend/src/solar.js gmstDeg, so the fixture and the browser
    agree on the Earth rotation they use.
    """
    days = (epoch - J2000_MS) / DAY_MS
    centuries = days / 36525.0
    return wrap_deg(
        280.46061837
        + 360.98564736629 * days
        + 0.000387933 * centuries * centuries
        - centuries ** 3 / 38710000.0
    )


# --------------------------------------------------------------------------------------
# two-body circular orbit with Earth rotation
# --------------------------------------------------------------------------------------


def position_eci(raan_deg: float, arg_lat_deg: float, semi_major_m: float) -> tuple[float, float, float]:
    """Inertial position of a circular orbit, equatorial frame, argument of perigee zero."""
    raan = math.radians(raan_deg)
    arg_lat = math.radians(arg_lat_deg)
    inc = math.radians(TARGET_INCLINATION_DEG)
    cos_lat, sin_lat = math.cos(arg_lat), math.sin(arg_lat)
    cos_raan, sin_raan = math.cos(raan), math.sin(raan)
    return (
        semi_major_m * (cos_lat * cos_raan - sin_lat * sin_raan * math.cos(inc)),
        semi_major_m * (cos_lat * sin_raan + sin_lat * cos_raan * math.cos(inc)),
        semi_major_m * sin_lat * math.sin(inc),
    )


def velocity_eci(raan_deg: float, arg_lat_deg: float, semi_major_m: float, mean_motion: float) -> tuple[float, float, float]:
    """Inertial velocity of the circular orbit, the derivative of position_eci in u times n."""
    raan = math.radians(raan_deg)
    arg_lat = math.radians(arg_lat_deg)
    inc = math.radians(TARGET_INCLINATION_DEG)
    cos_lat, sin_lat = math.cos(arg_lat), math.sin(arg_lat)
    cos_raan, sin_raan = math.cos(raan), math.sin(raan)
    rate = mean_motion * semi_major_m
    return (
        rate * (-sin_lat * cos_raan - cos_lat * sin_raan * math.cos(inc)),
        rate * (-sin_lat * sin_raan + cos_lat * cos_raan * math.cos(inc)),
        rate * (cos_lat * math.sin(inc)),
    )


def rotate_about_z(vector: tuple[float, float, float], angle_deg: float) -> tuple[float, float, float]:
    angle = math.radians(angle_deg)
    cos_a, sin_a = math.cos(angle), math.sin(angle)
    return (
        vector[0] * cos_a - vector[1] * sin_a,
        vector[0] * sin_a + vector[1] * cos_a,
        vector[2],
    )


def subpoint(position: tuple[float, float, float]) -> tuple[float, float, float]:
    radius = math.sqrt(position[0] ** 2 + position[1] ** 2 + position[2] ** 2)
    latitude = math.degrees(math.asin(position[2] / radius))
    longitude = wrap_signed_deg(math.degrees(math.atan2(position[1], position[0])))
    return latitude, longitude, radius


def argument_of_latitude_southbound(site_lat_deg: float) -> float:
    """Argument of latitude at which the orbit crosses the site latitude going south.

    For a circular orbit the sub-satellite latitude obeys sin(latitude) = sin(i) sin(u),
    where u is the argument of latitude measured from the ascending node. The
    descending branch has cos(u) < 0, so increasing u decreases the latitude and the
    ground track runs south, which is the branch the environmental assessment corridor
    admits from Canso.
    """
    argument = math.sin(math.radians(site_lat_deg)) / math.sin(math.radians(TARGET_INCLINATION_DEG))
    if abs(argument) > 1.0:
        raise ValueError(
            f"inclination {TARGET_INCLINATION_DEG} deg never crosses the site latitude "
            f"{site_lat_deg} deg"
        )
    return 180.0 - math.degrees(math.asin(argument))


def solve_raan_for_site(epoch0: float, site_lat_deg: float, site_lon_deg: float) -> float:
    """RAAN for which the southbound crossing of the site latitude is over the site.

    The inertial longitude of a point of the orbit at argument of latitude u is
    RAAN + atan2(cos(i) sin(u), cos(u)), and the ECEF longitude of the same point is
    that value less the Greenwich mean sidereal angle. Setting the ECEF longitude to
    the site longitude therefore solves for the RAAN in closed form, with u already
    fixed by the site latitude through argument_of_latitude_southbound.
    """
    theta0 = gmst_deg(epoch0)
    arg_lat = argument_of_latitude_southbound(site_lat_deg)
    inc = math.radians(TARGET_INCLINATION_DEG)
    inertial_offset = math.degrees(
        math.atan2(math.cos(inc) * math.sin(math.radians(arg_lat)), math.cos(math.radians(arg_lat)))
    )
    return wrap_deg(site_lon_deg + theta0 - inertial_offset)


def local_azimuth_deg(position: tuple[float, float, float], velocity: tuple[float, float, float]) -> float:
    """Compass azimuth of a velocity vector, resolved in the local frame of a position."""
    latitude, longitude, _ = subpoint(position)
    lat = math.radians(latitude)
    lon = math.radians(longitude)
    east = (-math.sin(lon), math.cos(lon), 0.0)
    north = (-math.sin(lat) * math.cos(lon), -math.sin(lat) * math.sin(lon), math.cos(lat))
    east_speed = sum(a * b for a, b in zip(velocity, east))
    north_speed = sum(a * b for a, b in zip(velocity, north))
    return wrap_deg(math.degrees(math.atan2(east_speed, north_speed)))


def inertial_launch_azimuth_deg(
    theta0: float, raan_deg: float, arg_lat_deg: float, semi_major_m: float, mean_motion: float
) -> float:
    """Azimuth of the orbital velocity at the injection point, spec II.2.

    The plane of this orbit contains the site position vector and the velocity, so
    the classical relation cos(i) = cos(phi_s) sin(beta) holds exactly for this
    azimuth, which is the inertial azimuth the window rows report as azimuth_deg.
    """
    position = rotate_about_z(position_eci(raan_deg, arg_lat_deg, semi_major_m), -theta0)
    inertial = rotate_about_z(velocity_eci(raan_deg, arg_lat_deg, semi_major_m, mean_motion), -theta0)
    return local_azimuth_deg(position, inertial)


def ground_track_heading_deg(
    theta0: float, raan_deg: float, arg_lat_deg: float, semi_major_m: float, mean_motion: float
) -> float:
    """Ground track compass heading at the injection point, that is the rotating frame value.

    The Earth rotates under the vehicle, so the ground velocity is the inertial
    velocity less omega cross position. At Canso the correction is about 2.6 deg,
    which is why the rotating-frame azimuth of the same instant differs from the
    inertial one; spec II.6 reports both.
    """
    position = rotate_about_z(position_eci(raan_deg, arg_lat_deg, semi_major_m), -theta0)
    inertial = rotate_about_z(velocity_eci(raan_deg, arg_lat_deg, semi_major_m, mean_motion), -theta0)
    velocity = (
        inertial[0] + OMEGA_SID_RAD_S * position[1],
        inertial[1] - OMEGA_SID_RAD_S * position[0],
        inertial[2],
    )
    return local_azimuth_deg(position, velocity)


def expected_launch_azimuth_deg(site_lat_deg: float) -> float:
    """Direct ascent azimuth of spec II.2 on the southbound branch.

    Spec II.2 states cos(i) = cos(phi_s) sin(beta). The two roots are beta and
    180 deg - beta; the southbound root, the one the corridor admits from Canso, is
    180 deg - degrees(arcsin(cos(i) / cos(phi_s))).
    """
    argument = math.cos(math.radians(TARGET_INCLINATION_DEG)) / math.cos(math.radians(site_lat_deg))
    return wrap_deg(180.0 - math.degrees(math.asin(argument)))


def build_ephemeris(first_liftoff: str, site_lat_deg: float, site_lon_deg: float) -> tuple[dict[str, Any], dict[str, Any]]:
    """The SSO ground track of the fixture, two orbits from the first liftoff at 60 s."""
    existing = read_json(FIXTURE_DIR / "ephemeris.json")
    epoch0 = epoch_ms(parse_instant(first_liftoff))
    semi_major_m = R_EARTH_M + TARGET_ALTITUDE_KM * 1000.0
    mean_motion = math.sqrt(GM_M3_S2 / semi_major_m ** 3)
    period_s = 2.0 * math.pi / mean_motion

    raan_deg = solve_raan_for_site(epoch0, site_lat_deg, site_lon_deg)
    theta0 = gmst_deg(epoch0)
    arg_lat_deg = argument_of_latitude_southbound(site_lat_deg)
    inertial_azimuth = inertial_launch_azimuth_deg(theta0, raan_deg, arg_lat_deg, semi_major_m, mean_motion)
    heading_deg = ground_track_heading_deg(theta0, raan_deg, arg_lat_deg, semi_major_m, mean_motion)

    last_sample_s = EPHEMERIS_STEP_S * int((EPHEMERIS_ORBITS * period_s) // EPHEMERIS_STEP_S)
    points = []
    for index in range(last_sample_s // EPHEMERIS_STEP_S + 1):
        offset_s = index * EPHEMERIS_STEP_S
        arg_lat = arg_lat_deg + math.degrees(mean_motion * offset_s)
        position = rotate_about_z(
            position_eci(raan_deg, arg_lat, semi_major_m),
            -(theta0 + OMEGA_SID_RAD_S * math.degrees(offset_s)),
        )
        latitude, longitude, radius = subpoint(position)
        points.append(
            {
                "t_utc": format_instant(parse_instant(first_liftoff) + dt.timedelta(seconds=offset_s)),
                "lat_deg": round(latitude, LAT_LON_DECIMALS),
                "lon_deg": round(longitude, LAT_LON_DECIMALS),
                "alt_km": round((radius - R_EARTH_M) / 1000.0, ALT_DECIMALS),
            }
        )

    ephemeris = {
        "orbit_id": ORBIT_ID,
        "frame": "ECEF",
        "points": points,
        "ground_track_valid": True,
        "constants_block": existing["constants_block"],
    }
    report = {
        "period_s": period_s,
        "semi_major_m": semi_major_m,
        "mean_motion_rad_s": mean_motion,
        "raan_deg": raan_deg,
        "arg_lat_deg": arg_lat_deg,
        "inertial_launch_azimuth_deg": inertial_azimuth,
        "ground_track_heading_deg": heading_deg,
        "expected_launch_azimuth_deg": expected_launch_azimuth_deg(site_lat_deg),
        "last_sample_s": last_sample_s,
        "samples": len(points),
        "first_point": points[0],
        "last_point": points[-1],
        "southernmost_lat_deg": min(point["lat_deg"] for point in points),
        "northernmost_lat_deg": max(point["lat_deg"] for point in points),
        "altitude_span_km": max(point["alt_km"] for point in points) - min(point["alt_km"] for point in points),
    }
    return ephemeris, report


# --------------------------------------------------------------------------------------
# windows rows
# --------------------------------------------------------------------------------------


def build_windows(existing: dict[str, Any]) -> dict[str, Any]:
    """The window rows with injection exactly INJECTION_OFFSET_S after liftoff.

    Every other field of the frozen fixture is carried over untouched, including the
    reachable verdict, the constants and provenance blocks, engine_version "stub" and
    computation_ms.
    """
    rows = existing.get("windows")
    if not isinstance(rows, list) or len(rows) != 3:
        raise ValueError("the frozen windows fixture must carry three rows to regenerate")
    liftoffs = [parse_instant(row["t_liftoff_utc"]) for row in rows]
    for earlier, later in zip(liftoffs, liftoffs[1:]):
        if later <= earlier:
            raise ValueError("the three liftoff instants must be strictly increasing")
    days = {(later - earlier).days for earlier, later in zip(liftoffs, liftoffs[1:])}
    if days != {1}:
        raise ValueError(f"the three liftoff instants must be on consecutive days, found {sorted(days)}")

    regenerated = json.loads(json.dumps(existing))
    for row, liftoff in zip(regenerated["windows"], liftoffs):
        row["t_liftoff_utc"] = format_instant(liftoff)
        row["t_injection_utc"] = format_instant(liftoff + dt.timedelta(seconds=INJECTION_OFFSET_S))
    regenerated["engine_version"] = "stub"
    return regenerated


# --------------------------------------------------------------------------------------
# a small JSON Schema check, stdlib only
# --------------------------------------------------------------------------------------


class SchemaError(Exception):
    pass


class SchemaSet:
    """The subset of JSON Schema 2020-12 that the frozen schemas use.

    Supported keywords: $ref to a sibling file or to a local $defs pointer, type,
    enum, required, properties, additionalProperties, items, minimum, maximum, const
    and the date and date-time formats. Any other keyword in a frozen schema is
    reported by check_keywords below rather than silently ignored, so the check cannot
    pass by not looking at a constraint.
    """

    SUPPORTED = {
        "$schema", "$id", "$defs", "$ref", "title", "description", "type", "enum",
        "required", "properties", "additionalProperties", "items", "minimum",
        "maximum", "format", "default", "const",
    }

    def __init__(self, directory: Path) -> None:
        self.documents = {path.name: json.loads(path.read_text(encoding="utf-8")) for path in sorted(directory.glob("*.json"))}
        self.origin = "?"

    def resolve(self, reference: str) -> tuple[dict[str, Any], str]:
        file_name, _, pointer = reference.partition("#")
        target = self.documents[file_name] if file_name else self.documents[self.origin]
        node: Any = target
        for token in [part for part in pointer.split("/") if part]:
            node = node[token.replace("~1", "/").replace("~0", "~")]
        return node, file_name if file_name else self.origin

    def check_keywords(self, node: dict[str, Any], where: str) -> list[str]:
        unknown: list[str] = []
        if not isinstance(node, dict):
            return unknown
        for keyword in node:
            if keyword not in self.SUPPORTED:
                unknown.append(f"{where}: unsupported keyword {keyword}")
        for name, child in (node.get("properties") or {}).items():
            unknown.extend(self.check_keywords(child, f"{where}.{name}"))
        if isinstance(node.get("items"), dict):
            unknown.extend(self.check_keywords(node["items"], f"{where}[]"))
        for name, child in (node.get("$defs") or {}).items():
            unknown.extend(self.check_keywords(child, f"{where}.$defs.{name}"))
        return unknown

    def validate(self, instance: Any, schema_name: str, where: str = "$") -> list[str]:
        errors: list[str] = []
        previous_origin, self.origin = self.origin, schema_name
        try:
            errors.extend(self._validate(instance, self.documents[schema_name], where))
        finally:
            self.origin = previous_origin
        return errors

    def _validate(self, instance: Any, schema: Any, where: str) -> list[str]:
        if isinstance(schema, dict) and "$ref" in schema:
            resolved, origin = self.resolve(schema["$ref"])
            previous_origin, self.origin = self.origin, origin
            try:
                return self._validate(instance, resolved, where)
            finally:
                self.origin = previous_origin
        if not isinstance(schema, dict):
            return []
        errors: list[str] = []

        expected = schema.get("type")
        if expected is not None:
            names = expected if isinstance(expected, list) else [expected]
            if not any(matches_type(instance, name) for name in names):
                return [f"{where}: expected type {expected}, found {type(instance).__name__}"]

        if "enum" in schema and instance not in schema["enum"]:
            errors.append(f"{where}: {instance!r} is not one of {schema['enum']}")
        if "const" in schema and instance != schema["const"]:
            errors.append(f"{where}: {instance!r} is not {schema['const']!r}")

        if isinstance(instance, bool):
            pass
        elif isinstance(instance, (int, float)):
            if "minimum" in schema and instance < schema["minimum"]:
                errors.append(f"{where}: {instance} is below the minimum {schema['minimum']}")
            if "maximum" in schema and instance > schema["maximum"]:
                errors.append(f"{where}: {instance} is above the maximum {schema['maximum']}")

        if isinstance(instance, str):
            fmt = schema.get("format")
            if fmt == "date" and not RFC3339_DATE.match(instance):
                errors.append(f"{where}: {instance!r} is not an ISO-8601 date")
            if fmt == "date-time" and not RFC3339_DATE_TIME.match(instance):
                errors.append(f"{where}: {instance!r} is not an ISO-8601 date-time with a Z or numeric offset")

        if isinstance(instance, dict):
            for name in schema.get("required", []):
                if name not in instance:
                    errors.append(f"{where}: required property {name} is missing")
            properties = schema.get("properties") or {}
            for name, value in instance.items():
                if name in properties:
                    errors.extend(self._validate(value, properties[name], f"{where}.{name}"))
                elif schema.get("additionalProperties") is False:
                    errors.append(f"{where}: property {name} is not allowed")

        if isinstance(instance, list) and isinstance(schema.get("items"), dict):
            for index, item in enumerate(instance):
                errors.extend(self._validate(item, schema["items"], f"{where}[{index}]"))
        return errors


def matches_type(instance: Any, name: str) -> bool:
    if name == "object":
        return isinstance(instance, dict)
    if name == "array":
        return isinstance(instance, list)
    if name == "string":
        return isinstance(instance, str)
    if name == "boolean":
        return isinstance(instance, bool)
    if name == "integer":
        return isinstance(instance, int) and not isinstance(instance, bool)
    if name == "number":
        return isinstance(instance, (int, float)) and not isinstance(instance, bool)
    if name == "null":
        return instance is None
    raise SchemaError(f"unknown type keyword value {name}")


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, document: dict[str, Any]) -> None:
    path.write_text(json.dumps(document, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")


# --------------------------------------------------------------------------------------
# entry point
# --------------------------------------------------------------------------------------


def validate_fixtures(schemas: SchemaSet, names: Iterable[str]) -> list[str]:
    failures: list[str] = []
    for name in names:
        schema_name = SCHEMA_FOR_FIXTURE[name]
        document = read_json(FIXTURE_DIR / name)
        errors = schemas.validate(document, schema_name)
        if errors:
            failures.extend(f"{name} against {schema_name}: {error}" for error in errors)
    return failures


def self_check(schemas: SchemaSet) -> tuple[list[str], int]:
    """Prove the subset validator is not vacuous against the frozen examples.

    Every good example of the five fixture schemas must pass and every bad example
    must be rejected. The contract tests run the same examples through jsonschema, so
    agreement here means this check sees the same constraints they do.
    """
    failures: list[str] = []
    checked = 0
    for schema_name in sorted(set(SCHEMA_FOR_FIXTURE.values())):
        stem = schema_name.removesuffix(".json")
        for path in sorted((REPO_ROOT / "tests" / "contract" / "examples" / "good").glob(f"{stem}_*.json")):
            checked += 1
            errors = schemas.validate(read_json(path), schema_name)
            if errors:
                failures.append(f"{path.name} must validate: {errors[0]}")
        for path in sorted((REPO_ROOT / "tests" / "contract" / "examples" / "bad").glob(f"{stem}_*.json")):
            checked += 1
            if not schemas.validate(read_json(path), schema_name):
                failures.append(f"{path.name} must be rejected by {schema_name}")
    return failures, checked


def main(argv: list[str]) -> int:
    check_only = "--check" in argv[1:]

    schemas = SchemaSet(SCHEMA_DIR)
    for schema_name in sorted(set(SCHEMA_FOR_FIXTURE.values())):
        for problem in schemas.check_keywords(schemas.documents[schema_name], schema_name):
            print(f"schema keyword warning: {problem}", file=sys.stderr)

    windows_existing = read_json(FIXTURE_DIR / "windows.json")
    site = read_json(FIXTURE_DIR / "site.json")
    site_lat, site_lon = float(site["phi_s_deg"]), float(site["lambda_s_deg"])
    first_liftoff = windows_existing["windows"][0]["t_liftoff_utc"]

    windows = build_windows(windows_existing)
    ephemeris, report = build_ephemeris(first_liftoff, site_lat, site_lon)

    print(f"site {site['name']} at {site_lat} N, {site_lon} W (site.json)")
    print(f"target {ORBIT_ID} inclination {TARGET_INCLINATION_DEG} deg, {TARGET_ALTITUDE_KM} km circular")
    print(f"semi-major axis {report['semi_major_m']:.1f} m, period {report['period_s']:.3f} s, "
          f"mean motion {report['mean_motion_rad_s']:.9f} rad/s")
    print(f"solved plane: RAAN {report['raan_deg']:.6f} deg, argument of latitude "
          f"{report['arg_lat_deg']:.6f} deg at the first liftoff {first_liftoff}")
    print(f"inertial launch azimuth {report['inertial_launch_azimuth_deg']:.4f} deg against the "
          f"direct ascent azimuth {report['expected_launch_azimuth_deg']:.4f} deg of spec II.2; "
          f"ground track heading in the rotating frame {report['ground_track_heading_deg']:.4f} deg, "
          f"the Earth rotation correction being {report['ground_track_heading_deg'] - report['inertial_launch_azimuth_deg']:.4f} deg")
    print(f"samples {report['samples']} over {report['last_sample_s']} s, step {EPHEMERIS_STEP_S} s, "
          f"{EPHEMERIS_ORBITS} orbits of {report['period_s']:.3f} s")
    print(f"first sample {report['first_point']}")
    print(f"last sample {report['last_point']}")
    print(f"latitude span {report['southernmost_lat_deg']:.5f} to {report['northernmost_lat_deg']:.5f} deg, "
          f"altitude span {report['altitude_span_km']:.6f} km")

    azimuth_gap = abs(
        wrap_signed_deg(report["inertial_launch_azimuth_deg"] - report["expected_launch_azimuth_deg"])
    )
    if azimuth_gap > 0.01:
        raise ValueError(f"the plane misses the direct ascent azimuth of spec II.2 by {azimuth_gap} deg")
    if not 150.0 <= report["ground_track_heading_deg"] <= 240.0:
        raise ValueError(
            f"the ground track heading {report['ground_track_heading_deg']} deg is not the "
            "southbound branch the corridor admits from Canso"
        )
    if report["altitude_span_km"] > 0.001:
        raise ValueError("a circular orbit must hold altitude")
    if report["first_point"]["lat_deg"] != report["first_point"]["lat_deg"]:
        raise ValueError("the first sample latitude is not a number")
    if abs(report["first_point"]["lat_deg"] - site_lat) > 10 ** -LAT_LON_DECIMALS:
        raise ValueError("the first sample must sit over the site latitude")
    if abs(report["first_point"]["lon_deg"] - site_lon) > 10 ** -LAT_LON_DECIMALS:
        raise ValueError("the first sample must sit over the site longitude")
    if report["first_point"]["t_utc"] != first_liftoff:
        raise ValueError("the ephemeris must start at the first liftoff instant")
    if report["southernmost_lat_deg"] >= report["northernmost_lat_deg"]:
        raise ValueError("the track must span both hemispheres")
    for row in windows["windows"]:
        offset = (parse_instant(row["t_injection_utc"]) - parse_instant(row["t_liftoff_utc"])).total_seconds()
        if offset != INJECTION_OFFSET_S:
            raise ValueError(f"injection offset {offset} s on row {row['t_liftoff_utc']}")

    if not check_only:
        write_json(FIXTURE_DIR / "windows.json", windows)
        write_json(FIXTURE_DIR / "ephemeris.json", ephemeris)
        print(f"wrote {FIXTURE_DIR / 'windows.json'} and {FIXTURE_DIR / 'ephemeris.json'}")

    failures = validate_fixtures(schemas, sorted(SCHEMA_FOR_FIXTURE))
    example_failures, examples_checked = self_check(schemas)
    failures.extend(example_failures)
    if failures:
        print("fixture schema check FAILED:", file=sys.stderr)
        for failure in failures:
            print(f"  {failure}", file=sys.stderr)
        return 1
    for name in sorted(SCHEMA_FOR_FIXTURE):
        print(f"{name} validates against {SCHEMA_FOR_FIXTURE[name]}")
    print(
        f"the schema subset check accepted every good example and rejected every bad example "
        f"of the five fixture schemas, {examples_checked} frozen examples"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))