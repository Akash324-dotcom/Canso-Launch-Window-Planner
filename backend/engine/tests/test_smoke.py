"""E0 Scaffold.

RED first. This file was written and run before backend/engine/__init__.py existed.
The import at module scope is deliberate: it fails collection outright when the
engine package is absent, which is the strongest possible RED for a scaffold task.
"""

import math

import pytest

from backend.engine import compute_windows

# A minimal well-formed spec IV.1 request, transcribed from the frozen contract
# example tests/contract/examples/good/windows_request_good_minimal_leo.json.
MINIMAL_REQUEST = {
    "target": {"type": "CUSTOM", "h_t_km": 500.0, "i_t_deg": 98.1},
    "site": "canso",
    "date_range": {"start": "2026-10-05", "end": "2026-10-07"},
    "vehicle_profile_id": "cyclone4m",
}

# Fields the API composes on top of the engine's return value. The engine must
# never emit them (integration contract, Seam 1).
API_ADDED_TOP_LEVEL = ("constants_block", "provenance_block")
API_ADDED_WINDOW = ("p_success", "horizon_label", "forecast_issue_time")
API_ADDED_WINDOW_COMPONENT = ("weather",)


def test_compute_windows_is_importable():
    """RED: the import above already proves this, asserted for a readable failure."""
    assert callable(compute_windows)


def test_response_has_the_engine_shape_and_no_more():
    """Written for the E0 stub; retained as the shape contract the engine must keep.

    An unreachable target legitimately produces no windows, which is where the
    emptiness assertion still belongs. The response must carry exactly the five
    engine-owned keys and nothing else, because the API adds the rest and the
    frozen schema sets additionalProperties false.
    """
    unreachable = dict(MINIMAL_REQUEST)
    unreachable["target"] = {"type": "CUSTOM", "h_t_km": 400.0, "i_t_deg": 45.1}
    response = compute_windows(unreachable)
    assert isinstance(response, dict)
    assert set(response) == {
        "reachable",
        "plane_change_dv_ms",
        "sso_consistency_warning",
        "windows",
        "engine_version",
        "computation_ms",
    }
    assert response["windows"] == []
    assert response["reachable"] is False
    assert response["plane_change_dv_ms"] is not None
    assert response["sso_consistency_warning"] is None
    assert isinstance(response["engine_version"], str) and response["engine_version"]
    assert isinstance(response["computation_ms"], (int, float))


def test_engine_does_not_emit_api_composed_fields():
    response = compute_windows(MINIMAL_REQUEST)
    for key in API_ADDED_TOP_LEVEL:
        assert key not in response, f"{key} is composed by the API, not the engine"


def test_engine_is_pure_and_repeatable():
    first = compute_windows(MINIMAL_REQUEST)
    second = compute_windows(MINIMAL_REQUEST)
    for key in ("reachable", "windows", "plane_change_dv_ms", "engine_version"):
        assert first[key] == second[key]


def test_engine_does_not_mutate_the_request():
    import copy

    original = copy.deepcopy(MINIMAL_REQUEST)
    compute_windows(MINIMAL_REQUEST)
    assert MINIMAL_REQUEST == original


@pytest.mark.parametrize("bad", [{}, {"target": {"type": "CUSTOM"}}])
def test_stub_rejects_malformed_requests_with_value_error(bad):
    """The contract guarantees well-formed requests; this guards the obvious edges."""
    with pytest.raises(ValueError):
        compute_windows(bad)


def test_computation_ms_is_finite():
    response = compute_windows(MINIMAL_REQUEST)
    assert math.isfinite(response["computation_ms"])
    assert response["computation_ms"] >= 0.0