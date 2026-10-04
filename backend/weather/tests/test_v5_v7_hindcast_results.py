"""Issue #7, V5 to V7: the hindcast on the committed data, the report and the generated fixture."""

from __future__ import annotations

import csv
import hashlib
import importlib.util
import io
import json
from datetime import date
from pathlib import Path

import pytest

from backend.weather import climatology, config, criteria, hindcast, hindcast_report
from backend.weather.scripts import run_hindcast

REPO = Path(__file__).resolve().parents[3]
WEATHER = REPO / "backend" / "weather"
FIXTURE = REPO / "backend" / "fixtures" / "skill.json"


def load_script():
    spec = importlib.util.spec_from_file_location("build_skill_fixture", REPO / "scripts" / "build_skill_fixture.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def real(tmp_path_factory):
    """The hindcast over the longest supported period, computed once into a private cache."""
    previous = hindcast.CACHE_DIR
    hindcast.CACHE_DIR = tmp_path_factory.mktemp("hindcast_cache")
    try:
        start, end = hindcast.longest_period("canso")
        lead_max = config.load_sources()["hindcast"]["lead_max_days"]
        yield {"start": start, "end": end, "lead_max": lead_max,
               "result": hindcast.compute(start, end, lead_max), "outputs": run_hindcast.build("canso"),
               "fixture": load_script().build("canso")}
    finally:
        hindcast.CACHE_DIR = previous


# V5 ----------------------------------------------------------------------------------------------------------

def test_the_period_is_the_longest_the_committed_data_supports_and_is_recorded(real):
    runs = hindcast.source_metadata("canso")
    archive_end = date.fromisoformat(climatology.archive_metadata("canso")["period_end"][:10])

    assert real["start"] == runs["coverage"]["first_run"][:10]
    assert date.fromisoformat(real["end"]) < archive_end
    assert real["result"]["period"] == {"start": real["start"], "end": real["end"]}


def test_the_series_has_exactly_one_entry_per_lead_with_a_real_sample(real):
    series = real["result"]["skill_series"]

    assert [entry["lead_time_days"] for entry in series] == list(range(1, real["lead_max"] + 1))
    for entry in series:
        assert entry["n_cases"] > 0 and entry["bss"] is not None
        sample = [(row["p"], row["o"]) for row in real["result"]["pairs"]
                  if row["lead_time_days"] == entry["lead_time_days"]]
        assert entry["n_cases"] == len(sample)
        assert entry["bs"] == pytest.approx(hindcast.brier_score(sample))
        assert entry["bs_ref"] == pytest.approx(hindcast.reference_brier_score(sample))


def test_every_case_is_accounted_for(real):
    """Complete issue dates times leads = pairs + forecasts excluded for a missing value + missing outcomes."""
    result = real["result"]
    possible = result["coverage"]["issue_dates_complete"] * real["lead_max"]

    assert len(result["pairs"]) + result["excluded"]["forecast_with_missing_value"] + result["excluded"][
        "outcome_missing"] == possible
    assert result["excluded"]["issue_date_without_every_run"] == len(result["coverage"]["issue_dates_incomplete"])


def test_the_base_rate_is_the_observed_launchable_fraction_of_the_verified_days(real):
    from backend.weather import observations

    days = sorted({row["valid_date"] for row in real["result"]["pairs"]})
    outcomes = [observations.observed_launchable(day) for day in days]

    assert None not in outcomes
    assert real["result"]["base_rate"] == pytest.approx(sum(outcomes) / len(outcomes))
    assert real["result"]["verified_days"] == len(days)


def test_the_response_has_the_spec_iv4_shape(real):
    body = hindcast.response(real["result"])

    assert list(body) == ["period", "verification_source", "reference_forecast", "base_rate", "skill_series",
                          "reliability_bins", "roc_points", "skill_horizon_measured_days", "constants_block"]
    assert body["verification_source"] == "era5" and body["reference_forecast"] == "climatology_base_rate"
    assert all(entry["n"] > 0 for entry in body["reliability_bins"])
    assert sum(entry["n"] for entry in body["reliability_bins"]) == len(real["result"]["pairs"])
    assert body["constants_block"]["citation_id"].startswith("run_")


def test_the_committed_raw_outputs_are_what_the_hindcast_computes(real):
    for name, text in real["outputs"].items():
        assert (WEATHER / name).read_text(encoding="utf-8") == text, f"{name} was not produced by run_hindcast"
    rows = list(csv.DictReader(io.StringIO((WEATHER / "data/hindcast/pairs_canso.csv").read_text())))
    assert len(rows) == len(real["result"]["pairs"])
    assert all(0.0 <= float(row["p"]) <= 1.0 and row["o"] in {"0", "1"} for row in rows)


# V6 ----------------------------------------------------------------------------------------------------------

def test_the_report_states_the_period_the_sources_the_criteria_version_and_n_cases_per_lead(real):
    report = (WEATHER / "HINDCAST.md").read_text(encoding="utf-8")
    result = real["result"]

    assert f"{real['start']} to {real['end']}" in report
    assert result["forecast_source"] in report and result["criteria_version"] in report
    assert "| n_cases | " + " | ".join(str(e["n_cases"]) for e in result["skill_series"]) + " |" in report
    order = [report.index(heading) for heading in ("## 1. What was run", "## 2. Brier skill score by lead time",
                                                   "## 3. Reliability", "## 4. Verdict", "## 5. Caveats")]
    assert order == sorted(order)


def test_a_lead_with_fewer_than_30_cases_is_reported_with_its_count_stated(real):
    """Issue #7 V4: such a lead 'is still reported but the observation count is stated in HINDCAST.md'.

    The real run has no such lead, so the report is rendered from the real result with two sample sizes cut.
    """
    result = json.loads(json.dumps({key: value for key, value in real["result"].items() if key != "pairs"}))
    result["observed_violation_frequency"] = hindcast.observed_violation_frequency(
        "canso", result["criteria_version"], sorted({row["valid_date"] for row in real["result"]["pairs"]}))
    result["skill_series"][8]["n_cases"] = 20
    result["skill_series"][9]["n_cases"] = 7

    report = hindcast_report.render(result, hindcast.source_metadata("canso"), climatology.archive_metadata("canso"),
                                    criteria.load_criteria(result["criteria_version"]), config.load_skill_horizon())

    assert "**Small samples.** Fewer than 30 cases: lead 9 (20 cases), lead 10 (7 cases)." in report
    assert "a skill value from so few cases is not a validation" in report
    assert "| 9 | 20 |" in report and "| 10 | 7 |" in report, "the leads are still reported in the BSS table"
    assert "every lead has at least 30 cases" not in report


def test_the_verdict_says_in_plain_words_what_the_numbers_show(real):
    report = (WEATHER / "HINDCAST.md").read_text(encoding="utf-8")
    result = real["result"]
    positive = [entry for entry in result["skill_series"] if entry["bss"] > 0]

    for line in hindcast_report.verdict(result):
        assert line in report
    if not positive:
        assert "BSS is at or below zero at every lead." in report
    else:
        assert "BSS is at or below zero at every lead." not in report


def test_the_calibration_criterion_is_reported_under_both_readings_and_the_stricter_one_decides(real):
    """Spec III.4 criterion 2: 'mean |observed - predicted| across bins <= 0.15'.

    'Predicted' can be read as the mean forecast inside the bin or as the bin centre the response carries. The
    report gives both figures, computed here from the pairs, and the verdict uses the larger of the two.
    """
    report = (WEATHER / "HINDCAST.md").read_text(encoding="utf-8")
    pairs = [(row["p"], row["o"]) for row in real["result"]["pairs"]]
    bins = hindcast.reliability_bins(pairs, n_bins=config.load_sources()["hindcast"]["reliability_bins"])
    width = 1 / config.load_sources()["hindcast"]["reliability_bins"]
    by_mean, by_centre = [], []
    for entry in bins:
        inside = [p for p, _ in pairs if abs(p - entry["p_center"]) <= width / 2 + 1e-9]
        assert len(inside) == entry["n"]
        by_mean.append(abs(entry["observed_freq"] - sum(inside) / len(inside)))
        by_centre.append(abs(entry["observed_freq"] - entry["p_center"]))
    gap_mean, gap_centre = sum(by_mean) / len(bins), sum(by_centre) / len(bins)
    worst = max(gap_mean, gap_centre)

    assert f"against the mean forecast in each bin: {gap_mean:.3f}" in report
    assert f"against the bin centre: {gap_centre:.3f}" in report
    verdict_line = next(line for line in report.splitlines() if line.startswith("2. At least"))
    assert f"gap {worst:.3f}" in verdict_line
    assert ("NOT met" in verdict_line) == (len(bins) < 5 or worst > 0.15)
    if "NOT met" in verdict_line:
        assert "No recalibration was applied" in report


def test_the_verdict_sentences_for_each_kind_of_result():
    def result(values):
        series = [{"lead_time_days": lead, "bss": value} for lead, value in enumerate(values, start=1)]
        return {"skill_series": series, "lead_max": len(values),
                "skill_horizon_measured_days": hindcast.measured_horizon(series)}

    assert hindcast_report.verdict(result([-0.1, 0.0, -0.3]))[0].startswith("BSS is at or below zero at every lead.")
    assert "disappears after lead 2" in hindcast_report.verdict(result([0.3, 0.1, -0.2]))[0]
    assert "at every lead from 1 to 3 days" in hindcast_report.verdict(result([0.3, 0.2, 0.1]))[0]
    assert "at or below zero at lead 1" in hindcast_report.verdict(result([-0.1, 0.2, 0.1]))[0]
    again = hindcast_report.verdict(result([0.3, -0.1, 0.2]))
    assert "disappears after lead 1" in again[0] and "above zero again at lead(s) 3" in again[1]


def test_the_anti_tuning_record_matches_the_criteria_file_in_use(real):
    result = real["result"]
    path = config.DATA_DIR / f"{result['criteria_version']}.json"

    assert result["criteria_version"] == criteria.current_criteria_version()
    assert result["criteria_sha256"] == hashlib.sha256(path.read_bytes()).hexdigest()
    assert result["criteria_sha256"] in (WEATHER / "HINDCAST.md").read_text(encoding="utf-8")
    assert result["criteria_evaluated"] == [row["criterion_id"] for row in climatology.evaluated_rows(
        "canso", criteria.load_criteria(result["criteria_version"]))]


def test_the_hindcast_scores_the_leads_spec_iii4_names_whatever_the_operational_boundary_is(real):
    """Spec III.4: 'leads 1-10 days'. The hindcast measures the boundary, so it cannot take its range from it."""
    cfg = config.load_sources()["hindcast"]

    assert cfg["lead_max_days"] == 10 and "III.4" in cfg["lead_max_days_source"]
    assert [entry["lead_time_days"] for entry in real["result"]["skill_series"]] == list(range(1, 11))


def test_the_operational_boundary_is_the_measured_crossover_with_its_number_and_sample_size(real):
    """Issue #7 V6: BSS positive at short leads and dead later, so the skill horizon config is set accordingly."""
    result = real["result"]
    series = {entry["lead_time_days"]: entry for entry in result["skill_series"]}
    crossover = result["skill_horizon_measured_days"]
    horizon = config.load_skill_horizon()

    assert crossover is not None and crossover < real["lead_max"], "this test is for a result that crosses zero"
    assert horizon["max_forecast_lead_days"] == crossover
    measured = horizon["measured"]
    assert measured["period"] == result["period"]
    assert measured["forecast_source"] == result["forecast_source"]
    assert measured["members_per_issue_date"] == result["members_per_issue_date"]
    assert measured["criteria_version"] == result["criteria_version"]
    for key, lead in (("last_lead_with_skill", crossover), ("first_lead_without_skill", crossover + 1)):
        assert measured[key]["lead_time_days"] == lead
        assert measured[key]["n_cases"] == series[lead]["n_cases"]
        assert measured[key]["bss"] == round(series[lead]["bss"], 3)
    assert measured["last_lead_with_skill"]["bss"] > 0 >= measured["first_lead_without_skill"]["bss"]


def test_the_report_states_the_crossover_and_the_boundary_set_from_it(real):
    result = real["result"]
    series = {entry["lead_time_days"]: entry for entry in result["skill_series"]}
    crossover = result["skill_horizon_measured_days"]
    report = (WEATHER / "HINDCAST.md").read_text(encoding="utf-8")

    assert (f"`data/skill_horizon.json` sets the FORECAST boundary to {crossover} days, the measured crossover"
            in report)
    assert f"BSS {series[crossover]['bss']:.3f} on {series[crossover]['n_cases']} cases at lead {crossover}" in report
    assert (f"BSS {series[crossover + 1]['bss']:.3f} on {series[crossover + 1]['n_cases']} cases at lead "
            f"{crossover + 1}") in report


def test_the_readme_quotes_the_skill_series_of_the_committed_result(real):
    """V8. The README repeats the BSS by lead; the numbers must be the ones the hindcast computed."""
    readme = (WEATHER / "README.md").read_text(encoding="utf-8")
    series = real["result"]["skill_series"]

    assert "| BSS | " + " | ".join(f"{entry['bss']:.3f}" for entry in series) + " |" in readme
    assert "| n_cases | " + " | ".join(str(entry["n_cases"]) for entry in series) + " |" in readme


# V7 ----------------------------------------------------------------------------------------------------------

def test_the_skill_fixture_is_the_hindcast_response_written_by_the_committed_script(real):
    assert FIXTURE.read_text(encoding="utf-8") == real["fixture"], "skill.json was not produced by the script"
    assert json.loads(real["fixture"]) == json.loads(json.dumps(hindcast.response(real["result"])))


def test_running_the_fixture_script_twice_gives_byte_identical_output(real):
    assert load_script().build("canso") == real["fixture"]


def test_the_seam_1_entry_point_returns_the_same_response(real, monkeypatch):
    from backend import weather

    body = weather.hindcast(real["start"], real["end"], real["lead_max"])

    assert body == hindcast.response(real["result"])
