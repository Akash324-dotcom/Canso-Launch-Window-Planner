"""Request values the engine must refuse or complete, found by the browser walk against the live service.

* A corridor override with one bound crashed the request (HTTP 500 at the service): the
  frozen request schema allows either bound alone, so the missing one is the site's.
* ``ltan_hours`` of "25:99" was accepted and answered. It is not a time of day.
* ``raan_tolerance_deg`` of 0 and below was accepted and gave windows of zero and of
  negative width.
"""

from __future__ import annotations

import pytest

from backend.engine import compute_windows, target

BASE = {
    "target": {"type": "SSO", "ltan_hours": "10:30"},
    "site": "canso",
    "date_range": {"start": "2026-10-04", "end": "2026-10-05"},
    "vehicle_profile_id": "cyclone4m",
    "include_weather": False,
}

SITE_CORRIDOR = target.load_site("canso")["corridor"]


def southbound_rows(response: dict) -> list[dict]:
    return [row for row in response["windows"] if 90.0 <= row["azimuth_deg"] <= 270.0]


def test_the_site_corridor_admits_the_southbound_sso_azimuth():
    """The baseline the two tests below move: 191.53 deg lies inside the site corridor."""
    response = compute_windows(BASE)
    rows = southbound_rows(response)

    assert SITE_CORRIDOR["A_min_deg"] < rows[0]["azimuth_deg"] < SITE_CORRIDOR["A_max_deg"]
    assert response["reachable"] is True
    assert all(row["screens"]["hazard"] == "pass" for row in rows)


def test_an_override_of_the_lower_bound_alone_keeps_the_upper_bound_of_the_site():
    """A_min 120 with the site's A_max: 191.53 deg is still inside, so nothing changes."""
    response = compute_windows({**BASE, "corridor": {"A_min_deg": 120.0}})

    assert response["reachable"] is True
    assert all(row["screens"]["hazard"] == "pass" for row in southbound_rows(response))


def test_an_override_of_the_upper_bound_alone_keeps_the_lower_bound_of_the_site():
    """A_max 150 with the site's A_min: 191.53 deg is outside, so the target is corridor-blocked."""
    response = compute_windows({**BASE, "corridor": {"A_max_deg": 150.0}})

    assert response["reachable"] is False
    assert response["windows"], "the rows are kept, each with the constraint that stopped it"
    assert all(row["constraint_fired"] == "hazard_area" for row in response["windows"])


def test_a_bound_given_as_null_means_the_bound_of_the_site():
    response = compute_windows({**BASE, "corridor": {"A_min_deg": None, "A_max_deg": 150.0}})

    assert response["reachable"] is False


def test_the_resolved_corridor_holds_both_bounds():
    resolved = target.resolve({**BASE, "corridor": {"A_min_deg": 120.0}}, epoch_jd=2461318.5)

    assert resolved.corridor["A_min_deg"] == 120.0
    assert resolved.corridor["A_max_deg"] == SITE_CORRIDOR["A_max_deg"]


@pytest.mark.parametrize("value", ["25:99", "24:00", "10:60", "-1:30", "10:5x", "noon", "24", "-0.5"])
def test_a_local_time_that_does_not_exist_is_refused(value):
    with pytest.raises(ValueError, match="ltan_hours"):
        compute_windows({**BASE, "target": {"type": "SSO", "ltan_hours": value}})


@pytest.mark.parametrize("value, hours", [("00:00", 0.0), ("06:00", 6.0), ("10:30", 10.5), ("23:59", 23.0 + 59.0 / 60.0), ("10.5", 10.5)])
def test_a_valid_local_time_is_read_as_decimal_hours(value, hours):
    resolved = target.resolve({**BASE, "target": {"type": "SSO", "ltan_hours": value}}, epoch_jd=2461318.5)

    assert resolved.ltan_hours == pytest.approx(hours)


@pytest.mark.parametrize("value", [0, 0.0, -1.0, -0.001])
def test_a_plane_tolerance_that_is_not_positive_is_refused(value):
    with pytest.raises(ValueError, match="raan_tolerance_deg"):
        compute_windows({**BASE, "raan_tolerance_deg": value})


def test_a_positive_plane_tolerance_scales_the_window_width():
    narrow = compute_windows({**BASE, "raan_tolerance_deg": 0.5})["windows"][0]["window_width_s"]
    wide = compute_windows({**BASE, "raan_tolerance_deg": 2.0})["windows"][0]["window_width_s"]

    assert narrow > 0.0
    assert wide == pytest.approx(4.0 * narrow, rel=1.0e-6)
