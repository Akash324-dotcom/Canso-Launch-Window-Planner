"""The offline fixtures of spec V.5 must satisfy the frozen contract themselves.

Spec V.5 makes the fixtures the demo floor: if a live call fails during judging the
service answers from these documents. That only works while they are schema valid, so
each one is validated here against the frozen schema its name names.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from backend.api.schemas import errors_for

FIXTURE_DIR = Path(__file__).resolve().parents[2] / "fixtures"

FIXTURE_SCHEMAS = {
    "windows.json": "windows_response",
    "weather.json": "weather_probability_response",
    "skill.json": "skill_response",
    "site.json": "site_response",
    "ephemeris.json": "ephemeris_response",
}


@pytest.mark.parametrize(("filename", "schema_name"), sorted(FIXTURE_SCHEMAS.items()))
def test_fixture_validates_against_its_frozen_schema(filename: str, schema_name: str) -> None:
    path = FIXTURE_DIR / filename
    assert path.is_file(), f"{filename} is missing; spec V.5 makes it the demo floor"
    document = json.loads(path.read_text(encoding="utf-8"))
    errors = errors_for(schema_name, document)
    assert not errors, f"{filename} must be valid against {schema_name}.json: {errors}"


@pytest.mark.parametrize("filename", sorted(FIXTURE_SCHEMAS))
def test_fixture_is_a_json_object_with_no_trailing_content(filename: str) -> None:
    text = (FIXTURE_DIR / filename).read_text(encoding="utf-8")
    assert isinstance(json.loads(text), dict)
    assert text.endswith("\n")


def test_every_configured_fixture_exists_on_disk() -> None:
    from backend.api.config import Settings

    settings = Settings.load()
    assert sorted(settings.fixture_paths) == sorted(
        name.removesuffix(".json") for name in FIXTURE_SCHEMAS
    )
    for name, relative in sorted(settings.fixture_paths.items()):
        assert settings.resolve(relative).is_file(), name
        assert relative == f"backend/fixtures/{name}.json"


def test_the_window_fixture_describes_an_sso_target_from_canso() -> None:
    document = json.loads((FIXTURE_DIR / "windows.json").read_text(encoding="utf-8"))
    assert document["engine_version"] == "stub"
    assert document["reachable"] is True
    assert len(document["windows"]) == 3
    site = document["provenance_block"]["site"]
    assert site["name"] == "canso"
    assert abs(site["phi_s_deg"] - 45.3) < 1e-9
    inclinations = {window["reached_inclination_deg"] for window in document["windows"]}
    assert inclinations == {98.08}
    assert all(window["reached_inclination_deg"] > site["phi_s_deg"] for window in document["windows"])


def test_the_window_fixture_carries_both_shared_blocks() -> None:
    document = json.loads((FIXTURE_DIR / "windows.json").read_text(encoding="utf-8"))
    assert errors_for("constants_block", document["constants_block"]) == []
    assert errors_for("provenance_block", document["provenance_block"]) == []
    assert document["constants_block"]["citation_id"].startswith("run_")


def test_the_weather_fixture_is_a_recorded_snapshot() -> None:
    document = json.loads((FIXTURE_DIR / "weather.json").read_text(encoding="utf-8"))
    assert document["source"] == "snapshot_cache"
    assert document["horizon_label"] in {"FORECAST", "CLIMATOLOGY"}
    if document["horizon_label"] == "CLIMATOLOGY":
        assert document["ensemble_size"] is None


def test_fixture_windows_and_the_weather_snapshot_agree() -> None:
    """The route recomposes p_success, so the frozen rows must already agree with it."""
    windows = json.loads((FIXTURE_DIR / "windows.json").read_text(encoding="utf-8"))
    weather = json.loads((FIXTURE_DIR / "weather.json").read_text(encoding="utf-8"))
    for window in windows["windows"]:
        components = window["p_success_components"]
        expected = weather["p_launch"] * components["range"] * components["conjunction"]
        assert window["p_success"] == pytest.approx(expected)
        assert window["horizon_label"] == weather["horizon_label"]
        assert window["forecast_issue_time"] == weather["forecast_issue_time"]


def test_every_fixture_constants_block_carries_the_configured_constants() -> None:
    """Found at integration: two fixtures held J2 = 0.000108262668, a tenth of spec II.10.

    The constants live in ``backend/api/data/constants.json`` and nowhere else, so a
    fixture that prints a constants block must print those values.
    """
    from backend.api.provenance import load_constants

    constants = load_constants()
    checked = 0
    for name in sorted(path.name for path in FIXTURE_DIR.glob("*.json")):
        document = json.loads((FIXTURE_DIR / name).read_text(encoding="utf-8"))
        block = document.get("constants_block")
        if block is None:
            continue
        checked += 1
        for constant, value in constants.values.items():
            assert block[constant] == value, f"{name}: {constant}"
    assert checked >= 3


def test_every_contract_example_constants_block_carries_the_spec_value_of_j2() -> None:
    """Found by the browser walk: the frozen examples held J2 = 0.000108262668.

    Spec II.10 gives J2 = 1.08262668e-3. The schema types the field and cannot check
    its value, so a tenth of it validated for as long as nobody read the number. An
    example is what a reader copies, so the good and the bad examples alike must
    carry the value of ``data/constants.json``; a bad example is bad for the reason
    its name gives, not for a wrong constant.
    """
    from backend.api.provenance import load_constants

    expected = load_constants().values["J2"]
    examples = Path(__file__).resolve().parents[3] / "tests" / "contract" / "examples"
    checked = 0
    for path in sorted(examples.rglob("*.json")):
        text = path.read_text(encoding="utf-8")
        if '"J2"' not in text:
            continue

        def blocks(node: object):
            if isinstance(node, dict):
                if "J2" in node and not isinstance(node["J2"], str):
                    yield node
                for value in node.values():
                    yield from blocks(value)
            elif isinstance(node, list):
                for value in node:
                    yield from blocks(value)

        for block in blocks(json.loads(text)):
            checked += 1
            assert block["J2"] == expected, f"{path.name}: J2 {block['J2']!r}"
    assert checked >= 20
