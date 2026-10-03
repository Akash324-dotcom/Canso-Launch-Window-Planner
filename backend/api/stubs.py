"""Offline stub layer, task A3 of issue #4.

Spec IV.7 rule 1 and the seam 1 signature in ``docs/00_INTEGRATION_CONTRACT.md``
say the same thing twice: the service answers from ``backend.engine.compute_windows``
the moment that function exists, and until then from a precomputed document under
``backend/fixtures``. This module is the second of those two paths. Every response
it produces carries ``engine_version: "stub"`` so that nobody can mistake it for
engine output.

Two pieces of arithmetic live here, both taken verbatim from the specification and
both labelled by claim status as ``docs/00_INTEGRATION_CONTRACT.md`` section 5 requires:

* Reachability, spec II.4 and spec II.9, marked PROVED in the contract because it is
  algebraic. Direct ascent from site latitude ``phi_s`` reaches inclination ``i`` iff
  ``i`` lies in the image of the corridor under ``i(beta) = arccos(cos(phi_s) sin(beta))``
  on the southbound branch.
* The plane-change penalty of spec II.5, ``2 v_c sin(Delta_i / 2)`` with
  ``v_c = sqrt(GM / (R_e + h_t))``. It is computed from the constants block, never from a
  literal. The value is the engine's to own once ENGINE lands; the stub computes it so
  that the flagship honesty case of spec III.5 returns a real number rather than a null.

Nothing here fetches anything. The service must answer with the network unplugged.
"""

from __future__ import annotations

import json
import math
import time
from pathlib import Path
from typing import Any

from backend.api.config import Settings
from backend.api.errors import UpstreamUnavailable
from backend.api.provenance import load_constants

STUB_ENGINE_VERSION = "stub"

API_OWNED_WINDOW_FIELDS = (
    "p_success",
    "horizon_label",
    "forecast_issue_time",
)
API_OWNED_COMPONENT_FIELDS = ("weather",)

TARGET_CLASSES = ("LEO", "POLAR", "SSO", "CUSTOM")


# --------------------------------------------------------------------- fixtures


def load_document(path: Path, layer: str, settings: Settings) -> dict[str, Any]:
    """Read one offline fixture document, or report the outage as spec V.5 requires.

    A missing or unreadable precomputed document means there is no answer at all,
    live or precomputed. That is a genuine 503 with the fixture path named, never a
    silent empty result.
    """
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as failure:
        raise UpstreamUnavailable(
            f"the {layer} layer is unreachable and the offline fixture at "
            f"{settings.relative(path)} could not be read: {failure}",
            retry_after_s=settings.retry_after_s["upstream_unavailable"],
            fixture_path=settings.relative(path),
            layer=layer,
        ) from failure


def load_windows_document(settings: Settings) -> dict[str, Any]:
    """The frozen window rows served while ENGINE has not landed."""
    return load_document(settings.fixture_path("windows"), "engine", settings)


def load_weather_document(settings: Settings) -> dict[str, Any]:
    """The frozen weather snapshot served while WEATHER has not landed.

    Spec IV.3 already reserves the source value ``snapshot_cache`` for exactly this
    case: a recorded forecast that is echoed rather than refetched.
    """
    return load_document(settings.fixture_path("weather"), "weather", settings)


def fixture_sources(
    settings: Settings, effective_request: dict[str, Any], engine_is_live: bool
) -> list[str]:
    """The offline documents this request will read, for the provenance block.

    The provenance block reports the files that were actually read, so the route asks
    the stub layer which files that will be rather than guessing them.
    """
    if engine_is_live:
        return []
    sources = [settings.relative(settings.fixture_path("windows"))]
    if bool(effective_request.get("include_weather", True)):
        sources.append(settings.relative(settings.fixture_path("weather")))
    return sources


# ---------------------------------------------------------------------- targets


def resolve_target(settings: Settings, target: dict[str, Any]) -> dict[str, Any]:
    """Resolve a request target to the inclination and altitude the stub reasons about.

    Spec IV.1 type mapping: LEO, POLAR and SSO resolve to their configured class and
    CUSTOM takes its two numbers from the request. The class values come from
    ``backend/api/data/service.json``, never from a literal in this module.
    """
    target_type = str(target["type"])
    if target_type == "CUSTOM":
        return {
            "type": target_type,
            "i_t_deg": float(target["i_t_deg"]),
            "h_t_km": float(target["h_t_km"]),
            "source": "request body, spec II.10 target orbit row",
        }
    if target_type not in TARGET_CLASSES:
        raise ValueError(f"target type {target_type!r} is not in the spec IV.1 enumeration")

    defaults = settings.target_classes[target_type]
    altitude = target.get("h_t_km")
    inclination = target.get("i_t_deg")
    source = str(defaults["source"])
    if altitude is None:
        altitude = defaults["h_t_km"]
    if inclination is None and target_type == "SSO" and altitude is not None:
        inclination = sso_inclination_for_altitude(settings, float(altitude))
        source = f"{source}; inclination read from the {settings.sso['inclination_table_source']}"
    if inclination is None:
        inclination = defaults["i_t_deg"]
    return {
        "type": target_type,
        "i_t_deg": float(inclination),
        "h_t_km": None if altitude is None else float(altitude),
        "source": source,
    }


def sso_inclination_for_altitude(settings: Settings, altitude_km: float) -> float | None:
    """Inclination of the spec II.6 table at or below ``altitude_km``.

    The table is transcribed from the specification into configuration. Between two
    tabulated rows the nearest lower row is used, so the value is a documented table
    read rather than an interpolation the API invented.
    """
    table = {
        float(key): float(value) for key, value in settings.sso["inclination_by_altitude_km"].items()
    }
    at_or_below = [altitude for altitude in table if altitude <= altitude_km]
    if not at_or_below:
        return None
    return table[max(at_or_below)]


def sso_consistency_warning(
    settings: Settings, target: dict[str, Any], resolved: dict[str, Any]
) -> dict[str, Any] | None:
    """Spec II.6 (a): an inclination that the requested altitude cannot sustain.

    The warning is an object in the 200 body. It is never an HTTP error, because it is
    an answer about the target rather than a fault in the request.
    """
    if resolved["type"] != "SSO" or target.get("i_t_deg") is None:
        return None
    required = sso_inclination_for_altitude(settings, resolved["h_t_km"])
    if required is None:
        return None
    gap = abs(float(target["i_t_deg"]) - required)
    tolerance = float(settings.sso["consistency_tolerance_deg"])
    if gap <= tolerance:
        return None
    return {
        "reason": "sso_inclination_inconsistent_with_altitude",
        "requested_i_t_deg": float(target["i_t_deg"]),
        "required_i_t_deg": required,
        "h_t_km": resolved["h_t_km"],
        "detail": (
            "spec II.6: the inclination is altitude specific, so this node would precess "
            f"at {settings.sso['required_nodal_rate_deg_per_day']} deg/day only at about "
            f"{required} deg at {resolved['h_t_km']} km. The gap accumulates as LTAN drift."
        ),
        "tolerance_deg": tolerance,
        "source": settings.sso["inclination_table_source"],
    }


# ----------------------------------------------------------------- reachability


def inclination_at_azimuth(phi_s_deg: float, azimuth_deg: float) -> float:
    """Spec II.2 read backwards: ``i(beta) = arccos(cos(phi_s) sin(beta))``."""
    cos_inclination = math.cos(math.radians(phi_s_deg)) * math.sin(math.radians(azimuth_deg))
    return math.degrees(math.acos(max(-1.0, min(1.0, cos_inclination))))


def reachability(
    phi_s_deg: float, inclination_deg: float, corridor: dict[str, Any]
) -> tuple[bool, float, float]:
    """Spec II.4 on the southbound branch: the reachable inclination band.

    The map ``i(beta) = arccos(cos(phi_s) sin(beta))`` is monotone over the configured
    corridor, so the reachable set is the closed interval between the inclinations the
    two corridor bounds produce. Spec II.4 writes that interval as
    ``[i(A_max), i(A_min)]``; with the shipped corridor of 90 to 200 deg the mapping is
    ascending rather than descending, so the two endpoints are ordered by value here and
    the set is identical either way. The upper end reproduces the specification's own
    statement that a bound of 200 deg caps the reachable inclination at about 104 deg.

    Returns the verdict and the band, so a caller can report the band it used rather
    than only the verdict.
    """
    at_min = inclination_at_azimuth(phi_s_deg, float(corridor["A_min_deg"]))
    at_max = inclination_at_azimuth(phi_s_deg, float(corridor["A_max_deg"]))
    lower, upper = min(at_min, at_max), max(at_min, at_max)
    return lower <= inclination_deg <= upper, lower, upper


def plane_change_penalty(
    settings: Settings, phi_s_deg: float, inclination_deg: float, altitude_km: float | None
) -> float | None:
    """Spec II.5: the cheapest two-impulse plane change that reaches the target.

    Returns None when the insertion altitude is unknown, because spec IV.1 makes the
    penalty nullable exactly for an unreachable target whose cost is not computable.
    """
    if altitude_km is None:
        return None
    constants = load_constants(settings)
    radius_m = float(constants.values["R_e"]) + float(altitude_km) * 1000.0
    circular_speed = math.sqrt(float(constants.values["GM"]) / radius_m)
    gap_rad = math.radians(abs(phi_s_deg - inclination_deg))
    return 2.0 * circular_speed * math.sin(gap_rad / 2.0)


# ------------------------------------------------------------------- composition


def strip_api_owned_fields(window: dict[str, Any]) -> dict[str, Any]:
    """Drop the fields the API composes, mirroring the seam 1 engine signature."""
    stripped = {key: value for key, value in window.items() if key not in API_OWNED_WINDOW_FIELDS}
    components = {
        key: value
        for key, value in window.get("p_success_components", {}).items()
        if key not in API_OWNED_COMPONENT_FIELDS
    }
    stripped["p_success_components"] = components
    return stripped


def select_windows(
    settings: Settings, windows: list[dict[str, Any]], resolved: dict[str, Any]
) -> list[dict[str, Any]]:
    """Keep the fixture rows that describe the resolved target.

    The offline floor ships rows for one orbit class at a time. Echoing a row whose
    ``reached_inclination_deg`` belongs to a different class would be a wrong answer
    dressed as a right one, so a class with no rows gets the informative empty result
    spec IV.1 defines instead.
    """
    tolerance = float(settings.service["fixture_inclination_tolerance_deg"])
    return [
        strip_api_owned_fields(window)
        for window in windows
        if abs(float(window["reached_inclination_deg"]) - resolved["i_t_deg"]) <= tolerance
    ]


def compute_windows(settings: Settings, effective_request: dict[str, Any]) -> dict[str, Any]:
    """The engine seam, served from the offline document. Task A3.

    Returns the spec IV.1 response body minus ``p_success``, ``horizon_label``,
    ``forecast_issue_time`` and ``p_success_components.weather``, which the route
    composes from the weather layer, and minus the two shared blocks, which are
    stamped from configuration.
    """
    started = time.perf_counter()
    document = load_windows_document(settings)
    site = settings.site_document(str(effective_request["site"]))
    resolved = resolve_target(settings, effective_request["target"])
    corridor = document_corridor(site, effective_request.get("corridor"))

    reachable, _, _ = reachability(
        float(site["phi_s_deg"]), resolved["i_t_deg"], corridor
    )
    warning = sso_consistency_warning(settings, effective_request["target"], resolved)
    if not reachable:
        body = {
            "reachable": False,
            "plane_change_dv_ms": plane_change_penalty(
                settings,
                float(site["phi_s_deg"]),
                resolved["i_t_deg"],
                resolved["h_t_km"],
            ),
            "sso_consistency_warning": warning,
            "windows": [],
            "engine_version": STUB_ENGINE_VERSION,
        }
    else:
        body = {
            "reachable": bool(document["reachable"]),
            "plane_change_dv_ms": document.get("plane_change_dv_ms"),
            "sso_consistency_warning": warning,
            "windows": select_windows(settings, document["windows"], resolved),
            "engine_version": STUB_ENGINE_VERSION,
        }
    body["computation_ms"] = round((time.perf_counter() - started) * 1000.0, 3)
    return body


def document_corridor(site: dict[str, Any], override: dict[str, Any] | None) -> dict[str, Any]:
    """The corridor the reachability test uses: the request override, else the site."""
    corridor = {
        "A_min_deg": site["corridor"]["A_min_deg"],
        "A_max_deg": site["corridor"]["A_max_deg"],
    }
    for bound in ("A_min_deg", "A_max_deg"):
        if override and override.get(bound) is not None:
            corridor[bound] = override[bound]
    return corridor


# ---------------------------------------------------------------------- weather


def compose_weather(
    settings: Settings, effective_request: dict[str, Any], window: dict[str, Any]
) -> dict[str, Any]:
    """The four weather-derived fields of one window row, spec IV.1.

    With ``include_weather`` false the schema forbids null for three of the four, so
    the schema-valid neutral value is used instead and recorded in the log: weather
    imposes no penalty because it was excluded, the probability is the product of the
    two deterministic pre-screens, and the horizon label is CLIMATOLOGY with no
    forecast issue time, which is the honest label for a value no forecast produced.
    """
    components = dict(window.get("p_success_components", {}))
    deterministic = float(components.get("range", 1.0)) * float(components.get("conjunction", 1.0))
    if not bool(effective_request.get("include_weather", True)):
        components["weather"] = 1.0
        return {
            "p_success": deterministic,
            "p_success_components": components,
            "horizon_label": "CLIMATOLOGY",
            "forecast_issue_time": None,
        }

    snapshot = load_weather_document(settings)
    weather = float(snapshot["p_launch"])
    components["weather"] = weather
    return {
        "p_success": weather * deterministic,
        "p_success_components": components,
        "horizon_label": snapshot["horizon_label"],
        "forecast_issue_time": snapshot["forecast_issue_time"],
    }