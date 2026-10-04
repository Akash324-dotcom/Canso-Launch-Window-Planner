/** Issue 26, control 3: Brier skill by lead with n_cases, the measured horizon, and the claim status. */
import { afterEach, describe, expect, it } from 'vitest';
import { clone, loadExample, textOf } from './helpers.js';
import { SKILL, start } from './researcherHelpers.js';

afterEach(() => {
  document.body.innerHTML = '';
});

describe('researcher layer, skill display', () => {
  it('asks /v1/validation/skill and lists BSS and n_cases for every lead of the answer', async () => {
    const skill = loadExample(SKILL);
    const { app, calls } = await start({}, { select: true });

    const call = calls.find((entry) => entry.url.includes('/validation/skill'));
    expect(new URL(call.url).searchParams.get('period_start')).toBe(skill.period.start);
    const rows = [...document.querySelectorAll('#analysis-skill-rows tr[data-lead-time-days]')];
    expect(rows.map((row) => row.getAttribute('data-lead-time-days'))).toEqual(skill.skill_series.map((entry) => String(entry.lead_time_days)));
    skill.skill_series.forEach((entry, index) => {
      expect(rows[index].querySelector('[data-field="bss"]').textContent).toBe(String(entry.bss));
      expect(rows[index].querySelector('[data-field="n_cases"]').textContent).toBe(String(entry.n_cases));
    });
    app.stop();
  });

  it('labels the claim SKETCHED and states the period and the sample size behind it', async () => {
    // The example: leads 1, 5 and 9 with 96, 96 and 72 cases, 264 pairs; BSS 0.489, 0.13, -0.065; horizon 8.
    const skill = loadExample(SKILL);
    const { app } = await start({}, { select: true });
    const claim = document.getElementById('analysis-skill-claim');

    expect(claim.getAttribute('data-claim-status')).toBe('SKETCHED');
    expect(claim.getAttribute('data-n-min')).toBe('72');
    expect(claim.getAttribute('data-n-max')).toBe('96');
    expect(claim.getAttribute('data-pairs')).toBe('264');
    expect(claim.getAttribute('data-horizon-days')).toBe('8');
    const text = claim.textContent;
    expect(text).toContain('Claim status SKETCHED');
    expect(text).toContain(`${skill.period.start} to ${skill.period.end}`);
    expect(text).toContain('n_cases 72 to 96 per lead');
    expect(text).toContain('264 forecast and outcome pairs');
    expect(text).toContain('Measured skill horizon 8 days');
    expect(text).toContain('BSS above zero at leads 1, 5');
    expect(text).toContain('at or below zero at leads 9');
    expect(text).toContain('The response carries no claim status field');
    app.stop();
  });

  it('follows the answer: another series gives another claim', async () => {
    const other = clone(loadExample(SKILL));
    other.period = { start: '2026-04-02', end: '2026-09-27' };
    other.skill_horizon_measured_days = null;
    other.skill_series = [
      { lead_time_days: 1, bs: 0.3, bs_ref: 0.2, bss: -0.5, n_cases: 20 },
      { lead_time_days: 2, bs: 0.3, bs_ref: 0.2, bss: -0.5, n_cases: 18 },
    ];
    const { app } = await start({ skill: () => other }, { select: true });
    const claim = document.getElementById('analysis-skill-claim');

    expect(claim.getAttribute('data-horizon-days')).toBe('');
    expect(claim.getAttribute('data-pairs')).toBe('38');
    expect(claim.textContent).toContain('2026-04-02 to 2026-09-27');
    expect(claim.textContent).toContain('Measured skill horizon null in this response');
    expect(claim.textContent).toContain('BSS is at or below zero at every lead');
    expect(claim.textContent).toContain('n_cases 18 to 20 per lead');
    app.stop();
  });

  it('shows the absent state before any skill answer exists', async () => {
    const { app } = await start();
    const claim = document.getElementById('analysis-skill-claim');

    expect(claim.getAttribute('data-claim-status')).toBe('');
    expect(textOf('#analysis-skill-claim')).toBe('No skill series loaded, so no claim is stated.');
    app.stop();
  });
});
