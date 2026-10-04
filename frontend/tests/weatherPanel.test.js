import { readFileSync } from 'node:fs';
import path from 'node:path';
import { pathToFileURL } from 'node:url';
import { afterEach, describe, expect, it } from 'vitest';
import { WEATHER_THRESHOLDS } from '../src/config.js';
import { weatherBand } from '../src/weatherBands.js';
import {
  boot,
  clone,
  flush,
  installContractApi,
  jsonResponse,
  loadExample,
  textOf,
} from './helpers.js';

const STUB = 'windows_response_good_stub.json';
const SITE = 'site_response_good_canso_verified_corridor.json';
const EPHEMERIS = 'ephemeris_response_good_leo45.json';
const SKILL = 'skill_response_good_brier_skill_series.json';
const FORECAST = 'weather_probability_response_good_forecast.json';
const CLIMATOLOGY = 'weather_probability_response_good_climatology_ensemble_null.json';

const STYLES_URL = new URL('styles.css', pathToFileURL(`${process.cwd()}${path.sep}`));

async function settle() {
  await flush();
  await flush();
}

function contractHandler(weather, response = loadExample(STUB)) {
  return (url) => {
    const target = String(url);
    if (target.endsWith('/windows')) {
      return jsonResponse(clone(response));
    }
    if (target.includes('/ephemeris')) {
      return jsonResponse(loadExample(EPHEMERIS));
    }
    if (target.includes('/site')) {
      return jsonResponse(loadExample(SITE));
    }
    if (target.includes('/weather/probability')) {
      return jsonResponse(clone(weather));
    }
    if (target.includes('/validation/skill')) {
      return jsonResponse(loadExample(SKILL));
    }
    return jsonResponse({ detail: 'unrouted' }, 404);
  };
}

async function startWithWeather(exampleName) {
  const fetchMock = installContractApi(contractHandler(loadExample(exampleName)));
  const { app } = boot();
  app.start();
  await settle();
  document.querySelectorAll('#window-rows tr[data-liftoff-utc]')[0].dispatchEvent(
    new Event('click', { bubbles: true }),
  );
  await settle();
  return { app, fetchMock };
}

afterEach(() => {
  document.body.innerHTML = '';
});

describe('F4 screen 3 weather panel', () => {
  it('styles the CLIMATOLOGY badge differently from the FORECAST badge', async () => {
    const forecast = await startWithWeather(FORECAST);
    const forecastBadge = document.getElementById('weather-launch-horizon-badge');
    const forecastClass = forecastBadge.getAttribute('class');
    const forecastStyle = forecastBadge.getAttribute('data-horizon-style');
    expect(forecastBadge.getAttribute('data-horizon')).toBe('FORECAST');
    expect(forecastClass).toContain('badge-forecast');
    expect(forecastStyle).toBe('forecast');
    expect(textOf('#weather-launch-indicator')).toContain('issued 09:00Z, 3 Oct 2026');
    forecast.app.stop();

    const climatology = await startWithWeather(CLIMATOLOGY);
    const climatologyBadge = document.getElementById('weather-launch-horizon-badge');
    expect(climatologyBadge.getAttribute('data-horizon')).toBe('CLIMATOLOGY');
    const climatologyStyle = climatologyBadge.getAttribute('data-horizon-style');
    expect(climatologyStyle).toBe('climatology');
    expect(climatologyStyle).not.toBe(forecastStyle);
    const climatologyClass = climatologyBadge.getAttribute('class');
    expect(climatologyClass).toContain('badge-climatology');
    expect(climatologyClass).not.toBe(forecastClass);

    const styles = readFileSync(STYLES_URL, 'utf8');
    const forecastRule = styles.slice(styles.indexOf('.badge-forecast {'));
    const climatologyRule = styles.slice(styles.indexOf('.badge-climatology {'));
    expect(forecastRule.slice(0, forecastRule.indexOf('}'))).not.toBe(
      climatologyRule.slice(0, climatologyRule.indexOf('}')),
    );
    expect(climatologyRule).toContain('dashed');
    expect(forecastRule).toContain('var(--ok)');

    climatology.app.stop();
  });

  it('renders the hindcast skill curve as an inline SVG series with N points', async () => {
    const skill = loadExample(SKILL);
    const { app } = await startWithWeather(FORECAST);

    const chart = document.querySelector('#weather-skill-curve');
    expect(chart).not.toBeNull();
    expect(chart.tagName.toLowerCase()).toBe('svg');
    expect(chart.querySelectorAll('script')).toHaveLength(0);

    const points = [...chart.querySelectorAll('circle[data-lead-time-days]')];
    expect(points).toHaveLength(skill.skill_series.length);
    expect(chart.getAttribute('data-point-count')).toBe(String(skill.skill_series.length));
    skill.skill_series.forEach((entry, index) => {
      expect(points[index].getAttribute('data-lead-time-days')).toBe(String(entry.lead_time_days));
      expect(points[index].getAttribute('data-bss')).toBe(String(entry.bss));
      expect(points[index].getAttribute('data-n-cases')).toBe(String(entry.n_cases));
    });
    expect(chart.querySelector('polyline.chart-line').getAttribute('data-point-count')).toBe(
      String(skill.skill_series.length),
    );
    expect(
      chart.querySelector('line[data-measured-skill-horizon-days]').getAttribute(
        'data-measured-skill-horizon-days',
      ),
    ).toBe(String(skill.skill_horizon_measured_days));
    expect(chart.querySelectorAll('image')).toHaveLength(0);
    expect(textOf('#weather-skill-note')).toContain(skill.base_rate.toString());
    expect(textOf('#weather-skill-note')).toContain(skill.verification_source);
    expect(textOf('#weather-skill-note')).toContain(skill.skill_horizon_measured_days.toString());

    app.stop();
  });

  it('puts the probability number, the horizon badge and the issue time beside the colour', async () => {
    const weather = loadExample(FORECAST);
    const { app } = await startWithWeather(FORECAST);

    const rowBlock = document.getElementById('weather-row-indicator-block');
    const row = loadExample(STUB).windows[0];
    expect(rowBlock.getAttribute('data-band')).toBe('YELLOW');
    expect(rowBlock.querySelector('.indicator-probability').getAttribute('data-probability')).toBe(
      String(row.p_success_components.weather),
    );
    expect(rowBlock.textContent).toContain('62.0%');
    expect(rowBlock.textContent).toContain(row.horizon_label);
    expect(rowBlock.textContent).toContain('issued 09:00Z, 3 Oct 2026');

    const launchBlock = document.getElementById('weather-launch-indicator-block');
    expect(launchBlock.getAttribute('data-band')).toBe(weatherBand(weather.p_launch).band);
    expect(launchBlock.querySelector('.indicator-value').textContent).toBe('58.0%');
    expect(textOf('#weather-thresholds')).toContain('ASSUMPTION');
    expect(textOf('#weather-thresholds')).toContain('0.70');
    expect(textOf('#weather-thresholds')).toContain('0.40');
    expect(textOf('#weather-thresholds')).toContain(WEATHER_THRESHOLDS.source);

    app.stop();
  });

  it('bands every probability of the frozen examples from the configured thresholds', async () => {
    expect(weatherBand(WEATHER_THRESHOLDS.green_min).band).toBe('GREEN');
    expect(weatherBand(0.6999).band).toBe('YELLOW');
    expect(weatherBand(WEATHER_THRESHOLDS.yellow_min).band).toBe('YELLOW');
    expect(weatherBand(0.3999).band).toBe('RED');
    expect(weatherBand(null).band).toBe('GREY');
    expect(weatherBand(null).label).toBe('no probability available');

    const { app } = await startWithWeather(FORECAST);
    expect(document.getElementById('screen-weather').getAttribute('data-bands')).toBe('YELLOW,YELLOW');
    app.stop();
  });

  it('lists every criterion with its VERIFIED or PROXY flag on expand', async () => {
    const weather = loadExample(FORECAST);
    const { app } = await startWithWeather(FORECAST);

    const details = document.getElementById('weather-criteria');
    expect(details.tagName.toLowerCase()).toBe('details');
    expect(details.open).toBe(false);

    const rows = [...document.querySelectorAll('#weather-criteria-rows tr[data-criterion-id]')];
    expect(rows).toHaveLength(weather.components.length);
    weather.components.forEach((component, index) => {
      expect(rows[index].getAttribute('data-criterion-id')).toBe(component.criterion_id);
      expect(rows[index].querySelector('[data-p-violation]').getAttribute('data-p-violation')).toBe(
        String(component.p_violation),
      );
      const flag = rows[index].querySelector('[data-flag]');
      expect(flag.getAttribute('data-flag')).toBe(component.flag);
      expect(flag.getAttribute('class')).toContain(
        component.flag === 'VERIFIED' ? 'badge-verified' : 'badge-proxy',
      );
    });

    details.open = true;
    expect(details.open).toBe(true);
    expect(textOf('#weather-criteria')).toContain('VERIFIED');
    expect(textOf('#weather-criteria')).toContain('PROXY');

    app.stop();
  });

  it('renders the grey no-probability state instead of a colour when the row carries none', async () => {
    const response = loadExample(STUB);
    delete response.windows[0].p_success_components.weather;
    installContractApi(contractHandler(loadExample(FORECAST), response));
    const { app } = boot();

    app.start();
    await settle();
    document.querySelectorAll('#window-rows tr[data-liftoff-utc]')[0].dispatchEvent(
      new Event('click', { bubbles: true }),
    );
    await settle();

    const block = document.getElementById('weather-row-indicator-block');
    expect(block.getAttribute('data-band')).toBe('GREY');
    expect(block.textContent).toContain('no probability available');
    expect(textOf('#weather-honesty')).toContain('no probability at all');

    app.stop();
  });
});