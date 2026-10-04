"""The launch azimuth is a per-branch quantity, not a per-request one.

Spec (II.2) solves the ascent geometry for the SOUTHBOUND branch,
``beta = 180 - asin(cos(i)/cos(phi_s))``, which is the branch the Canso
environmental assessment admits. The other branch into the SAME plane is the
prograde partner azimuth ``180 - beta``, computed by
``reachability.northbound_partner_deg``.

WHY THE BRANCH MATTERS PHYSICALLY. Into one target plane the site crosses twice
per orbital period: once on the ascending branch of (II.9) and once on its
descending branch, half a period apart. Both are genuine launch opportunities
into that plane. They are not the same flight, though. The two azimuths are
180 deg apart in heading, so the ground track during ascent, the position over
which the vehicle is exposed, and the hazard-area footprint are different for
each. A row that reports the southbound number on a northbound flight states a
launch direction the vehicle never flies, AND hands the range screen a southbound
azimuth for a northbound launch, so the row reads as clear when the environmental
assessment forbids it.

WHAT IS NOT A BRANCH QUANTITY. The plane is not. (II.9)'s two branches are two
passes through ONE plane, so the conjunction screen compares every row of a
request against the same plane and the screen target keeps the request's RAAN.
Folding the branch into the screen target would be the branch trap
``_search_target`` already documents, applied one layer up, and would move the
G1 published anchors by half a period.
"""

from __future__ import annotations

import pytest

from backend.engine import compute_windows, engine, frames, j2, provenance, reachability

SITE = provenance.load_json("site_canso.json")
PHI_S = float(SITE["latitude_deg"])
CORRIDOR = SITE["corridor"]

CANSO_SSO_REQUEST = {
    "target": {"type": "SSO"},
    "site": "canso",
    "date_range": {"start": "2026-03-01", "end": "2026-03-01"},
    "vehicle_profile_id": "cyclone4m",
    "include_weather": False,
}


def _branch_of(row: dict) -> str:
    """Which site crossing a row is, read back from the row's own azimuth.

    The response schema has no branch field, so the branch is recovered from the
    physics rather than assumed. The hazard screen already draws exactly this
    line: the Canso assessment admits the southbound branch only, so a row that
    passes the range screen is the southbound crossing and a row that fails it on
    northbound grounds is the ascending one.
    """
    return "descending" if row["screens"]["hazard"] == "pass" else "ascending"


def _rows() -> list[dict]:
    response = compute_windows(CANSO_SSO_REQUEST)
    assert response["reachable"] is True
    assert response["windows"], "the canonical Canso SSO request must return windows"
    return response["windows"]


def _by_branch(rows: list[dict]) -> dict[str, dict]:
    grouped: dict[str, dict] = {}
    for row in rows:
        branch = _branch_of(row)
        assert branch not in grouped, f"more than one {branch} crossing in one day"
        grouped[branch] = row
    return grouped


# --- The partner relation the rows must obey ----------------------------------


def test_the_two_daily_crossings_report_different_launch_directions() -> None:
    grouped = _by_branch(_rows())
    assert set(grouped) == {"ascending", "descending"}, (
        "the Canso SSO request must offer both site crossings of the plane"
    )
    assert grouped["ascending"]["azimuth_deg"] != grouped["descending"]["azimuth_deg"], (
        "both crossings report the same azimuth, so the request-level value is being "
        "reused on both branches and the northbound row names a direction never flown"
    )


def test_the_northbound_row_carries_the_prograde_partner_of_the_southbound_row() -> None:
    grouped = _by_branch(_rows())
    south = grouped["descending"]["azimuth_deg"]
    north = grouped["ascending"]["azimuth_deg"]
    assert north == pytest.approx(reachability.northbound_partner_deg(south), abs=1.0e-9)
    assert (south + north) % 360.0 == pytest.approx(180.0, abs=1.0e-9), (
        "the partner relation is beta_north = 180 - beta_south, so the two azimuths "
        "sum to 180 deg modulo 360; any other relation means the two branches were "
        "computed from different inputs"
    )


def test_the_compass_azimuth_is_derived_from_the_row_s_own_azimuth() -> None:
    """The rotating-frame correction must follow the branch, not a shared value."""
    for row in _rows():
        correction = row["azimuth_compass_deg"] - row["azimuth_deg"]
        expected = engine.frames.azimuth_correction_deg(
            row["azimuth_deg"], float(SITE["latitude_deg"])
        )
        assert correction == pytest.approx(expected, abs=1.0e-9)


def test_the_partner_relation_moves_with_inclination_and_is_not_a_constant() -> None:
    """A fixed offset would be wrong: the partner is a function of i, not of the site."""
    first = reachability.launch_azimuth_deg(97.4, PHI_S)
    second = reachability.launch_azimuth_deg(98.1, PHI_S)
    assert first is not None and second is not None
    assert first == pytest.approx(190.55071, abs=1.0e-4), (
        "the reference southbound azimuth at i = 97.4 deg from Canso; it is read from "
        "(II.2) and is pinned here so a change to the reachability algebra is visible"
    )
    assert reachability.northbound_partner_deg(first) == pytest.approx(349.44929, abs=1.0e-4)
    assert second - first == pytest.approx(1.00473, abs=1.0e-4), (
        "moving the inclination by 0.7 deg moves the southbound azimuth by about a "
        "degree, so no single constant partner offset can serve both inclinations"
    )


@pytest.mark.parametrize(
    "inclination,south",
    [(97.4, 190.55071), (98.1, 191.55544), (103.0, 198.65130)],
)
def test_the_branch_helper_applies_the_partner_only_on_the_ascending_branch(
    inclination: float, south: float
) -> None:
    base = reachability.launch_azimuth_deg(inclination, PHI_S)
    assert base == pytest.approx(south, abs=1.0e-4)
    assert engine._branch_azimuth_deg(base, "ascending") == pytest.approx(
        reachability.northbound_partner_deg(base), abs=1.0e-9
    )
    assert engine._branch_azimuth_deg(base, "descending") == base


def test_the_branch_helper_leaves_an_unreachable_target_alone() -> None:
    """None means the azimuth does not exist; there is no partner to compute."""
    assert engine._branch_azimuth_deg(None, "ascending") is None
    assert engine._branch_azimuth_deg(None, "descending") is None


# --- The consequence: the northbound row is refused by the range screen --------


def test_the_northbound_row_is_marked_unusable_when_it_violates_the_corridor() -> None:
    grouped = _by_branch(_rows())
    north = grouped["ascending"]
    assert north["screens"]["hazard"] == "fail", (
        "the northbound crossing must not read as range-clear at a site whose "
        "environmental assessment admits the southbound branch only"
    )
    assert north["constraint_fired"] == "hazard_area"
    assert north["p_success_components"]["range"] == 0.0


def test_the_southbound_row_stays_usable() -> None:
    grouped = _by_branch(_rows())
    south = grouped["descending"]
    assert south["screens"]["hazard"] == "pass"
    assert south["p_success_components"]["range"] == 1.0
    assert south["constraint_fired"] in {None, "conjunction_flagged"}


def test_the_refused_row_still_appears_in_the_response() -> None:
    """A hazard failure is an answer, not an omission: spec II.4 and the engine docstring."""
    rows = _rows()
    assert any(row["screens"]["hazard"] == "fail" for row in rows)
    assert any(row["screens"]["hazard"] == "pass" for row in rows), (
        "at least one southbound crossing must remain usable, or the target would be "
        "unreachable and the rows would not be emitted at all"
    )


def test_both_crossings_still_search_the_same_plane() -> None:
    """The plane must not move with the branch. That is the branch trap, and it is avoided.

    Two crossings of one plane are separated by about half an orbital period, and
    the plane's RAAN regresses over that interval, so the two rows report RAANs
    that differ by exactly the nodal drift and nothing else.
    """
    rows = sorted(_rows(), key=lambda row: row["t_liftoff_utc"])
    assert len(rows) == 2

    earlier, later = rows
    separation_days = (
        frames.julian_date_from_iso(later["t_liftoff_utc"])
        - frames.julian_date_from_iso(earlier["t_liftoff_utc"])
    )
    nodal_rate = j2.nodal_rate_deg_per_day(674.0, 98.1)
    expected_drift = nodal_rate * separation_days
    observed_drift = later["raan_deg"] - earlier["raan_deg"]
    assert observed_drift == pytest.approx(expected_drift, abs=0.2), (
        "the two rows are separated by secular nodal drift only, which is what it means "
        "for them to be two crossings of one plane; a different difference would mean "
        "the branch had been folded into the plane"
    )


def test_the_branch_helper_is_the_only_place_a_partner_is_computed() -> None:
    """Guards against the partner being recomputed inline somewhere else."""
    import inspect

    source = inspect.getsource(engine)
    assert source.count("northbound_partner_deg") == 1, (
        "the prograde partner must be applied in exactly one place, so there is one "
        "answer to the question of which branch flies which azimuth"
    )
