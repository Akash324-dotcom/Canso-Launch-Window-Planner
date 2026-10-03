import { afterEach, describe, expect, it, vi } from 'vitest';
import { FIXTURES, MODE_LIVE, MODE_OFFLINE } from '../src/config.js';
import { weatherBand } from '../src/weatherBands.js';
import {
  boot,
  clone,
  flush,
  installFetch,
  isApiUrl,
  loadCentresDocument,
  loadFixtureFile,
  textOf,
} from './helpers.js';

const FIXTURE_NAMES = Object.values(FIXTURES);

/**
 * The five shipped fixtures and the population centre file, read from the repository
 * the way the browser reads them over the static file server.
 */
function repositoryFiles() {
  const files = new Map(FIXTURE_NAMES.map((name) => [name, loadFixtureFile(name)]));
  files.set('centres.json', loadCentresDocument());
  return files;
}

function jsonReply(body) {
  return {
    ok: true,
    status: 200,
    async json() {
      return clone(body);
    },
  };
}

/**
 * The network is blocked: every URL under the API base is refused the way a browser
 * refuses it when the server is down, and only a repository file can answer. This is
 * the F7 condition, not a stub of the fixture loader.
 */
function installBlockedNetwork() {
  const files = repositoryFiles();
  const blocked = [];
  const fetchMock = installFetch(async (url) => {
    const target = String(url);
    if (isApiUrl(target)) {
      blocked.push(target);
      throw new TypeError('fetch failed: the network is blocked in this test');
    }
    const file = target.split('/').pop();
    if (!files.has(file)) {
      blocked.push(target);
      throw new TypeError(`fetch failed: ${target} is not a repository file`);
    }
    return jsonReply(files.get(file));
  });
  return { fetchMock, blocked, files };
}

/**
 * The same five documents served by the live path, so the two runs of the comparison
 * test differ only in where the bytes came from.
 */
function installLiveNetwork() {
  const files = repositoryFiles();
  const fetchMock = installFetch(async (url) => {
    const target = String(url);
    if (isApiUrl(target)) {
      if (target.includes('/weather/probability')) {
        return jsonReply(files.get(FIXTURES.weather));
      }
      if (target.includes('/validation/skill')) {
        return jsonReply(files.get(FIXTURES.skill));
      }
      if (target.includes('/ephemeris')) {
        return jsonReply(files.get(FIXTURES.ephemeris));
      }
      if (target.includes('/site')) {
        return jsonReply(files.get(FIXTURES.site));
      }
      if (target.endsWith('/windows')) {
        return jsonReply(files.get(FIXTURES.windows));
      }
      return jsonReply({ detail: 'unrouted' });
    }
    const file = target.split('/').pop();
    if (!files.has(file)) {
      throw new TypeError(`fetch failed: ${target} is not a repository file`);
    }
    return jsonReply(files.get(file));
  });
  return { fetchMock, files };
}

async function settle() {
  await flush();
  await flush();
  await flush();
}

function structureSignature(node) {
  const parts = [];
  const walk = (current) => {
    for (const child of current.children) {
      parts.push(`${child.tagName.toLowerCase()}${child.id === '' ? '' : `#${child.id}`}`);
      walk(child);
    }
  };
  walk(node);
  return parts.join('|');
}

function renderedRows() {
  return [...document.querySelectorAll('#window-rows tr[data-liftoff-utc]')].map((row) =>
    [...row.children].map((cell) => cell.textContent.replace(/\s+/g, ' ').trim()),
  );
}

function screenSignatures() {
  return {
    windowEngine: structureSignature(document.getElementById('screen-window-engine')),
    trajectory: structureSignature(document.getElementById('screen-trajectory')),
    weather: structureSignature(document.getElementById('screen-weather')),
    viewing: structureSignature(document.getElementById('screen-viewing')),
    analysis: structureSignature(document.getElementById('screen-analysis')),
  };
}

afterEach(() => {
  document.body.innerHTML = '';
  vi.useRealTimers();
});

describe('F7 offline fallback', () => {
  it('loads with the network blocked, renders every screen, runs the countdown and shows the banner', async () => {
    const windows = loadFixtureFile(FIXTURES.windows);
    const skill = loadFixtureFile(FIXTURES.skill);
    const weather = loadFixtureFile(FIXTURES.weather);
    const site = loadFixtureFile(FIXTURES.site);
    const ephemeris = loadFixtureFile(FIXTURES.ephemeris);
    vi.useFakeTimers();
    vi.setSystemTime(new Date('2026-10-03T12:00:00Z'));
    const { fetchMock, blocked } = installBlockedNetwork();
    const { app } = boot();

    app.start();
    await vi.advanceTimersByTimeAsync(0);
    await vi.advanceTimersByTimeAsync(0);

    const state = app.store.getState();
    expect(blocked.length).toBeGreaterThan(0);
    expect(state.mode).toBe(MODE_OFFLINE);
    expect(state.status).toBe('degraded');
    expect(state.engineResponseOrigin).toBe('fixture');
    expect(state.engineResponse).toEqual(windows);
    expect(state.fixtureFailures).toEqual([]);

    for (const file of FIXTURE_NAMES) {
      expect(fetchMock.mock.calls.some((call) => String(call[0]).endsWith(file))).toBe(true);
    }

    const banner = document.getElementById('mode-banner');
    expect(banner.hidden).toBe(false);
    expect(textOf('#mode-banner')).toContain('OFFLINE PRECOMPUTED DATA');
    expect(textOf('#mode-banner')).toContain(MODE_OFFLINE);
    expect(textOf('#mode-banner')).toContain(windows.constants_block.citation_id);
    expect(textOf('#mode-banner')).toContain(FIXTURES.windows);
    expect(textOf('#mode-banner')).toContain('fetch failed');

    const rows = [...document.querySelectorAll('#window-rows tr[data-liftoff-utc]')];
    expect(rows.map((row) => row.getAttribute('data-liftoff-utc'))).toEqual(
      windows.windows.map((row) => row.t_liftoff_utc),
    );
    expect(document.getElementById('constants-footer').hidden).toBe(false);
    expect(textOf('#constants-body')).toContain(String(windows.constants_block.J2));
    expect(textOf('#window-table-sub')).toContain(`${windows.windows.length} windows returned`);

    rows[0].dispatchEvent(new Event('click', { bubbles: true }));
    await vi.advanceTimersByTimeAsync(0);
    await vi.advanceTimersByTimeAsync(0);

    const selected = app.store.getState();
    expect(selected.ephemerisOrigin).toBe('fixture');
    expect(selected.siteOrigin).toBe('fixture');
    expect(selected.weatherOrigin).toBe('fixture');
    expect(selected.skillOrigin).toBe('fixture');
    for (const file of FIXTURE_NAMES) {
      expect(textOf('#mode-banner')).toContain(file);
      expect(fetchMock.mock.calls.some((call) => String(call[0]).endsWith(file))).toBe(true);
    }
    expect(selected.ephemerisResponse).toEqual(ephemeris);
    expect(selected.siteResponse).toEqual(site);
    expect(selected.weatherResponse).toEqual(weather);
    expect(selected.skillResponse).toEqual(skill);
    expect(selected.centres).toEqual(loadCentresDocument().centres);

    expect(document.querySelectorAll('#trajectory-track li[data-track-point]')).toHaveLength(
      ephemeris.points.length,
    );
    expect(document.getElementById('corridor-check').getAttribute('data-available')).toBe('true');
    expect(document.querySelectorAll('#trajectory-centres li[data-centre-id]')).toHaveLength(
      selected.centres.length,
    );
    expect(document.getElementById('weather-skill-curve')).not.toBeNull();
    expect(document.querySelectorAll('#weather-skill-curve circle[data-lead-time-days]')).toHaveLength(
      skill.skill_series.length,
    );
    expect(document.getElementById('weather-launch-indicator-block').getAttribute('data-band')).toBe(
      weatherBand(weather.p_launch).band,
    );
    expect(document.getElementById('weather-launch-horizon-badge').getAttribute('data-horizon')).toBe(
      weather.horizon_label,
    );
    expect(
      document.querySelectorAll('#weather-criteria-rows tr[data-criterion-id]'),
    ).toHaveLength(weather.components.length);
    expect(document.querySelectorAll('#viewing-rows tr[data-centre-id]')).toHaveLength(
      selected.centres.length,
    );
    expect(document.querySelectorAll('#analysis-skill-rows tr[data-lead-time-days]')).toHaveLength(
      skill.skill_series.length,
    );
    expect(document.querySelectorAll('#analysis-reliability-rows tr[data-p-center]')).toHaveLength(
      skill.reliability_bins.length,
    );
    expect(document.querySelectorAll('#analysis-roc-rows tr[data-threshold]')).toHaveLength(
      skill.roc_points.length,
    );
    expect(document.getElementById('analysis-reliability-diagram')).not.toBeNull();
    expect(document.getElementById('analysis-config-hash').textContent).toContain(
      windows.constants_block.citation_id,
    );
    expect(document.querySelectorAll('#analysis-source-files li[data-source-file]')).toHaveLength(
      windows.provenance_block.source_files.length,
    );

    const target = app.countdown.targetRow;
    expect(target).toEqual(windows.windows[0]);
    expect(textOf('#countdown-utc')).toBe(
      `T- ${target.t_liftoff_utc.slice(0, 10)} ${target.t_liftoff_utc.slice(11, 19)}Z`,
    );
    expect(textOf('#countdown-value-text')).toBe('1d 23:42:17');
    await vi.advanceTimersByTimeAsync(2000);
    expect(textOf('#countdown-value-text')).toBe('1d 23:42:15');
    expect(textOf('#countdown-atlantic')).toContain('ADT');

    app.stop();
  });

  it('renders the same element tree as the live path, one renderer and two sources', async () => {
    installLiveNetwork();
    const live = boot();
    live.app.start();
    await settle();
    document.querySelectorAll('#window-rows tr[data-liftoff-utc]')[0].dispatchEvent(
      new Event('click', { bubbles: true }),
    );
    await settle();
    const liveState = live.app.store.getState();
    const liveSignatures = screenSignatures();
    const liveRows = renderedRows();
    expect(liveState.mode).toBe(MODE_LIVE);
    expect(liveState.engineResponseOrigin).toBe('api');
    expect(liveState.ephemerisOrigin).toBe('api');
    live.app.stop();
    document.body.innerHTML = '';

    const { blocked } = installBlockedNetwork();
    const offline = boot();
    offline.app.start();
    await settle();
    document.querySelectorAll('#window-rows tr[data-liftoff-utc]')[0].dispatchEvent(
      new Event('click', { bubbles: true }),
    );
    await settle();
    const offlineState = offline.app.store.getState();
    const offlineSignatures = screenSignatures();
    const offlineRows = renderedRows();

    expect(offlineState.mode).toBe(MODE_OFFLINE);
    expect(offlineState.engineResponseOrigin).toBe('fixture');
    expect(offlineState.ephemerisOrigin).toBe('fixture');
    expect(blocked.length).toBeGreaterThan(0);
    expect(offlineState.engineResponse).toEqual(liveState.engineResponse);
    expect(offlineState.siteResponse).toEqual(liveState.siteResponse);
    expect(offlineState.weatherResponse).toEqual(liveState.weatherResponse);
    expect(offlineState.skillResponse).toEqual(liveState.skillResponse);
    expect(offlineSignatures).toEqual(liveSignatures);
    expect(offlineRows).toEqual(liveRows);
    expect(document.getElementById('mode-banner').hidden).toBe(false);
    for (const file of FIXTURE_NAMES) {
      expect(textOf('#mode-banner')).toContain(file);
    }

    offline.app.stop();
  });
});