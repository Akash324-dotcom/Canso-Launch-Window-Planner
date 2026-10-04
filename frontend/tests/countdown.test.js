import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { MODE_OFFLINE } from '../src/config.js';
import {
  boot,
  fixtureResponseFor,
  installFetch,
  installWindowsApi,
  isApiUrl,
  jsonResponse,
  loadExample,
  textOf,
  withLiftoffShifted,
} from './helpers.js';

const STUB = 'windows_response_good_stub.json';
const NO_WINDOWS = 'windows_response_good_reachable_no_windows.json';
const UNREACHABLE = 'windows_response_good_unreachable.json';

beforeEach(() => {
  vi.useFakeTimers();
  vi.setSystemTime(new Date('2026-10-03T12:00:00Z'));
});

afterEach(() => {
  document.body.innerHTML = '';
  vi.useRealTimers();
});

async function startWith(exampleName) {
  installWindowsApi(() => jsonResponse(loadExample(exampleName)));
  const { app } = boot();
  app.start();
  await vi.advanceTimersByTimeAsync(0);
  return app;
}

describe('F2 countdown', () => {
  it('renders the remaining time, the absolute UTC instant and the Atlantic instant', async () => {
    const app = await startWith(STUB);

    expect(textOf('#countdown-value')).toBe('2d 01:42:11');
    expect(textOf('#countdown-utc')).toBe('T- 2026-10-05 13:42:11Z');
    expect(textOf('#countdown-atlantic')).toBe('10:42 ADT, Oct 5');

    app.stop();
  });

  it('renders "No window in range" with the reason when the windows array is empty', async () => {
    const app = await startWith(NO_WINDOWS);

    expect(app.store.getState().engineResponse.windows).toEqual([]);
    expect(textOf('#countdown-value')).toBe('No window in range');
    expect(textOf('#countdown-reason')).toContain('No crossing of the target plane');
    expect(document.getElementById('countdown-reason').hidden).toBe(false);
    expect(document.getElementById('honesty-panel').hidden).toBe(true);

    app.stop();
  });

  it('shows the penalty panel and the constants when the target is unreachable', async () => {
    const app = await startWith(UNREACHABLE);
    const response = loadExample(UNREACHABLE);

    expect(response.reachable).toBe(false);
    expect(textOf('#countdown-value')).toBe('No window in range');
    expect(textOf('#countdown-reason')).toContain('not reachable');

    const panel = document.getElementById('honesty-panel');
    expect(panel.hidden).toBe(false);
    expect(textOf('#honesty-plane-change-dv-ms')).toBe(`${response.plane_change_dv_ms} m/s`);

    const footer = document.getElementById('constants-footer');
    expect(footer.hidden).toBe(false);
    expect(textOf('#constants-body')).toContain(String(response.constants_block.J2));
    expect(textOf('#constants-body')).toContain(String(response.constants_block.GM));
    expect(textOf('#constants-body')).toContain(String(response.constants_block.R_e));
    expect(textOf('#constants-body')).toContain(response.constants_block.citation_id);
    expect(textOf('#constants-body')).toContain(response.constants_block.source.J2);

    app.stop();
  });

  it('changes the countdown value when the fetched target changes', async () => {
    let payload = loadExample(STUB);
    installWindowsApi(() => jsonResponse(payload));
    const { app } = boot();

    app.start();
    await vi.advanceTimersByTimeAsync(0);
    const before = textOf('#countdown-value');
    const beforeIso = textOf('#countdown-utc');
    expect(before).toBe('2d 01:42:11');

    await vi.advanceTimersByTimeAsync(1000);
    expect(textOf('#countdown-value')).toBe('2d 01:42:10');

    payload = withLiftoffShifted(payload, 3 * 86400000);
    await app.dispatch();

    expect(textOf('#countdown-value')).toBe('5d 01:42:10');
    expect(textOf('#countdown-utc')).not.toBe(beforeIso);
    expect(app.countdown.targetRow).toBe(app.store.getState().engineResponse.windows[0]);
    expect(app.store.getState().engineResponse.windows[0].t_liftoff_utc).toBe(
      payload.windows[0].t_liftoff_utc,
    );

    app.stop();
  });

  it('stops counting when the launch time passes and does not loop', async () => {
    vi.setSystemTime(new Date('2026-10-05T13:40:00Z'));
    const app = await startWith(STUB);

    expect(textOf('#countdown-value')).toBe('00:02:11');

    await vi.advanceTimersByTimeAsync(132000);

    const passed = textOf('#countdown-value');
    expect(passed).toBe('Liftoff time passed');
    expect(textOf('#countdown-reason')).toContain('2026-10-05 13:42:11Z');

    await vi.advanceTimersByTimeAsync(60000);
    expect(textOf('#countdown-value')).toBe(passed);

    app.stop();
  });

  it('keeps the last fetched target through a backend outage', async () => {
    let fail = false;
    installFetch(async (url) => {
      if (isApiUrl(url)) {
        if (fail) {
          throw new TypeError('fetch failed');
        }
        return jsonResponse(loadExample(STUB));
      }
      return fixtureResponseFor(url);
    });
    const { app } = boot();

    app.start();
    await vi.advanceTimersByTimeAsync(0);
    const before = textOf('#countdown-value');
    const rowsBefore = document.querySelectorAll('#window-rows tr[data-liftoff-utc]').length;
    expect(before).toBe('2d 01:42:11');

    fail = true;
    await vi.advanceTimersByTimeAsync(1000);
    await app.dispatch();

    expect(app.store.getState().mode).toBe(MODE_OFFLINE);
    expect(app.store.getState().engineResponseOrigin).toBe('api_stale');
    expect(textOf('#mode-banner')).toContain('offline_precomputed');
    expect(textOf('#countdown-stale')).toContain('last fetched target');
    expect(textOf('#countdown-value')).toBe('2d 01:42:10');
    expect(document.querySelectorAll('#window-rows tr[data-liftoff-utc]')).toHaveLength(rowsBefore);
    expect(app.countdown.targetRow.t_liftoff_utc).toBe('2026-10-05T13:42:11Z');

    app.stop();
  });
});
