"""The ascent of a window row and the orbit it is injected into. Spec IV.2.

``ephemeris`` answers the propagation seam of ``GET /v1/orbits/{id}/ephemeris``.
The track it returns is the direct ascent from the site that lifts off at ``start``:
on the pad at liftoff, at orbit altitude in the plane of (II.14) at injection, and on
the circular orbit in its drifting plane afterwards. For a window row, whose liftoff
instant is by construction the instant the target plane holds the site, that is the
ascent of the row.

WHAT IS STATED AND WHAT IS ASSUMED

The boundary values are statements the engine already makes, and none is chosen here:

    liftoff     the pad of the site file, at rest on the rotating Earth
                heading: the rotating-frame azimuth of spec II.6
                (``frames.launch_azimuth_compass``), the row's azimuth_compass_deg
    injection   t_to_inj_s of the vehicle profile after liftoff
                altitude h_t, climb rate zero, because the orbit is circular
                in the plane Omega_ach(t_l) of (II.14), fixed in inertial space
                in-plane rate n = sqrt(GM / (R_e + h_t)^3)

The path between them is NOT integrated. The vehicle guide publishes a timeline of
events and no trajectory, so there is no thrust, mass flow, guidance or gravity turn
here. Each coordinate is the polynomial of lowest order that meets its boundary
values:

    argument of latitude   u(t) = u_0 + n t^2 / (2 T)
                           at rest at liftoff, rate n at injection: three conditions,
                           a quadratic. The arc flown, n T / 2, follows from it.
    altitude               h(t) = h_0 + (h_t - h_0) (3 s^2 - 2 s^3),  s = t / T
                           level at both ends: four conditions, a cubic.
    node longitude         Lambda(t) = Lambda_0 - omega_sid f(t), in the Earth-fixed frame,
                           f(t) = T (a s^2 + b s^3 + c s^4)
                           f(0) = 0 and f'(0) = 0, the vehicle starts fixed to the Earth;
                           f''(0) = kappa / T, the heading of spec II.6;
                           f(T) = T, the plane of (II.14) is reached at injection;
                           f'(T) = 1, the plane is fixed in inertial space from there:
                           five conditions, a quartic, a = kappa / 2, b = 3 - 2a, c = a - 2,
                           kappa = (R_e / (R_e + h_t))^(3/2).

That polynomial form is an ASSUMPTION, the answer carries the flag, and
``t_to_inj_s`` is itself flagged ASSUMPTION in the vehicle profile. The track is a
picture of where the row goes that a map can draw and a viewer can read. It is not a
trajectory and it prices nothing.

The Earth is a sphere of radius R_e here, as in (II.9) and (II.10): the latitude of
the site file is used as the latitude on that sphere, which is what puts the first
sample on the pad exactly, and ``alt_km`` is height above the sphere.
"""

from __future__ import annotations

import datetime as dt
import math
from typing import Any, Mapping

from backend.engine import frames, injection, j2, provenance, reachability
from backend.engine import target as target_module

FRAME = "ECEF"
BRANCHES = ("descending", "ascending")
MODEL_FLAG = "ASSUMPTION"
MODEL_STATEMENT = (
    "Kinematic ascent, not integrated: no thrust, mass flow, guidance or gravity turn. "
    "Liftoff on the pad at rest on the rotating Earth, heading on the rotating-frame "
    "azimuth of spec II.6; injection t_to_inj_s later at orbit altitude, level, in the "
    "plane of (II.14) at the circular rate. Between them each coordinate is the "
    "polynomial of lowest order that meets those boundary values. After injection the "
    "circular orbit, its node drifting at the J2 rate of (II.7)."
)


def ephemeris(
    *,
    orbit_id: str,
    start: str,
    end: str,
    step_s: float,
    i_t_deg: float,
    h_t_km: float | None,
    site: str | None = None,
    vehicle_profile_id: str | None = None,
    branch: str | None = None,
) -> dict[str, Any]:
    """The ascent that lifts off from ``site`` at ``start``, then the orbit, to ``end``.

    Samples are taken every ``step_s`` from ``start``, and at ``end`` itself when the
    step does not land on it, so a track asked for up to the injection instant reaches
    the injection point. Raises ``ValueError`` for a target the site cannot reach, an
    unknown site or vehicle, an unreadable instant, or an empty grid.
    """
    if h_t_km is None:
        raise ValueError("h_t_km is required: an ascent needs the altitude it climbs to")
    if not step_s > 0.0:
        raise ValueError("step_s is a sampling interval in seconds and must be positive")
    first = _instant(start, "start")
    last = _instant(end, "end")
    if last < first:
        raise ValueError("end precedes start, so the requested track is empty")

    site_document = target_module.load_site(site or target_module.DEFAULT_SITE)
    latitude = float(site_document["latitude_deg"])
    if not reachability.reachable(float(i_t_deg), latitude):
        raise ValueError(
            f"a direct ascent from {site_document['name']} at {latitude:g} deg cannot reach "
            f"an inclination of {float(i_t_deg):g} deg, so the target has no ascent"
        )
    profile_id = vehicle_profile_id or site_document.get("vehicle_profile_id")
    if not profile_id:
        raise ValueError(
            f"vehicle_profile_id is required: the site file of {site_document['name']} names no vehicle"
        )
    profile = injection.load_vehicle(profile_id)
    crossing = _branch(branch, float(i_t_deg), site_document)
    path = _Path(site_document, float(i_t_deg), float(h_t_km), float(profile["t_to_inj_s"]), crossing)

    span = (last - first).total_seconds()
    offsets = [index * float(step_s) for index in range(int(math.floor(span / float(step_s))) + 1)]
    if span - offsets[-1] > 1.0e-9:
        offsets.append(span)

    points = []
    for offset in offsets:
        lat_deg, lon_deg, alt_km = path.at(offset)
        points.append(
            {
                "t_utc": _iso(first + dt.timedelta(seconds=offset)),
                "lat_deg": round(lat_deg, 6),
                "lon_deg": round(lon_deg, 6),
                "alt_km": round(alt_km, 6),
            }
        )

    injection_lat, injection_lon, _ = path.at(path.t_to_inj_s)
    return {
        "orbit_id": orbit_id,
        "frame": FRAME,
        "points": points,
        "model": {
            "flag": MODEL_FLAG,
            "statement": MODEL_STATEMENT,
            "site": site_document["name"],
            "vehicle_profile_id": profile_id,
            "branch": crossing,
            "t_to_inj_s": path.t_to_inj_s,
            "t_to_inj_flag": _t_to_inj_flag(profile),
            "launch_azimuth_compass_deg": path.compass_azimuth_deg,
            "downrange_at_injection_km": _great_circle_km(
                latitude, float(site_document["longitude_deg"]), injection_lat, injection_lon
            ),
            "sources": {
                "pad": "site file, latitude_deg, longitude_deg and altitude_m",
                "t_to_inj_s": f"vehicle profile {profile_id}, t_to_inj_s",
                "plane": "(II.14), Omega_ach(t_l) = GMST(t_l) + lambda_s - delta",
                "heading": "spec II.6 eq. A2, frames.launch_azimuth_compass",
                "nodal_rate": "(II.7), j2.nodal_rate_rad_s",
            },
        },
    }


class _Path:
    """Latitude, longitude and altitude as functions of the seconds since liftoff."""

    def __init__(
        self,
        site: Mapping[str, Any],
        i_t_deg: float,
        h_t_km: float,
        t_to_inj_s: float,
        branch: str,
    ) -> None:
        if not t_to_inj_s > 0.0:
            raise ValueError("t_to_inj_s of the vehicle profile must be positive")
        latitude = math.radians(float(site["latitude_deg"]))
        self.inclination = math.radians(i_t_deg)
        self.h_t_km = h_t_km
        self.h_0_km = float(site.get("altitude_m", 0.0)) / 1000.0
        self.t_to_inj_s = t_to_inj_s

        ratio = max(-1.0, min(1.0, math.sin(latitude) / math.sin(self.inclination)))
        ascending = math.asin(ratio)
        self.u_0 = ascending if branch == "ascending" else math.pi - ascending
        self.node_0 = math.radians(float(site["longitude_deg"])) - self._right_ascension_from_node(self.u_0)

        radius_m = provenance.R_E + h_t_km * 1000.0
        self.mean_motion = math.sqrt(provenance.GM / radius_m**3)
        self.nodal_rate = j2.nodal_rate_rad_s(h_t_km, i_t_deg)
        kappa = (provenance.R_E / radius_m) ** 1.5
        self.a = kappa / 2.0
        self.b = 3.0 - 2.0 * self.a
        self.c = self.a - 2.0

        beta = reachability.launch_azimuth_deg(i_t_deg, float(site["latitude_deg"]))
        if branch == "ascending":
            beta = reachability.northbound_partner_deg(beta)
        self.compass_azimuth_deg = frames.launch_azimuth_compass(beta, float(site["latitude_deg"]))

    def _right_ascension_from_node(self, argument: float) -> float:
        return math.atan2(math.cos(self.inclination) * math.sin(argument), math.cos(argument))

    def at(self, offset_s: float) -> tuple[float, float, float]:
        """Geocentric latitude and longitude in degrees and altitude in km."""
        duration = self.t_to_inj_s
        if offset_s <= duration:
            s = offset_s / duration
            argument = self.u_0 + self.mean_motion * offset_s**2 / (2.0 * duration)
            slip = duration * (self.a * s**2 + self.b * s**3 + self.c * s**4)
            altitude = self.h_0_km + (self.h_t_km - self.h_0_km) * (3.0 * s**2 - 2.0 * s**3)
            node = self.node_0 - provenance.OMEGA_SID_RAD_S * slip
        else:
            coast = offset_s - duration
            argument = self.u_0 + self.mean_motion * (duration / 2.0 + coast)
            altitude = self.h_t_km
            node = (
                self.node_0
                - provenance.OMEGA_SID_RAD_S * duration
                - (provenance.OMEGA_SID_RAD_S - self.nodal_rate) * coast
            )
        latitude = math.asin(max(-1.0, min(1.0, math.sin(self.inclination) * math.sin(argument))))
        longitude = node + self._right_ascension_from_node(argument)
        return (
            math.degrees(latitude),
            (math.degrees(longitude) + 180.0) % 360.0 - 180.0,
            altitude,
        )


def _branch(requested: str | None, i_t_deg: float, site: Mapping[str, Any]) -> str:
    """The crossing to draw: the one named, else the one the site admits.

    The seam is given an instant and an orbit, not a row, so it cannot tell which of
    the two crossings of the plane a caller means. It draws the crossing the site
    admits by its direction policy and its corridor, the test the hazard screen
    applies. Where the site admits neither, the stated direction policy decides, and
    with no policy the southbound azimuth of (II.2), which is the reference azimuth
    of the engine.
    """
    if requested is not None:
        if requested not in BRANCHES:
            raise ValueError(f"branch must be one of {', '.join(BRANCHES)}, not {requested!r}")
        return requested
    corridor = site["corridor"]
    southbound = reachability.launch_azimuth_deg(i_t_deg, float(site["latitude_deg"]))
    azimuths = {
        "descending": southbound,
        "ascending": reachability.northbound_partner_deg(southbound),
    }
    for name in BRANCHES:
        if reachability.direction_admitted(azimuths[name], corridor) and reachability.azimuth_in_corridor(
            azimuths[name], corridor
        ):
            return name
    policy = reachability.direction_policy(corridor)
    if policy is not None and policy["admitted_branch"] == "northbound":
        return "ascending"
    return "descending"


def _t_to_inj_flag(profile: Mapping[str, Any]) -> str:
    for row in profile.get("rows", []):
        if row.get("key") == "t_to_inj_s":
            return str(row["flag"])
    return "ASSUMPTION"


def _instant(value: str, field: str) -> dt.datetime:
    try:
        parsed = dt.datetime.fromisoformat(str(value).strip().replace("Z", "+00:00").replace("z", "+00:00"))
    except ValueError:
        raise ValueError(f"{field} must be an ISO-8601 instant such as 2026-10-05T13:40:00Z") from None
    if parsed.tzinfo is None:
        raise ValueError(f"{field} must carry a UTC offset or a Z suffix")
    return parsed.astimezone(dt.timezone.utc)


def _iso(moment: dt.datetime) -> str:
    text = moment.strftime("%Y-%m-%dT%H:%M:%S")
    if moment.microsecond:
        text += f".{moment.microsecond:06d}".rstrip("0")
    return text + "Z"


def _great_circle_km(lat1_deg: float, lon1_deg: float, lat2_deg: float, lon2_deg: float) -> float:
    p1, p2 = math.radians(lat1_deg), math.radians(lat2_deg)
    cosine = math.sin(p1) * math.sin(p2) + math.cos(p1) * math.cos(p2) * math.cos(
        math.radians(lon2_deg - lon1_deg)
    )
    return provenance.R_E / 1000.0 * math.acos(max(-1.0, min(1.0, cosine)))
