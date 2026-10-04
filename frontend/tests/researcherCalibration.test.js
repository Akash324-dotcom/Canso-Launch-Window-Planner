/** Issue 26, control 4: reliability bins, ROC points and the calibration gap against the 0.15 bound. */
import { afterEach, describe, expect, it } from 'vitest';
import { CALIBRATION_GAP_BOUND, CALIBRATION_MIN_BINS } from '../src/config.js';
import { calibrationGap } from '../src/researcher.js';
import { clone, loadExample } from './helpers.js';
import { SKILL, start } from './researcherHelpers.js';

afterEach(() => {
  document.body.innerHTML = '';
});

function skillWithBins(bins) {
  return { ...clone(loadExample(SKILL)), reliability_bins: bins };
}

// The bins of the committed hindcast (backend/fixtures/skill.json, rounded): gap against the
// bin centres (0.113 + 0.094 + 0.157 + 0.247 + 0.125) / 5 = 0.1472.
const FIVE_BINS = [
  { p_center: 0.05, observed_freq: 0.163, n: 922 },
  { p_center: 0.25, observed_freq: 0.344, n: 343 },
  { p_center: 0.55, observed_freq: 0.393, n: 163 },
  { p_center: 0.75, observed_freq: 0.503, n: 143 },
  { p_center: 0.95, observed_freq: 0.825, n: 114 },
];

describe('researcher layer, calibration', () => {
  it('computes the mean absolute gap between observed frequency and bin centre', () => {
    expect(CALIBRATION_GAP_BOUND).toBe(0.15);
    expect(CALIBRATION_MIN_BINS).toBe(5);
    expect(calibrationGap(FIVE_BINS).gap).toBeCloseTo(0.1472, 4);
    expect(calibrationGap(FIVE_BINS).populated).toBe(5);
    // 0.04, 0.06, 0.06: mean 0.0533
    expect(calibrationGap(loadExample(SKILL).reliability_bins).gap).toBeCloseTo(0.053333, 5);
    expect(calibrationGap([]).gap).toBeNull();
    expect(calibrationGap([{ p_center: 0.5, observed_freq: 0.5, n: 0 }]).populated).toBe(0);
  });

  it('renders the bins and the ROC points of the answer of /v1/validation/skill', async () => {
    const skill = skillWithBins(FIVE_BINS);
    const { app, calls } = await start({ skill: () => skill }, { select: true });

    expect(calls.some((call) => call.url.includes('/validation/skill'))).toBe(true);
    const bins = [...document.querySelectorAll('#analysis-reliability-rows tr[data-p-center]')];
    expect(bins.map((row) => row.getAttribute('data-p-center'))).toEqual(FIVE_BINS.map((bin) => String(bin.p_center)));
    const roc = [...document.querySelectorAll('#analysis-roc-rows tr[data-threshold]')];
    expect(roc.map((row) => row.getAttribute('data-threshold'))).toEqual(skill.roc_points.map((point) => String(point.threshold)));
    expect(roc[1].querySelector('[data-field="pod"]').textContent).toBe(String(skill.roc_points[1].pod));
    app.stop();
  });

  it('shows the gap against the bound and says which reading it is', async () => {
    const { app } = await start({ skill: () => skillWithBins(FIVE_BINS) }, { select: true });
    const node = document.getElementById('analysis-calibration');

    expect(node.getAttribute('data-calibration-state')).toBe('met_bin_centre');
    expect(node.getAttribute('data-gap')).toBe('0.147');
    expect(node.getAttribute('data-populated-bins')).toBe('5');
    const text = node.textContent;
    expect(text).toContain('5 populated bins, at least 5 required: met');
    expect(text).toContain('0.147 against the bound 0.15: at or below the bound');
    expect(text).toContain('This is the reading the response supports');
    expect(text).toContain('mean forecast inside each bin, which GET /v1/validation/skill does not return');
    expect(text).toContain('cannot be computed here');
    app.stop();
  });

  it('says not met when the gap is above the bound, and when the bins are too few', async () => {
    const wide = FIVE_BINS.map((bin) => ({ ...bin, observed_freq: bin.p_center > 0.5 ? bin.p_center - 0.3 : bin.p_center + 0.3 }));
    const first = await start({ skill: () => skillWithBins(wide) }, { select: true });
    let node = document.getElementById('analysis-calibration');
    expect(node.getAttribute('data-calibration-state')).toBe('not_met_bin_centre');
    expect(node.textContent).toContain('0.300 against the bound 0.15: above the bound');
    first.app.stop();
    document.body.innerHTML = '';

    const second = await start({}, { select: true });
    node = document.getElementById('analysis-calibration');
    expect(node.getAttribute('data-calibration-state')).toBe('too_few_bins');
    expect(node.textContent).toContain('3 populated bins, at least 5 required: not met');
    expect(node.textContent).toContain('0.053 against the bound 0.15');
    second.app.stop();
  });

  it('shows the absent state without a skill answer', async () => {
    const { app } = await start();
    const node = document.getElementById('analysis-calibration');

    expect(node.getAttribute('data-calibration-state')).toBe('no_answer');
    expect(node.textContent).toBe('No reliability bins loaded, so no calibration gap is computed.');
    app.stop();
  });
});
