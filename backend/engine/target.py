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
    raan_deg: float
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
    """Read a named site from configuration. Only "canso" is defined."""
    if site_name != DEFAULT_SITE:
        raise ValueError(
            f"unknown site {site_name!r}; the engine ships configuration for {DEFAULT_SITE!r} only"
        )
    return provenance.load_json("site_canso.json")


def _parse_ltan(text: str) -> float:
    """Parse "HH:MM" or a bare decimal hour count into decimal hours."""
    if ":" in text:
        hours, _, minutes = text.partition(":")
        return int(hours) + int(minutes) / 60.0
    value = float(text)
    return value


def resolve(request: Mapping[str, Any]) -> Target:
    """Resolve type, altitude, inclination, plane and tolerance per spec IV.1."""
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
    if inclination is None:
        inclination = (
            sso.required_inclination_deg(altitude_km) if orbit_class == "SSO"
            else defaults["i_t_deg"]
        )

    if ltan_hours is not None:
        inclination = sso.required_inclination_deg(altitude_km)
        raan_deg = None  # date-indexed through the LTAN; see sso.raan_for_ltan_deg
    else:
        raan_deg = target.get("raan_deg")
        if raan_deg is None and orbit_class == "SSO":
            inclination = sso.required_inclination_deg(altitude_km)

    tolerance = request.get("raan_tolerance_deg")
    if tolerance is None:
        tolerance = defaults["raan_tolerance_deg"]

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
        raan_deg=None if raan_deg is None else float(raan_deg),
        raan_tolerance_deg=float(tolerance),
        lat_deg=float(site["latitude_deg"]),
        lon_deg=float(site["longitude_deg"]),
        ltan_hours=ltan_hours,
        ltan_branch=ltan_branch,
        site_name=site["name"],
        corridor=request.get("corridor") or site["corridor"],
        epoch_jd=0.0,
        warning=warning,
    )


def azimuth_for(target: Target) -> float | None:
    return reachability.launch_azimuth_deg(target.i_t_deg, target.lat_deg)


def corridor_admits(target: Target) -> bool:
    beta = azimuth_for(target)
    return beta is not None and reachability.azimuth_in_corridor(beta, target.corridor)