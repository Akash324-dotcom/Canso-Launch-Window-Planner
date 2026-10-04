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
    """Parse "HH:MM" or a bare decimal hour count into decimal hours."""
    if ":" in text:
        hours, _, minutes = text.partition(":")
        return int(hours) + int(minutes) / 60.0
    value = float(text)
    return value


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
        corridor=request.get("corridor") or site["corridor"],
        epoch_jd=epoch_jd,
        warning=warning,
    )


def azimuth_for(target: Target) -> float | None:
    return reachability.launch_azimuth_deg(target.i_t_deg, target.lat_deg)
