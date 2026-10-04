"""Render backend/weather/HINDCAST.md from a hindcast result, so that the report cannot drift from the numbers.

Every figure in the report is read from the result written by scripts/run_hindcast.py. The sentences of the
verdict are chosen by rule from those figures; none is typed by hand after looking at a score.
"""

from __future__ import annotations

SMALL_SAMPLE = 30          # issue #7 V4: a lead with fewer cases than this is reported with that fact stated
MIN_POPULATED_BINS = 5     # spec III.4 pass criterion 2
MAX_CALIBRATION_GAP = 0.15  # spec III.4 pass criterion 2


def _number(value, digits=3) -> str:
    return "n/a" if value is None else f"{value:.{digits}f}"


def verdict(result: dict) -> list[str]:
    """The reading of the skill series, in fixed sentences selected by the numbers."""
    series = result["skill_series"]
    positive = [entry["lead_time_days"] for entry in series if entry["bss"] is not None and entry["bss"] > 0]
    horizon = result["skill_horizon_measured_days"]
    lines = []
    if not positive:
        lines.append("BSS is at or below zero at every lead. Against the climatological base rate of the same "
                     "sample, the forecast probability shows no skill at any lead from 1 to "
                     f"{result['lead_max']} days in this period.")
    elif horizon is None:
        lines.append("BSS is at or below zero at lead 1, so there is no unbroken band of skill starting at the "
                     f"shortest lead. It is above zero only at lead(s) {', '.join(map(str, positive))}.")
    else:
        if horizon == result["lead_max"]:
            lines.append(f"BSS is above zero at every lead from 1 to {horizon} days. Skill against climatology "
                         "does not disappear inside the range that was tested.")
        else:
            lines.append(f"BSS is above zero from lead 1 to lead {horizon} and is at or below zero at lead "
                         f"{horizon + 1}. Skill against climatology disappears after lead {horizon}.")
        later = [lead for lead in positive if lead > horizon]
        if later:
            lines.append(f"BSS is above zero again at lead(s) {', '.join(map(str, later))}, after the first lead "
                         "without skill. Those values are not counted as part of the skill band.")
    return lines


def disposition(result: dict, review: dict) -> list[str]:
    """Section 7: what was decided about the calibration criterion after the review, and on what evidence."""
    bounds, decided = review["period_bounds_check"], review["calibration_disposition"]
    if decided["route"] != "b":
        raise ValueError("only route (b) of the review, the miss declared as the finding, is written up here")
    gaps, boot = result["calibration"]["gaps"], result["calibration"]["bootstrap"]
    low, high = boot["interval"]
    share = boot["share_at_or_below_bound"]
    bound = boot["bound"]
    if low > bound:
        reading = ("The bound lies below the whole interval. The miss is not sampling noise: a larger sample of "
                   "the same forecast system would not be expected to meet the bound.")
    elif high <= bound:
        reading = "The whole interval lies at or below the bound."
    else:
        reading = ("The interval excludes zero: the forecast is not perfectly calibrated, which is the "
                   "overconfidence described in section 4. The bound lies inside the interval: the miss of "
                   f"{gaps['larger'] - bound:.3f} is smaller than the sampling uncertainty of the gap, so "
                   "whether the gap is above or below the bound cannot be decided from this sample.")
        if low <= 0:
            raise ValueError("the reading above states that the interval excludes zero")
    lines = [
        "## 7. Disposition of criterion 2 (review of 4 October 2026)",
        "",
        f"Criterion 2 of spec III.4 is missed: gap {_number(gaps['larger'])} against a bound of {bound}. The review "
        "of this gate on issue #7 named two honest routes: (a) widen the verification sample and re-run, recording "
        "both results; (b) declare the miss the finding. It ruled out touching a criteria threshold.",
        "",
        f"Route (a), a wider sample, is not available. Checked on {bounds['checked_at']}:",
        "",
        f"- Start of the period. The forecast archive refuses the run of {bounds['run_refused']} (answer: "
        f"'{bounds['run_refused_answer']}'). Its first run is {bounds['first_run_available']}, the first issue "
        "date of this hindcast.",
        f"- End of the period. The ERA5 reanalysis is published up to {bounds['reanalysis_last_hour_published']}, "
        "which is the last hour of the committed archive.",
        "",
        f"The period {result['period']['start']} to {result['period']['end']} is therefore the widest the open "
        "data supports on that day. No second result exists to record beside the first.",
        "",
        "What a wider sample could change was estimated from the sample itself. The pairs were resampled "
        f"{boot['replicates']} times in {boot['blocks']} blocks of {boot['block_days']} consecutive valid dates "
        f"(seed {boot['seed']}; blocks, because the pairs of one valid date share one outcome; non-overlapping "
        f"blocks after {review['calibration_bootstrap']['method_reference']['reference'].split(' (')[0]} "
        f"{review['calibration_bootstrap']['method_reference']['reference'].split('(')[1][:4]}, doi "
        f"{review['calibration_bootstrap']['method_reference']['doi']}). From the "
        f"{100 * boot['interval_quantiles'][0]:.0f}th to the {100 * boot['interval_quantiles'][1]:.0f}th "
        f"percentile of the resamples the larger of the two gap readings runs from {low:.3f} to {high:.3f}, and "
        f"{100 * share:.1f} percent of the resamples are at or below the bound. {reading}",
        "",
        f"Route (b) is taken: the miss is the finding. Decided on {decided['decided_on']} by the owner of the "
        "WEATHER workflow. Criterion 2 stays NOT met in section 4. No recalibration was applied. No threshold, "
        "bin, window, criteria row or data source was changed after the first skill number existed (section 6); "
        "the resampling above is an uncertainty estimate and feeds nothing back into the forecast or the verdict.",
        "",
        "Gate evidence:",
        "",
        "- This file, generated by `python -m backend.weather.scripts.run_hindcast canso` from "
        "`data/hindcast/result_canso.json` and `data/hindcast/pairs_canso.csv`.",
        "- `backend/weather/tests/test_v0_v1_scoring.py` (hand-checked scoring), "
        "`tests/test_v2_v4_hindcast.py` (loop, exclusions, cache) and `tests/test_v5_v7_hindcast_results.py` "
        "(the real run, this report, the anti-tuning checksum, the fixture).",
        "- `backend/fixtures/skill.json`, written by `scripts/build_skill_fixture.py`; a test regenerates it and "
        "compares the bytes.",
        "",
    ]
    return lines


def render(result: dict, runs_meta: dict, archive_meta: dict, criteria_table: dict, horizon_cfg: dict,
           review: dict | None = None) -> str:
    series = result["skill_series"]
    cov = result["coverage"]
    excluded = result["excluded"]
    aggregate = result["aggregate"]
    detail = {entry["p_center"]: entry["mean_forecast"] for entry in result["reliability_mean_forecast"]}
    bins = result["reliability_bins"]
    gaps = [abs(entry["observed_freq"] - detail[entry["p_center"]]) for entry in bins]
    mean_gap = sum(gaps) / len(gaps) if gaps else None
    centre_gaps = [abs(entry["observed_freq"] - entry["p_center"]) for entry in bins]
    centre_gap = sum(centre_gaps) / len(centre_gaps) if centre_gaps else None
    worst_gap = max(mean_gap, centre_gap) if gaps else None
    small = [entry["lead_time_days"] for entry in series if entry["n_cases"] < SMALL_SAMPLE]
    proxies = [row["criterion_id"] for row in criteria_table["criteria"]
               if row["flag"] == "PROXY" and row["criterion_id"] in result["criteria_evaluated"]]
    gap = archive_meta.get("gap_filled", {}).get("visibility", {})

    out = []
    add = out.append
    add("# Hindcast of the launch-weather probability")
    add("")
    add("Issue #7, gate G2. This file is generated by `python -m backend.weather.scripts.run_hindcast canso` from "
        "the committed data. Every number below is read from `data/hindcast/result_canso.json`; a test regenerates "
        "the file and compares it byte for byte.")
    add("")
    add("## 1. What was run")
    add("")
    add(f"- Period, by forecast issue date: {result['period']['start']} to {result['period']['end']}.")
    add(f"- Forecast source: `{result['forecast_source']}`. {runs_meta['description']}. "
        f"Accessed {runs_meta['accessed']}.")
    add(f"- Forecast probability: the fraction of the {result['members_per_issue_date']} runs initialised on the "
        "issue date that satisfy every criterion over the evaluation window of the valid date, a time-lagged "
        "ensemble, computed by `ensemble.ensemble_probability`, the function the operational layer uses.")
    add(f"- Verification source: observed outcome from the hourly archive (`{archive_meta['file']}`, acquisition "
        f"`{archive_meta['acquisition']}`, {archive_meta['period_start']} to {archive_meta['period_end']}): ERA5 "
        "reanalysis for every model field and the Port Hawkesbury station observation for visibility. The response "
        "field says `era5`, the only value the contract allows.")
    add("- Reference forecast: the climatological base rate of the same verification sample, lead by lead.")
    add(f"- Criteria version: `{result['criteria_version']}`, sha256 `{result['criteria_sha256']}`, "
        f"{len(result['criteria_evaluated'])} rows evaluated on both sides by the same function.")
    add(f"- Verified days: {result['verified_days']}. Base rate, the launchable fraction of those days: "
        f"{_number(result['base_rate'])}.")
    add(f"- Forecast archive coverage: {cov['issue_dates_complete']} of {cov['issue_dates_expected']} issue dates "
        f"have all {result['members_per_issue_date']} runs; {cov['runs_missing']} of {cov['runs_expected']} runs "
        f"are missing. Incomplete issue dates: {', '.join(cov['issue_dates_incomplete']) or 'none'}.")
    add(f"- Excluded and counted: {excluded['issue_date_without_every_run']} issue dates without every run; "
        f"{excluded['forecast_with_missing_value']} (issue date, lead) forecasts with a missing value; "
        f"{excluded['outcome_missing']} (issue date, lead) cases with no observed outcome.")
    add("")
    add("Cases per lead:")
    add("")
    add("| Lead (days) | " + " | ".join(str(entry["lead_time_days"]) for entry in series) + " |")
    add("|---|" + "---|" * len(series))
    add("| n_cases | " + " | ".join(str(entry["n_cases"]) for entry in series) + " |")
    add("")
    add("## 2. Brier skill score by lead time")
    add("")
    add("BS = mean((p - o)^2). BS_ref is the same score for the constant forecast p = base rate of that lead's "
        "sample. BSS = 1 - BS / BS_ref. A negative BSS is reported as it is.")
    add("")
    add("| Lead (days) | n_cases | Base rate | BS | BS_ref | BSS |")
    add("|---|---|---|---|---|---|")
    for entry in series:
        rate = None
        sample = [row["o"] for row in result.get("pairs", []) if row["lead_time_days"] == entry["lead_time_days"]]
        if sample:
            rate = sum(sample) / len(sample)
        add(f"| {entry['lead_time_days']} | {entry['n_cases']} | {_number(rate)} | {_number(entry['bs'], 4)} | "
            f"{_number(entry['bs_ref'], 4)} | {_number(entry['bss'])} |")
    add("")
    if aggregate:
        low, high = aggregate["leads"]
        add(f"Leads {low} to {high} pooled ({aggregate['n_cases']} cases): BS {_number(aggregate['bs'], 4)}, "
            f"BS_ref {_number(aggregate['bs_ref'], 4)}, BSS {_number(aggregate['bss'])}.")
        add("")
    add("## 3. Reliability")
    add("")
    add(f"All leads pooled, {sum(entry['n'] for entry in bins)} cases, ten equal-width bins. Bins that hold no "
        "forecast are left out. With four runs the forecast probability can only be 0, 0.25, 0.5, 0.75 or 1, so at "
        "most five bins can be populated.")
    add("")
    add("| Bin centre | Mean forecast in bin | Observed frequency | n |")
    add("|---|---|---|---|")
    for entry in bins:
        add(f"| {entry['p_center']:.2f} | {_number(detail[entry['p_center']])} | {_number(entry['observed_freq'])} | "
            f"{entry['n']} |")
    add("")
    add(f"Populated bins: {len(bins)}. Mean absolute difference between observed frequency and forecast across "
        "the populated bins, under the two readings of 'predicted' in spec III.4: against the mean forecast in each "
        f"bin: {_number(mean_gap)}; against the bin centre: {_number(centre_gap)}. The verdict below uses the larger "
        "figure.")
    add("")
    add("ROC points for the decision 'forecast yes when p is at or above the threshold' (pod: probability of "
        "detection; far: false-alarm rate):")
    add("")
    add("| Threshold | POD | False-alarm rate |")
    add("|---|---|---|")
    for point in result["roc_points"]:
        add(f"| {point['threshold']:.2f} | {_number(point['pod'])} | {_number(point['far'])} |")
    add("")
    add("## 4. Verdict")
    add("")
    for line in verdict(result):
        add(line)
        add("")
    add("Against the pass criteria of spec III.4:")
    add("")
    if aggregate:
        met = aggregate["bss"] is not None and aggregate["bss"] > 0
        add(f"1. BSS above zero for leads {aggregate['leads'][0]} to {aggregate['leads'][1]} pooled: "
            f"{'met' if met else 'NOT met'} (BSS {_number(aggregate['bss'])}).")
    calibrated = len(bins) >= MIN_POPULATED_BINS and worst_gap is not None and worst_gap <= MAX_CALIBRATION_GAP
    add(f"2. At least {MIN_POPULATED_BINS} populated reliability bins with a mean absolute calibration gap of at "
        f"most {MAX_CALIBRATION_GAP}: {'met' if calibrated else 'NOT met'} ({len(bins)} bins, gap "
        f"{_number(worst_gap)}).")
    add("3. The skill-by-lead series is served by `hindcast()` in the shape of spec IV.4: met; "
        "`backend/fixtures/skill.json` is that response.")
    add("")
    if not calibrated:
        freqs = [entry["observed_freq"] for entry in bins]
        rising = all(low < high for low, high in zip(freqs, freqs[1:]))
        shape = ("The observed frequency rises from bin to bin, but less steeply than the diagonal"
                 if rising else "The observed frequency does not rise from every bin to the next")
        add(f"Criterion 2 is not met and is reported as a miss. {shape}: in the lowest populated bin (centre "
            f"{bins[0]['p_center']:.2f}) the day was launchable in {_number(freqs[0])} of cases, in the highest "
            f"(centre {bins[-1]['p_center']:.2f}) in {_number(freqs[-1])}. A four-member ensemble is expected to be "
            "overconfident in this way. Spec III.4 names histogram recalibration as the remedy for a diagram that "
            "is far from the diagonal. No recalibration was applied: a map fitted to four GFS runs does not carry "
            "over to the operational 82-member product, and fitting it on the sample it is then scored on would "
            "make the gap small by construction.")
        add("")
    horizon = result["skill_horizon_measured_days"]
    add(f"Measured skill horizon (`skill_horizon_measured_days`): {horizon if horizon is not None else 'null'}.")
    boundary = horizon_cfg["max_forecast_lead_days"]
    if horizon is not None and horizon < result["lead_max"] and boundary == horizon:
        by_lead = {entry["lead_time_days"]: entry for entry in series}
        last, first = by_lead[horizon], by_lead[horizon + 1]
        add("")
        add(f"`data/skill_horizon.json` sets the FORECAST boundary to {boundary} days, the measured crossover, as "
            f"issue #7 V6 prescribes: BSS {_number(last['bss'])} on {last['n_cases']} cases at lead {horizon}, "
            f"BSS {_number(first['bss'])} on {first['n_cases']} cases at lead {horizon + 1}, period "
            f"{result['period']['start']} to {result['period']['end']}. Beyond {boundary} days `probability()` "
            f"answers from climatology. The value it replaces was {horizon_cfg['prior']['max_forecast_lead_days']} "
            f"days, a prior from the literature. The flag stays {horizon_cfg['flag']}: the measurement is one "
            "period and a forecast system that is not the operational one, as the caveats below state.")
    else:
        add("")
        add(f"The FORECAST boundary in `data/skill_horizon.json` is {boundary} days (flag {horizon_cfg['flag']}). "
            "It is not the measured crossover of this run.")
    add("")
    add("## 5. Caveats")
    add("")
    add("- **This is not a verification of the operational probability.** No open archive keeps past runs of the "
        "ECMWF or GEFS ensembles in a readable form. The forecasts verified here are four runs of the GFS "
        "deterministic model per issue date. The result tests the criteria, the evaluation chain and the "
        "predictability of the event; it says nothing about the calibration of the 82-member operational product.")
    add(f"- **The period is short.** The forecast archive starts on {runs_meta['coverage']['first_run'][:10]}; "
        "earlier runs are not kept. The sample covers one spring, one summer and the start of one autumn, not a "
        "full year, so it cannot show the winter months, when the launchable fraction is lowest.")
    add("- **Four members give a coarse probability.** Only five probability values are possible, which limits the "
        "resolution of the reliability table and of the Brier score.")
    if small:
        counts = {entry["lead_time_days"]: entry["n_cases"] for entry in series}
        listed = ", ".join(f"lead {lead} ({counts[lead]} cases)" for lead in small)
        add(f"- **Small samples.** Fewer than {SMALL_SAMPLE} cases: {listed}. The scores of these leads are in the "
            "table above, but a skill value from so few cases is not a validation.")
    else:
        add(f"- Sample sizes: every lead has at least {SMALL_SAMPLE} cases, between "
            f"{min(entry['n_cases'] for entry in series)} and {max(entry['n_cases'] for entry in series)}. "
            "Consecutive days are not independent, so the effective sample is smaller than the count.")
    add(f"- **Proxy rows.** {len(proxies)} of the {len(result['criteria_evaluated'])} evaluated rows are flagged "
        f"PROXY: {', '.join(proxies)}. The event that is verified is defined by the proxy set, not by any vehicle's "
        "launch commit criteria.")
    add("- **Visibility is observed 48.3 km from the site**, at Port Hawkesbury, and "
        f"{gap.get('hours', 0)} of {archive_meta['hours']} archive hours of visibility are filled from "
        f"{gap.get('source', 'no other source')}.")
    add("- **ERA5 route.** Surface fields come from the Open-Meteo ERA5 archive and CAPE from "
        f"{archive_meta['field_sources']['cape']}. Both are the ERA5 reanalysis.")
    add("- The forecast model and the reanalysis are different systems. Part of any forecast error is the "
        "difference between how GFS and ERA5 represent the same quantity, low cloud and gusts above all.")
    add("")
    add("Observed violation frequency of each criterion over the verified days, the check the issue asks for "
        "before a score is accepted (a criterion that is almost never satisfied makes every day look like a "
        "failure and depresses forecast and reference alike):")
    add("")
    add("| Criterion | Days violated |")
    add("|---|---|")
    for key, value in result["observed_violation_frequency"].items():
        add(f"| `{key}` | {100 * value:.1f} % |")
    add("")
    add("## 6. Anti-tuning record")
    add("")
    add(f"The hindcast uses `{result['criteria_version']}` exactly as the operational layer loads it: the checksum "
        "above is the checksum of `data/" + result["criteria_version"] + ".json` at the time of the run, and a test "
        "compares it with the file. The criteria table was revised twice on 3 October 2026, for the reasons logged "
        "in `progress.md` (strict compliance with the issue text; removal of assumed limits), before any hindcast "
        "existed and before any skill number had been computed. Since the first hindcast run no threshold has been "
        "changed. If a threshold is ever changed after this point, both results must be recorded here.")
    add("")
    if review is not None and "calibration" in result:
        out.extend(disposition(result, review))
    return "\n".join(out)
