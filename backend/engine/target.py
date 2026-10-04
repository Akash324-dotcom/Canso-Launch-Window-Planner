"""Request resolution: turn a spec IV.1 request into a target the modules can use.

Kept apart from :mod:`backend.engine` so that composition stays thin and no
arithmetic happens at the call site. Every site-, vehicle- and criteria-dependent
value arrives from ``data/*.json``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping

from backend.engine import provenance, reachability, sso

DEFAULT_SITE = "canso"


@dataclass(frozen=True)
class Target:
    """Everything the window and injection solvers need, fully resolved."""

    orbit_class: str
    i_t_deg: float
    altitude_km: float
    raan_deg: float | None
    raan_tolerance_deg: float
    lat_deg: float
    lon_deg: float
    ltan_hours: float | None
    ltan_branch: str
    site_name: str
    corridor: Mapping[str, Any]
    epoch_jd: float
    warning: dict[str, Any] | None = field(default=None)

    @property
    def free_raan(self) -> bool:
        return self.raan_deg is None


def load_site(site_name: str) -> dict[str, Any]:
    """Read a named site from configuration.

    ``canso`` is the product site and lives at ``site_canso.json`` as the
    integration contract names it. The other names resolve under ``sites/`` and
    exist so the G1 credibility gate can drive the shipped seam at the launch
    sites of the published anchors; they carry ``site_role: g1_anchor`` and are
    not product configuration.
    """
    if site_name == DEFAULT_SITE:
        return provenance.load_json("site_canso.json")
    if not site_name or any(character in site_name for character in "/\\."):
        raise ValueError(f"invalid site name {site_name!r}")
    try:
        return provenance.load_json(f"sites/{site_name}.json")
    except FileNotFoundError as error:
        raise ValueError(f"unknown site {site_name!r}") from error


def _parse_ltan(text: str) -> float:
    """Parse "HH:MM" or a bare decimal hour count into decimal hours on [0, 24).

    A local time that does not exist is refused. "25:99" used to be read as 26.65
    hours and answered with windows for a node time that no orbit has.
    """
    text = str(text).strip()
    problem = ValueError(
        f"target.ltan_hours {text!r} is not a local time: expected HH:MM from 00:00 to 23:59, "
        "or decimal hours from 0 up to but not including 24"
    )
    try:
        if ":" in text:
            hours_text, _, minutes_text = text.partition(":")
            if not (hours_text.isdigit() and minutes_text.isdigit()):
                raise problem
            hours, minutes = int(hours_text), int(minutes_text)
            if hours > 23 or minutes > 59:
                raise problem
            return hours + minutes / 60.0
        value = float(text)
    except ValueError as error:
        raise problem from error
    if not 0.0 <= value < 24.0:
        raise problem
    return value


REQUEST_OVERRIDE_FLAG = "UNSOURCED_REQUEST_OVERRIDE"


def _corridor_for(request: Mapping[str, Any], site: Mapping[str, Any]) -> Mapping[str, Any]:
    """The corridor of the request: the site corridor, with any bound the request overrides.

    The frozen request schema allows either bound alone and allows null for a bound,
    so a missing or null bound is the bound of the site. Passing the partial override
    on as it came left one bound undefined and the reachability test raised.
    """
    override = request.get("corridor")
    if not override:
        return site["corridor"]
    given = {
        key: override[key]
        for key in ("A_min_deg", "A_max_deg")
        if override.get(key) is not None
    }
    merged = dict(override)
    site_flags = site["corridor"].get("flags", {})
    merged["flags"] = {}
    for key in ("A_min_deg", "A_max_deg"):
        merged[key] = given.get(key, site["corridor"][key])
        merged["flags"][key] = REQUEST_OVERRIDE_FLAG if key in given else site_flags.get(key)
    # The override moves bounds. The direction policy is a statement about the site
    # and travels with every corridor of that site.
    if "direction_policy" in site["corridor"]:
        merged["direction_policy"] = site["corridor"]["direction_policy"]
    return merged


def resolve(request: Mapping[str, Any], epoch_jd: float) -> Target:
    """Resolve type, altitude, inclination, plane and tolerance per spec IV.1.

    ``epoch_jd`` is the start of the requested range and is the date the target
    plane is referenced to. An LTAN-slaved orbit has a DATE-INDEXED plane, so a
    search that does not know the epoch derives its RAAN from the wrong date and
    returns windows on the wrong days.
    """
    site = load_site(request.get("site") or DEFAULT_SITE)
    target = request["target"]
    orbit_class = target["type"]

    defaults = site["target_classes"][orbit_class]
    altitude_km = target.get("h_t_km")
    inclination = target.get("i_t_deg")

    ltan_hours = _parse_ltan(target["ltan_hours"]) if target.get("ltan_hours") else None
    ltan_branch = str(target.get("ltan_branch") or defaults.get("ltan_branch") or "ascending")

    if altitude_km is None:
        altitude_km = defaults["h_t_km"]

    # An inclination stated in the request always WINS over a derived one. Spec
    # II.6 says the engine accepts either an LTAN or an explicit inclination and
    # derives the other, and a request may state both. Deriving over a stated
    # value made the window time independent of the published inclination, which
    # would let the G1 gate pass without using the number it claims to use.
    if ltan_hours is not None:
        raan_deg: float | None = None  # date-indexed through the node time
        if inclination is None:
            inclination = sso.required_inclination_deg(altitude_km)
    else:
        raan_deg = target.get("raan_deg")
        if inclination is None:
            inclination = (
                sso.required_inclination_deg(altitude_km)
                if orbit_class == "SSO"
                else defaults["i_t_deg"]
            )

    tolerance = request.get("raan_tolerance_deg")
    if tolerance is None:
        tolerance = defaults["raan_tolerance_deg"]
    elif not float(tolerance) > 0.0:
        # (II.12): the window width is 2 * tolerance / sweep rate. Zero gives a window
        # of no width and a negative value a negative width; neither is a window.
        raise ValueError(
            f"raan_tolerance_deg must be greater than 0, got {tolerance!r}: it is the half-width "
            "of the admitted plane error and governs the window width"
        )

    warning = sso.consistency_warning(
        i_t_deg=inclination,
        altitude_km=altitude_km,
        ltan_hours=ltan_hours,
        orbit_class=orbit_class,
    )

    return Target(
        orbit_class=orbit_class,
        i_t_deg=float(inclination),
        altitude_km=float(altitude_km),
        raan_deg=None if raan_deg is None else float(raan_deg),  # noqa: E501
        raan_tolerance_deg=float(tolerance),
        lat_deg=float(site["latitude_deg"]),
        lon_deg=float(site["longitude_deg"]),
        ltan_hours=ltan_hours,
        ltan_branch=ltan_branch,
        site_name=site["name"],
        corridor=_corridor_for(request, site),
        epoch_jd=epoch_jd,
        warning=warning,
    )


def azimuth_for(target: Target) -> float | None:
    return reachability.launch_azimuth_deg(target.i_t_deg, target.lat_deg)
