"""Which angle the window equation needs: the site-to-node offset of (II.10). Issue W5b.

Two forms were in dispute for ``delta`` in

    GMST(t) + lambda_s = Omega_t(t) + delta                                   (II.9)

    form A   delta = asin(tan(phi) / tan(i))     the engine, spec (II.10)
    form B   delta = asin(sin(phi) / sin(i))     the "spherical triangle" form

At i = 98.1 deg and phi = 45.3 deg they give -8.27 deg and +45.89 deg. The
derivation is in ``docs/physics/ii10_delta_hazard_policy.md``. These tests are its numerical
side, and they use no closed form for the thing they check:

* a plane is built from its normal and the site from its right ascension and
  latitude, and the site is in the plane exactly when ``r . n = 0``;
* the orbit is walked from the ascending node to the latitude of the site by
  bisection on the height above the equator, and the right ascension and the arc
  travelled are read off the point that is reached.

Both constructions say the same thing: form A is the right-ascension difference
between the site meridian and the ascending node, which is what (II.9) adds to
Omega, and form B is the argument of latitude, the arc along the orbit from the
node to the site. Form B is a correct formula for a different quantity.

The last tests are the empirical side: the published launches of gate G1 under
each form. Nothing in the engine is changed by this file.
"""

from __future__ import annotations

import importlib.util
import math
from pathlib import Path

import pytest

from backend.engine import window

DEG = math.pi / 180.0

# Inclinations and site latitudes that cover prograde, near polar and retrograde
# planes, and the sites of the gate (Kourou, Vandenberg, Canso, Plesetsk).
INCLINATIONS = (51.6, 63.4, 87.9, 97.05, 98.1, 98.74, 120.0)
LATITUDES = (5.2392, 28.5, 34.6327, 45.3, 62.887)
NODES = (0.0, 37.0, 211.5, 359.0)


def form_a(i_deg: float, lat_deg: float) -> float:
    return math.degrees(math.asin(math.tan(lat_deg * DEG) / math.tan(i_deg * DEG)))


def form_b(i_deg: float, lat_deg: float) -> float:
    return math.degrees(math.asin(math.sin(lat_deg * DEG) / math.sin(i_deg * DEG)))


def reachable(i_deg: float, lat_deg: float) -> bool:
    """A plane passes over a latitude only if that latitude is below its highest one."""
    return abs(lat_deg) < min(i_deg, 180.0 - i_deg) - 1.0e-9


CASES = [(i, lat) for i in INCLINATIONS for lat in LATITUDES if reachable(i, lat)]


def plane_normal(raan_deg: float, i_deg: float) -> tuple[float, float, float]:
    """Unit normal of the orbit plane, along the angular momentum."""
    raan, inc = raan_deg * DEG, i_deg * DEG
    return (math.sin(inc) * math.sin(raan), -math.sin(inc) * math.cos(raan), math.cos(inc))


def site_unit(ra_deg: float, lat_deg: float) -> tuple[float, float, float]:
    """Unit vector of a point at right ascension ``ra`` and latitude ``lat``."""
    ra, lat = ra_deg * DEG, lat_deg * DEG
    return (math.cos(lat) * math.cos(ra), math.cos(lat) * math.sin(ra), math.sin(lat))


def dot(a: tuple[float, float, float], b: tuple[float, float, float]) -> float:
    return sum(x * y for x, y in zip(a, b))


def walk_to_latitude(i_deg: float, lat_deg: float) -> tuple[float, float]:
    """Walk the orbit from the ascending node up to a latitude. No inverse formula.

    In the frame whose x axis points at the ascending node, the point at argument
    of latitude u is (cos u, cos i sin u, sin i sin u). Its height sin i sin u rises
    from the node to the top of the orbit, so the latitude is found by bisection.
    Returns the right ascension of that point measured from the node, and u.
    """
    inc = i_deg * DEG
    low, high = 0.0, 90.0
    for _ in range(200):
        middle = 0.5 * (low + high)
        if math.sin(inc) * math.sin(middle * DEG) < math.sin(lat_deg * DEG):
            low = middle
        else:
            high = middle
    u = 0.5 * (low + high)
    ra_from_node = math.degrees(math.atan2(math.cos(inc) * math.sin(u * DEG), math.cos(u * DEG)))
    return ra_from_node, u


# The geometry -------------------------------------------------------------------------------------------------

@pytest.mark.parametrize("i_deg, lat_deg", CASES)
def test_form_a_puts_the_site_in_the_plane_on_both_branches(i_deg, lat_deg):
    """r . n = 0 with RA_site = Omega + delta, and with RA_site = Omega + 180 - delta."""
    delta = form_a(i_deg, lat_deg)
    for raan in NODES:
        normal = plane_normal(raan, i_deg)
        assert abs(dot(site_unit(raan + delta, lat_deg), normal)) < 1.0e-12
        assert abs(dot(site_unit(raan + 180.0 - delta, lat_deg), normal)) < 1.0e-12


@pytest.mark.parametrize("i_deg, lat_deg", CASES)
def test_form_b_leaves_the_site_out_of_the_plane(i_deg, lat_deg):
    """Used as the offset of (II.9), form B puts the site meridian in the wrong place."""
    delta = form_b(i_deg, lat_deg)
    for raan in NODES:
        miss = abs(dot(site_unit(raan + delta, lat_deg), plane_normal(raan, i_deg)))
        assert miss > 1.0e-3, f"i {i_deg}, latitude {lat_deg}: the site would be in the plane"


def test_at_canso_form_b_misses_the_plane_by_37_degrees():
    """Hand computation for i = 98.1 deg, phi = 45.3 deg, delta = +45.8865 deg.

    r . n = -cos(phi) sin(i) sin(delta) + sin(phi) cos(i)
          = -0.703395 * 0.990024 * 0.717962 + 0.710799 * (-0.140901) = -0.6001
    The angle between the site vector and the plane is asin(0.6001) = 36.88 deg.
    """
    miss = dot(site_unit(form_b(98.1, 45.3), 45.3), plane_normal(0.0, 98.1))

    assert miss == pytest.approx(-0.6001, abs=2.0e-4)
    assert math.degrees(math.asin(abs(miss))) == pytest.approx(36.88, abs=0.01)


@pytest.mark.parametrize("i_deg, lat_deg", CASES)
def test_walking_the_orbit_gives_form_a_as_right_ascension_and_form_b_as_arc(i_deg, lat_deg):
    """The construction that uses neither formula names both quantities."""
    ra_from_node, argument_of_latitude = walk_to_latitude(i_deg, lat_deg)

    assert ra_from_node == pytest.approx(form_a(i_deg, lat_deg), abs=1.0e-9)
    assert argument_of_latitude == pytest.approx(form_b(i_deg, lat_deg), abs=1.0e-9)


@pytest.mark.parametrize("i_deg, lat_deg", CASES)
def test_form_b_is_the_angle_between_the_node_and_the_site(i_deg, lat_deg):
    """With the site in the plane, the arc from the node to it is asin(sin phi / sin i)."""
    raan = 37.0
    site = site_unit(raan + form_a(i_deg, lat_deg), lat_deg)
    node = (math.cos(raan * DEG), math.sin(raan * DEG), 0.0)

    arc = math.degrees(math.acos(max(-1.0, min(1.0, dot(site, node)))))

    assert arc == pytest.approx(form_b(i_deg, lat_deg), abs=1.0e-9)


@pytest.mark.parametrize("i_deg, lat_deg", CASES)
def test_the_two_forms_are_two_sides_of_one_right_spherical_triangle(i_deg, lat_deg):
    """Napier: tan(delta_A) = cos(i) tan(u), with u the arc of form B."""
    left = math.tan(form_a(i_deg, lat_deg) * DEG)
    right = math.cos(i_deg * DEG) * math.tan(form_b(i_deg, lat_deg) * DEG)

    assert left == pytest.approx(right, abs=1.0e-12)


def test_the_forms_coincide_only_for_a_site_on_the_equator():
    for i_deg in INCLINATIONS:
        assert form_a(i_deg, 0.0) == pytest.approx(0.0, abs=1e-12)
        assert form_b(i_deg, 0.0) == pytest.approx(0.0, abs=1e-12)
    assert form_a(90.0 - 1.0e-9, 45.3) == pytest.approx(0.0, abs=1.0e-6), "polar plane: the meridian is the plane"
    assert form_b(90.0, 45.3) == pytest.approx(45.3, abs=1.0e-9), "polar plane: the arc is the latitude"


def test_a_retrograde_plane_puts_the_site_meridian_west_of_the_node():
    """Going north on a retrograde orbit the right ascension falls, so delta is negative.

    Walked, not derived: at i = 98.1 deg the point at the latitude of Canso lies
    8.27 deg west of the ascending node, after 45.89 deg of arc.
    """
    ra_from_node, argument_of_latitude = walk_to_latitude(98.1, 45.3)

    assert ra_from_node == pytest.approx(-8.2689, abs=1.0e-4)
    assert argument_of_latitude == pytest.approx(45.8865, abs=1.0e-4)
    assert walk_to_latitude(51.6, 28.5)[0] > 0.0, "a prograde plane puts it east of the node"


# The engine --------------------------------------------------------------------------------------------------

@pytest.mark.parametrize("i_deg, lat_deg", CASES)
def test_the_engine_uses_the_right_ascension_form(i_deg, lat_deg):
    assert window.site_node_offset_deg(i_deg, lat_deg) == pytest.approx(form_a(i_deg, lat_deg), abs=1.0e-12)
    assert window.descending_offset_deg(i_deg, lat_deg) == pytest.approx(180.0 - form_a(i_deg, lat_deg), abs=1.0e-12)


def test_the_engine_offset_at_canso_for_the_two_spec_examples():
    """Direct evaluation at phi_s = 45.3 deg. The spec text quotes 2.37 and -8.16 deg.

    asin(tan 45.3 / tan 87.9) = asin(1.010527 / 27.2715) = 2.1235 deg
    asin(tan 45.3 / tan 98.1) = asin(1.010527 / -7.02637) = -8.2689 deg
    The quoted -8.16 deg is the value at i = 98.0 deg (-8.1648 deg).
    """
    assert window.site_node_offset_deg(87.9, 45.3) == pytest.approx(2.1235, abs=1.0e-4)
    assert window.site_node_offset_deg(98.1, 45.3) == pytest.approx(-8.2689, abs=1.0e-4)
    assert window.site_node_offset_deg(98.0, 45.3) == pytest.approx(-8.1648, abs=1.0e-4)


# The published launches of gate G1 under each form -------------------------------------------------------------

def _gate():
    """The gate module, loaded by path: its helpers are the ones gate G1 itself runs."""
    path = Path(__file__).with_name("test_reproduce_published_windows.py")
    spec = importlib.util.spec_from_file_location("g1_gate_for_ii10", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def gate_residuals(gate) -> dict[str, float]:
    """Residual of each anchor in minutes, the profile bias subtracted where the gate does."""
    residuals = {}
    for case in gate.CASES:
        residual = gate._window_centre_minutes(case)
        if case.get("ascent_profile"):
            residual -= gate._profile_bias(case)
        residuals[case["id"]] = residual
    return residuals


# Gate residuals recorded for W5a after the replay on main, minutes.
RECORDED = {
    "sentinel_1c_2024_12_05": -1.545,
    "earthcare_2024_05_28": -0.547,
    "sentinel_5p_2017_10_13": 0.914,
    "sentinel_3a_2016_02_16": 0.133,
    "sentinel_3b_2018_04_25": -0.133,
    "sentinel_3c_2026_09_15": 2.257,
}


def test_every_published_launch_is_reproduced_under_form_a():
    gate = _gate()
    residuals = gate_residuals(gate)

    assert set(residuals) == set(RECORDED)
    for name, expected in RECORDED.items():
        assert residuals[name] == pytest.approx(expected, abs=1.0e-3), name
        assert abs(residuals[name]) <= gate.TOLERANCE_MIN


def test_no_published_launch_is_reproduced_under_form_b(monkeypatch):
    """The decisive check. With the arc in place of the right ascension every anchor fails.

    The offset moves by form B minus form A, between 6 deg at Kourou and 81 deg at
    Plesetsk, and the site sweeps a degree in about four minutes, so the nearest
    crossing moves by tens of minutes to hours.
    """
    gate = _gate()

    def offset_of_form_b(i_t_deg: float, lat_deg: float) -> float:
        return form_b(i_t_deg, lat_deg)

    monkeypatch.setattr(gate.window, "site_node_offset_deg", offset_of_form_b)
    residuals = gate_residuals(gate)

    assert set(residuals) == set(RECORDED)
    for name, residual in residuals.items():
        assert abs(residual) > gate.TOLERANCE_MIN, f"{name}: {residual:+.3f} min would pass the gate"
    assert min(abs(value) for value in residuals.values()) > 4 * gate.TOLERANCE_MIN


# The hazard screen's southbound rule on sites other than Canso --------------------------------------------------
#
# These two tests record a finding of issue W5b and change nothing. They pin what the
# screen does today so that the verdict in docs/physics/ii10_delta_hazard_policy.md rests on a run,
# and they will need rewriting when a per-site policy replaces the constant.

NORTHBOUND_ANCHORS = {
    "sentinel_1c_2024_12_05": "kourou_ela1",
    "sentinel_5p_2017_10_13": "plesetsk_133",
    "sentinel_3a_2016_02_16": "plesetsk_133",
    "sentinel_3b_2018_04_25": "plesetsk_133",
    "sentinel_3c_2026_09_15": "kourou_ela1",
}


def test_the_crossing_that_reproduces_a_launch_from_kourou_or_plesetsk_is_northbound_and_refused():
    """Five of the six published launches flew north, and the screen refuses that crossing.

    The row of compute_windows nearest the published instant is the launch that was
    flown. From Kourou and from Plesetsk it has an azimuth between 340 and 352 deg.
    The screen marks it ``hazard: fail``. From Vandenberg, which does fly south, the
    nearest row passes. The refusal is now the work of the placeholder corridors of
    the gate sites alone (90 to 260 deg, ASSUMPTION); it stands until a published
    corridor replaces them.
    """
    from backend.engine import compute_windows, frames

    gate = _gate()
    for case in gate.CASES:
        response = compute_windows(gate._gate_request(case))
        published = frames.julian_date_from_iso(case["published_liftoff_utc"])
        nearest = min(
            response["windows"],
            key=lambda row: abs(frames.julian_date_from_iso(row["t_liftoff_utc"]) - published),
        )
        if case["id"] in NORTHBOUND_ANCHORS:
            assert gate.site_for_gate(case) == NORTHBOUND_ANCHORS[case["id"]]
            assert 340.0 < nearest["azimuth_deg"] < 352.0, case["id"]
            assert nearest["screens"]["hazard"] == "fail", case["id"]
            assert nearest["constraint_fired"] == "hazard_area", case["id"]
        else:
            assert case["id"] == "earthcare_2024_05_28"
            assert 180.0 < nearest["azimuth_deg"] < 200.0
            assert nearest["screens"]["hazard"] == "pass"


def test_the_refusal_at_another_site_no_longer_cites_the_canso_assessment():
    """The southbound statement is Canso data now; another site is refused by its own corridor.

    Before the per-site policy, this test pinned the reason "Canso environmental
    assessment" on a refusal at Kourou and at Plesetsk. The refusal remains, because
    the corridors of the gate sites are placeholders (90 to 260 deg, ASSUMPTION), and
    the reason now says exactly that.
    """
    from backend.engine import provenance, screens

    for site, azimuth in (("kourou_ela1", 351.79), ("plesetsk_133", 340.52)):
        corridor = provenance.load_json(f"sites/{site}.json")["corridor"]
        verdict = screens.hazard_screen(azimuth, corridor, {})

        assert verdict.hazard == "fail"
        assert "Canso" not in verdict.reason, site
        assert "[90, 260] deg (bounds flagged ASSUMPTION)" in verdict.reason, site
        assert "NOT A PUBLISHED CORRIDOR" in corridor["source"], site

    canso = provenance.load_json("site_canso.json")["corridor"]
    assert canso["direction_policy"]["admitted_branch"] == "southbound"
    assert 90.0 <= canso["A_min_deg"] and canso["A_max_deg"] <= 270.0
