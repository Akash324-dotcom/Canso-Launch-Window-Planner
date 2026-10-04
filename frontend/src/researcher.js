/**
 * The researcher layer of issue 26: what a reader needs to trust and reuse a number.
 *
 * Every function here derives its result from a response object of the service and from
 * nothing else. Where the service does not carry what a statement would need, the function
 * returns an absent state and the page says so; no value is filled in.
 */
import { CALIBRATION_GAP_BOUND, CALIBRATION_MIN_BINS } from './config.js';

/** Mean absolute difference between observed frequency and bin centre over the populated bins. */
export function calibrationGap(bins) {
  const populated = (Array.isArray(bins) ? bins : []).filter((bin) => Number(bin.n) > 0);
  if (populated.length === 0) {
    return { gap: null, populated: 0 };
  }
  const total = populated.reduce(
    (sum, bin) => sum + Math.abs(Number(bin.observed_freq) - Number(bin.p_center)),
    0,
  );
  return { gap: total / populated.length, populated: populated.length };
}

/**
 * Spec III.4 criterion 2 as far as the skill response supports it. The response gives the
 * centre of each bin, not the mean forecast inside it, so only the bin-centre reading can be
 * computed; the state names that reading, and the gate verdict is left to the hindcast report.
 */
export function calibrationState(skillResponse) {
  if (skillResponse === null || skillResponse === undefined || !Array.isArray(skillResponse.reliability_bins)) {
    return { state: 'no_answer', gap: null, populated: 0, text: 'No reliability bins loaded, so no calibration gap is computed.' };
  }
  const { gap, populated } = calibrationGap(skillResponse.reliability_bins);
  if (gap === null) {
    return { state: 'no_bins', gap: null, populated: 0, text: 'The skill answer holds no populated reliability bin, so no calibration gap is computed.' };
  }
  const enough = populated >= CALIBRATION_MIN_BINS;
  const within = gap <= CALIBRATION_GAP_BOUND;
  const state = !enough ? 'too_few_bins' : within ? 'met_bin_centre' : 'not_met_bin_centre';
  const text =
    `Calibration, spec III.4 criterion 2. ${populated} populated bins, at least ${CALIBRATION_MIN_BINS} required: ` +
    `${enough ? 'met' : 'not met'}. Mean absolute difference between observed_freq and p_center over the populated ` +
    `bins: ${gap.toFixed(3)} against the bound ${CALIBRATION_GAP_BOUND}: ${within ? 'at or below the bound' : 'above the bound'}. ` +
    'This is the reading the response supports. The verdict of gate G2 uses the mean forecast inside each bin, which ' +
    'GET /v1/validation/skill does not return, so that verdict cannot be computed here; it is recorded in ' +
    'backend/weather/HINDCAST.md.';
  return { state, gap, populated, text };
}

/**
 * The claim the skill series supports, with the period and the sample behind it. The skill
 * response has no claim status field, so the label is SKETCHED, the default the issue sets.
 */
export function skillClaim(skillResponse) {
  const series = Array.isArray(skillResponse?.skill_series) ? skillResponse.skill_series : [];
  if (skillResponse === null || skillResponse === undefined || series.length === 0) {
    return { status: '', nMin: null, nMax: null, pairs: null, horizon: null, text: 'No skill series loaded, so no claim is stated.' };
  }
  const counts = series.map((entry) => Number(entry.n_cases));
  const nMin = Math.min(...counts);
  const nMax = Math.max(...counts);
  const pairs = counts.reduce((sum, value) => sum + value, 0);
  const positive = series.filter((entry) => Number(entry.bss) > 0).map((entry) => entry.lead_time_days);
  const rest = series.filter((entry) => !(Number(entry.bss) > 0)).map((entry) => entry.lead_time_days);
  const horizon = skillResponse.skill_horizon_measured_days ?? null;
  const period = skillResponse.period ?? {};
  let reading;
  if (positive.length === 0) {
    reading = 'BSS is at or below zero at every lead';
  } else if (rest.length === 0) {
    reading = `BSS above zero at every lead (${positive.join(', ')})`;
  } else {
    reading = `BSS above zero at leads ${positive.join(', ')} and at or below zero at leads ${rest.join(', ')}`;
  }
  const text =
    `Claim status SKETCHED. Hindcast ${period.start} to ${period.end}, ${series.length} lead times, n_cases ${nMin} to ` +
    `${nMax} per lead, ${pairs} forecast and outcome pairs; verification ${skillResponse.verification_source}, reference ` +
    `${skillResponse.reference_forecast}. ${reading}. Measured skill horizon ` +
    `${horizon === null ? 'null in this response' : `${Number(horizon)} days`} (skill_horizon_measured_days). ` +
    'The response carries no claim status field, so the label is SKETCHED, the default for a hindcast of one period; ' +
    'a narrower label would have to come from the service.';
  return { status: 'SKETCHED', nMin, nMax, pairs, horizon: horizon === null ? null : Number(horizon), text };
}

/** How many criteria of a weather answer carry each flag. */
export function flagCounts(components) {
  const rows = Array.isArray(components) ? components : [];
  const counts = {};
  for (const row of rows) {
    counts[String(row.flag)] = (counts[String(row.flag)] ?? 0) + 1;
  }
  return { total: rows.length, verified: counts.VERIFIED ?? 0, proxy: counts.PROXY ?? 0, counts };
}

/** The horizon labels and issue times that stand behind the p_success column of the window table. */
export function windowUncertainty(rows) {
  const list = Array.isArray(rows) ? rows : [];
  const labels = [];
  const counts = {};
  const issues = [];
  let withoutIssue = 0;
  for (const row of list) {
    const label = String(row.horizon_label);
    if (!labels.includes(label)) {
      labels.push(label);
    }
    counts[label] = (counts[label] ?? 0) + 1;
    if (row.forecast_issue_time === null || row.forecast_issue_time === undefined) {
      withoutIssue += 1;
    } else if (!issues.includes(row.forecast_issue_time)) {
      issues.push(row.forecast_issue_time);
    }
  }
  return { labels, counts, issues, withoutIssue, rows: list.length };
}
