"""W1 criteria table: structure, the VERIFIED/PROXY rule, inventory coverage and the evaluator."""

from __future__ import annotations

import json

import pytest

from backend.weather import criteria
from backend.weather.errors import CriteriaVersionMissingError

REQUIRED_ROW_KEYS = {"criterion_id", "parameter", "limit", "unit", "source_citation", "flag", "comparison"}
INVENTORY_ROWS = set(range(1, 28))


@pytest.fixture(scope="module")
def table() -> dict:
    return criteria.load_criteria("criteria_v1")


@pytest.fixture(scope="module")
def rows(table) -> dict:
    return {row["criterion_id"]: row for row in table["criteria"]}


def test_criteria_v1_loads_and_names_its_own_version(table):
    assert table["criteria_version"] == "criteria_v1"
    assert len(table["criteria"]) > 0


def test_every_row_has_the_required_keys_and_legal_values(table):
    for row in table["criteria"]:
        missing = REQUIRED_ROW_KEYS - set(row)
        assert not missing, f"{row.get('criterion_id')} lacks {sorted(missing)}"
        assert row["flag"] in {"VERIFIED", "PROXY"}, row["criterion_id"]
        assert row["comparison"] in {"lt", "gt", "between"}, row["criterion_id"]
        assert isinstance(row["criterion_id"], str) and row["criterion_id"]
        assert isinstance(row["parameter"], str) and row["parameter"]
        assert isinstance(row["unit"], str) and row["unit"]
        assert isinstance(row["source_citation"], str) and row["source_citation"].strip()


def test_every_row_states_a_numeric_limit(table):
    for row in table["criteria"]:
        limit = row["limit"]
        if row["comparison"] == "between":
            assert isinstance(limit, list) and len(limit) == 2, row["criterion_id"]
            assert all(isinstance(value, (int, float)) for value in limit) and limit[0] <= limit[1]
        else:
            assert isinstance(limit, (int, float)) and not isinstance(limit, bool), row["criterion_id"]


def test_criterion_ids_are_unique(table):
    ids = [row["criterion_id"] for row in table["criteria"]]
    assert len(ids) == len(set(ids))


def test_every_verified_row_has_a_named_document_a_url_and_a_verbatim_quote(table):
    """The hard rule: a row without a verifiable source must be PROXY."""
    verified = [row for row in table["criteria"] if row["flag"] == "VERIFIED"]
    assert verified, "the table carries no VERIFIED row at all"
    for row in verified:
        assert row["source_citation"].strip(), row["criterion_id"]
        assert row.get("source_url", "").startswith("https://"), row["criterion_id"]
        assert row.get("source_quote", "").strip(), row["criterion_id"]
        assert row.get("source_accessed", "").strip(), row["criterion_id"]


def test_the_verified_rule_is_enforced_by_the_validator_not_by_convention(table):
    broken = json.loads(json.dumps(table))
    target = next(row for row in broken["criteria"] if row["flag"] == "VERIFIED")
    target["source_quote"] = "  "

    with pytest.raises(ValueError, match="VERIFIED"):
        criteria.validate_table(broken)


def test_a_row_without_a_limit_is_refused_by_the_validator(table):
    broken = json.loads(json.dumps(table))
    broken["criteria"][0]["limit"] = None

    with pytest.raises(ValueError, match="limit"):
        criteria.validate_table(broken)


def test_no_row_rests_on_an_assumed_limit(table):
    """Owner rule: an assumed number is not tolerated. Every limit is published or derived from published facts."""
    for row in table["criteria"]:
        text = json.dumps(row).upper()
        assert "ASSUMPTION" not in text and "ASSUMED" not in text, row["criterion_id"]


def test_every_proxy_row_names_the_substitution_and_the_published_basis_of_its_limit(table):
    proxies = [row for row in table["criteria"] if row["flag"] == "PROXY"]
    assert proxies
    for row in proxies:
        assert "SUBSTITUTION" in row["_comment"], row["criterion_id"]
        basis = row["limit_basis"]
        assert basis["document"].strip() and basis["quote"].strip() and basis["accessed"], row["criterion_id"]
        assert basis["url"].startswith("https://"), row["criterion_id"]


def test_every_row_of_the_27_row_variable_inventory_is_represented(table):
    as_criteria = {row["inventory_row"] for row in table["criteria"]}
    not_assessed = {entry["inventory_row"] for entry in table["not_assessed"]}

    assert as_criteria | not_assessed == INVENTORY_ROWS
    for entry in table["not_assessed"]:
        assert entry["label"].strip() and entry["reason"].strip()


def test_every_variable_the_issue_names_has_a_row_or_a_stated_reason(table):
    """Issue W1: surface wind speed and gusts, direction, visibility, precipitation type and rate, ceiling,
    temperature, lightning, upper-level wind at 850/700/500/300/200 hPa, cloud cover.

    All have a row except upper-level wind, for which no numeric limit is published anywhere; an assumed limit
    is not tolerated, so it is a not_assessed entry that says so.
    """
    parameters = [row["parameter"] for row in table["criteria"]]
    for name in ("wind_speed_10m", "wind_gusts_10m", "wind_direction_10m", "visibility", "snowfall",
                 "precipitation", "temperature_2m", "cape", "cloud_cover_low", "cloud_cover_mid"):
        assert name in parameters, name
    ids = [row["criterion_id"] for row in table["criteria"]]
    assert any("ceiling" in name for name in ids)
    assert any("lightning" in name for name in ids)
    assert any(name.startswith("cloud_cover") for name in ids)
    upper = next(entry for entry in table["not_assessed"] if entry["inventory_row"] == 4)
    assert "850" in upper["label"] and "200" in upper["label"]
    assert "no numeric" in upper["reason"].lower()


def test_the_site_specific_rules_of_the_canso_environmental_assessment_are_cited(table):
    cited = " ".join(json.dumps(row) for row in table["criteria"])
    assert "Any precipitation at the launch site or within the flight path will prohibit a launch." in cited
    assert "Reduced visibility will prohibit launch." in cited
    assert "populated areas up range" in cited


def test_the_lightning_row_is_one_of_the_two_proxies_the_issue_names_and_explains_the_substitution(table):
    lightning = [row for row in table["criteria"] if "lightning" in row["criterion_id"]]

    assert len(lightning) == 1
    row = lightning[0]
    assert row["parameter"] in {"cape", "showers", "convective_precipitation"}
    assert row["flag"] == "PROXY"
    assert "field mill" in row["_comment"].lower()
    assert "cloud-top" in row["_comment"].lower()


def test_the_direction_sector_is_computed_from_published_coordinates_not_chosen(rows):
    """The sector is the set of wind directions that blow from the site centre toward the named communities."""
    from backend.weather import config
    from backend.weather.scripts import derive_direction_sector

    row = rows["wind_direction"]
    low, high = derive_direction_sector.sector(config.load_site("canso"))

    assert row["comparison"] == "between"
    assert row["limit"] == [round(low, 1), round(high, 1)]
    assert 0 <= row["limit"][0] < row["limit"][1] <= 360


def test_the_bearing_arithmetic_against_hand_values():
    from backend.weather.scripts import derive_direction_sector as d

    assert d.initial_bearing(45.0, -61.0, 46.0, -61.0) == pytest.approx(0.0, abs=1e-9)      # due north
    assert d.initial_bearing(45.0, -61.0, 44.0, -61.0) == pytest.approx(180.0, abs=1e-9)    # due south
    assert d.initial_bearing(0.0, 0.0, 0.0, 1.0) == pytest.approx(90.0, abs=1e-9)           # due east on the equator
    assert d.wind_from(350.0) == pytest.approx(170.0) and d.wind_from(100.0) == pytest.approx(280.0)


def test_the_sources_the_issue_names_were_read_and_are_recorded(table):
    read = " ".join(entry["document"] for entry in table["sources_read"])
    for name in ("Space Shuttle Weather Launch Commit Criteria", "Falcon User's Guide", "Roeder",
                 "Canso Spaceport Facility"):
        assert name in read, name
    for entry in table["sources_read"]:
        assert entry["url"].startswith("https://") and entry["accessed"] and entry["finding"].strip()
    cited = " ".join(row["source_citation"] for row in table["criteria"])
    assert "FS-2008-02-039-KSC" in cited and "Roeder" in cited


def test_unknown_criteria_version_raises_the_error_api_maps_to_criteria_version_missing():
    with pytest.raises(CriteriaVersionMissingError) as raised:
        criteria.load_criteria("nonexistent")

    assert raised.value.constraint_fired == "criteria_version_missing"
    assert raised.value.criteria_version == "nonexistent"


def test_the_default_version_is_resolved_from_the_data_directory_not_from_a_literal():
    assert criteria.current_criteria_version() in criteria.available_versions()
    assert criteria.load_criteria(None)["criteria_version"] == criteria.current_criteria_version()


def test_published_limits_are_converted_from_their_source_units_correctly(rows):
    assert rows["surface_wind_speed"]["limit"] == pytest.approx(30 * 0.44704, abs=1e-4)             # 30 mph
    assert rows["surface_wind_gust"]["limit"] == pytest.approx(33 * 1852 / 3600, abs=1e-4)          # 33 kt
    assert rows["ground_operations_wind"]["limit"] == pytest.approx(42 * 1852 / 3600, abs=1e-4)     # 42 kt
    assert rows["temperature_hot"]["limit"] == pytest.approx((99 - 32) * 5 / 9, abs=1e-4)           # 99 degF
    assert rows["visibility"]["limit"] == pytest.approx(4 * 1852, abs=1e-6)                         # 4 NM
    assert rows["ceiling_proxy_low_cloud"]["limit"] == pytest.approx(5 / 8 * 100)                   # 5 oktas
    assert rows["cloud_cover_thick_layer_proxy"]["limit"] == pytest.approx(7 / 8 * 100)             # above 7 oktas
    assert rows["lightning_proxy_cape"]["limit"] == 1000.0                                          # SPC class


# The evaluator -------------------------------------------------------------------------------------------

GT = {"criterion_id": "g", "parameter": "x", "comparison": "gt", "limit": 10.0}
LT = {"criterion_id": "l", "parameter": "x", "comparison": "lt", "limit": -10.0}
BETWEEN = {"criterion_id": "b", "parameter": "x", "comparison": "between", "limit": [200.0, 290.0]}


@pytest.mark.parametrize(
    "row, value, expected",
    [
        (GT, 10.1, True), (GT, 10.0, False), (GT, 3.0, False),
        (LT, -10.1, True), (LT, -10.0, False), (LT, 4.0, False),
        (BETWEEN, 200.0, True), (BETWEEN, 250.0, True), (BETWEEN, 290.0, True), (BETWEEN, 199.9, False),
        (GT, None, None), (LT, None, None), (BETWEEN, None, None),
    ],
)
def test_comparison_states_when_a_criterion_is_violated(row, value, expected):
    assert criteria.is_violated(row, value) is expected


def test_a_window_is_violated_by_the_worst_hour_and_unknown_when_a_value_is_missing():
    rows = [GT, {"criterion_id": "cold", "parameter": "t", "comparison": "lt", "limit": -10.0}]
    calm = [{"x": 1.0, "t": 5.0}, {"x": 2.0, "t": 4.0}]
    gusty = [{"x": 1.0, "t": 5.0}, {"x": 11.0, "t": 4.0}]
    gap = [{"x": 1.0, "t": 5.0}, {"x": None, "t": 4.0}]

    assert criteria.window_violations(rows, calm) == {"g": False, "cold": False}
    assert criteria.window_violations(rows, gusty) == {"g": True, "cold": False}
    assert criteria.window_violations(rows, gap) == {"g": None, "cold": False}
    assert criteria.window_launchable(rows, calm) == 1
    assert criteria.window_launchable(rows, gusty) == 0
    assert criteria.window_launchable(rows, gap) is None
    assert criteria.window_launchable(rows, []) is None


def test_a_missing_value_cannot_hide_a_violation_seen_in_another_hour():
    hours = [{"x": 11.0}, {"x": None}]
    assert criteria.window_violations([GT], hours) == {"g": True}
    assert criteria.window_launchable([GT], hours) == 0
