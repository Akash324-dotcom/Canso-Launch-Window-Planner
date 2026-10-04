/** Issue 26, control 5: per-criterion breakdown with its flags, and the criteria version. */
import { afterEach, describe, expect, it } from 'vitest';
import { clone, loadExample, textOf } from './helpers.js';
import { FORECAST, start } from './researcherHelpers.js';

afterEach(() => {
  document.body.innerHTML = '';
});

describe('researcher layer, criteria transparency', () => {
  it('lists every criterion of the weather answer with its violation share and flag', async () => {
    const weather = loadExample(FORECAST);
    const { app, calls } = await start({}, { select: true });

    expect(calls.some((call) => call.url.includes('/weather/probability'))).toBe(true);
    const rows = [...document.querySelectorAll('#weather-criteria-rows tr[data-criterion-id]')];
    expect(rows.map((row) => row.getAttribute('data-criterion-id'))).toEqual(weather.components.map((entry) => entry.criterion_id));
    weather.components.forEach((entry, index) => {
      expect(rows[index].querySelector('[data-p-violation]').getAttribute('data-p-violation')).toBe(String(entry.p_violation));
      expect(rows[index].querySelector('[data-flag]').getAttribute('data-flag')).toBe(entry.flag);
    });
    app.stop();
  });

  it('counts the VERIFIED and PROXY rows of the answer', async () => {
    // The example: wind_850hPa VERIFIED, lightning_3h PROXY, cloud_ceiling VERIFIED.
    const { app } = await start({}, { select: true });
    const summary = document.getElementById('weather-criteria-summary');

    expect(summary.getAttribute('data-verified')).toBe('2');
    expect(summary.getAttribute('data-proxy')).toBe('1');
    expect(summary.textContent).toContain('3 criteria: 2 VERIFIED, 1 PROXY');
    app.stop();
  });

  it('shows the criteria version of the answer and follows another answer', async () => {
    const other = clone(loadExample(FORECAST));
    other.criteria_version = 'criteria_v1';
    other.components = other.components.map((entry) => ({ ...entry, flag: 'PROXY' }));
    const { app } = await start({ weather: () => other }, { select: true });

    expect(document.getElementById('weather-criteria-summary').getAttribute('data-criteria-version')).toBe('criteria_v1');
    expect(textOf('#weather-criteria-summary')).toContain('criteria version criteria_v1');
    expect(textOf('#weather-criteria-summary')).toContain('3 criteria: 0 VERIFIED, 3 PROXY');
    const select = document.getElementById('criteria-version-select');
    expect([...select.options].map((option) => option.value)).toEqual(['criteria_v1']);
    app.stop();
  });

  it('does not offer a choice of version, because the API offers no list, and says so', async () => {
    const { app } = await start({}, { select: true });
    const select = document.getElementById('criteria-version-select');

    expect(select.disabled).toBe(true);
    expect([...select.options].map((option) => option.value)).toEqual(['v1']);
    expect(textOf('#criteria-version-note')).toContain('The API offers no list of criteria versions');
    expect(textOf('#criteria-version-note')).toContain('cannot be chosen here');
    app.stop();
  });

  it('shows the absent state before a weather answer exists', async () => {
    const { app } = await start();

    expect(textOf('#weather-criteria-summary')).toBe('No weather answer loaded, so no criteria are listed.');
    expect(document.getElementById('criteria-version-select').options).toHaveLength(1);
    expect(document.getElementById('criteria-version-select').options[0].value).toBe('');
    app.stop();
  });
});
