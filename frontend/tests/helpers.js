import { readFileSync } from 'node:fs';
import path from 'node:path';
import { pathToFileURL } from 'node:url';
import { vi } from 'vitest';
import { API_BASE, FIXTURES } from '../src/config.js';
import { createApp } from '../src/app.js';

const PROJECT_ROOT = pathToFileURL(`${process.cwd()}${path.sep}`);
const EXAMPLES_DIR = new URL('../tests/contract/examples/good/', PROJECT_ROOT);
const INDEX_URL = new URL('index.html', PROJECT_ROOT);

export const FIXTURE_EXAMPLES = {
  [FIXTURES.windows]: 'windows_response_good_stub.json',
  [FIXTURES.weather]: 'weather_probability_response_good_forecast.json',
  [FIXTURES.skill]: 'skill_response_good_brier_skill_series.json',
  [FIXTURES.site]: 'site_response_good_canso_verified_corridor.json',
  [FIXTURES.ephemeris]: 'ephemeris_response_good_leo45.json',
};

export function loadExample(fileName) {
  return JSON.parse(readFileSync(new URL(fileName, EXAMPLES_DIR), 'utf8'));
}

export function jsonResponse(body, status = 200) {
  return {
    ok: status >= 200 && status < 300,
    status,
    async json() {
      return body;
    },
  };
}

export function isApiUrl(url) {
  return String(url).startsWith(API_BASE);
}

export function fixtureResponseFor(url) {
  const file = String(url).split('/').pop();
  const exampleName = FIXTURE_EXAMPLES[file];
  if (exampleName === undefined) {
    return jsonResponse({ detail: 'no example registered for this fixture' }, 404);
  }
  return jsonResponse(loadExample(exampleName));
}

export function installFetch(handler) {
  const fetchMock = vi.fn(handler);
  globalThis.fetch = fetchMock;
  return fetchMock;
}

export function installWindowsApi(handler) {
  return installFetch(async (url, init) => {
    if (isApiUrl(url)) {
      return handler(url, init);
    }
    return fixtureResponseFor(url);
  });
}

export function mountIndexMarkup() {
  const html = readFileSync(INDEX_URL, 'utf8');
  const body = html.match(/<body[^>]*>([\s\S]*)<\/body>/i);
  document.body.innerHTML = body === null ? html : body[1];
  return {
    root: document.getElementById('screen-window-engine'),
    bannerHost: document.getElementById('mode-banner'),
  };
}

export function boot(overrides = {}) {
  const { root, bannerHost } = mountIndexMarkup();
  const app = createApp({ root, bannerHost, ...overrides });
  return { app, root, bannerHost };
}

export function flush() {
  return new Promise((resolve) => {
    setTimeout(resolve, 0);
  });
}

export function textOf(selector) {
  const node = document.querySelector(selector);
  return node === null ? null : node.textContent.replace(/\s+/g, ' ').trim();
}

export function clone(value) {
  return JSON.parse(JSON.stringify(value));
}

export function withLiftoffShifted(example, shiftMs) {
  const response = clone(example);
  for (const row of response.windows) {
    const shifted = new Date(Date.parse(row.t_liftoff_utc) + shiftMs).toISOString();
    row.t_liftoff_utc = shifted;
    row.t_injection_utc = new Date(Date.parse(row.t_injection_utc) + shiftMs).toISOString();
  }
  return response;
}

export function withRows(example, rows) {
  const response = clone(example);
  response.windows = clone(rows);
  return response;
}

export function withRowFlags(example, rowFlags) {
  const response = clone(example);
  response.provenance_block.row_flags = { ...rowFlags };
  return response;
}
