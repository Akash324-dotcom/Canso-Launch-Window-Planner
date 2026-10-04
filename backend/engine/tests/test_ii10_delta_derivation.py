"""Which (II.10) closed form is `delta`? Spec II.10 derivation, decided by test.

An adversarial report claimed the site-to-node offset should be
``asin(sin(phi_s)/sin(i))`` rather than the shipped ``asin(tan(phi_s)/tan(i))``.
Both forms pass the shipped reachability check, so that check cannot tell them
apart, and the claim looked plausible enough to cost four published anchors.

This file settles it three ways, so that a future edit which swaps the form
fails here loudly:

  * GEOMETRY, from vectors. An orbit is built from (i, Omega) with no closed
    form involved; the argument of latitude is bisected until the
    ECI/ECEF/geodetic round trip puts the sub-satellite point at the geodetic
    site latitude; the right ascension is then read off the vector. Whichever
    closed form reproduces that number is the hour-angle offset of (II.9).

  * ALGEBRA, from the ground-track relations. sin(phi_s) = sin(i) sin(u) and
    tan(delta) = cos(i) tan(u) force sin(delta) = tan(phi_s)/tan(i). The sin
    form is the first relation inverted, so it returns u, the argument of
    latitude, an angle in the orbit plane rather than a right ascension.

  * GATE. Residuals of (II.9) at the published launch instants. The sin form
    misses every anchor by hours, which is the physical signature of putting an
    orbit-plane angle where a right-ascension difference belongs.

The conclusion and its derivations are recorded in docs/physics/ii10_delta.md.
"""

from __future__ import annotations

import json
import math
import pathlib

import pytest

from backend.engine import frames, j2, sso, window

DEG = math.pi / 180.0
RAD = 180.0 / math.pi

PUBLISHED = json.loads(
    (pathlib.Path(__file__).resolve().parents[1] / "data" / "published_windows.json").read_text()
)
CASES = PUBLISHED["cases"]
TOLERANCE_MIN = PUBLISHED["tolerance_minutes"]

# (inclination, site latitude) covering the gate anchors and the advertised
# Canso classes, including a prograde pair and a near-polar pair.
GEOMETRY_ROWS = [
    (98.1, 45.3),
    (98.18, 5.2392),
    (98.74, 62.887),
    (97.05, 34.6327),
    (98.62, 62.887),
    (98.6276, 62.887),
    (98.6, 5.2392),
    (87.9, 45.3),
    (69.4, 45.3),
    (70.0, 20.0),
    (100.0, 70.0),
]


def _offset_tan(i_deg: float, phi_s_deg: float) -> float:
    """The shipped (II.10) form."""
    return window.site_node_offset_deg(i_deg, phi_s_deg)


def _offset_sin(i_deg: float, phi_s_deg: float) -> float:
    """The proposed form: the argument of latitude, not the hour angle."""
    return math.degrees(math.asin(math.sin(phi_s_deg * DEG) / math.sin(i_deg * DEG)))


def _hour_angle_from_vectors(i_deg: float, phi_s_deg: float, raan_deg: float) -> float:
    """delta = RA of the sub-satellite point minus RAAN, from vectors alone."""
    i = i_deg * DEG
    radius_m = 6371.0e3 + 800.0e3

    def position(u: float) -> tuple[float, float, float]:
        return (
            radius_m * (math.cos(u) * math.cos(raan_deg * DEG)
                        - math.sin(u) * math.sin(raan_deg * DEG) * math.cos(i)),
            radius_m * (math.cos(u) * math.sin(raan_deg * DEG)
                        + math.sin(u) * math.cos(raan_deg * DEG) * math.cos(i)),
            radius_m * math.sin(u) * math.sin(i),
        )

    def geodetic_latitude(u: float) -> float:
        lat, _, _ = frames.ecef_to_geodetic(*frames.eci_to_ecef(position(u), 2451545.0))
        return lat

    lo, hi = -math.pi / 2.0, math.pi / 2.0
    for _ in range(200):
        mid = 0.5 * (lo + hi)
        if geodetic_latitude(mid) < phi_s_deg:
            lo = mid
        else:
            hi = mid
    u = 0.5 * (lo + hi)
    assert geodetic_latitude(u) == pytest.approx(phi_s_deg, abs=1.0e-9), (
        "the point is not over the site, so this row proves nothing"
    )
    x, y, _ = position(u)
    ra_point = math.atan2(y, x) * RAD
    return (ra_point - raan_deg + 180.0) % 360.0 - 180.0


def _wrap(x: float) -> float:
    return (x + 180.0) % 360.0 - 180.0


# --- Geometry ----------------------------------------------------------------


@pytest.mark.parametrize("i_deg,phi_s_deg", GEOMETRY_ROWS, ids=lambda v: str(v))
def test_the_tan_form_is_the_hour_angle_offset_from_the_ground_track(i_deg, phi_s_deg):
    """delta from (II.9) is RA_site - RAAN, so the tan form must be the vector value.

    The tolerance absorbs the geodetic/geocentric flattening term the spherical
    identity omits. It is the flattening correction, not slack: the proposed sin
    form misses by degrees to hundreds of degrees on these same rows.
    """
    vector = _hour_angle_from_vectors(i_deg, phi_s_deg, 213.7)
    shipped = _offset_tan(i_deg, phi_s_deg)
    assert abs(_wrap(vector - shipped)) < 0.25, (
        f"i={i_deg} phi_s={phi_s_deg}: vector hour angle {vector:.5f} deg disagrees with "
        f"the shipped (II.10) form {shipped:.5f} deg"
    )


@pytest.mark.parametrize("i_deg,phi_s_deg", GEOMETRY_ROWS, ids=lambda v: str(v))
def test_the_sin_form_is_not_the_hour_angle_offset(i_deg, phi_s_deg):
    """It returns the argument of latitude, so it must NOT match the vector value."""
    vector = _hour_angle_from_vectors(i_deg, phi_s_deg, 213.7)
    proposed = _offset_sin(i_deg, phi_s_deg)
    assert abs(_wrap(vector - proposed)) > 5.0, (
        f"i={i_deg} phi_s={phi_s_deg}: the sin form came within 5 deg of the hour-angle "
        "offset, which would mean the two quantities coincide and this file is wrong"
    )


# --- Algebra -----------------------------------------------------------------


@pytest.mark.parametrize("i_deg,phi_s_deg", GEOMETRY_ROWS, ids=lambda v: str(v))
def test_tan_delta_and_argument_of_latitude_are_linked_by_cos_i(i_deg, phi_s_deg):
    """sin(phi_s) = sin(i) sin(u) and tan(delta) = cos(i) tan(u) force the tan form."""
    u = _offset_sin(i_deg, phi_s_deg)
    chained = math.degrees(
        math.atan(math.cos(i_deg * DEG) * math.tan(u * DEG))
    )
    assert chained == pytest.approx(_offset_tan(i_deg, phi_s_deg), abs=1.0e-9), (
        "the ground-track relations do not reproduce (II.10); the derivation is wrong"
    )


@pytest.mark.parametrize("i_deg,phi_s_deg", GEOMETRY_ROWS, ids=lambda v: str(v))
def test_the_two_forms_share_one_reachability_predicate(i_deg, phi_s_deg):
    """Why the confusion survived: both return a value exactly when i >= phi_s.

    |tan phi_s/tan i| <= 1 and |sin phi_s/sin i| <= 1 are the same statement, so
    a reachability test cannot distinguish the two forms. This is recorded so the
    next reader does not treat that agreement as corroboration.
    """
    tan_ratio = abs(math.tan(phi_s_deg * DEG) / math.tan(i_deg * DEG))
    sin_ratio = abs(math.sin(phi_s_deg * DEG) / math.sin(i_deg * DEG))
    assert (tan_ratio <= 1.0) == (sin_ratio <= 1.0)
    assert (tan_ratio <= 1.0) == (i_deg >= phi_s_deg)


def test_both_forms_agree_on_the_unreachable_case():
    """i < phi_s: both refuse, so the guard is not what tells them apart."""
    for i_deg, phi_s_deg in [(45.1, 45.3), (30.0, 45.3), (87.0, 88.0)]:
        assert window.site_node_offset_deg(i_deg, phi_s_deg) is None
        assert abs(math.tan(phi_s_deg * DEG) / math.tan(i_deg * DEG)) > 1.0
        assert abs(math.sin(phi_s_deg * DEG) / math.sin(i_deg * DEG)) > 1.0


# --- Gate --------------------------------------------------------------------


def _residuals_minutes(case: dict, offset_deg: float) -> dict[str, float]:
    """(II.9) residual in minutes at the published instant, per site crossing."""
    published_jd = frames.julian_date_from_iso(case["published_liftoff_utc"])
    nodal_rate = j2.nodal_rate_deg_per_day(case["altitude_km"], case["inclination_deg"])
    sweep_deg_per_day = window.sweep_rate_deg_per_hour(nodal_rate) * 24.0
    residuals = {}
    for branch, offset in (("ascending", offset_deg), ("descending", 180.0 - offset_deg)):

        def residual(jd: float, offset: float = offset) -> float:
            raan = sso.raan_for_ltan_deg(jd, case["ltan_hours"], case["ltan_branch"])
            return frames.gmst_degrees_unwrapped(jd) + case["longitude_deg"] - offset - raan

        half_period = 180.0 / sweep_deg_per_day
        lo, hi = published_jd - half_period, published_jd + half_period
        level = 360.0 * round(residual(published_jd) / 360.0)
        assert residual(lo) - level < 0.0 < residual(hi) - level, "root must be bracketed"
        for _ in range(200):
            mid = 0.5 * (lo + hi)
            if residual(mid) - level < 0.0:
                lo = mid
            else:
                hi = mid
        residuals[branch] = (0.5 * (lo + hi) - published_jd) * 1440.0
    return residuals


def _corrected(case: dict, offset_deg: float) -> float:
    residuals = _residuals_minutes(case, offset_deg)
    return min(residuals.values(), key=abs) - case.get("profile_bias_min", 0.0)


@pytest.mark.parametrize("case", CASES, ids=[case["id"] for case in CASES])
def test_the_shipped_tan_form_keeps_every_published_anchor_inside_the_gate(case):
    residual = _corrected(case, _offset_tan(case["inclination_deg"], case["latitude_deg"]))
    assert abs(residual) <= TOLERANCE_MIN, (
        f"{case['id']}: shipped (II.10) form is {residual:+.3f} min from the published instant"
    )


@pytest.mark.parametrize("case", CASES, ids=[case["id"] for case in CASES])
def test_the_proposed_sin_form_would_break_every_published_anchor(case):
    """The decisive evidence, asserted as a test so the swap cannot land quietly."""
    residual = _corrected(case, _offset_sin(case["inclination_deg"], case["latitude_deg"]))
    assert abs(residual) > TOLERANCE_MIN, (
        f"{case['id']}: the sin form lands within the gate at {residual:+.3f} min, so this "
        "file's conclusion is wrong and must be re-derived"
    )


def test_the_sin_form_miss_is_latitude_dependent_so_no_constant_offset_recovers_it():
    """A refit constant cannot rescue the sin form; its error grows with latitude."""
    offsets = []
    for case in CASES:
        difference = _offset_sin(case["inclination_deg"], case["latitude_deg"]) - _offset_tan(
            case["inclination_deg"], case["latitude_deg"]
        )
        offsets.append((case["latitude_deg"], difference))
    at_low_lat = min(difference for lat, difference in offsets if lat < 10.0)
    at_high_lat = max(difference for lat, difference in offsets if lat > 60.0)
    assert at_high_lat - at_low_lat > 50.0, (
        "the sin-form error is nearly constant in latitude; a single offset might "
        "recover it and the rejection would be premature"
    )


# --- Hazard screen -----------------------------------------------------------


def test_the_hazard_verdict_follows_the_site_corridor_at_every_configured_site():
    """The hard-coded southbound rule is gone, so the screen judges a site by its own file.

    Earlier this test pinned that rule as redundant at every configured site, and the
    next one pinned the defect that it refused a northbound corridor by citing Canso. The
    rule was removed (docs/physics/ii10_delta_hazard_policy.md section 9, and
    test_hazard_direction_policy.py), so both now pin the corrected behaviour: the
    verdict for a flown azimuth agrees with membership of the site's corridor, and a
    direction policy applies only where the site file states one.
    """
    from backend.engine import reachability, screens, target

    for site_name in ("canso", "kourou_ela1", "plesetsk_133", "vandenberg_slc4e"):
        site = target.load_site(site_name)
        corridor = site["corridor"]
        azimuth = reachability.launch_azimuth_deg(98.6, float(site["latitude_deg"]))
        verdict = screens.hazard_screen(azimuth, corridor, {})
        assert (verdict.hazard == "pass") == reachability.azimuth_in_corridor(azimuth, corridor), (
            f"{site_name}: the hazard verdict must follow the site corridor"
        )


def test_a_northbound_corridor_is_admitted_when_the_site_states_no_direction_policy():
    """A site may declare a northbound corridor and is no longer refused for it.

    The Rockot/Briz-KM SSO profile recorded in published_windows.json flies a
    341.5 deg corridor out of Plesetsk, which is exactly this shape. The refusal that
    named Canso's assessment while screening a different site was the defect; it is
    removed, and the verdict now names only the corridor.
    """
    from backend.engine import screens

    northbound = {"A_min_deg": 330.0, "A_max_deg": 350.0, "branch": "northbound"}
    verdict = screens.hazard_screen(341.5, northbound, {})
    assert verdict.hazard == "pass"
    assert "Canso" not in verdict.reason
