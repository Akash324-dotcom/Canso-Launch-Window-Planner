/**
 * Regression tests for the defects the browser walk found against a running API
 * (real Chrome, the shipped page, main plus the CORS change). Each test names the walk
 * item it guards. The walk itself is recorded in frontend/BROWSER_WALK.md.
 */
import { readFileSync } from 'node:fs';
import path from 'node:path';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { FIXTURES, MODE_LIVE, MODE_OFFLINE, TRACK_START_TOLERANCE_KM } from '../src/config.js';
import { corridorCheck } from '../src/geo.js';
import {
  boot,
  clone,
  flush,
  installContractApi,
  jsonResponse,
  loadExample,
  textOf,
  withLiftoffShifted,
} from './helpers.js';

const STUB = 'windows_response_good_stub.json';
const UNREACHABLE = 'windows_response_good_unreachable.json';
const SITE = 'site_response_good_canso_verified_corridor.json';
const EPHEMERIS = 'ephemeris_response_good_leo45.json';
const SKILL = 'skill_response_good_brier_skill_series.json';
const FORECAST = 'weather_probability_response_good_forecast.json';

afterEach(() => {
  document.body.innerHTML = '';
  vi.useRealTimers();
});

async function settle() {
  await flush();
  await flush();
  await flush();
}

function selectFirstRow() {
  document.querySelectorAll('#window-rows tr[data-liftoff-utc]')[0].dispatchEvent(
    new Event('click', { bubbles: true }),
  );
}

/** The API as the walk met it: the skill endpoint refuses a request without a period. */
function liveApi(overrides = {}) {
  const calls = [];
  const handler = (url) => {
    const target = String(url);
    calls.push(target);
    if (target.endsWith('/windows')) {
      return jsonResponse(clone(overrides.windows ?? loadExample(STUB)));
    }
    if (target.includes('/citation')) {
      return overrides.citation === undefined
        ? jsonResponse({ detail: 'unknown run' }, 404)
        : overrides.citation(target);
    }
    if (target.includes('/ephemeris')) {
      return jsonResponse(clone(overrides.ephemeris ?? loadExample(EPHEMERIS)));
    }
    if (target.includes('/site')) {
      return jsonResponse(clone(loadExample(SITE)));
    }
    if (target.includes('/weather/probability')) {
      return jsonResponse(clone(loadExample(FORECAST)));
    }
    if (target.includes('/validation/skill')) {
      const query = new URL(target).searchParams;
      if (!query.has('period_start') || !query.has('period_end')) {
        return jsonResponse({ error: 'request_schema_violation', violations: ['/period_start: Field required'] }, 422);
      }
      return jsonResponse(clone(loadExample(SKILL)));
    }
    return jsonResponse({ detail: 'unrouted' }, 404);
  };
  return { handler, calls };
}

describe('walk items 5 and 6: the skill series comes from a live response', () => {
  it('asks for the verification period of the recorded hindcast, so the request is not refused', async () => {
    const { handler, calls } = liveApi();
    installContractApi(handler);
    const { app, bannerHost } = boot();
    app.start();
    await settle();
    selectFirstRow();
    await settle();

    const recorded = loadExample(SKILL).period;
    const skillCall = calls.find((url) => url.includes('/validation/skill'));
    const query = new URL(skillCall).searchParams;
    expect(query.get('period_start')).toBe(recorded.start);
    expect(query.get('period_end')).toBe(recorded.end);

    const state = app.store.getState();
    expect(state.skillOrigin).toBe('api');
    expect(state.mode).toBe(MODE_LIVE);
    expect(bannerHost.hidden).toBe(true);
    expect(document.querySelectorAll('#analysis-skill-rows tr[data-lead-time-days], #analysis-skill-rows tr').length).toBe(
      loadExample(SKILL).skill_series.length,
    );
    expect(textOf('#analysis-skill-note')).toContain(`period_start=${recorded.start}`);

    app.stop();
  });
});

describe('walk item 6: the constants of the analysis view come from GET /v1/citation', () => {
  function citationFor(response) {
    return {
      citation_id: response.constants_block.citation_id,
      run_id: response.constants_block.citation_id,
      config_hash: 'ce4fb5178ec2b5ea272a736ec630505cd0f00e919aa5d2046378d5d0c10d4a3a',
      constants: { J2: 0.00108262668, GM: 398600441800000, R_e: 6378137, omega_sid_rad_s: 0.00007292115, gmst_model: 'IAU_1982' },
      constants_sources: { J2: 'citation source of J2', GM: 'citation source of GM' },
      criteria_version: 'v1',
      engine_version: 'engine-0.1.0',
      source_files: ['backend/api/data/constants.json'],
    };
  }

  it('requests the citation of the run and shows its config hash and constants', async () => {
    const windows = loadExample(STUB);
    const { handler, calls } = liveApi({ citation: () => jsonResponse(citationFor(windows)) });
    installContractApi(handler);
    const { app } = boot();
    app.start();
    await settle();

    const citationCall = calls.find((url) => url.includes('/citation'));
    expect(new URL(citationCall).searchParams.get('id')).toBe(windows.constants_block.citation_id);
    expect(app.store.getState().citationOrigin).toBe('api');

    const hash = textOf('#analysis-config-hash');
    expect(hash).toContain('ce4fb5178ec2b5ea272a736ec630505cd0f00e919aa5d2046378d5d0c10d4a3a');
    expect(hash).toContain('GET /v1/citation');
    expect(hash).not.toContain('Config hash, that is constants_block.citation_id');
    const body = textOf('#analysis-provenance-body');
    expect(body).toContain('citation source of J2');
    expect(document.getElementById('analysis-provenance-body').getAttribute('data-constants-origin')).toBe('citation');

    app.stop();
  });

  it('says so, and invents no config hash, when the citation cannot be read', async () => {
    const { handler } = liveApi();
    installContractApi(handler);
    const { app, bannerHost } = boot();
    app.start();
    await settle();

    const hash = textOf('#analysis-config-hash');
    expect(hash).toContain('GET /v1/citation did not answer for this run (HTTP 404)');
    expect(hash).toContain('no config hash is shown');
    expect(document.getElementById('analysis-provenance-body').getAttribute('data-constants-origin')).toBe('windows_response');
    expect(bannerHost.hidden).toBe(true);

    app.stop();
  });

  it('does not show an answer that is not the record of this run', async () => {
    const { handler } = liveApi({ citation: () => jsonResponse({ detail: 'unrouted' }) });
    installContractApi(handler);
    const { app } = boot();
    app.start();
    await settle();

    expect(app.store.getState().citationOrigin).toBeNull();
    expect(textOf('#analysis-config-hash')).toContain('the answer is not the stored record of this run');
    expect(document.getElementById('analysis-provenance-body').getAttribute('data-constants-origin')).toBe('windows_response');

    app.stop();
  });

  it('does not ask for a citation in offline mode, where no run was stored', async () => {
    const calls = [];
    installContractApi((url) => {
      calls.push(String(url));
      throw new TypeError('Failed to fetch');
    });
    const { app } = boot();
    app.start();
    await settle();

    expect(app.store.getState().mode).toBe(MODE_OFFLINE);
    expect(calls.filter((url) => url.includes('/citation'))).toHaveLength(0);
    expect(textOf('#analysis-config-hash')).toContain(`offline fixture ${FIXTURES.windows}`);

    app.stop();
  });
});

describe('walk item 11: no statement on the page that nothing produced', () => {
  it('reads the T_to_inj flag from the citation record instead of saying the vehicle file does not exist', async () => {
    const windows = loadExample(STUB);
    const record = {
      citation_id: windows.constants_block.citation_id,
      config_hash: 'ce4fb5178ec2b5ea272a736ec630505cd0f00e919aa5d2046378d5d0c10d4a3a',
      constants: { J2: 0.00108262668 },
      constants_sources: {},
      vehicle_profile_id: 'cyclone4m',
      vehicle_rows: [
        { key: 'ascent_profile.first_motion_s', flag: 'VERIFIED', source: 'user guide table 2.2' },
        { key: 't_to_inj_s', flag: 'ASSUMPTION', source: 'Not published. Derived from the section 2.5.2 timeline' },
      ],
    };
    const { handler } = liveApi({ citation: () => jsonResponse(record) });
    installContractApi(handler);
    const { app } = boot();
    app.start();
    await settle();

    const note = textOf('#analysis-duration-note');
    expect(note).not.toContain('does not exist on this branch');
    expect(note).toContain('t_to_inj_s is flagged ASSUMPTION');
    expect(note).toContain('Not published. Derived from the section 2.5.2 timeline');
    expect(note).toContain('vehicle_rows of GET /v1/citation');

    app.stop();
  });

  it('says where the flag would come from when no citation record is available', async () => {
    const { handler } = liveApi();
    installContractApi(handler);
    const { app } = boot();
    app.start();
    await settle();

    const note = textOf('#analysis-duration-note');
    expect(note).not.toContain('does not exist on this branch');
    expect(note).toContain('no citation record is available for this run, so no flag is shown');

    app.stop();
  });
});

describe('walk item 3: an unreachable target that still has rows', () => {
  it('does not say the window list is empty when the engine returned rows stopped by the corridor', async () => {
    const response = clone(loadExample(STUB));
    response.reachable = false;
    response.plane_change_dv_ms = null;
    for (const row of response.windows) {
      row.constraint_fired = 'hazard_area';
      row.screens = { ...row.screens, hazard: 'fail' };
    }
    const { handler } = liveApi({ windows: response });
    installContractApi(handler);
    const { app } = boot();
    app.start();
    await settle();

    const explanation = textOf('#honesty-explanation');
    expect(document.getElementById('honesty-panel').hidden).toBe(false);
    expect(explanation).not.toContain('window list is empty');
    expect(explanation).toContain(`${response.windows.length} window row(s)`);
    expect(explanation).toContain('hazard_area');
    expect(textOf('#honesty-plane-change-dv-ms')).toBe('null in this response');

    app.stop();
  });

  it('keeps the plane change and the empty-list wording for a target with no rows', async () => {
    const response = loadExample(UNREACHABLE);
    const { handler } = liveApi({ windows: response });
    installContractApi(handler);
    const { app } = boot();
    app.start();
    await settle();

    expect(response.windows).toHaveLength(0);
    expect(textOf('#honesty-explanation')).toContain('the window list is empty');
    expect(textOf('#honesty-plane-change-dv-ms')).toBe(`${response.plane_change_dv_ms} m/s`);

    app.stop();
  });
});

describe('walk item 8: the corridor guard', () => {
  const site = loadExample(SITE);
  const ascent = { start: '2026-10-05T13:42:11Z', end: '2026-10-05T13:47:26Z' };
  const at = (iso, lat, lon, alt = 100) => ({ t_utc: iso, lat_deg: lat, lon_deg: lon, alt_km: alt });

  it('accepts the sample on the pad instead of counting it as a violation', () => {
    const check = corridorCheck(site, [
      at('2026-10-05T13:42:11Z', site.phi_s_deg, site.lambda_s_deg, 0),
      at('2026-10-05T13:44:46Z', 45.2779, -60.941),
      at('2026-10-05T13:47:21Z', 45.2558, -60.882),
    ], { ascent });

    expect(check.inside).toBe(true);
    expect(check.violations).toHaveLength(0);
    expect(check.starts_at_site).toBe(true);
  });

  it('checks the ascent of the selected row and leaves the later orbit out', () => {
    const check = corridorCheck(site, [
      at('2026-10-05T13:42:11Z', site.phi_s_deg, site.lambda_s_deg, 0),
      at('2026-10-05T13:44:46Z', 45.2779, -60.941),
      at('2026-10-05T14:30:00Z', -60.0, 20.0, 550),
      at('2026-10-05T15:10:00Z', 70.0, -150.0, 550),
    ], { ascent });

    expect(check.samples).toHaveLength(2);
    expect(check.samples_outside_ascent).toBe(2);
    expect(check.inside).toBe(true);
  });

  it('refuses a track whose sample at the liftoff instant is not at the site', () => {
    // What GET /v1/orbits/sso981/ephemeris returned for a live row during the walk.
    const check = corridorCheck(site, [
      at('2026-10-05T13:42:11Z', -68.238589, 84.408706, 674),
      at('2026-10-05T13:47:11Z', -50.750506, 101.479764, 674),
    ], { ascent });

    expect(check.starts_at_site).toBe(false);
    expect(check.inside).toBe(false);
    expect(check.start_distance_km).toBeGreaterThan(10000);
    expect(TRACK_START_TOLERANCE_KM).toBeGreaterThan(0);
  });

  it('says on the page that such a track is not an ascent from the site', async () => {
    const bogus = clone(loadExample(EPHEMERIS));
    bogus.points = [
      { t_utc: '2026-10-05T13:42:11Z', lat_deg: -68.238589, lon_deg: 84.408706, alt_km: 674 },
      { t_utc: '2026-10-05T13:47:11Z', lat_deg: -50.750506, lon_deg: 101.479764, alt_km: 674 },
    ];
    const { handler } = liveApi({ ephemeris: bogus });
    installContractApi(handler);
    const { app } = boot();
    app.start();
    await settle();
    selectFirstRow();
    await settle();

    const guard = document.getElementById('corridor-check');
    expect(guard.getAttribute('data-inside')).toBe('false');
    expect(guard.getAttribute('data-starts-at-site')).toBe('false');
    expect(guard.textContent).toContain('TRACK REJECTED by the UI');
    expect(guard.textContent).toContain('km from the site at the liftoff instant');
    expect(guard.textContent).not.toContain('Every sample of this track lies inside the corridor');

    app.stop();
  });
});

describe('walk item 2: the countdown keeps ticking', () => {
  it('starts again when a new target arrives after a liftoff time has passed', async () => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date('2026-10-05T13:42:00Z'));
    let response = loadExample(STUB);
    installContractApi((url) => {
      if (String(url).endsWith('/windows')) {
        return jsonResponse(clone(response));
      }
      return jsonResponse({ detail: 'unrouted' }, 404);
    });
    const { app } = boot();
    app.start();
    await vi.advanceTimersByTimeAsync(0);
    expect(textOf('#countdown-value')).toBe('00:00:11');

    await vi.advanceTimersByTimeAsync(15000);
    expect(textOf('#countdown-value')).toBe('Liftoff time passed');

    response = withLiftoffShifted(loadExample(STUB), 3600000);
    await app.dispatch();
    await vi.advanceTimersByTimeAsync(0);
    const first = textOf('#countdown-value');
    expect(first).toMatch(/^\d\d:\d\d:\d\d$/);

    await vi.advanceTimersByTimeAsync(5000);
    expect(textOf('#countdown-value')).not.toBe(first);

    app.stop();
  });
});

describe('walk, control sweep: inputs that reach the service', () => {
  function change(id, value) {
    const node = document.getElementById(id);
    node.value = value;
    node.dispatchEvent(new Event('change', { bubbles: true }));
  }

  it.each(['25:99', '24:00', '10:60', '7:5'])('refuses the impossible local time %s instead of posting it', async (value) => {
    const { handler, calls } = liveApi();
    installContractApi(handler);
    const { app } = boot();
    app.start();
    await settle();
    const before = calls.filter((url) => url.endsWith('/windows')).length;

    change('ltan-hours', value);
    await settle();

    expect(calls.filter((url) => url.endsWith('/windows'))).toHaveLength(before);
    expect(textOf('#input-error')).toContain('ltan_hours must be a local time from 00:00 to 23:59');

    app.stop();
  });

  it.each(['00:00', '6:00', '10:30', '23:59'])('posts the valid local time %s', async (value) => {
    const { handler, calls } = liveApi();
    installContractApi(handler);
    const { app } = boot();
    app.start();
    await settle();
    const before = calls.filter((url) => url.endsWith('/windows')).length;

    change('ltan-hours', value);
    await settle();

    expect(calls.filter((url) => url.endsWith('/windows'))).toHaveLength(before + 1);
    expect(textOf('#input-error') ?? '').toBe('');

    app.stop();
  });

  it('says that the weather layer is excluded when include_weather is off', async () => {
    const excluded = clone(loadExample(STUB));
    for (const row of excluded.windows) {
      row.p_success_components.weather = 1.0;
      row.p_success = row.p_success_components.range * row.p_success_components.conjunction;
      row.horizon_label = 'CLIMATOLOGY';
      row.forecast_issue_time = null;
    }
    const { handler } = liveApi({ windows: excluded });
    installContractApi(handler);
    const { app } = boot();
    app.start();
    await settle();
    expect(textOf('#window-table-sub')).not.toContain('weather layer is excluded');

    const box = document.getElementById('include-weather');
    box.checked = false;
    box.dispatchEvent(new Event('change', { bubbles: true }));
    await settle();

    const sub = textOf('#window-table-sub');
    expect(sub).toContain('The weather layer is excluded from this request (include_weather false)');
    expect(sub).toContain('p_success is the product of the range and conjunction components only');
    expect(sub).toContain('not a climatological probability');

    app.stop();
  });
});

describe('walk: console errors of the shipped page', () => {
  it('declares its icon, so the browser does not ask the static server for /favicon.ico', () => {
    const html = readFileSync(path.join(process.cwd(), 'index.html'), 'utf8');

    expect(html).toMatch(/<link rel="icon" href="data:,"\s*\/>/);
  });
});
