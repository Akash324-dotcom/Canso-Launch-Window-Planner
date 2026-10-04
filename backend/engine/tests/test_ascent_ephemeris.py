"""The ephemeris of a window row is the ascent of that row.

Browser walk defect B1: the page asks for the track from ``t_liftoff_utc`` to
``t_injection_utc`` of the selected row and was answered with a segment of the
orbit at orbit altitude, 16,812 km from the pad at the liftoff instant.
``backend.engine.ephemeris`` answers with the direct ascent from the site that lifts
off at ``start``: on the pad at liftoff, in the plane of (II.14) at orbit altitude
at injection, and on that orbit afterwards.

Every boundary value asserted here is a statement the engine already makes: the pad
of the site file, the plane of (II.14), the rotating-frame azimuth of spec II.6, the
time to injection of the vehicle profile and the circular rate of the target orbit.
The path between them is a flagged ASSUMPTION and the answer says so.
"""

from __future__ import annotations

import datetime as dt
import math

import pytest

from backend import engine
from backend.engine import compute_windows, frames, j2, provenance, reachability, window

SITE = provenance.load_json("site_canso.json")
PROFILE = provenance.load_json("vehicles/cyclone4m.json")
LAT = SITE["latitude_deg"]
LON = SITE["longitude_deg"]
T_INJ = PROFILE["t_to_inj_s"]
LIFTOFF = "2026-10-05T02:55:33Z"
I_SSO, H_SSO = 98.1, 674.0


def at(offset_s: float) -> str:
    moment = dt.datetime(2026, 10, 5, 2, 55, 33, tzinfo=dt.timezone.utc) + dt.timedelta(seconds=offset_s)
    return moment.strftime("%Y-%m-%dT%H:%M:%SZ")


def track(end_s: float, step_s: float, **overrides):
    arguments = {
        "orbit_id": "sso981",
        "start": LIFTOFF,
        "end": at(end_s),
        "step_s": step_s,
        "i_t_deg": I_SSO,
        "h_t_km": H_SSO,
    }
    arguments.update(overrides)
    return engine.ephemeris(**arguments)


def great_circle_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    p1, p2, dl = math.radians(lat1), math.radians(lat2), math.radians(lon2 - lon1)
    cosine = math.sin(p1) * math.sin(p2) + math.cos(p1) * math.cos(p2) * math.cos(dl)
    return provenance.R_E / 1000.0 * math.acos(max(-1.0, min(1.0, cosine)))


def bearing_deg(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    p1, p2, dl = math.radians(lat1), math.radians(lat2), math.radians(lon2 - lon1)
    east = math.sin(dl) * math.cos(p2)
    north = math.cos(p1) * math.sin(p2) - math.sin(p1) * math.cos(p2) * math.cos(dl)
    return math.degrees(math.atan2(east, north)) % 360.0


def out_of_plane_deg(point: dict, raan_deg: float, i_deg: float) -> float:
    """Angle between the inertial position of a sample and a plane (raan, i)."""
    jd = frames.julian_date_from_iso(point["t_utc"])
    right_ascension = math.radians(point["lon_deg"] + frames.gmst_degrees(jd))
    declination = math.radians(point["lat_deg"])
    position = (
        math.cos(declination) * math.cos(right_ascension),
        math.cos(declination) * math.sin(right_ascension),
        math.sin(declination),
    )
    raan, inclination = math.radians(raan_deg), math.radians(i_deg)
    normal = (
        math.sin(inclination) * math.sin(raan),
        -math.sin(inclination) * math.cos(raan),
        math.cos(inclination),
    )
    return math.degrees(math.asin(sum(a * b for a, b in zip(position, normal))))


def achievable_raan_deg(liftoff_iso: str, i_deg: float) -> float:
    """(II.14) on the descending crossing: GMST(t_l) + lambda_s - (180 - delta)."""
    jd = frames.julian_date_from_iso(liftoff_iso)
    return (frames.gmst_degrees(jd) + LON - window.descending_offset_deg(i_deg, LAT)) % 360.0


# --- The seam ------------------------------------------------------------------


def test_the_engine_exports_the_ephemeris_the_api_seam_calls():
    answer = track(T_INJ, 60.0)

    assert answer["orbit_id"] == "sso981"
    assert answer["frame"] == "ECEF"
    for point in answer["points"]:
        assert set(point) == {"t_utc", "lat_deg", "lon_deg", "alt_km"}


# --- Liftoff -------------------------------------------------------------------


def test_the_track_starts_on_the_pad_at_the_liftoff_instant():
    first = track(T_INJ, 60.0)["points"][0]

    assert first["t_utc"] == LIFTOFF
    assert first["lat_deg"] == pytest.approx(LAT, abs=1.0e-6)
    assert first["lon_deg"] == pytest.approx(LON, abs=1.0e-6)
    assert first["alt_km"] == pytest.approx(SITE["altitude_m"] / 1000.0, abs=1.0e-9)


def test_the_vehicle_is_at_rest_on_the_pad_at_liftoff():
    """One second after liftoff it has moved metres, not the 327 m a point fixed in space would."""
    points = track(2.0, 1.0)["points"]

    assert great_circle_km(LAT, LON, points[1]["lat_deg"], points[1]["lon_deg"]) < 0.02
    assert points[1]["alt_km"] < 0.01


def test_the_track_leaves_the_pad_on_the_rotating_frame_azimuth_of_the_row():
    """Spec II.6: the ground-relative launch azimuth is the row's azimuth_compass_deg.

    The heading is a boundary value at liftoff, so it is read five seconds in, 150 m
    from the pad, where the six-decimal rounding of the samples is 0.04 deg of bearing
    and the track has turned 0.11 deg from its first heading.
    """
    beta = reachability.launch_azimuth_deg(I_SSO, LAT)
    compass = frames.launch_azimuth_compass(beta, LAT)
    answer = track(5.0, 5.0)
    early = answer["points"][1]

    assert answer["model"]["launch_azimuth_compass_deg"] == pytest.approx(compass, abs=1.0e-9)
    assert bearing_deg(LAT, LON, early["lat_deg"], early["lon_deg"]) == pytest.approx(compass, abs=0.2)
    assert early["lat_deg"] < LAT, "Canso admits the southbound branch only"


# --- Injection -----------------------------------------------------------------


def test_the_track_reaches_orbit_altitude_in_the_plane_of_ii14_at_injection():
    last = track(T_INJ, 60.0)["points"][-1]

    assert last["t_utc"] == at(T_INJ)
    assert last["alt_km"] == pytest.approx(H_SSO, abs=1.0e-6)
    assert out_of_plane_deg(last, achievable_raan_deg(LIFTOFF, I_SSO), I_SSO) == pytest.approx(
        0.0, abs=2.0e-3
    )


def test_the_closing_instant_is_sampled_when_the_step_does_not_land_on_it():
    """The page asks at 300 s steps over a 540 s ascent and must still see the injection point."""
    points = track(T_INJ, 300.0)["points"]

    assert [point["t_utc"] for point in points] == [LIFTOFF, at(300.0), at(T_INJ)]


def test_the_altitude_rises_monotonically_and_levels_off_at_injection():
    points = track(T_INJ, 10.0)["points"]
    altitudes = [point["alt_km"] for point in points]

    assert altitudes == sorted(altitudes)
    assert max(altitudes) == pytest.approx(H_SSO, abs=1.0e-6)
    climbs = [upper - lower for lower, upper in zip(altitudes, altitudes[1:])]
    assert climbs[-1] < 0.05 * max(climbs), "the climb rate falls to zero at a circular injection"
    assert climbs[0] < 0.05 * max(climbs), "and starts from zero on the pad"


def test_the_ground_speed_never_exceeds_the_ground_speed_of_the_orbit():
    points = track(T_INJ + 60.0, 10.0)["points"]
    hops = [
        great_circle_km(a["lat_deg"], a["lon_deg"], b["lat_deg"], b["lon_deg"])
        for a, b in zip(points, points[1:])
    ]
    orbit_hop = hops[-1]

    assert max(hops) <= orbit_hop * 1.02
    assert hops[0] < orbit_hop * 0.05


# --- After injection -----------------------------------------------------------


def test_after_injection_the_track_is_the_circular_orbit_in_the_drifting_plane():
    points = track(T_INJ + 3600.0, 60.0)["points"]
    after = [point for point in points if point["t_utc"] > at(T_INJ)]
    raan = achievable_raan_deg(LIFTOFF, I_SSO)
    rate = j2.nodal_rate_deg_per_day(H_SSO, I_SSO)

    assert len(after) == 60
    for point in after:
        assert point["alt_km"] == pytest.approx(H_SSO, abs=1.0e-6)
        elapsed_days = (
            frames.julian_date_from_iso(point["t_utc"]) - frames.julian_date_from_iso(at(T_INJ))
        )
        assert out_of_plane_deg(point, raan + rate * elapsed_days, I_SSO) == pytest.approx(
            0.0, abs=2.0e-3
        )


def test_the_handover_to_the_orbit_is_continuous_in_position_and_speed():
    points = track(T_INJ + 2.0, 1.0)["points"]
    before = great_circle_km(points[-4]["lat_deg"], points[-4]["lon_deg"], points[-3]["lat_deg"], points[-3]["lon_deg"])
    after = great_circle_km(points[-2]["lat_deg"], points[-2]["lon_deg"], points[-1]["lat_deg"], points[-1]["lon_deg"])

    assert before == pytest.approx(after, rel=0.02)


# --- The row of a real window --------------------------------------------------


def test_the_ephemeris_of_a_window_row_ends_in_the_plane_the_row_reports():
    request = {
        "site": "canso",
        "target": {"type": "SSO", "h_t_km": H_SSO, "i_t_deg": I_SSO, "ltan_hours": "10:30"},
        "date_range": {"start": "2026-10-05", "end": "2026-10-06"},
        "vehicle_profile_id": "cyclone4m",
    }
    rows = [row for row in compute_windows(request)["windows"] if row["screens"]["hazard"] == "pass"]
    assert rows
    for row in rows:
        answer = engine.ephemeris(
            orbit_id="sso981",
            start=row["t_liftoff_utc"],
            end=row["t_injection_utc"],
            step_s=300.0,
            i_t_deg=I_SSO,
            h_t_km=H_SSO,
        )
        first, last = answer["points"][0], answer["points"][-1]

        assert (first["lat_deg"], first["lon_deg"], first["alt_km"]) == (
            pytest.approx(LAT, abs=1.0e-6),
            pytest.approx(LON, abs=1.0e-6),
            0.0,
        )
        assert last["t_utc"] == row["t_injection_utc"]
        assert last["alt_km"] == pytest.approx(H_SSO, abs=1.0e-6)
        # The plane the engine solves the row in is (II.14) at the row's liftoff. The
        # row's instants are rounded to the second, which is 0.004 deg of sweep.
        assert out_of_plane_deg(
            last, achievable_raan_deg(row["t_liftoff_utc"], I_SSO), I_SSO
        ) == pytest.approx(0.0, abs=0.005)
        # raan_deg of the row is the plane of the window search, which the engine holds
        # to the solved plane within the tolerance of the target class.
        tolerance = SITE["target_classes"]["SSO"]["raan_tolerance_deg"]
        assert abs(out_of_plane_deg(last, row["raan_deg"], I_SSO)) < tolerance


# --- Refusals and the branch ---------------------------------------------------


def test_an_inclination_the_site_cannot_reach_has_no_ascent():
    with pytest.raises(ValueError, match="reach"):
        track(T_INJ, 60.0, orbit_id="leo45", i_t_deg=45.1, h_t_km=400.0)


def test_a_caller_may_name_the_crossing_and_the_default_is_the_one_the_site_admits():
    default = track(120.0, 120.0)
    north = track(120.0, 120.0, branch="ascending")

    assert default["model"]["branch"] == "descending"
    assert default["points"][1]["lat_deg"] < LAT
    assert north["model"]["branch"] == "ascending"
    assert north["points"][1]["lat_deg"] > LAT
    with pytest.raises(ValueError, match="branch"):
        track(120.0, 120.0, branch="sideways")


def test_an_unknown_site_or_vehicle_is_refused():
    with pytest.raises(ValueError):
        track(T_INJ, 60.0, site="nowhere")
    with pytest.raises(ValueError):
        track(T_INJ, 60.0, vehicle_profile_id="nothing")


def test_an_end_before_the_start_and_a_step_that_is_not_positive_are_refused():
    with pytest.raises(ValueError, match="end"):
        engine.ephemeris(
            orbit_id="sso981", start=at(60.0), end=LIFTOFF, step_s=60.0, i_t_deg=I_SSO, h_t_km=H_SSO
        )
    with pytest.raises(ValueError, match="step_s"):
        track(T_INJ, 0.0)


# --- What the answer says about itself ----------------------------------------


def test_the_answer_states_that_the_path_is_an_assumption_and_names_its_inputs():
    model = track(T_INJ, 60.0)["model"]

    assert model["flag"] == "ASSUMPTION"
    assert model["t_to_inj_s"] == T_INJ
    assert model["t_to_inj_flag"] == "ASSUMPTION"
    assert model["site"] == "canso"
    assert model["vehicle_profile_id"] == "cyclone4m"
    assert "not integrated" in model["statement"]
    assert model["downrange_at_injection_km"] == pytest.approx(
        great_circle_km(LAT, LON, *[track(T_INJ, T_INJ)["points"][-1][key] for key in ("lat_deg", "lon_deg")]),
        rel=0.02,
    )


def test_the_site_file_names_the_vehicle_the_ascent_is_drawn_for():
    assert SITE["vehicle_profile_id"] == "cyclone4m"
