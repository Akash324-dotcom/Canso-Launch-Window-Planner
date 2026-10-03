import { readFileSync } from 'node:fs';
import path from 'node:path';
import { pathToFileURL } from 'node:url';
import { vi } from 'vitest';
import { API_BASE, CENTRES_FILE, FIXTURES } from '../src/config.js';
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

export const CENTRES_URL_PART = CENTRES_FILE;

export function loadExample(fileName) {
  return JSON.parse(readFileSync(new URL(fileName, EXAMPLES_DIR), 'utf8'));
}

/**
 * The shipped offline fixture as it sits in backend/fixtures, read from disk. F7 uses
 * this loader so that the offline tests exercise the files the browser would read, not
 * the frozen contract examples.
 */
export function loadFixtureFile(name) {
  return JSON.parse(readFileSync(new URL(`../backend/fixtures/${name}`, PROJECT_ROOT), 'utf8'));
}

export function loadCentresDocument() {
  return JSON.parse(readFileSync(new URL('src/data/centres.json', PROJECT_ROOT), 'utf8'));
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
  if (file === CENTRES_URL_PART) {
    return jsonResponse(loadCentresDocument());
  }
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

/**
 * Routes every GET of the /v1 contract to handler(url), and every fixture and data file
 * read to the frozen examples. The handler receives the URL so a test can answer an
 * ephemeris request differently per window row.
 */
export function installContractApi(handler) {
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
    trajectoryHost: document.getElementById('screen-trajectory'),
    weatherHost: document.getElementById('screen-weather'),
    viewingHost: document.getElementById('screen-viewing'),
    analysisHost: document.getElementById('screen-analysis'),
  };
}

export function boot(overrides = {}) {
  const { root, bannerHost, trajectoryHost, weatherHost, viewingHost, analysisHost } = mountIndexMarkup();
  const app = createApp({
    root,
    bannerHost,
    trajectoryHost,
    weatherHost,
    viewingHost,
    analysisHost,
    ...overrides,
  });
  return { app, root, bannerHost, trajectoryHost, weatherHost, viewingHost, analysisHost };
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
