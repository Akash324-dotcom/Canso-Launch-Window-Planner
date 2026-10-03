import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { FIXTURES, WINDOW_TABLE_COLUMNS } from '../src/config.js';
import { cellText, csvRow } from '../src/export.js';
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

function handler(overrides = {}) {
  return (url) => {
    const target = String(url);
    if (target.endsWith('/windows')) {
      return jsonResponse(clone(overrides.response ?? loadExample(STUB)));
    }
    if (target.includes('/ephemeris')) {
      return jsonResponse(clone(loadExample(EPHEMERIS)));
    }
    if (target.includes('/site')) {
      return jsonResponse(clone(loadExample(SITE)));
    }
    if (target.includes('/weather/probability')) {
      return jsonResponse(clone(loadExample(FORECAST)));
    }
    if (target.includes('/validation/skill')) {
      return jsonResponse(clone(loadExample(SKILL)));
    }
    return jsonResponse({ detail: 'unrouted' }, 404);
  };
}

async function settle() {
  await flush();
  await flush();
}

async function startApp(overrides = {}) {
  installContractApi(handler(overrides));
  const booted = boot();
  booted.app.start();
  await settle();
  document.querySelectorAll('#window-rows tr[data-liftoff-utc]')[0].dispatchEvent(
    new Event('click', { bubbles: true }),
  );
  await settle();
  return booted;
}

/**
 * Captures what the download path hands to the browser: the Blob of the anchor href and
 * the anchor attributes, by listening for the click the export dispatches. Calling
 * preventDefault on the event keeps jsdom from trying to navigate to the object URL.
 */
function captureDownloads() {
  const captured = [];
  const blobs = [];
  const createObjectURL = vi.fn((blob) => {
    blobs.push(blob);
    return `blob:canso-${blobs.length}`;
  });
  globalThis.URL.createObjectURL = createObjectURL;
  globalThis.URL.revokeObjectURL = vi.fn();
  const listener = (event) => {
    const anchor = event.target;
    if (anchor.tagName !== 'A') {
      return;
    }
    captured.push({
      tag: anchor.tagName,
      href: anchor.getAttribute('href'),
      download: anchor.getAttribute('download'),
      rel: anchor.getAttribute('rel'),
    });
    event.preventDefault();
  };
  document.addEventListener('click', listener, true);
  return {
    captured,
    blobs,
    createObjectURL,
    stop() {
      document.removeEventListener('click', listener, true);
      delete globalThis.URL.createObjectURL;
      delete globalThis.URL.revokeObjectURL;
    },
  };
}

beforeEach(() => {
  document.body.innerHTML = '';
});

afterEach(() => {
  document.body.innerHTML = '';
});

describe('F6 screen 5 scientific analysis', () => {
  it('produces a download whose rows equal the rendered table', async () => {
    const response = loadExample(STUB);
    const { app } = await startApp({ response });
    const capture = captureDownloads();

    document.getElementById('download-window-csv').dispatchEvent(new Event('click', { bubbles: true }));
    document.getElementById('download-response-json').dispatchEvent(new Event('click', { bubbles: true }));
    const [csvResult, jsonResult] = capture.captured;
    capture.stop();

    expect(csvResult.tag).toBe('A');
    expect(csvResult.download).toBe(`canso-windows-${response.constants_block.citation_id}.csv`);
    expect(csvResult.rel).toBe('noopener');
    expect(capture.createObjectURL).toHaveBeenCalledTimes(2);
    expect(capture.blobs[0].type).toBe('text/csv');
    expect(capture.blobs[1].type).toBe('application/json');

    const csv = await capture.blobs[0].text();
    const lines = csv.split('\n').filter((line) => line !== '');
    const renderedRows = [...document.querySelectorAll('#window-rows tr[data-liftoff-utc]')];
    const renderedHeader = [...document.querySelectorAll('#window-table thead th')].map(cellText);
    expect(lines[0]).toBe(csvRow(renderedHeader));
    expect(renderedHeader).toEqual(WINDOW_TABLE_COLUMNS.map((column) => column.label));
    expect(lines).toHaveLength(renderedRows.length + 1);

    renderedRows.forEach((row, index) => {
      const renderedCells = [...row.children].map(cellText);
      expect(lines[index + 1]).toBe(csvRow(renderedCells));
      expect(renderedCells).toHaveLength(WINDOW_TABLE_COLUMNS.length);
      const window = response.windows[index];
      expect(renderedCells[0]).toContain(window.t_liftoff_utc.slice(0, 10));
      expect(renderedCells[0]).toContain(window.t_liftoff_utc.slice(11, 19));
      expect(renderedCells[1]).toContain(window.t_injection_utc.slice(0, 10));
      expect(renderedCells[1]).toContain(window.t_injection_utc.slice(11, 19));
      expect(renderedCells[2]).toBe(`${window.window_width_s.toFixed(1)} s`);
      expect(renderedCells[3]).toBe(window.azimuth_deg.toFixed(1));
      expect(renderedCells[4]).toBe(window.reached_inclination_deg.toFixed(1));
      expect(renderedCells[5]).toBe(`${(window.p_success * 100).toFixed(1)}%`);
      expect(renderedCells[6]).toContain(window.horizon_label);
      expect(renderedCells[7]).toContain('hazard clear');
    });

    const json = await capture.blobs[1].text();
    expect(JSON.parse(json)).toEqual(response);
    expect(jsonResult.download).toBe(`canso-response-${response.constants_block.citation_id}.json`);
    expect(textOf('#analysis-download-note')).toContain('canso-windows-');
    expect(textOf('#analysis-download-note')).toContain('canso-response-');

    app.stop();
  });

  it('shows every source file the run declared in the provenance panel', async () => {
    const response = loadExample(STUB);
    const { app } = await startApp({ response });

    const panel = document.getElementById('analysis-provenance');
    const listed = [...panel.querySelectorAll('#analysis-source-files li[data-source-file]')];
    expect(listed.map((item) => item.getAttribute('data-source-file'))).toEqual(
      response.provenance_block.source_files,
    );
    for (const file of response.provenance_block.source_files) {
      expect(panel.textContent).toContain(file);
    }

    const body = document.getElementById('analysis-provenance-body');
    expect(body.getAttribute('data-criteria-version')).toBe(response.provenance_block.criteria_version);
    expect(body.getAttribute('data-citation-id')).toBe(response.constants_block.citation_id);
    expect(textOf('#analysis-criteria-version')).toContain(response.provenance_block.criteria_version);
    expect(textOf('#analysis-criteria-version')).toContain(response.provenance_block.vehicle_profile_id);
    expect(textOf('#analysis-config-hash')).toContain(response.constants_block.citation_id);
    expect(textOf('#analysis-config-hash')).toContain(response.constants_block.gmst_model);

    for (const [key, value] of Object.entries(response.constants_block)) {
      if (key === 'source') {
        continue;
      }
      expect(body.textContent).toContain(String(value));
    }
    for (const [key, value] of Object.entries(response.constants_block.source)) {
      expect(body.textContent).toContain(`source of ${key}`);
      expect(body.textContent).toContain(value);
    }
    expect(body.textContent).toContain(response.provenance_block.vehicle_profile_id);
    expect(body.textContent).toContain(response.engine_version);
    expect(body.textContent).toContain(String(response.provenance_block.corridor.A_min_deg));
    expect(body.textContent).toContain(JSON.stringify(response.provenance_block.site));

    app.stop();
  });

  it('surfaces the vehicle duration of every window row', async () => {
    const response = loadExample(STUB);
    const { app } = await startApp({ response });

    const rows = [...document.querySelectorAll('#analysis-duration-rows tr[data-liftoff-utc]')];
    expect(rows).toHaveLength(response.windows.length);
    response.windows.forEach((window, index) => {
      expect(rows[index].getAttribute('data-liftoff-utc')).toBe(window.t_liftoff_utc);
      const cells = [...rows[index].children].map((cell) => cell.getAttribute('data-field'));
      expect(cells).toEqual([
        't_liftoff_utc',
        't_injection_utc',
        'window_center_shift_s',
        'liftoff_instant_error_min',
        'ascent_s',
      ]);
      const values = [...rows[index].children].map((cell) => cell.textContent);
      expect(values[0]).toBe(window.t_liftoff_utc);
      expect(values[1]).toBe(window.t_injection_utc);
      expect(values[2]).toBe(String(window.window_center_shift_s));
      expect(values[3]).toBe(String(window.liftoff_instant_error_min));
      expect(values[4]).toBe(
        ((Date.parse(window.t_injection_utc) - Date.parse(window.t_liftoff_utc)) / 1000).toFixed(1),
      );
    });
    expect(textOf('#analysis-duration-note')).toContain(String(response.windows[0].liftoff_instant_error_min));
    expect(textOf('#analysis-duration-note')).toContain('T_to_inj');

    app.stop();
  });

  it('renders the Brier skill table and chart with the measured skill horizon', async () => {
    const skill = loadExample(SKILL);
    const { app } = await startApp();

    const rows = [...document.querySelectorAll('#analysis-skill-rows tr[data-lead-time-days]')];
    expect(rows).toHaveLength(skill.skill_series.length);
    skill.skill_series.forEach((entry, index) => {
      expect(rows[index].getAttribute('data-lead-time-days')).toBe(String(entry.lead_time_days));
      const cells = [...rows[index].children].map((cell) => cell.getAttribute('data-field'));
      expect(cells).toEqual(['lead_time_days', 'bs', 'bs_ref', 'bss', 'n_cases']);
      [...rows[index].children].forEach((cell, cellIndex) => {
        expect(cell.textContent).toBe(String(entry[['lead_time_days', 'bs', 'bs_ref', 'bss', 'n_cases'][cellIndex]]));
      });
    });

    const chart = document.getElementById('analysis-skill-curve');
    expect(chart.tagName.toLowerCase()).toBe('svg');
    expect(chart.querySelectorAll('circle[data-lead-time-days]')).toHaveLength(skill.skill_series.length);
    expect(
      chart.querySelector('line[data-measured-skill-horizon-days]').getAttribute(
        'data-measured-skill-horizon-days',
      ),
    ).toBe(String(skill.skill_horizon_measured_days));
    expect(textOf('#analysis-skill-note')).toContain(skill.verification_source);
    expect(textOf('#analysis-skill-note')).toContain(String(skill.skill_horizon_measured_days));

    app.stop();
  });

  it('renders the reliability diagram with the perfect reliability diagonal and the ROC points', async () => {
    const skill = loadExample(SKILL);
    const { app } = await startApp();

    const diagram = document.getElementById('analysis-reliability-diagram');
    expect(diagram.tagName.toLowerCase()).toBe('svg');
    expect(diagram.getAttribute('data-series')).toBe('reliability');
    const points = [...diagram.querySelectorAll('circle[data-p-center]')];
    expect(points).toHaveLength(skill.reliability_bins.length);
    skill.reliability_bins.forEach((bin, index) => {
      expect(points[index].getAttribute('data-p-center')).toBe(String(bin.p_center));
      expect(points[index].getAttribute('data-observed-freq')).toBe(String(bin.observed_freq));
      expect(points[index].getAttribute('data-n')).toBe(String(bin.n));
    });
    expect(
      diagram.querySelector('line[data-reference="perfect_reliability"]'),
    ).not.toBeNull();
    expect(diagram.querySelector('line[data-base-rate]').getAttribute('data-base-rate')).toBe(
      String(skill.base_rate),
    );

    const binRows = [...document.querySelectorAll('#analysis-reliability-rows tr[data-p-center]')];
    expect(binRows).toHaveLength(skill.reliability_bins.length);
    const rocRows = [...document.querySelectorAll('#analysis-roc-rows tr[data-threshold]')];
    expect(rocRows).toHaveLength(skill.roc_points.length);
    skill.roc_points.forEach((point, index) => {
      expect(rocRows[index].getAttribute('data-threshold')).toBe(String(point.threshold));
      expect(rocRows[index].textContent).toContain(String(point.pod));
      expect(rocRows[index].textContent).toContain(String(point.far));
    });

    app.stop();
  });

  it('offers the five offline fixture files and states the claim status of the series', async () => {
    const { app } = await startApp();

    const links = [...document.querySelectorAll('#analysis-fixture-links a[data-fixture-file]')];
    expect(links.map((link) => link.getAttribute('data-fixture-file'))).toEqual(Object.values(FIXTURES));
    for (const link of links) {
      expect(link.getAttribute('href')).toBe(`../backend/fixtures/${link.getAttribute('data-fixture-file')}`);
    }
    expect(textOf('#analysis-claims')).toContain('PROVED');
    expect(textOf('#analysis-claims')).toContain('SKETCHED');
    expect(textOf('#analysis-claims')).toContain('CONJECTURE');

    app.stop();
  });
});