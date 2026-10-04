"""Ground tracks for ``GET /v1/orbits/{id}/ephemeris``, spec IV.2, task A5.

The endpoint answers from ``backend.engine.ephemeris`` the moment that function
exists, and from an offline record until then. Two offline records exist, and the
difference between them is stated here rather than left to be discovered:

* the three named classes of spec IV.2 are served from **recorded segments**, one per
  class, listed in ``service.json`` under ``ephemeris.base_tracks``. Each lives under
  ``backend/api/data/ephemeris`` because a record this workflow resamples and repeats
  is its own configuration; ``backend/fixtures`` is FRONTEND content under contract
  section 0 and Seam 3, and its document is read as the demo floor of spec V.5 rather
  than as a base track. A recorded segment for one class cannot describe another, so
  each class has a segment of its own rather than one class's track being relabelled.
* a custom id created by ``POST /v1/windows`` has no recorded segment, so the same
  documented closed form that produced the records produces one at request time
  from the target the POST recorded.

The closed form is the ground track of a circular orbit, and nothing more:

    latitude  = asin(sin(i) sin(u))          over the argument of latitude u
    longitude advances at (n - omega_sid)     n = sqrt(GM / (R_e + h)^3)
    altitude  = h, constant, because the orbit is circular

Every quantity in it comes from ``backend/api/data/constants.json`` and from the
target the request supplied. There is no J2 precession and no perturbation: those
are ENGINE's terms, they arrive with ``backend.engine.ephemeris`` at gate G1, and
the closed form is a documented stand-in rather than a claim. Spec IV.2 is explicit
that full force models are not offered.

A recorded segment is resampled onto the requested grid by linear interpolation in
latitude and in unwrapped longitude, and is repeated beyond its recorded span,
because a ground track repeats. The repeat is a property of the offline floor;
``ground_track_valid`` is the flag that tells a client how far to trust the track,
and spec IV.2 sets it false beyond the three-day horizon.
"""

from __future__ import annotations

import importlib
import datetime as dt
import json
import math
from typing import Any, Sequence

from backend.api.config import Settings
from backend.api.errors import ContractViolation, UpstreamUnavailable
from backend.api.orbits import RegisteredOrbit, resolve_orbit
from backend.api.provenance import constants_block_for

FRAME = "ECEF"
EPHEMERIS_SCHEMA = "ephemeris_response"
RECORDED_POINTS_PER_REVOLUTION = 20


def parse_instant(value: str, field: str) -> dt.datetime:
    """Parse an ISO-8601 instant, reporting a bad one as a 422 rather than a 500."""
    text = value.strip()
    try:
        parsed = dt.datetime.fromisoformat(text.replace("Z", "+00:00").replace("z", "+00:00"))
    except (AttributeError, ValueError):
        raise ContractViolation(
            f"{field} must be an ISO-8601 instant such as 2026-10-05T13:40:00Z",
            schema_name="ephemeris_response",
            violations=[f"/{field}: {value!r} is not an ISO-8601 instant"],
        ) from None
    if parsed.tzinfo is None:
        raise ContractViolation(
            f"{field} must carry a UTC offset or a Z suffix",
            schema_name="ephemeris_response",
            violations=[f"/{field}: {value!r} has no offset"],
        )
    return parsed.astimezone(dt.timezone.utc)


def iso(moment: dt.datetime) -> str:
    return moment.astimezone(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def ground_track_valid(start: dt.datetime, end: dt.datetime, horizon_days: float) -> bool:
    """Spec IV.2: false beyond the three-day horizon for conjunction-derived tracks."""
    return (end - start).total_seconds() <= horizon_days * 86400.0


def point_count(start: dt.datetime, end: dt.datetime, step_s: float, ceiling: int) -> int:
    """How many samples the requested grid holds, inclusive of both ends."""
    span = (end - start).total_seconds()
    if span < 0:
        raise ContractViolation(
            "end precedes start, so the requested ground track is empty",
            schema_name="ephemeris_response",
            violations=[f"/end: {iso(end)} is earlier than {iso(start)}"],
        )
    return int(math.floor(span / step_s)) + 1


def check_point_ceiling(count: int, ceiling: int, step_s: float) -> None:
    if count > ceiling:
        raise ContractViolation(
            f"the requested grid holds {count} points at a step of {step_s:g} s, above the "
            f"configured ceiling of {ceiling}. Raise step_s or shorten the interval.",
            schema_name="ephemeris_response",
            violations=[f"/points: {count} exceeds the ceiling of {ceiling}"],
        )


def check_step(step_s: float) -> float:
    if step_s <= 0:
        raise ContractViolation(
            "step_s is a sampling interval in seconds and cannot be zero or negative",
            schema_name="ephemeris_response",
            violations=[f"/step_s: {step_s:g} is not positive"],
        )
    return step_s


# ------------------------------------------------------------------ resampling


def resample(
    points: Sequence[dict[str, Any]],
    start: dt.datetime,
    end: dt.datetime,
    step_s: float,
) -> list[dict[str, Any]]:
    """Place a recorded segment on the requested grid.

    Interpolation is linear in latitude and in unwrapped longitude, so the 180 deg
    seam does not produce a spike. Beyond the recorded span the segment repeats,
    which is what a ground track does and what the offline record can express.
    """
    first = parse_instant(points[0]["t_utc"], "points/0/t_utc")
    last = parse_instant(points[-1]["t_utc"], "points/-1/t_utc")
    span = (last - first).total_seconds()
    if span <= 0:
        raise ValueError("a recorded ground-track segment must span a positive interval")

    unwrapped = _unwrapped(points, first)
    samples: list[dict[str, Any]] = []
    index = 0
    while True:
        moment = start + dt.timedelta(seconds=index * step_s)
        if moment > end:
            break
        offset = _segment_offset(moment, first, span)
        latitude, longitude, altitude = _interpolate(points, unwrapped, offset)
        samples.append(
            {
                "t_utc": iso(moment),
                "lat_deg": round(latitude, 6),
                "lon_deg": wrap_longitude(longitude),
                "alt_km": round(altitude, 6),
            }
        )
        index += 1
    return samples


def _segment_offset(moment: dt.datetime, first: dt.datetime, span: float) -> float:
    """Seconds into the segment, wrapping once the recorded span is exceeded.

    The instant one span after the start is the last recorded sample, not the first
    one, so the record is reproduced exactly at its own resolution; only samples
    strictly beyond it repeat.
    """
    elapsed = (moment - first).total_seconds()
    offset = elapsed % span
    if offset == 0.0 and elapsed >= span:
        return span
    return offset


def _unwrapped(points: Sequence[dict[str, Any]], first: dt.datetime) -> list[float]:
    """Longitudes made continuous, so interpolation crosses 180 deg smoothly."""
    running: list[float] = []
    previous: float | None = None
    for point in points:
        longitude = float(point["lon_deg"])
        if previous is not None:
            while longitude - previous > 180.0:
                longitude -= 360.0
            while longitude - previous < -180.0:
                longitude += 360.0
        running.append(longitude)
        previous = longitude
    return running


def _interpolate(
    points: Sequence[dict[str, Any]], unwrapped: Sequence[float], offset: float
) -> tuple[float, float, float]:
    """Latitude, longitude and altitude at ``offset`` seconds into the segment."""
    if offset <= 0.0:
        return float(points[0]["lat_deg"]), unwrapped[0], float(points[0]["alt_km"])
    for index in range(1, len(points)):
        upper = parse_instant(points[index]["t_utc"], "t_utc")
        lower = parse_instant(points[index - 1]["t_utc"], "t_utc")
        upper_offset = (upper - parse_instant(points[0]["t_utc"], "t_utc")).total_seconds()
        lower_offset = (lower - parse_instant(points[0]["t_utc"], "t_utc")).total_seconds()
        if offset <= upper_offset:
            fraction = (offset - lower_offset) / (upper_offset - lower_offset)
            latitude = float(points[index - 1]["lat_deg"]) + fraction * (
                float(points[index]["lat_deg"]) - float(points[index - 1]["lat_deg"])
            )
            longitude = unwrapped[index - 1] + fraction * (unwrapped[index] - unwrapped[index - 1])
            altitude = float(points[index - 1]["alt_km"]) + fraction * (
                float(points[index]["alt_km"]) - float(points[index - 1]["alt_km"])
            )
            return latitude, longitude, altitude
    return float(points[-1]["lat_deg"]), unwrapped[-1], float(points[-1]["alt_km"])


def wrap_longitude(longitude: float) -> float:
    return round((longitude + 180.0) % 360.0 - 180.0, 6)


# ------------------------------------------------------- the closed-form record


def mean_motion_rad_s(settings: Settings, altitude_km: float) -> float:
    """Two-body mean motion from the spec II.10 constants, never from a literal."""
    from backend.api.provenance import load_constants

    constants = load_constants(settings).values
    radius_m = float(constants["R_e"]) + float(altitude_km) * 1000.0
    return math.sqrt(float(constants["GM"]) / radius_m**3)


def orbital_period_s(settings: Settings, altitude_km: float) -> float:
    return 2.0 * math.pi / mean_motion_rad_s(settings, altitude_km)


def ground_track_rate_deg_per_s(settings: Settings, altitude_km: float) -> float:
    """How fast the track moves in longitude: the orbital rate less the Earth's."""
    from backend.api.provenance import load_constants

    constants = load_constants(settings).values
    return math.degrees(mean_motion_rad_s(settings, altitude_km) - float(constants["omega_sid_rad_s"]))


def closed_form_segment(
    settings: Settings,
    orbit: RegisteredOrbit,
    first_epoch: str,
    site_latitude_deg: float | None = None,
    site_longitude_deg: float | None = None,
) -> list[dict[str, Any]]:
    """A circular ground-track segment for one target, anchored at the site.

    The segment starts at ``first_epoch`` on the ascending equator crossing and is
    laid out so that the southbound pass crosses the site longitude at the site
    latitude, which is the geometry spec II.9 describes. It contains
    ``RECORDED_POINTS_PER_REVOLUTION`` intervals of whole seconds, so the record
    spans one revolution to within the rounding of the interval and a repeat begins
    where the previous one ended. Whole seconds matter: the recorded instants are
    written at second resolution, so an interval with a fractional part would make the
    resampler unable to land on a recorded sample.

    A site further from the equator than the orbit can reach has no crossing to
    anchor on. That is reachability, spec II.4, and it is why the flagship low-Earth class
    the specification advertises is the unreachable one; the segment then starts on
    the equator crossing at the site longitude.
    """
    if orbit.h_t_km is None:
        raise ValueError(
            f"orbit {orbit.orbit_id} has no recorded altitude, so no circular track can be laid out"
        )
    site = (site_latitude_deg, site_longitude_deg)
    inclination = math.radians(orbit.i_t_deg)
    phase_argument, phase_longitude = _site_phase(settings, inclination, site)
    mean_motion = mean_motion_rad_s(settings, orbit.h_t_km)
    rate = ground_track_rate_deg_per_s(settings, orbit.h_t_km)
    period = 2.0 * math.pi / mean_motion
    step = float(round(period / RECORDED_POINTS_PER_REVOLUTION))
    node_longitude = phase_longitude - rate * (phase_argument / mean_motion)

    epoch = parse_instant(first_epoch, "first_epoch")
    segment: list[dict[str, Any]] = []
    for index in range(RECORDED_POINTS_PER_REVOLUTION + 1):
        seconds = index * step
        argument = mean_motion * seconds
        segment.append(
            {
                "t_utc": iso(epoch + dt.timedelta(seconds=seconds)),
                "lat_deg": round(math.degrees(math.asin(math.sin(inclination) * math.sin(argument))), 6),
                "lon_deg": wrap_longitude(node_longitude + rate * seconds),
                "alt_km": round(float(orbit.h_t_km), 6),
            }
        )
    return segment


def _site_phase(
    settings: Settings, inclination_rad: float, site: tuple[float | None, float | None]
) -> tuple[float, float]:
    """Argument of latitude and node longitude that put the southbound pass at the site.

    The descending crossing of the site latitude follows from spec II.9,
    ``delta(i, phi_s) = asin(tan(phi_s)/tan(i))``: it is at
    ``pi - asin(sin(phi_s)/sin(i))``. The argument of latitude advances at the mean
    motion, so the node longitude follows by dividing by it, which is what makes the
    two quantities commensurable.
    """
    site_latitude, site_longitude = site
    if site_latitude is None or site_longitude is None:
        return 0.0, 0.0
    ratio = math.sin(math.radians(site_latitude)) / math.sin(inclination_rad)
    if abs(ratio) > 1.0:
        return 0.0, site_longitude
    return math.pi - math.asin(ratio), site_longitude


# --------------------------------------------------------------- the route body


def recorded_segment(settings: Settings, orbit: RegisteredOrbit) -> list[dict[str, Any]]:
    """The recorded points for an orbit id, or a 503 when no record is readable."""
    if orbit.preset is None:
        return []
    path = settings.base_track_path(orbit.orbit_id)
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as failure:
        raise UpstreamUnavailable(
            f"the propagation seam is unavailable and the recorded ground track at "
            f"{settings.relative(path)} could not be read: {failure}",
            retry_after_s=settings.retry_after_s["upstream_unavailable"],
            fixture_path=settings.relative(path),
            layer="engine",
        ) from failure
    return list(document["points"])


def preset_orbit(settings: Settings, orbit_id: str) -> RegisteredOrbit:
    """The orbit record of one of the three named classes of spec IV.2."""
    return resolve_orbit(settings, _empty_registry(), orbit_id)


def _empty_registry() -> Any:
    from backend.api.orbits import OrbitRegistry

    return OrbitRegistry()


def live_ephemeris() -> Any | None:
    """``backend.engine.ephemeris`` once ENGINE lands it, else None."""
    try:
        engine = importlib.import_module("backend.engine")
    except ImportError:
        return None
    return getattr(engine, "ephemeris", None)


def points_for(
    settings: Settings,
    orbit: RegisteredOrbit,
    start: dt.datetime,
    end: dt.datetime,
    step_s: float,
) -> tuple[list[dict[str, Any]], str]:
    """The samples to serve, and which source produced them.

    The propagation seam is asked first, and its answer is validated against the frozen
    schema before it is served: a live layer that returns something the contract does
    not describe is a worse outcome than the offline floor, so a malformed answer falls
    through to the record rather than reaching a client.
    """
    seam = live_ephemeris()
    if seam is not None:
        document = _from_seam(seam, settings, orbit, start, end, step_s)
        if document is not None:
            return document, f"backend.engine.ephemeris for {orbit.orbit_id}"

    segment = recorded_segment(settings, orbit)
    if segment:
        return (
            resample(segment, start, end, step_s),
            settings.relative(settings.base_track_path(orbit.orbit_id)),
        )

    site = settings.site_document(settings.default_site)
    generated = closed_form_segment(
        settings,
        orbit,
        first_epoch=iso(start),
        site_latitude_deg=float(site["phi_s_deg"]),
        site_longitude_deg=float(site["lambda_s_deg"]),
    )
    return resample(generated, start, end, step_s), CLOSED_FORM_SOURCE


CLOSED_FORM_SOURCE = "closed_form_circular_track"


def _from_seam(
    seam: Any,
    settings: Settings,
    orbit: RegisteredOrbit,
    start: dt.datetime,
    end: dt.datetime,
    step_s: float,
) -> list[dict[str, Any]] | None:
    """Ask the propagation seam, and accept its answer only if it holds the contract."""
    from backend.api.schemas import errors_for

    try:
        answer = seam(
            orbit_id=orbit.orbit_id,
            start=iso(start),
            end=iso(end),
            step_s=step_s,
            i_t_deg=orbit.i_t_deg,
            h_t_km=orbit.h_t_km,
        )
    except Exception:
        return None
    points = answer.get("points") if isinstance(answer, dict) else None
    if not isinstance(points, list) or not points:
        return None

    probe = {
        "orbit_id": orbit.orbit_id,
        "frame": FRAME,
        "points": points,
        "ground_track_valid": True,
        "constants_block": constants_block_for(settings, kind=f"seam:{orbit.orbit_id}"),
    }
    point_errors = [
        error
        for error in errors_for(EPHEMERIS_SCHEMA, probe)
        if list(error.absolute_path)[:1] == ["points"]
    ]
    if point_errors:
        return None
    return [dict(point) for point in points]