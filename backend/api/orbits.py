"""Orbit ids and the records that create them, tasks A5 and A6 of issue #4.

Spec IV.2 names the ids of the ephemeris endpoint: ``leo45``, ``polar879`` and
``sso981``, plus "custom orbit ids created implicitly by POST /v1/windows
(response orbit_id)".

That last clause cannot be taken literally against the frozen contract, and the
reason is recorded in ``docs/log/api.md``: ``windows_response.json`` closes
``additionalProperties``, so the window response has no field in which an
``orbit_id`` could travel, and the schema is frozen at gate G0. The identifier is
therefore recorded where the API owns it, in two places that a later reader can
find: the orbit registry below, which every POST adds to, and the stored run record
of task A6. Both are consulted by the ephemeris route, so an id created by a POST is
resolvable after a restart as well as before.

Nothing here computes orbital mechanics. The registry maps an identifier to the
target a request resolved to, and the preset matching uses the configured
tolerances.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable

from backend.api.config import Settings
from backend.api.errors import UnknownResourceError

PRESET_RESOURCE_KIND = "orbit"


@dataclass(frozen=True)
class RegisteredOrbit:
    """One orbit id the ephemeris endpoint may serve."""

    orbit_id: str
    i_t_deg: float
    h_t_km: float | None
    preset: str | None
    citation_id: str | None = None
    source_files: tuple[str, ...] = field(default_factory=tuple)


def match_preset(settings: Settings, inclination_deg: float) -> str | None:
    """The named class a resolved inclination belongs to, or None.

    A request whose inclination is close enough to a published class is that
    class, because the published ground track and the published drift are for that
    class. Beyond the configured tolerance the target is genuinely custom and gets
    its own identifier rather than being described by someone else's track.
    """
    tolerance = float(settings.orbits_config["preset_match_tolerance_deg"])
    for orbit_id, record in settings.target_classes.items():
        if abs(float(record["i_t_deg"]) - inclination_deg) <= tolerance:
            return orbit_id
    return None


def custom_orbit_id(inclination_deg: float, altitude_km: float | None) -> str:
    """A readable, deterministic identifier for a target that names no class.

    The numbers come from the request and are formatted, never looked up, so the
    identifier is reproducible from the run that created it.
    """
    altitude = "unknownalt" if altitude_km is None else f"{altitude_km:.1f}"
    return f"custom-{inclination_deg:.1f}-{altitude}"


def orbit_id_for_target(settings: Settings, resolved: dict[str, Any]) -> str:
    """The identifier ``POST /v1/windows`` records for a resolved target."""
    preset = match_preset(settings, float(resolved["i_t_deg"]))
    if preset is not None:
        return settings.ephemeris_config["preset_ids"][preset]
    return custom_orbit_id(float(resolved["i_t_deg"]), resolved.get("h_t_km"))


class OrbitRegistry:
    """The custom orbit ids this process has served a window request for.

    Session state only, and deliberately so: the durable copy of a custom id is
    the stored run record, which the route also reads. A restart therefore loses
    the in-memory copy and finds the record instead.
    """

    def __init__(self) -> None:
        self._orbits: dict[str, RegisteredOrbit] = {}

    def register(self, orbit: RegisteredOrbit) -> RegisteredOrbit:
        self._orbits[orbit.orbit_id] = orbit
        return orbit

    def get(self, orbit_id: str) -> RegisteredOrbit | None:
        return self._orbits.get(orbit_id)

    def ids(self) -> list[str]:
        return sorted(self._orbits)

    def __len__(self) -> int:
        return len(self._orbits)

    def __contains__(self, orbit_id: str) -> bool:
        return orbit_id in self._orbits


def resolve_orbit(
    settings: Settings,
    registry: OrbitRegistry,
    orbit_id: str,
    recorded: Iterable[RegisteredOrbit] = (),
) -> RegisteredOrbit:
    """The orbit an ephemeris request is about, or a 404.

    Three sources in order: the three named classes of spec IV.2, the ids this
    process has registered, and the ids found in the stored run records, which is
    what makes a custom id resolvable after a restart.
    """
    preset = settings.ephemeris_config["preset_ids"]
    if orbit_id in preset.values():
        return _preset_orbit(settings, orbit_id)
    known = registry.get(orbit_id)
    if known is not None:
        return known
    for candidate in recorded:
        if candidate.orbit_id == orbit_id:
            return candidate
    raise UnknownResourceError(PRESET_RESOURCE_KIND, orbit_id)


def _preset_orbit(settings: Settings, orbit_id: str) -> RegisteredOrbit:
    for name, preset_id in settings.ephemeris_config["preset_ids"].items():
        if preset_id != orbit_id:
            continue
        record = settings.target_classes[name]
        return RegisteredOrbit(
            orbit_id=orbit_id,
            i_t_deg=float(record["i_t_deg"]),
            h_t_km=None if record.get("h_t_km") is None else float(record["h_t_km"]),
            preset=name,
        )
    raise UnknownResourceError(PRESET_RESOURCE_KIND, orbit_id)