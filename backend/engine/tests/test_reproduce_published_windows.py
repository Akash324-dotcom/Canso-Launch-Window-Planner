"""E10. GATE G1: reproduce published launch windows. Spec III.2.

THE CREDIBILITY TEST. This test stays in the suite permanently. It is what unblocks
frontend work on live data.

PROTOCOL. For each published launch in ``data/published_windows.json`` the engine
is given ONLY:

  * the site coordinates,
  * the PUBLISHED target inclination,
  * the PUBLISHED local time of the ascending or descending node,
  * the date of the published launch,

and must produce a window centre within the tolerance of the PUBLISHED launch
instant. The published RAAN is never given, and never back-solved from the
launch time, because back-solving would make the test circular and worthless.

WHAT IS AND IS NOT THE ENGINE'S INPUT. The node time determines the plane, so the
required RAAN is date-indexed and the engine derives it from the Sun's right
ascension through (II.19). The residual that remains is the site's position in
the plane, which is what the site-to-node offset delta of (II.10) carries. That
is why the Plesetsk anchor at 62.9 N, whose delta is about -17.5 deg, is the
sharpest of the three: a low-latitude site has a delta near zero and would hide a
missing term.

TOLERANCE. The data file states it and it is not relaxed anywhere in this file.
Spec III.2 sets +/-2 min; the issue brief sets 5 min. Both are asserted, so a
regression that slips inside 5 minutes but outside 2 is still caught.
"""

from __future__ import annotations

import pytest

from backend.engine import frames, j2, provenance, sso, window

PUBLISHED = provenance.load_json("published_windows.json")
CASES = PUBLISHED["cases"]
TOLERANCE_MIN = PUBLISHED["tolerance_minutes"]
SPEC_III_2_TOLERANCE_MIN = 2.0


def _window_centre_minutes(case: dict) -> float:
    """Minutes between the engine's window centre and the published launch instant.

    Solves the engine's own plane condition: the site's right ascension must equal
    the RAAN implied by the published node time, offset by the site-to-node delta
    of (II.10) on the published branch.
    """
    published_jd = frames.julian_date_from_iso(case["published_liftoff_utc"])
    inclination = case["inclination_deg"]
    branch = case["ltan_branch"]
    nodal_rate = j2.nodal_rate_deg_per_day(case["altitude_km"], inclination)
    sweep_deg_per_day = (
        window.sweep_rate_deg_per_hour(nodal_rate) * 24.0
    )

    ascending = window.site_node_offset_deg(inclination, case["latitude_deg"])
    assert ascending is not None, f"{case['id']}: no offset for inclination {inclination}"
    offset_deg = 180.0 - ascending if branch == "descending" else ascending

    def residual(jd: float) -> float:
        raan = sso.raan_for_ltan_deg(jd, case["ltan_hours"], branch)
        return (
            frames.gmst_degrees_unwrapped(jd)
            + case["longitude_deg"]
            - offset_deg
            - raan
        )

    half_period_days = 180.0 / sweep_deg_per_day
    lo = published_jd - half_period_days
    hi = published_jd + half_period_days
    level = 360.0 * round(residual(published_jd) / 360.0)
    assert residual(lo) - level < 0.0 < residual(hi) - level, "root must be bracketed"

    for _ in range(200):
        mid = 0.5 * (lo + hi)
        if residual(mid) - level < 0.0:
            lo = mid
        else:
            hi = mid
    return (0.5 * (lo + hi) - published_jd) * 1440.0


def test_the_gate_file_declares_three_to_five_published_cases():
    assert 3 <= len(CASES) <= 5


@pytest.mark.parametrize("case", CASES, ids=[case["id"] for case in CASES])
def test_window_centre_lands_within_five_minutes_of_the_published_instant(case):
    """GATE G1. The pass criterion is 5 minutes and it is not relaxed."""
    residual_min = _window_centre_minutes(case)
    assert abs(residual_min) <= TOLERANCE_MIN, (
        f"{case['id']}: engine window centre is {residual_min:+.3f} min from the published "
        f"launch instant, outside the {TOLERANCE_MIN} minute gate"
    )


@pytest.mark.parametrize("case", CASES, ids=[case["id"] for case in CASES])
def test_window_centre_also_meets_the_tighter_spec_tolerance(case):
    """Spec III.2 sets 2 minutes as the disclosed standard. Reported per case."""
    residual_min = _window_centre_minutes(case)
    assert abs(residual_min) <= SPEC_III_2_TOLERANCE_MIN, (
        f"{case['id']}: {residual_min:+.3f} min, outside spec III.2's 2 minute standard "
        f"though inside the 5 minute gate"
    )


@pytest.mark.parametrize("case", CASES, ids=[case["id"] for case in CASES])
def test_every_case_carries_its_source_and_access_date(case):
    for key in ("inclination_url", "published_window_url", "instant_url"):
        assert case[key].startswith("http"), f"{case['id']} {key} is not a URL"
    assert case["inclination_source"], f"{case['id']} must name its inclination source"
    assert len(case["ltan_source"]) > 20, (
        f"{case['id']} must record where its node time came from, in enough detail to "
        "check whether it is an ascending or a descending node"
    )
    assert case["ltan_branch"] in case["ltan_source"].lower() or "node" in case["ltan_source"].lower()
    assert PUBLISHED["accessed"]
    assert case["published_window"], f"{case['id']} must quote the published window"
    assert case["timezone_arithmetic"], f"{case['id']} must show its timezone arithmetic"


@pytest.mark.parametrize("case", CASES, ids=[case["id"] for case in CASES])
def test_every_case_is_a_sun_synchronous_node_not_a_rendezvous_time(case):
    """Guards against a future anchor that is only reproducible because it was fitted."""
    assert case["ltan_branch"] in {"ascending", "descending"}
    assert case["inclination_deg"] > 90.0, "sun-synchronous orbits are retrograde here"
    assert "why_plane_bound" in case
    assert "raan" not in case, "a published RAAN here would be a back-solved circular input"


def test_the_gate_does_not_widen_its_tolerance_to_absorb_a_miss():
    """If an anchor ever needs the tolerance raised, this fails first."""
    assert TOLERANCE_MIN == 5.0


def test_rejected_candidates_record_why_they_were_dropped():
    """A dropped anchor must carry a reason, not vanish quietly."""
    rejected = PUBLISHED["rejected_candidates"]
    assert len(rejected) >= 3
    for entry in rejected:
        assert entry["reason"], entry
        assert len(entry["reason"]) > 60, "a reason must actually explain"


def test_measured_residuals_are_stable_across_repeated_runs():
    """Determinism on the gate: the same anchor must give the same number twice."""
    for case in CASES:
        first = _window_centre_minutes(case)
        second = _window_centre_minutes(case)
        assert first == second


def test_gate_residuals_are_reported_for_the_record(case_id=None):
    """Prints the residual table. Run with -s to see it; it always passes."""
    lines = [
        f"  {case['id']:28s} i={case['inclination_deg']:7.3f} "
        f"{case['ltan_branch']:10s} {_window_centre_minutes(case):+8.3f} min"
        for case in CASES
    ]
    print("\nGATE G1 residuals, engine minus published:\n" + "\n".join(lines))