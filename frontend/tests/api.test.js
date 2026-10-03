import { afterEach, describe, expect, it, vi } from 'vitest';
import {
  API_BASE,
  FIXTURES,
  MODE_LIVE,
  MODE_OFFLINE,
  REQUEST_TIMEOUT_MS,
} from '../src/config.js';
import {
  boot,
  clone,
  fixtureResponseFor,
  flush,
  installFetch,
  installWindowsApi,
  isApiUrl,
  jsonResponse,
  loadExample,
  textOf,
  withRows,
} from './helpers.js';

const STUB = 'windows_response_good_stub.json';
const CLIMATOLOGY = 'windows_response_good_climatology_constraint_fired.json';

function twoWindowResponse() {
  const base = loadExample(STUB);
  const extra = loadExample(CLIMATOLOGY);
  return { ...base, windows: [...base.windows, ...extra.windows] };
}

afterEach(() => {
  document.body.innerHTML = '';
  vi.useRealTimers();
});

describe('F1 API client and state machine', () => {
  it('posts the built request to the configured API base exactly once per input change', async () => {
    const payload = loadExample(STUB);
    const fetchMock = installWindowsApi(() => jsonResponse(payload));
    const { app } = boot();

    app.start();
    await flush();

    expect(fetchMock).toHaveBeenCalledTimes(1);
    expect(fetchMock.mock.calls[0][0]).toBe(`${API_BASE}/windows`);
    const firstBody = JSON.parse(fetchMock.mock.calls[0][1].body);
    expect(firstBody.target.type).toBe('SSO');
    expect(firstBody.site).toBe('canso');
    expect(firstBody.vehicle_profile_id).toBe('cyclone4m');
    expect(Object.keys(firstBody).sort()).toEqual(
      ['date_range', 'include_weather', 'site', 'target', 'vehicle_profile_id'].sort(),
    );

    const targetSelect = document.getElementById('target-type');
    targetSelect.value = 'LEO';
    targetSelect.dispatchEvent(new Event('change', { bubbles: true }));
    await flush();

    expect(fetchMock).toHaveBeenCalledTimes(2);
    expect(JSON.parse(fetchMock.mock.calls[1][1].body).target.type).toBe('LEO');

    app.stop();
  });

  it('populates the store from the mocked response and renders N rows in the table', async () => {
    const payload = twoWindowResponse();
    installWindowsApi(() => jsonResponse(payload));
    const { app } = boot();

    app.start();
    await flush();

    const state = app.store.getState();
    expect(state.mode).toBe(MODE_LIVE);
    expect(state.status).toBe('ready');
    expect(state.engineResponseOrigin).toBe('api');
    expect(state.engineResponse.windows).toHaveLength(payload.windows.length);
    expect(document.querySelectorAll('#window-rows tr[data-liftoff-utc]')).toHaveLength(
      payload.windows.length,
    );

    app.stop();
  });

  it('renders the countdown and the table from the same response object', async () => {
    const payload = twoWindowResponse();
    installWindowsApi(() => jsonResponse(payload));
    const { app } = boot();

    app.start();
    await flush();

    const state = app.store.getState();
    const target = payload.windows.find(
      (row) => Date.parse(row.t_liftoff_utc) > Date.now(),
    );
    expect(app.countdown.targetRow).toBe(target);
    expect(state.engineResponse.windows).toContain(target);
    expect(document.querySelector('#countdown-utc').textContent).toBe(
      `T- ${target.t_liftoff_utc.slice(0, 10)} ${target.t_liftoff_utc.slice(11, 19)}Z`,
    );

    app.stop();
  });

  it('switches to offline_precomputed, loads the five fixtures and shows the banner on fetch failure', async () => {
    const fixture = loadExample(STUB);
    const requested = [];
    installFetch(async (url) => {
      requested.push(String(url));
      if (isApiUrl(url)) {
        throw new TypeError('fetch failed');
      }
      return fixtureResponseFor(url);
    });
    const { app } = boot();

    app.start();
    await flush();

    const state = app.store.getState();
    expect(state.mode).toBe(MODE_OFFLINE);
    expect(state.engineResponseOrigin).toBe('fixture');
    expect(state.engineResponse).toEqual(fixture);
    expect(document.getElementById('mode-banner').hidden).toBe(false);
    expect(textOf('#mode-banner')).toContain('offline_precomputed');
    expect(textOf('#mode-banner')).toContain(fixture.constants_block.citation_id);
    expect(document.querySelectorAll('#window-rows tr[data-liftoff-utc]')).toHaveLength(
      fixture.windows.length,
    );
    for (const file of Object.values(FIXTURES)) {
      expect(requested.some((url) => url.endsWith(file))).toBe(true);
    }
    expect(state.fixtureFailures).toEqual([]);

    app.stop();
  });

  it('switches to offline_precomputed when the request exceeds the configured timeout', async () => {
    vi.useFakeTimers();
    installFetch((url, init) => {
      if (isApiUrl(url)) {
        return new Promise((_resolve, reject) => {
          init.signal.addEventListener('abort', () => {
            reject(new DOMException('The operation was aborted.', 'AbortError'));
          }, { once: true });
        });
      }
      return fixtureResponseFor(url);
    });
    const { app } = boot();

    app.start();
    await vi.advanceTimersByTimeAsync(0);
    expect(app.store.getState().mode).toBe(MODE_LIVE);

    await vi.advanceTimersByTimeAsync(REQUEST_TIMEOUT_MS);

    const state = app.store.getState();
    expect(state.mode).toBe(MODE_OFFLINE);
    expect(state.error).toContain('timed out');
    expect(textOf('#mode-banner')).toContain('offline_precomputed');

    app.stop();
  });

  it('renders the include_weather=false path with null weather fields without crashing', async () => {
    const payload = loadExample(CLIMATOLOGY);
    expect(payload.windows[0].forecast_issue_time).toBeNull();
    const fetchMock = installWindowsApi(() => jsonResponse(payload));
    const { app } = boot();

    app.start();
    await flush();

    const includeWeather = document.getElementById('include-weather');
    includeWeather.checked = false;
    includeWeather.dispatchEvent(new Event('change', { bubbles: true }));
    await flush();

    expect(JSON.parse(fetchMock.mock.calls.at(-1)[1].body).include_weather).toBe(false);
    const row = document.querySelector('#window-rows tr[data-liftoff-utc]');
    expect(row).not.toBeNull();
    expect(row.querySelector('[data-horizon]').getAttribute('data-horizon')).toBe('CLIMATOLOGY');
    expect(row.textContent).toContain('CLIMATOLOGY');
    expect(row.textContent).toContain('no forecast issue time');

    app.stop();
  });

  it('marks a hazard rejected row and refuses it as the countdown target', async () => {
    const rejected = clone(loadExample(STUB).windows[0]);
    rejected.t_liftoff_utc = '2026-10-04T13:42:11Z';
    rejected.t_injection_utc = '2026-10-04T13:47:26Z';
    rejected.constraint_fired = 'hazard_area';
    rejected.screens.hazard = 'fail';
    const payload = withRows(loadExample(STUB), [rejected, loadExample(STUB).windows[0]]);
    installWindowsApi(() => jsonResponse(payload));
    const { app } = boot();

    app.start();
    await flush();

    const rows = document.querySelectorAll('#window-rows tr[data-liftoff-utc]');
    expect(rows).toHaveLength(2);
    expect(rows[0].getAttribute('data-hazard-rejected')).toBe('true');
    expect(rows[0].textContent).toContain('hazard_area');
    expect(rows[1].getAttribute('data-hazard-rejected')).toBe('false');
    expect(app.countdown.targetRow).toBe(payload.windows[1]);

    app.stop();
  });

  it('surfaces an HTTP error status as the reason in the offline banner', async () => {
    installFetch(async (url) => {
      if (isApiUrl(url)) {
        return jsonResponse({ detail: 'engine warming up' }, 503);
      }
      return fixtureResponseFor(url);
    });
    const { app } = boot();

    app.start();
    await flush();

    expect(app.store.getState().mode).toBe(MODE_OFFLINE);
    expect(app.store.getState().error).toContain('HTTP 503');
    expect(textOf('#mode-banner')).toContain('HTTP 503');

    app.stop();
  });
});
