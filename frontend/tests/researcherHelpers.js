/**
 * Shared set-up for the researcher layer tests (issue 26): a mock of the /v1 service that
 * records every call and answers from the frozen contract examples, unless a test hands in
 * its own answer. Nothing here is a fixture of backend/fixtures.
 */
import { vi } from 'vitest';
import { boot, clone, flush, installContractApi, jsonResponse, loadExample } from './helpers.js';

export const STUB = 'windows_response_good_stub.json';
export const SITE = 'site_response_good_canso_verified_corridor.json';
export const EPHEMERIS = 'ephemeris_response_good_leo45.json';
export const SKILL = 'skill_response_good_brier_skill_series.json';
export const FORECAST = 'weather_probability_response_good_forecast.json';

export async function settle() {
  await flush();
  await flush();
  await flush();
}

/**
 * `answers` may hold `windows(body, url)`, `citation(url)`, `skill(url)`, `weather(url)`:
 * each returns the body to send, or a `jsonResponse` for a status other than 200.
 */
export function service(answers = {}) {
  const calls = [];
  const reply = (value) => (value !== null && typeof value === 'object' && typeof value.json === 'function' ? value : jsonResponse(clone(value)));
  const handler = (url, init) => {
    const target = String(url);
    const body = init !== undefined && init.body !== undefined ? JSON.parse(init.body) : null;
    calls.push({ url: target, method: init?.method ?? 'GET', body });
    if (target.endsWith('/windows')) {
      return reply(answers.windows === undefined ? loadExample(STUB) : answers.windows(body, target));
    }
    if (target.includes('/citation')) {
      return answers.citation === undefined ? jsonResponse({ detail: 'unknown run' }, 404) : reply(answers.citation(target));
    }
    if (target.includes('/ephemeris')) {
      return reply(loadExample(EPHEMERIS));
    }
    if (target.includes('/site')) {
      return reply(loadExample(SITE));
    }
    if (target.includes('/weather/probability')) {
      return reply(answers.weather === undefined ? loadExample(FORECAST) : answers.weather(target));
    }
    if (target.includes('/validation/skill')) {
      const query = new URL(target).searchParams;
      if (!query.has('period_start') || !query.has('period_end')) {
        return jsonResponse({ error: 'request_schema_violation' }, 422);
      }
      return reply(answers.skill === undefined ? loadExample(SKILL) : answers.skill(target));
    }
    return jsonResponse({ detail: 'unrouted' }, 404);
  };
  return { handler, calls, posts: () => calls.filter((call) => call.method === 'POST' && call.url.endsWith('/windows')) };
}

export async function start(answers = {}, { select = false } = {}) {
  const mock = service(answers);
  installContractApi(mock.handler);
  const booted = boot();
  booted.app.start();
  await settle();
  if (select) {
    selectRow(0);
    await settle();
  }
  return { ...booted, ...mock };
}

export function selectRow(index) {
  document.querySelectorAll('#window-rows tr[data-liftoff-utc]')[index].dispatchEvent(new Event('click', { bubbles: true }));
}

export function change(id, value) {
  const node = document.getElementById(id);
  if (node.type === 'checkbox') {
    node.checked = value;
  } else {
    node.value = value;
  }
  node.dispatchEvent(new Event('change', { bubbles: true }));
}

export function displayedRows() {
  return [...document.querySelectorAll('#window-rows tr[data-liftoff-utc]')];
}

/** What a click on a download button hands to the browser: file name and text. */
export function captureDownloads() {
  const files = [];
  const blobs = [];
  globalThis.URL.createObjectURL = vi.fn((blob) => {
    blobs.push(blob);
    return `blob:researcher-${blobs.length}`;
  });
  globalThis.URL.revokeObjectURL = vi.fn();
  const listener = (event) => {
    const anchor = event.target;
    if (anchor.tagName !== 'A' || !anchor.hasAttribute('download')) {
      return;
    }
    event.preventDefault();
    files.push({ filename: anchor.download, blob: blobs[blobs.length - 1] });
  };
  document.addEventListener('click', listener, true);
  return {
    files,
    async text(index) {
      return files[index].blob.text();
    },
    release() {
      document.removeEventListener('click', listener, true);
    },
  };
}

export function citationRecord(windowsResponse, extra = {}) {
  return {
    citation_id: windowsResponse.constants_block.citation_id,
    run_id: windowsResponse.constants_block.citation_id,
    config_hash: 'ce4fb5178ec2b5ea272a736ec630505cd0f00e919aa5d2046378d5d0c10d4a3a',
    generated_at: '2026-10-04T11:25:22Z',
    constants: { J2: 0.00108262668, GM: 398600441800000, R_e: 6378137, omega_sid_rad_s: 0.00007292115, gmst_model: 'IAU_1982' },
    constants_sources: { J2: 'citation source of J2' },
    criteria_version: 'v1',
    engine_version: 'engine-0.1.0',
    source_files: ['backend/api/data/constants.json', 'backend/api/data/service.json'],
    vehicle_profile_id: 'cyclone4m',
    vehicle_rows: [{ key: 't_to_inj_s', flag: 'ASSUMPTION', source: 'not published' }],
    ...extra,
  };
}
