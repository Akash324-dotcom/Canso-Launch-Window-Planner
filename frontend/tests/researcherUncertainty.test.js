/** Issue 26, control 7: no probability without its ensemble size, issue time and horizon label. */
import { afterEach, describe, expect, it } from 'vitest';
import { clone, loadExample, textOf } from './helpers.js';
import { FORECAST, SKILL, STUB, change, settle, start } from './researcherHelpers.js';

afterEach(() => {
  document.body.innerHTML = '';
});

describe('researcher layer, uncertainty beside every probability', () => {
  it('states label and issue time for the p_success column and that the window response has no ensemble size', async () => {
    const response = loadExample(STUB);
    const { app, posts } = await start({ windows: () => response });
    const node = document.getElementById('window-uncertainty');

    expect(posts()).toHaveLength(1);
    expect(node.getAttribute('data-horizon-labels')).toBe('FORECAST');
    const text = node.textContent;
    expect(text).toContain('horizon_label FORECAST');
    expect(text).toContain('forecast_issue_time 2026-10-03T09:00:00Z');
    expect(text).toContain('The ensemble size N is not a field of the window response');
    app.stop();
  });

  it('lists every label and issue time that occurs when the rows differ', async () => {
    const response = clone(loadExample(STUB));
    response.windows = [
      response.windows[0],
      { ...clone(response.windows[0]), t_liftoff_utc: '2026-10-20T13:42:11Z', t_injection_utc: '2026-10-20T13:47:26Z', horizon_label: 'CLIMATOLOGY', forecast_issue_time: null },
    ];
    const { app } = await start({ windows: () => response });
    const node = document.getElementById('window-uncertainty');

    expect(node.getAttribute('data-horizon-labels')).toBe('FORECAST,CLIMATOLOGY');
    expect(node.textContent).toContain('1 row(s) FORECAST');
    expect(node.textContent).toContain('1 row(s) CLIMATOLOGY');
    expect(node.textContent).toContain('no forecast issue time on 1 row(s)');
    app.stop();
  });

  it('says that p_success holds no weather probability when the weather layer is excluded', async () => {
    const excluded = clone(loadExample(STUB));
    for (const row of excluded.windows) {
      row.p_success_components.weather = 1.0;
      row.horizon_label = 'CLIMATOLOGY';
      row.forecast_issue_time = null;
    }
    const { app, posts } = await start({ windows: (body) => (body.include_weather === false ? excluded : loadExample(STUB)) });
    expect(textOf('#window-uncertainty')).not.toContain('include_weather false');

    change('include-weather', false);
    await settle();

    expect(posts().at(-1).body.include_weather).toBe(false);
    const text = textOf('#window-uncertainty');
    expect(text).toContain('The request excluded the weather layer (include_weather false)');
    expect(text).toContain('p_success above holds no weather probability');
    expect(text).toContain('horizon_label CLIMATOLOGY');
    app.stop();
  });

  it('puts the ensemble size of the weather answer beside the probability of the selected row', async () => {
    // The stub row lifts off on 2026-10-05 and the weather example is for 2026-10-05, 51 members.
    const weather = loadExample(FORECAST);
    const { app, calls } = await start({}, { select: true });
    const node = document.getElementById('weather-row-uncertainty');

    expect(calls.some((call) => call.url.includes('/weather/probability'))).toBe(true);
    expect(node.getAttribute('data-ensemble-size')).toBe(String(weather.ensemble_size));
    expect(node.textContent).toContain(`ensemble size N ${weather.ensemble_size}`);
    expect(node.textContent).toContain(`GET /v1/weather/probability for ${weather.date}`);
    app.stop();
  });

  it('does not borrow an ensemble size from an answer for another date', async () => {
    const other = { ...clone(loadExample(FORECAST)), date: '2026-12-01' };
    const { app } = await start({ weather: () => other }, { select: true });
    const node = document.getElementById('weather-row-uncertainty');

    expect(node.getAttribute('data-ensemble-size')).toBe('');
    expect(node.textContent).toContain('ensemble size N not available for this row');
    expect(node.textContent).toContain('2026-12-01');
    app.stop();
  });

  it('states N, issue time and label for the per-criterion shares', async () => {
    const weather = loadExample(FORECAST);
    const { app } = await start({}, { select: true });
    const text = textOf('#weather-criteria-uncertainty');

    expect(text).toContain(`horizon_label ${weather.horizon_label}`);
    expect(text).toContain(`forecast_issue_time ${weather.forecast_issue_time}`);
    expect(text).toContain(`ensemble size N ${weather.ensemble_size}`);
    app.stop();
  });

  it('says that a CLIMATOLOGY answer has no ensemble and no issue time', async () => {
    const climatology = { ...clone(loadExample(FORECAST)), horizon_label: 'CLIMATOLOGY', forecast_issue_time: null, ensemble_size: null };
    const { app } = await start({ weather: () => climatology }, { select: true });
    const text = textOf('#weather-criteria-uncertainty');

    expect(text).toContain('horizon_label CLIMATOLOGY');
    expect(text).toContain('forecast_issue_time null');
    expect(text).toContain('ensemble size N null');
    app.stop();
  });

  it('states the period and the sample behind the base rate', async () => {
    const skill = loadExample(SKILL);
    const { app } = await start({}, { select: true });
    const text = textOf('#analysis-base-rate');

    expect(text).toContain(`base_rate ${skill.base_rate}`);
    expect(text).toContain(`${skill.period.start} to ${skill.period.end}`);
    expect(text).toContain('not an ensemble probability');
    app.stop();
  });
});
