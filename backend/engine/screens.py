"""Range and conjunction screens. Spec II.8.

All three screens are PRE-SCREENS. Spec II.8 is explicit that they are coarse
deterministic filters, not operational products:

* Hazard area: a deterministic pass or fail that feeds P_range_clear as 0 or 1.
  It is documented as such and is not a probability.
* Conjunction: a coarse band-and-plane filter over committed TLEs, not CSpOC
  screening. Spec II.8 puts operational screening, automated NOTAM parsing,
  expected-casualty analysis and abort-mode coverage out of scope for 32 hours.
* NOTAM: display only. Spec II.8 says it never gates a window.

The conjunction screen NEVER touches the network during a test. It reads the
committed fixture in ``data/tle_fixture.json``, which records its own fetch time
and source so the provenance travels with the numbers.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any, Mapping

CONSTRAINT_PRE_SCREEN = "screen_level: pre_screen"
CONSTRAINT_DISPLAY_ONLY = "display_only"

HAZARD_AREA = "hazard_area"
CONJUNCTION_FLAGGED = "conjunction_flagged"

NOTAM_SOURCE = "Nav Canada, https://plan.navcanada.ca/ (display only, never gates a window)"


@dataclass(frozen=True)
class HazardVerdict:
    hazard: str
    p_range: int
    reason: str
    constraint_fired: str | None = None
    constraint_source: str = CONSTRAINT_PRE_SCREEN


@dataclass(frozen=True)
class ConjunctionVerdict:
    conjunction: str
    p_conjunction: int
    worst_miss_km: float
    threshold_km: float
    threshold_flag: str
    considerations: tuple[dict[str, Any], ...] = field(default_factory=tuple)
    source: str = ""
    fetched_utc: str = ""
    fidelity: str = (
        "This is a pre_screen, not an operational screen: an altitude-band and "
        "plane-proximity filter over three committed TLEs, not SGP4 conjunction "
        "screening and not a CSpOC product."
    )
    constraint_source: str = CONSTRAINT_PRE_SCREEN


@dataclass(frozen=True)
class NotamVerdict:
    notam: str = "none"
    p_notam: None = None
    constraint_fired: None = None
    reason: str = "Stub. The Nav Canada NOTAM path is display only and is not queried."
    source: str = NOTAM_SOURCE
    constraint_source: str = CONSTRAINT_DISPLAY_ONLY


@dataclass(frozen=True)
class ScreenResult:
    hazard: str
    conjunction: str
    notam: str
    p_range: int
    p_conjunction: int
    constraint_fired: str | None
    reasons: tuple[str, ...] = field(default_factory=tuple)

    def to_contract_fields(self) -> dict[str, str]:
        """Exactly the spec IV.1 ``screens`` object."""
        return {"hazard": self.hazard, "conjunction": self.conjunction, "notam": self.notam}


# --- Hazard (spec II.8) ------------------------------------------------------


def hazard_screen(
    azimuth_deg: float, corridor: Mapping[str, Any], profile: Mapping[str, Any]
) -> HazardVerdict:
    """Deterministic hazard-area test for one launch azimuth.

    The environmental assessment admits only southbound trajectories over the
    Atlantic, so a northbound azimuth is rejected regardless of where the numeric
    corridor bounds happen to sit. Inside the southbound branch the test is the
    corridor membership of (II.3).
    """
    if not _is_southbound(azimuth_deg):
        return HazardVerdict(
            hazard="fail",
            p_range=0,
            reason=(
                f"Azimuth {azimuth_deg:.2f} deg is northbound. The Canso environmental "
                "assessment states that all launches are conducted to the south over the "
                "Atlantic Ocean, so only the southbound branch is admissible."
            ),
            constraint_fired=HAZARD_AREA,
        )

    a_min = corridor["A_min_deg"]
    a_max = corridor["A_max_deg"]
    if a_min - 1.0e-9 <= azimuth_deg <= a_max + 1.0e-9:
        return HazardVerdict(
            hazard="pass",
            p_range=1,
            reason=(
                f"Southbound azimuth {azimuth_deg:.2f} deg lies inside the corridor "
                f"[{a_min:g}, {a_max:g}] deg."
            ),
        )
    return HazardVerdict(
        hazard="fail",
        p_range=0,
        reason=(
            f"Southbound azimuth {azimuth_deg:.2f} deg leaves the corridor "
            f"[{a_min:g}, {a_max:g}] deg, so the buffered footprint is not contained in "
            "the over-ocean hazard area."
        ),
        constraint_fired=HAZARD_AREA,
    )


def _is_southbound(azimuth_deg: float) -> bool:
    return 90.0 - 1.0e-9 <= azimuth_deg <= 270.0 + 1.0e-9


# --- Conjunction (spec II.8) -------------------------------------------------


def conjunction_screen(
    target: Mapping[str, Any], tle_fixture: Mapping[str, Any]
) -> ConjunctionVerdict:
    """Coarse conjunction pre-screen over a committed TLE fixture.

    An object is a consideration only when it is in the same ORBIT PLANE as the
    launch, which spec II.8 defines as all three of: mean altitude within the miss
    threshold, inclination within the plane tolerance, AND RAAN within the plane
    tolerance. Altitude and inclination alone do not define a plane. Two objects
    can share an altitude and an inclination to within a metre and a thousandth of
    a degree and still never approach each other, because their planes are
    rotated about the polar axis relative to one another; the plane is the reason
    the real screening products screen on it.

    The plane test needs a target RAAN. When the request leaves the plane free the
    miss is ``None``, the plane is not yet known, and ``None`` is treated as
    CONSERVATIVE, that is as "assume the plane matches and flag". Treating an
    unknown plane as clear would make a screen report a pass on the strength of a
    quantity it never had.
    """
    settings = target.get("conjunction", {})
    threshold_km = float(settings.get("miss_threshold_km", 50.0))
    threshold_flag = settings.get("miss_threshold_flag", "ASSUMPTION")
    plane_tolerance_deg = float(settings.get("plane_tolerance_deg", 5.0))

    target_altitude = float(target["altitude_km"])
    target_inclination = float(target["i_t_deg"])
    target_raan = target.get("raan_deg")

    considerations: list[dict[str, Any]] = []
    worst_miss_km = math.inf
    for satellite in tle_fixture["satellites"]:
        altitude_miss = abs(float(satellite["mean_altitude_km"]) - target_altitude)
        inclination_miss = abs(_inclination_of(satellite) - target_inclination)
        raan_miss = (
            abs((float(_raan_of(satellite)) - float(target_raan) + 180.0) % 360.0 - 180.0)
            if target_raan is not None
            else None
        )
        # A free target plane gives raan_miss None, which is CONSERVATIVE here: the
        # plane is unknown, so the object is assumed to share it and the row is
        # flagged. An unknown plane must never read as a clear plane.
        same_plane = raan_miss is None or raan_miss <= plane_tolerance_deg
        worst_miss_km = min(worst_miss_km, altitude_miss)
        if altitude_miss <= threshold_km and inclination_miss <= plane_tolerance_deg and same_plane:
            considerations.append(
                {
                    "norad_id": satellite["norad_id"],
                    "name": satellite["name"],
                    "mean_altitude_km": satellite["mean_altitude_km"],
                    "altitude_miss_km": altitude_miss,
                    "inclination_miss_deg": inclination_miss,
                    "raan_miss_deg": raan_miss,
                }
            )

    if not math.isfinite(worst_miss_km):
        worst_miss_km = max(target_altitude, 1.0e3)

    flagged = bool(considerations)
    return ConjunctionVerdict(
        conjunction="flagged" if flagged else "clear",
        p_conjunction=0 if flagged else 1,
        worst_miss_km=worst_miss_km,
        threshold_km=threshold_km,
        threshold_flag=threshold_flag,
        considerations=tuple(considerations),
        source=str(tle_fixture.get("source", "CelesTrak GP data")),
        fetched_utc=str(tle_fixture.get("fetched_utc", "")),
    )


def _inclination_of(satellite: Mapping[str, Any]) -> float:
    if "inclination_deg" in satellite:
        return float(satellite["inclination_deg"])
    return float(satellite["tle_line2"][8:16])


def _raan_of(satellite: Mapping[str, Any]) -> float:
    if "raan_deg" in satellite:
        return float(satellite["raan_deg"])
    return float(satellite["tle_line2"][17:25])


# --- NOTAM (spec II.8) -------------------------------------------------------


def notam_screen() -> NotamVerdict:
    """Display-only stub. Spec II.8: a NOTAM never gates a window."""
    return NotamVerdict()


# --- Combined ----------------------------------------------------------------


def evaluate(
    azimuth_deg: float,
    corridor: Mapping[str, Any],
    profile: Mapping[str, Any],
    target: Mapping[str, Any],
    tle_fixture: Mapping[str, Any],
) -> ScreenResult:
    """Run all three screens and report the first constraint that stopped the row."""
    hazard = hazard_screen(azimuth_deg, corridor, profile)
    conjunction = conjunction_screen(target, tle_fixture)
    notam = notam_screen()

    constraint = hazard.constraint_fired
    reasons = [hazard.reason]
    if constraint is None and conjunction.conjunction == "flagged":
        constraint = CONJUNCTION_FLAGGED
        reasons.append(
            f"Conjunction pre-screen flagged {len(conjunction.considerations)} committed "
            f"TLE object(s); worst altitude miss {conjunction.worst_miss_km:.2f} km against "
            f"a {conjunction.threshold_km:.2f} km threshold."
        )

    return ScreenResult(
        hazard=hazard.hazard,
        conjunction=conjunction.conjunction,
        notam=notam.notam,
        p_range=hazard.p_range,
        p_conjunction=conjunction.p_conjunction,
        constraint_fired=constraint,
        reasons=tuple(reasons),
    )