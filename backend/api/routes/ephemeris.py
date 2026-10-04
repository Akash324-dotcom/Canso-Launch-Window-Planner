"""``GET /v1/orbits/{id}/ephemeris``, spec IV.2, task A5 of issue #4.

The route resolves the id, samples the track and stamps the constants block. It
delegates the geometry to ``backend.api.ephemeris``, which asks
``backend.engine.ephemeris`` for the ascent that lifts off at ``start`` and the orbit
after it, and serves a recorded offline segment where that seam is absent or refuses.

An id the service does not know is a 404, because it is a genuine resource miss
and spec IV.7 rule 2 reserves 404 for exactly that. A request the service cannot
interpret, a missing or unparseable instant, a non-positive step, an end before the
start or a grid above the configured ceiling, is a 422. Nothing here is a 500.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Query, Request

from backend.api import ephemeris
from backend.api.config import Settings, get_settings
from backend.api.limits import READ_BUCKET
from backend.api.middleware import cached_response, rate_limited
from backend.api.orbits import RegisteredOrbit, resolve_orbit
from backend.api.publish import frozen_responses, get_query_extra, query_parameter

router = APIRouter(tags=["orbits"])

EPHEMERIS_SCHEMA = "ephemeris_response"

DESCRIPTION = (
    "An ECEF ground track for one orbit id, spec IV.2. The track is the direct ascent "
    "from the site that lifts off at start, then the orbit: the first point is on the "
    "pad, and the point t_to_inj_s later is at orbit altitude, so the interval from "
    "t_liftoff_utc to t_injection_utc of a window row is the ascent of that row. The "
    "end instant is sampled even when step_s does not land on it. The path between "
    "liftoff and injection is kinematic and flagged ASSUMPTION, not an integrated "
    "trajectory. An orbit the site cannot reach by direct ascent, and any orbit when "
    "the engine layer is absent, is served from a recorded or closed-form orbit "
    "segment. ground_track_valid is false beyond the three-day propagation horizon."
)


@router.get(
    "/orbits/{orbit_id}/ephemeris",
    openapi_extra=get_query_extra(
        [
            query_parameter(
                "start",
                {"type": "string", "format": "date-time"},
                True,
                "First instant of the track, ISO-8601 UTC.",
            ),
            query_parameter(
                "end",
                {"type": "string", "format": "date-time"},
                True,
                "Last instant of the track, ISO-8601 UTC.",
            ),
            query_parameter(
                "step_s",
                {"type": "number", "exclusiveMinimum": 0, "default": 300},
                False,
                "Sampling interval in seconds. Defaults to the configured value.",
            ),
        ],
        DESCRIPTION,
    ),
    responses=frozen_responses(EPHEMERIS_SCHEMA, DESCRIPTION),
    dependencies=[Depends(rate_limited(READ_BUCKET))],
)
def get_ephemeris(
    orbit_id: str,
    request: Request,
    start: str = Query(..., description="First instant of the track."),
    end: str = Query(..., description="Last instant of the track."),
    step_s: float | None = Query(None),
    settings: Settings = Depends(get_settings),
) -> dict[str, Any]:
    """One orbit ground track, spec IV.2."""

    def build() -> dict[str, Any]:
        from backend.api.provenance import constants_block_for

        configuration = settings.ephemeris_config
        resolved_step = ephemeris.check_step(
            float(configuration["default_step_s"] if step_s is None else step_s)
        )
        first = ephemeris.parse_instant(start, "start")
        last = ephemeris.parse_instant(end, "end")
        count = ephemeris.point_count(first, last, resolved_step, int(configuration["max_points"]))
        ephemeris.check_point_ceiling(count, int(configuration["max_points"]), resolved_step)

        orbit = _resolve(settings, request, orbit_id)
        points, _ = ephemeris.points_for(settings, orbit, first, last, resolved_step)
        return {
            "orbit_id": orbit.orbit_id,
            "frame": ephemeris.FRAME,
            "points": points,
            "ground_track_valid": ephemeris.ground_track_valid(
                first, last, float(configuration["ground_track_horizon_days"])
            ),
            "constants_block": constants_block_for(
                settings,
                date_start=first.date().isoformat(),
                request_payload={
                    "endpoint": "orbits/ephemeris",
                    "orbit_id": orbit.orbit_id,
                    "start": start,
                    "end": end,
                    "step_s": resolved_step,
                },
            ),
        }

    return cached_response(request, build)


def _resolve(settings: Settings, request: Request, orbit_id: str) -> RegisteredOrbit:
    """The orbit an id names, from the presets, the registry or the stored records."""
    from backend.api.citation import stored_orbits

    registry = getattr(request.app.state, "orbits", None)
    if registry is None:
        from backend.api.orbits import OrbitRegistry

        registry = OrbitRegistry()
    return resolve_orbit(settings, registry, orbit_id, recorded=stored_orbits(settings))