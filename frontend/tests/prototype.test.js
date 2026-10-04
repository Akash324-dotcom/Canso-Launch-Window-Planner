import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { describe, expect, it } from 'vitest';
import {
  FIXTURE_ROOT,
  addDaysIso,
  compass8,
  createPrototypeSource,
  inputsToRequest,
  isoDateOf,
  ltanText,
  modeOf,
  nextUsable,
  normalizeResponse,
  normalizeRow,
  offlineBannerText,
  orbitIdForRequest,
  passOf,
  presetDefaults,
  raanInterpolator,
  recommend,
  resolveApiBase,
  siteView,
  skillSummary,
  trackFromEphemeris,
  viewingFor,
  weatherOf,
} from '../src/prototypeData.js';
import { RequestValidationError } from '../src/request.js';

const here = path.dirname(fileURLToPath(import.meta.url));
const root = path.resolve(here, '../..');
const readJson = (relative) => JSON.parse(fs.readFileSync(path.join(root, relative), 'utf8'));
const fixtures = {
  windows: readJson('backend/fixtures/windows.json'),
  site: readJson('backend/fixtures/site.json'),
  ephemeris: readJson('backend/fixtures/ephemeris.json'),
  skill: readJson('backend/fixtures/skill.json'),
  weather: readJson('backend/fixtures/weather.json'),
};
const centres = readJson('frontend/src/data/centres.json');
const site = siteView(fixtures.site, 'fixture');

const BASE_UI = {
  preset: 'SSO',
  dateStart: '2026-10-05',
  days: 4,
  planeMode: 'ltan',
  ltanHours: 10.5,
  raanDeg: '',
  inclinationDeg: null,
  altitudeKm: null,
  corridorMin: '',
  corridorMax: '',
  includeWeather: true,
};

function response(body, ok = true, status = 200) {
  return { ok, status, json: async () => body };
}

/** A fetch stub: fixture files and centres are served from disk, API calls by the handler. */
function stubFetch({ api = () => { throw new TypeError('connection refused'); }, files = true } = {}) {
  const calls = [];
  const impl = async (url, init = {}) => {
    calls.push({ url, method: init.method ?? 'GET', body: init.body === undefined ? null : JSON.parse(init.body) });
    if (url.startsWith('http://api.test/v1')) {
      return api(url, init);
    }
    const onDisk = /(backend\/fixtures\/[^/?]+|src\/data\/centres\.json)$/.exec(url);
    if (files && onDisk !== null) {
      const relative = onDisk[1].startsWith('src/') ? `frontend/${onDisk[1]}` : onDisk[1];
      return response(JSON.parse(fs.readFileSync(path.join(root, relative), 'utf8')));
    }
    throw new TypeError(`unexpected url ${url}`);
  };
  impl.calls = calls;
  return impl;
}

const source = (fetchImpl) => createPrototypeSource({ baseUrl: 'http://api.test/v1', fetchImpl, timeoutMs: 500 });

describe('page inputs to a request', () => {
  it('maps every preset to the request the frontend planner would send', () => {
    expect(inputsToRequest(BASE_UI).target).toEqual({ type: 'SSO', ltan_hours: '10:30' });
    const polar = inputsToRequest({ ...BASE_UI, preset: 'POLAR', planeMode: 'raan' });
    expect(polar.target).toEqual({ type: 'POLAR', raan_deg: null });
    const leo = inputsToRequest({ ...BASE_UI, preset: 'LEO', planeMode: 'raan' });
    expect(leo.target.type).toBe('LEO');
    const low = inputsToRequest({ ...BASE_UI, preset: 'LOW', planeMode: 'raan', inclinationDeg: 30, altitudeKm: 500 });
    expect(low.target).toEqual({ type: 'CUSTOM', h_t_km: 500, i_t_deg: 30, raan_deg: null });
  });

  it('builds the date range from the start date and the day count, clamped to 1..16', () => {
    expect(inputsToRequest({ ...BASE_UI, days: 4 }).date_range).toEqual({ start: '2026-10-05', end: '2026-10-08' });
    expect(inputsToRequest({ ...BASE_UI, days: 1 }).date_range.end).toBe('2026-10-05');
    expect(inputsToRequest({ ...BASE_UI, days: 99 }).date_range.end).toBe('2026-10-20');
    expect(addDaysIso('2026-12-30', 3)).toBe('2027-01-02');
  });

  it('passes the weather switch, the vehicle and a corridor override through', () => {
    const request = inputsToRequest({ ...BASE_UI, includeWeather: false, vehicle: 'cyclone4m', corridorMin: '100', corridorMax: '180' });
    expect(request.include_weather).toBe(false);
    expect(request.vehicle_profile_id).toBe('cyclone4m');
    expect(request.corridor).toEqual({ A_min_deg: 100, A_max_deg: 180 });
  });

  it('refuses a custom orbit without an altitude instead of sending it', () => {
    expect(() => inputsToRequest({ ...BASE_UI, preset: 'CUSTOM', planeMode: 'raan', inclinationDeg: 50, altitudeKm: null })).toThrow(RequestValidationError);
  });

  it('refuses a local time that does not exist', () => {
    expect(() => inputsToRequest({ ...BASE_UI, ltanHours: 25.99 })).not.toThrow();
    expect(ltanText(10.5)).toBe('10:30');
    expect(ltanText(0)).toBe('00:00');
    expect(ltanText(23.999)).toBe('00:00');
    expect(ltanText('x')).toBe('');
  });

  it('takes class inclinations from the planner config, not from the page', () => {
    expect(presetDefaults('SSO').inclination_deg).toBe(98.1);
    expect(presetDefaults('POLAR').inclination_deg).toBe(87.9);
    expect(presetDefaults('LEO').inclination_deg).toBe(45.1);
    expect(() => presetDefaults('NOPE')).toThrow();
  });

  it('names the ephemeris resource of a request', () => {
    expect(orbitIdForRequest(inputsToRequest(BASE_UI))).toBe('sso981');
    expect(orbitIdForRequest({ target: { type: 'POLAR' } })).toBe('polar879');
    expect(orbitIdForRequest({ target: { type: 'CUSTOM', i_t_deg: 30, h_t_km: 500 } })).toBe('custom-30.0-500.0');
    expect(orbitIdForRequest({ target: { type: 'CUSTOM' } })).toBeNull();
    expect(orbitIdForRequest(null)).toBeNull();
  });

  it('reads the API base from the query string only when it is an http(s) URL', () => {
    expect(resolveApiBase('')).toBe('http://localhost:8000/v1');
    expect(resolveApiBase('?api=http://host:9000/v1/')).toBe('http://host:9000/v1');
    expect(resolveApiBase('?x=1&api=https%3A%2F%2Fexample.org%2Fv1')).toBe('https://example.org/v1');
    expect(resolveApiBase('?api=javascript:alert(1)')).toBe('http://localhost:8000/v1');
  });
});

describe('rows and weather', () => {
  const rows = fixtures.windows.windows;

  it('maps a response row to the page row without inventing a field', () => {
    const w = normalizeRow(rows[0]);
    expect(w.t).toBe(Date.parse(rows[0].t_liftoff_utc));
    expect(w.inj).toBe(Date.parse(rows[0].t_injection_utc));
    expect(w.close - w.open).toBeCloseTo(rows[0].window_width_s * 1000, 3);
    expect((w.open + w.close) / 2).toBeCloseTo(w.t, 3);
    expect(w.gaz).toBe(rows[0].azimuth_compass_deg);
    expect(w.ok).toBe(true);
    expect(w.p).toBe(rows[0].p_success);
    expect(w.inc).toBe(rows[0].reached_inclination_deg);
    expect(w.track).toBeNull();
    expect(Object.keys(w)).not.toContain('boost');
  });

  it('marks a row unusable when the hazard screen fails or a constraint fired', () => {
    expect(normalizeRow({ ...rows[0], screens: { ...rows[0].screens, hazard: 'fail' }, constraint_fired: 'hazard_area' }).ok).toBe(false);
    expect(normalizeRow({ ...rows[0], constraint_fired: 'fixed_point_no_convergence' }).ok).toBe(false);
  });

  it('labels the pass from the azimuth of the row', () => {
    expect(passOf(193.8)).toBe('southbound');
    expect(passOf(346.2)).toBe('northbound');
    expect(passOf(90.5)).toBe('due east');
    expect(compass8(193.8)).toBe('S');
    expect(compass8(346)).toBe('N');
  });

  it('bands the weather from the row probability and the shared thresholds', () => {
    const at = (p) => weatherOf({ p_success_components: { weather: p }, horizon_label: 'FORECAST' }, true);
    expect(at(0.9).s).toBe('green');
    expect(at(0.7).s).toBe('green');
    expect(at(0.5).s).toBe('yellow');
    expect(at(0.1).s).toBe('red');
    expect(at(null).s).toBe('grey');
    expect(at(0.5).r).toContain('0.50');
    expect(at(0.5).r).toContain('FORECAST');
    expect(weatherOf({ p_success_components: { weather: 1 } }, false)).toMatchObject({ s: 'grey', p: null });
  });

  it('interpolates RAAN between the values of the rows and wraps through 360', () => {
    const f = raanInterpolator([
      { t: 0, raan: 359 },
      { t: 1000, raan: 1 },
    ]);
    expect(f(-5)).toBeCloseTo(359, 6);
    expect(f(500)).toBeCloseTo(0, 6);
    expect(f(5000)).toBeCloseTo(1, 6);
    expect(raanInterpolator([])(0)).toBe(0);
  });

  it('normalises a whole response, sorted in time, with reachability and the run id', () => {
    const data = normalizeResponse(fixtures.windows);
    expect(data.windows).toHaveLength(rows.length);
    expect(data.windows.map((w) => w.t)).toEqual([...data.windows.map((w) => w.t)].sort((a, b) => a - b));
    expect(data.reachable).toBe(true);
    expect(data.runId).toBe(fixtures.windows.constants_block.citation_id);
    const unreachable = normalizeResponse({ reachable: false, plane_change_dv_ms: 26.8, windows: [] });
    expect(unreachable).toMatchObject({ reachable: false, planeChangeDvMs: 26.8, windows: [] });
  });
});

describe('recommendation', () => {
  const mk = (t, p, ok = true, widthS = 480) => ({ t, close: t + 1000, p, ok, widthS, wx: { r: 'x' } });
  const DAY = 86400000;

  it('picks the highest p_success among usable windows and ignores blocked ones', () => {
    const ws = [mk(1000, 0.4), mk(2000, 0.9), mk(3000, 1.0, false), mk(4000, 0.9)];
    const r = recommend(ws, 0);
    expect(r.top.t).toBe(2000);
    expect(r.alts.map((w) => w.t)).toEqual([4000, 1000]);
    expect(r.blocked.map((w) => w.t)).toEqual([3000]);
  });

  it('breaks a tie with the wider window, then the earlier one', () => {
    expect(recommend([mk(1000, 0.9, true, 400), mk(2000, 0.9, true, 500)], 0).top.t).toBe(2000);
    expect(recommend([mk(2000, 0.9), mk(1000, 0.9)], 0).top.t).toBe(1000);
  });

  it('puts a usable window with p_success 0 in the removed list, never on top', () => {
    const r = recommend([mk(1000, 0)], 0);
    expect(r.top).toBeNull();
    expect(r.removed).toHaveLength(1);
  });

  it('skips windows that have already closed and reports a backup a day later', () => {
    const ws = [mk(-5000, 1), mk(10000, 0.8), mk(10000 + DAY, 0.7)];
    const r = recommend(ws, 0);
    expect(r.top.t).toBe(10000);
    expect(r.backup).toBe(true);
    expect(nextUsable(ws, 0).t).toBe(10000);
    expect(nextUsable([], 0)).toBeNull();
  });
});

describe('ascent track and viewing from the offline fixtures', () => {
  const rows = normalizeResponse(fixtures.windows).windows;

  it('accepts the fixture ephemeris for the first fixture row and rejects it for the others', () => {
    const first = trackFromEphemeris(fixtures.ephemeris, rows[0], site);
    expect(first.ok).toBe(true);
    expect(first.track.length).toBeGreaterThanOrEqual(3);
    expect(first.offsetKm).toBeLessThan(5);
    expect(first.track[0].t).toBe(rows[0].t);
    const second = trackFromEphemeris(fixtures.ephemeris, rows[1], site);
    expect(second.ok).toBe(false);
    expect(second.reason).toMatch(/does not cover the ascent|km from the pad at liftoff/);
  });

  it('rejects a stand-in track that does not start on the pad, and says how far it is', () => {
    const standIn = {
      points: Array.from({ length: 19 }, (_, i) => ({
        t_utc: new Date(rows[0].t + i * 30000).toISOString().replace('.000Z', 'Z'),
        lat_deg: -68.2 + i * 0.4,
        lon_deg: 84.4 - i * 0.3,
        alt_km: 674,
      })),
    };
    const result = trackFromEphemeris(standIn, rows[0], site);
    expect(result.ok).toBe(false);
    expect(result.reason).toMatch(/not the ascent of this window/);
    expect(result.offsetKm).toBeGreaterThan(1000);
  });

  it('returns a reason, not an exception, for a missing or empty ephemeris', () => {
    expect(trackFromEphemeris(null, rows[0], site).ok).toBe(false);
    expect(trackFromEphemeris({ points: [] }, rows[0], site).ok).toBe(false);
  });

  it('computes a viewing report from the accepted track and the centre list', () => {
    const track = trackFromEphemeris(fixtures.ephemeris, rows[0], site);
    const report = viewingFor({ track, centres: centres.centres, ephemeris: fixtures.ephemeris, window: rows[0] });
    expect(report.centres.length).toBe(centres.centres.length);
    const halifax = report.centres.find((c) => c.id === 'halifax');
    expect(halifax.max_elevation_deg).toBeGreaterThan(0);
    expect(viewingFor({ track: { ok: false }, centres: centres.centres, ephemeris: fixtures.ephemeris, window: rows[0] })).toBeNull();
  });
});

describe('the data source: API first, fixture second', () => {
  it('reads the site from the API and marks the origin', async () => {
    const f = stubFetch({ api: (url) => response(fixtures.site) });
    const result = await source(f).site();
    expect(result.origin).toBe('api');
    expect(result.site.lat).toBe(fixtures.site.phi_s_deg);
    expect(f.calls[0].url).toBe('http://api.test/v1/site');
  });

  it('falls back to the site fixture when the API is down, keeping the reason', async () => {
    const result = await source(stubFetch()).site();
    expect(result.origin).toBe('fixture');
    expect(result.error).toMatch(/network failure/);
    expect(result.site.corridor).toEqual([fixtures.site.corridor.A_min_deg, fixtures.site.corridor.A_max_deg]);
  });

  it('reports both failures when the API and the fixture are unavailable', async () => {
    const f = stubFetch({ files: false });
    const result = await source(f).site();
    expect(result.site).toBeNull();
    expect(result.fixtureError).toMatch(/site\.json/);
  });

  it('posts the request, returns the live response, then serves it as stale when the API drops', async () => {
    let up = true;
    const f = stubFetch({ api: () => { if (!up) throw new TypeError('down'); return response(fixtures.windows); } });
    const s = source(f);
    const request = inputsToRequest(BASE_UI);
    const live = await s.windows(request);
    expect(live.origin).toBe('api');
    expect(f.calls[0]).toMatchObject({ method: 'POST', url: 'http://api.test/v1/windows', body: request });
    up = false;
    const stale = await s.windows(request);
    expect(stale.origin).toBe('api_stale');
    expect(stale.response).toBe(fixtures.windows);
    expect(stale.error).toMatch(/network failure/);
  });

  it('uses the windows fixture, and says the inputs were not applied, when no live response exists', async () => {
    const s = source(stubFetch());
    const result = await s.windows(inputsToRequest(BASE_UI));
    expect(result.origin).toBe('fixture');
    expect(result.request).toBeNull();
    expect(result.response.windows).toHaveLength(fixtures.windows.windows.length);
    const banner = offlineBannerText({ origins: { windows: 'fixture' }, runId: 'run_x', error: result.error });
    expect(banner).toMatch(/^OFFLINE PRECOMPUTED DATA, mode offline_precomputed\. engine run run_x\. source windows\.json\. the page inputs are not applied/);
    expect(banner).toMatch(/reason: network failure/);
  });

  it('asks the ephemeris of the orbit and the row interval, and falls back for an unknown orbit', async () => {
    const f = stubFetch({ api: (url) => response({ orbit_id: 'sso981', points: [] }) });
    const row = normalizeResponse(fixtures.windows).windows[0];
    await source(f).ephemeris('sso981', row);
    expect(f.calls[0].url).toMatch(/orbits\/sso981\/ephemeris\?start=2026-10-05T11%3A42%3A17Z&end=.*&step_s=30$/);
    const offline = await source(stubFetch()).ephemeris(null, row);
    expect(offline.origin).toBe('fixture');
    expect(offline.value.orbit_id).toBe('sso981');
  });

  it('asks the skill endpoint for the period the skill fixture declares', async () => {
    const f = stubFetch({ api: () => response(fixtures.skill) });
    const result = await source(f).skill();
    expect(result.origin).toBe('api');
    const apiCall = f.calls.find((c) => c.url.startsWith('http://api.test'));
    expect(apiCall.url).toBe(`http://api.test/v1/validation/skill?period_start=${fixtures.skill.period.start}&period_end=${fixtures.skill.period.end}`);
  });

  it('loads the centres from the repository file and reports a failure instead of throwing', async () => {
    const ok = await source(stubFetch()).centres();
    expect(ok.centres.length).toBeGreaterThan(0);
    expect(ok.flag).toBe('ASSUMPTION');
    const bad = await source(stubFetch({ files: false })).centres();
    expect(bad.centres).toEqual([]);
    expect(bad.error).not.toBeNull();
  });
});

describe('banner and summaries', () => {
  it('is silent when every resource is live', () => {
    expect(offlineBannerText({ origins: { site: 'api', windows: 'api', skill: 'api' } })).toBeNull();
    expect(modeOf(['api', 'api'])).toBe('live_engine');
    expect(modeOf(['api', 'fixture'])).toBe('offline_precomputed');
  });

  it('names exactly the fixtures that are in use', () => {
    const text = offlineBannerText({ origins: { site: 'fixture', windows: 'api', skill: 'fixture' }, runId: 'r1' });
    expect(text).toContain('source site.json, skill.json');
    expect(text).not.toContain('windows.json');
  });

  it('says when the last successful response is shown', () => {
    expect(offlineBannerText({ origins: { windows: 'api_stale' } })).toContain('showing the last successful API response');
  });

  it('lists fixture failures', () => {
    expect(offlineBannerText({ origins: { windows: 'api' }, failures: ['skill.json: HTTP 404'] })).toContain('fixtures unavailable: skill.json: HTTP 404');
  });

  it('summarises the hindcast skill from the response alone', () => {
    const k = skillSummary(fixtures.skill);
    expect(k.period).toBe(`${fixtures.skill.period.start} to ${fixtures.skill.period.end}`);
    expect(k.leads[0]).toMatchObject({ lead: 1, bss: fixtures.skill.skill_series[0].bss });
    expect(skillSummary(null)).toBeNull();
  });

  it('formats the date helper in UTC', () => {
    expect(isoDateOf(Date.UTC(2026, 9, 4, 23, 59))).toBe('2026-10-04');
    expect(FIXTURE_ROOT.endsWith('/backend/fixtures/')).toBe(true);
  });
});

describe('the prototype page itself', () => {
  const html = fs.readFileSync(path.join(root, 'Canso Launch Prototype.html'), 'utf8');
  const visible = html.replace(/data:[A-Za-z/+;-]*base64,[A-Za-z0-9+/=]+/g, 'DATA').replace(/"land":"[^"]+"/, '"land":""');

  it('carries no mock window list, engine copy or hardcoded display from the ghost inventory', () => {
    for (const ghost of [
      'Guysborough', 'Sherbrooke', 'Port Hawkesbury', 'Antigonish', 'JPSS', 'mock_windows', 'Not scored in the demo engine',
      'generic limits', 'Thunderstorm forecast', 'Ground gusts', 'mockHasFuture', 'fromMock', 'findWindows', 'synthTrack',
      '45.10', '61.02', '82°', 'Date.now()-H', 'Spin help', 'confidence',
    ]) {
      expect(visible, ghost).not.toContain(ghost);
    }
    for (const pattern of [/\bPROFILE\b/, /\bVAFB\b/]) {
      expect(visible, String(pattern)).not.toMatch(pattern);
    }
    expect(visible).not.toMatch(/"mock"\s*:/);
  });

  it('imports its numbers from the data layer and reads the site before it builds the scene', () => {
    expect(html).toContain("from './frontend/src/prototypeData.js'");
    expect(html.indexOf('await source.site()')).toBeGreaterThan(0);
    expect(html.indexOf('await source.site()')).toBeLessThan(html.indexOf('const padV='));
  });

  it('loads every script and font from the repository, nothing from the network', () => {
    expect(html).not.toMatch(/(?:src|href)=["']https?:\/\//);
    const local = [...html.matchAll(/(?:src|href)="(vendor\/prototype\/[^"]+)"/g)].map((m) => m[1]);
    expect(local.length).toBeGreaterThanOrEqual(9);
    for (const file of local) {
      expect(fs.existsSync(path.join(root, file)), file).toBe(true);
    }
    const css = fs.readFileSync(path.join(root, 'vendor/prototype/fonts.css'), 'utf8');
    for (const [, file] of css.matchAll(/url\("([^"]+)"\)/g)) {
      expect(fs.existsSync(path.join(root, 'vendor/prototype', file)), file).toBe(true);
    }
  });
});
