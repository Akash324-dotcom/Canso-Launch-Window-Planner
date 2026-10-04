"""W0 scaffold: the frozen Seam 1 entry point exists and returns the spec IV.3 key set."""

from __future__ import annotations

import inspect

SPEC_IV3_KEYS = {
    "date",
    "site",
    "p_launch",
    "horizon_label",
    "forecast_issue_time",
    "ensemble_size",
    "criteria_version",
    "components",
    "source",
}


def test_probability_is_importable_and_returns_the_spec_iv3_key_set():
    from backend.weather import probability

    result = probability("2026-10-07", "canso")

    assert isinstance(result, dict)
    assert set(result) == SPEC_IV3_KEYS
    assert result["date"] == "2026-10-07"
    assert result["site"] == "canso"


def test_probability_signature_is_the_frozen_seam_1_signature():
    from backend.weather import probability

    parameters = inspect.signature(probability).parameters

    assert list(parameters) == ["date_iso", "site", "criteria_version"]
    assert parameters["criteria_version"].default is None
