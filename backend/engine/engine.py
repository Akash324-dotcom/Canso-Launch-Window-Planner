"""Composition. Spec IV.1 request in, the engine's share of the response out.

Deliberately thin: no arithmetic happens here. Every number comes from
:mod:`backend.engine.frames`, :mod:`~backend.engine.reachability`,
:mod:`~backend.engine.j2`, :mod:`~backend.engine.window`,
:mod:`~backend.engine.injection`, :mod:`~backend.engine.sso` or
:mod:`~backend.engine.screens`, and every site-, vehicle- or criteria-dependent
value comes from ``data/*.json``.

REACHABILITY, AND A DELIBERATE READING OF THE SPEC. Spec (II.4) folds the
corridor into the reachability predicate, so ``reachable`` in the response is
corridor-inclusive. Spec claim (ii) states the corridor-free algebraic version.
Both are exposed by :mod:`backend.engine.reachability`. When a target is
geometrically reachable but blocked by the corridor, the response is
``reachable: false`` AND still carries the geometrically valid window rows, each
with ``constraint_fired: "hazard_area"``, so a caller sees which constraint
stopped it rather than an unexplained empty list. ``plane_change_dv_ms`` is null
in that case: (II.5) prices a gap to the reachable interval, not a corridor
restriction, and inventing a cost for a corridor violation would be wrong.

NO WEATHER. The engine never fetches a forecast and never guesses a probability.
``p_success`` and ``p_success_components.weather``, ``horizon_label`` and
``forecast_issue_time`` are composed by the API from the weather seam. Spec II.9
marks positive forecast skill at this site a CONJECTURE, and the engine does not
pretend otherwise by inventing a number.
"""

from __future__ import annotations

from typing import Any, Mapping

from backend.engine import (
    frames,
    injection,
    j2,
    provenance,
    reachability,
    screens,
    sso,
    target as target_module,
    window,
)

_VALID_TARGET_TYPES = frozenset({"LEO", "POLAR", "SSO", "CUSTOM"})


def _validate(request: Any) -> None:
    if not isinstance(request, dict):
        raise ValueError("request must be a dict")
    target = request.get("target")
    if not isinstance(target, dict):
        raise ValueError("request.target is required and must be an object")
    if target.get("type") not in _VALID_TARGET_TYPES:
        raise ValueError(f"request.target.type must be one of {sorted(_VALID_TARGET_TYPES)}")
    if target["type"] == "CUSTOM" and (
        not isinstance(target.get("h_t_km"), (int, float))
        or not isinstance(target.get("i_t_deg"), (int, float))
    ):
        raise ValueError("target.type CUSTOM requires numeric h_t_km and i_t_deg")
    date_range = request.get("date_range")
    if not isinstance(date_range, dict) or "start" not in date_range or "end" not in date_range:
        raise ValueError("request.date_range with start and end is required")
    if not isinstance(request.get("vehicle_profile_id"), str):
        raise ValueError("request.vehicle_profile_id is required")


def compose(request: Mapping[str, Any]) -> dict[str, Any]:
    """Run the whole pipeline for one request."""
    _validate(request)
    # Spec II.10 / III.6: the provenance block must name the files THIS run read,
    # not everything read earlier in the process.
    provenance.reset_source_files()
    start_jd = frames.julian_date_from_iso(f"{request['date_range']['start']}T00:00:00Z")
    resolved = target_module.resolve(request, start_jd)
    profile = injection.load_vehicle(request["vehicle_profile_id"])
    fixture = provenance.load_json("tle_fixture.json")

    # The end date is INCLUSIVE, so a range of one day means that whole day.
    # Treating "end" as midnight silently returned nothing for a same-day range,
    # which is what a caller asking for 5 October to 5 October expects to find.
    end_jd = frames.julian_date_from_iso(f"{request['date_range']['end']}T00:00:00Z") + 1.0
    if request["date_range"]["end"] < request["date_range"]["start"]:
        raise ValueError("date_range.end must not precede date_range.start")

    geometric = reachability.reachable(resolved.i_t_deg, resolved.lat_deg)
    admitted = reachability.reachable_in_corridor(
        resolved.i_t_deg, resolved.lat_deg, resolved.corridor
    )

    penalty = None
    if not geometric:
        penalty = reachability.plane_change_dv_ms(
            resolved.i_t_deg, resolved.lat_deg, resolved.altitude_km
        )

    rows: list[dict[str, Any]] = []
    if geometric:
        rows = _rows(resolved, profile, fixture, start_jd, end_jd)

    return {
        "reachable": admitted,
        "plane_change_dv_ms": penalty,
        "sso_consistency_warning": resolved.warning,
        "windows": rows,
    }


def _rows(
    resolved: target_module.Target,
    profile: dict[str, Any],
    fixture: dict[str, Any],
    start_jd: float,
    end_jd: float,
) -> list[dict[str, Any]]:
    """Every window in the range, each with its geometry and its screen verdict."""
    nodal_rate = j2.nodal_rate_deg_per_day(resolved.altitude_km, resolved.i_t_deg)
    azimuth = target_module.azimuth_for(resolved)
    screen_target = {
        "altitude_km": resolved.altitude_km,
        "i_t_deg": resolved.i_t_deg,
        "raan_deg": resolved.raan_deg,
        "conjunction": _conjunction_settings(resolved),
    }

    per_branch: list[tuple[str, dict[str, Any]]] = []
    for branch in ("ascending", "descending"):
        search_target = _search_target(resolved, branch, nodal_rate)
        if window.site_node_offset_deg(resolved.i_t_deg, resolved.lat_deg) is None:
            continue
        per_branch.append((branch, search_target))

    rows: list[dict[str, Any]] = []
    for branch, search_target in per_branch:
        found = window.find_windows(search_target, start_jd, end_jd, branch=branch)
        for entry in found:
            row = _row(resolved, profile, fixture, entry, branch, nodal_rate, azimuth, screen_target)
            rows.append(row)

    rows.sort(key=lambda item: item["t_liftoff_utc"])
    return rows


def _conjunction_settings(resolved: target_module.Target) -> dict[str, Any]:
    site = target_module.load_site(resolved.site_name)
    return site.get("conjunction", {})


def _search_target(
    resolved: target_module.Target, branch: str, nodal_rate: float
) -> dict[str, Any]:
    """Build the search target for one SITE crossing.

    ``branch`` selects which crossing of the plane (II.9) is searched. It must
    NOT change the plane: for a date-indexed LTAN target the plane comes from the
    PUBLISHED node branch on the request, and folding the site-crossing branch
    into it moved EarthCARE by twelve hours, which is the branch trap in its
    purest form.
    """
    raan = resolved.raan_deg
    if resolved.ltan_hours is not None:
        raan = sso.raan_for_ltan_deg(
            resolved.epoch_jd, resolved.ltan_hours, resolved.ltan_branch
        )
    return {
        "i_t_deg": resolved.i_t_deg,
        "raan_deg": 0.0 if raan is None else raan,
        "altitude_km": resolved.altitude_km,
        "nodal_rate_deg_per_day": nodal_rate,
        "raan_tolerance_deg": resolved.raan_tolerance_deg,
        "lat_deg": resolved.lat_deg,
        "lon_deg": resolved.lon_deg,
        "epoch_jd": resolved.epoch_jd,
        "branch": branch,
        "t_to_inj_s": 0.0,
        "ltan_hours": resolved.ltan_hours,
    }


def _branch_azimuth_deg(azimuth: float | None, branch: str) -> float | None:
    """The azimuth actually flown on this site's crossing, not just the request's.

    (II.2) solves for the SOUTHBOUND branch, ``beta = 180 - asin(cos(i)/cos(phi_s))``,
    and that is the branch the Canso environmental assessment admits. The ascending
    site crossing of the same plane is reached flying the prograde partner azimuth
    ``180 - beta``, which is a different trajectory over different ground: it is
    180 deg of heading away from the other branch and its ground footprint does not
    coincide. Reporting the southbound number on a northbound row states a launch
    direction the vehicle never flies, and it also hands the hazard screen a
    southbound azimuth for a northbound launch, so the row reads as clear.

    The partner is a function of the inclination, not a constant offset from it.
    From Canso at i = 97.4 deg the southbound azimuth is 190.55 deg and the partner
    is 349.45 deg; at i = 98.1 deg they are 191.56 deg and 348.44 deg. Both are
    derived from the same inclination that produced the southbound value, so the
    two branches can never drift out of the ``beta + partner = 540 deg`` relation.
    """
    if azimuth is None or branch != "ascending":
        return azimuth
    return reachability.northbound_partner_deg(azimuth)


def _row(
    resolved: target_module.Target,
    profile: dict[str, Any],
    fixture: dict[str, Any],
    entry: window.Window,
    branch: str,
    nodal_rate: float,
    azimuth: float | None,
    screen_target: dict[str, Any],
) -> dict[str, Any]:
    """One window row, with the injection-consistent refinement applied."""
    solve_target = _search_target(resolved, branch, nodal_rate)
    solve_target["t_to_inj_s"] = float(profile["t_to_inj_s"])
    solve_target["t_to_inj_flag"] = _t_to_inj_flag(profile)
    if resolved.ltan_hours is not None:
        # Re-date the plane to the window itself, still using the PUBLISHED node
        # branch and never the site-crossing branch.
        solve_target["raan_deg"] = sso.raan_for_ltan_deg(
            entry.centre_jd, resolved.ltan_hours, resolved.ltan_branch
        )
        solve_target["epoch_jd"] = entry.centre_jd

    solution = injection.solve_injection_consistent(
        solve_target, entry.open_jd, entry.close_jd
    )

    # The plane is NOT branch-dependent and must not be made so: (II.9)'s ascending
    # and descending site crossings are two passes through ONE plane, so screen_target
    # keeps the request's plane and the conjunction screen compares every row against
    # the same plane. Folding the branch into the screen target would be the branch
    # trap _search_target already documents, applied one layer up.
    row_azimuth = _branch_azimuth_deg(azimuth, branch)

    compass = (
        frames.azimuth_correction_deg(row_azimuth, resolved.lat_deg)
        if row_azimuth
        else 0.0
    )
    verdict = screens.evaluate(
        row_azimuth if row_azimuth is not None else 0.0,
        resolved.corridor,
        profile,
        screen_target,
        fixture,
    )

    return {
        "t_liftoff_utc": frames.iso_from_julian_date(solution.liftoff_jd),
        "t_injection_utc": frames.iso_from_julian_date(solution.injection_jd),
        "raan_deg": round(entry.raan_deg, 9),
        "azimuth_deg": round(row_azimuth, 9) if row_azimuth is not None else 0.0,
        "azimuth_compass_deg": (
            round(row_azimuth + compass, 9) if row_azimuth is not None else 0.0
        ),
        "reached_inclination_deg": resolved.i_t_deg,
        "window_width_s": entry.width_s,
        "window_center_shift_s": solution.window_center_shift_s,
        "liftoff_instant_error_min": solution.liftoff_instant_error_min,
        "p_success_components": {
            "range": float(verdict.p_range),
            "conjunction": float(verdict.p_conjunction),
        },
        "constraint_fired": solution.constraint_fired or verdict.constraint_fired,
        "screens": verdict.to_contract_fields(),
    }


def _t_to_inj_flag(profile: Mapping[str, Any]) -> str:
    for row in profile.get("rows", []):
        if row.get("key") == "t_to_inj_s":
            return str(row["flag"])
    return "ASSUMPTION"