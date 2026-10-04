import {
  API_BASE,
  FIXTURES,
  ORBIT_PRESETS,
  TRACK_START_TOLERANCE_KM,
  ELEVATION_MASK_DEG,
  VEHICLE_PROFILE_IDS,
  DEFAULT_SITE,
  DEFAULT_RANGE_DAYS,
  MODE_LIVE,
  MODE_OFFLINE,
} from './config.js';
import { createApiClient, requestJson } from './api.js';
import { buildWindowsRequest } from './request.js';
import { weatherBand } from './weatherBands.js';
import { greatCircleDistanceKm } from './geo.js';
import { ascentSamples, viewingReport } from './viewing.js';

/**
 * Data layer of `Canso Launch Prototype.html` (issue #27, ghost hunt).
 *
 * The prototype page used to carry its own copy of the window engine and a mock window list
 * embedded in the file. It now owns no numbers: every window, azimuth, probability, site
 * coordinate, corridor bound, ground track and viewing verdict comes from this module, which
 * reads the `/v1` API and falls back to the committed offline fixtures (`backend/fixtures`)
 * with the same offline banner the `frontend/` planner shows.
 *
 * Nothing in this file touches the DOM or three.js, so `tests/prototype.test.js` runs it
 * under vitest.
 */

const MIN_MS = 60000;
const DAY_MS = 86400000;

/** Ephemeris sampling interval for one ascent. The ascent lasts minutes, the default of 300 s gives 2 samples. */
export const PROTOTYPE_TRACK_STEP_S = 30;

/** Smallest number of ascent samples the page will draw an arc or place a satellite from. */
export const MIN_TRACK_SAMPLES = 3;

// Resolved against this module, not the page, so the page can sit anywhere. The module URL goes through a
// variable on purpose: a literal `new URL('x', import.meta.url)` is rewritten into an asset import by Vite (vitest).
const MODULE_URL = import.meta.url;
export const FIXTURE_ROOT = new URL('../../backend/fixtures/', MODULE_URL).href;
export const CENTRES_URL = new URL('./data/centres.json', MODULE_URL).href;

/** API base, overridable with `?api=http://host:port/v1` so a demo or a test can point elsewhere. */
export function resolveApiBase(search = '') {
  const match = /(?:^|[?&])api=([^&]+)/.exec(String(search));
  if (match === null) {
    return API_BASE;
  }
  const candidate = decodeURIComponent(match[1]).replace(/\/+$/, '');
  return /^https?:\/\//.test(candidate) ? candidate : API_BASE;
}

export function fixtureUrl(name) {
  const file = FIXTURES[name];
  if (file === undefined) {
    throw new Error(`unknown offline fixture: ${name}`);
  }
  return `${FIXTURE_ROOT}${file}`;
}

/* ------------------------------------------------------------------ presets and request */

const PRESET_BY_ID = Object.fromEntries(ORBIT_PRESETS.map((preset) => [preset.id, preset]));

/**
 * The orbit selector of the page. The three classes come from `ORBIT_PRESETS` (the same
 * table the `frontend/` planner uses) so the two pages cannot disagree on a class
 * inclination. `LOW` is a guided example for the unreachable case: a custom orbit well below
 * the pad latitude. It is an input the user can change, not a displayed fact.
 */
export const PRESET_ORDER = ['SSO', 'POLAR', 'LEO', 'LOW', 'CUSTOM'];

export const GUIDED_LOW_INCLINATION_DEG = 30;
export const GUIDED_LOW_ALTITUDE_KM = 500;

export function presetDefaults(id) {
  if (id === 'LOW') {
    return {
      target_type: 'CUSTOM',
      label: `Too low, ${GUIDED_LOW_INCLINATION_DEG} deg (guided example)`,
      inclination_deg: GUIDED_LOW_INCLINATION_DEG,
      altitude_km: GUIDED_LOW_ALTITUDE_KM,
      plane_mode: 'raan',
      ltan_hours: '',
    };
  }
  const preset = PRESET_BY_ID[id];
  if (preset === undefined) {
    throw new Error(`unknown orbit preset: ${id}`);
  }
  return {
    target_type: preset.id,
    label: preset.label,
    inclination_deg: preset.inclination_deg,
    altitude_km: null,
    plane_mode: preset.plane_mode,
    ltan_hours: preset.ltan_hours ?? '',
  };
}

export function presetLabel(id) {
  return presetDefaults(id).label;
}

/** An LTAN in decimal hours (the page's number input) as the `HH:MM` string the API takes. */
export function ltanText(hours) {
  const value = Number(hours);
  if (!Number.isFinite(value)) {
    return '';
  }
  const total = Math.round((((value % 24) + 24) % 24) * 60) % 1440;
  const h = String(Math.floor(total / 60)).padStart(2, '0');
  const m = String(total % 60).padStart(2, '0');
  return `${h}:${m}`;
}

export function isoDateOf(ms) {
  return new Date(ms).toISOString().slice(0, 10);
}

export function addDaysIso(isoDate, days) {
  return isoDateOf(Date.parse(`${isoDate}T00:00:00Z`) + days * DAY_MS);
}

/**
 * Page inputs to a `POST /v1/windows` body, through the same builder the `frontend/` planner
 * uses (`request.js`), so both pages send the same request for the same inputs.
 */
export function inputsToRequest(ui) {
  const defaults = presetDefaults(ui.preset);
  const days = Math.max(1, Math.min(16, Math.round(Number(ui.days) || DEFAULT_RANGE_DAYS)));
  const start = ui.dateStart;
  const customLike = defaults.target_type === 'CUSTOM';
  return buildWindowsRequest({
    target_type: defaults.target_type,
    h_t_km: customLike ? ui.altitudeKm : null,
    i_t_deg: customLike ? ui.inclinationDeg : null,
    plane_mode: ui.planeMode,
    ltan_hours: ui.planeMode === 'ltan' ? ltanText(ui.ltanHours) : null,
    raan_deg: ui.planeMode === 'raan' ? ui.raanDeg : null,
    date_start: start,
    date_end: addDaysIso(start, days - 1),
    vehicle_profile_id: ui.vehicle ?? VEHICLE_PROFILE_IDS[0],
    site: ui.site ?? DEFAULT_SITE,
    corridor_a_min_deg: ui.corridorMin,
    corridor_a_max_deg: ui.corridorMax,
    include_weather: ui.includeWeather !== false,
  });
}

/** Orbit id of the ephemeris resource for a request, or null when it cannot be named. */
export function orbitIdForRequest(request) {
  if (request === null || request === undefined || request.target === undefined) {
    return null;
  }
  const { type } = request.target;
  if (type !== 'CUSTOM') {
    const preset = PRESET_BY_ID[type];
    return preset === undefined ? null : preset.orbit_id;
  }
  const inc = Number(request.target.i_t_deg);
  const alt = Number(request.target.h_t_km);
  if (!Number.isFinite(inc) || !Number.isFinite(alt)) {
    return null;
  }
  // The backend names a custom orbit custom-<i, one decimal>-<h, one decimal>
  // (backend/api/orbits.py custom_orbit_id). A 404 for a guessed id is treated as "no track".
  return `custom-${inc.toFixed(1)}-${alt.toFixed(1)}`;
}

/* ------------------------------------------------------------------ site */

export function siteView(response, origin) {
  if (response === null || response === undefined) {
    return null;
  }
  const lat = Number(response.phi_s_deg);
  const lon = Number(response.lambda_s_deg);
  if (!Number.isFinite(lat) || !Number.isFinite(lon)) {
    return null;
  }
  const corridor = response.corridor ?? null;
  const min = corridor === null ? NaN : Number(corridor.A_min_deg);
  const max = corridor === null ? NaN : Number(corridor.A_max_deg);
  return {
    id: response.name ?? DEFAULT_SITE,
    lat,
    lon,
    corridor: Number.isFinite(min) && Number.isFinite(max) ? [min, max] : null,
    corridorFlag: corridor === null ? null : (corridor.flag ?? null),
    corridorSource: corridor === null ? null : (corridor.source ?? null),
    geometrySource: response.geometry_source ?? null,
    origin,
  };
}

export function coordinateText(site) {
  const lat = `${Math.abs(site.lat).toFixed(2)}°${site.lat >= 0 ? 'N' : 'S'}`;
  const lon = `${Math.abs(site.lon).toFixed(2)}°${site.lon >= 0 ? 'E' : 'W'}`;
  return `${lat} ${lon}`;
}

/* ------------------------------------------------------------------ windows */

export function passOf(azimuthDeg) {
  if (Math.abs(azimuthDeg - 90) < 2) {
    return 'due east';
  }
  return azimuthDeg < 90 || azimuthDeg > 270 ? 'northbound' : 'southbound';
}

export function horizonText(row) {
  const label = row.horizon_label ?? 'no horizon label';
  return row.forecast_issue_time ? `${label}, forecast issued ${row.forecast_issue_time}` : label;
}

/** Weather chip of one row, from the row's own probability and the band thresholds of `weatherBands.js`. */
export function weatherOf(row, includeWeather) {
  if (includeWeather === false) {
    return { s: 'grey', r: 'weather layer switched off for this request', p: null };
  }
  const raw = row.p_success_components === undefined ? null : row.p_success_components.weather;
  const probability = raw === null || raw === undefined ? null : Number(raw);
  const band = weatherBand(probability);
  const s = band.band.toLowerCase();
  if (s === 'grey') {
    return { s, r: band.reason, p: null };
  }
  return { s, r: `P(weather go) ${probability.toFixed(2)}, ${horizonText(row)}`, p: probability };
}

/**
 * One response row as the page uses it. Nothing is invented: `open` and `close` are the
 * liftoff instant plus or minus half of `window_width_s` (spec II.12, a full width), `ok` is the
 * hazard screen of the row, `gaz` is the compass azimuth of the row.
 */
export function normalizeRow(row, { includeWeather = true } = {}) {
  const t = Date.parse(row.t_liftoff_utc);
  const inj = Date.parse(row.t_injection_utc);
  const halfMs = (Number(row.window_width_s) / 2) * 1000;
  const gaz = Number(row.azimuth_compass_deg);
  const hazard = row.screens === undefined ? null : row.screens.hazard;
  return {
    t,
    open: t - halfMs,
    close: t + halfMs,
    inj,
    toOrbitMin: (inj - t) / MIN_MS,
    gaz,
    azimuth: Number(row.azimuth_deg),
    pass: passOf(gaz),
    ok: hazard === 'pass' && (row.constraint_fired === null || row.constraint_fired === undefined),
    hazard,
    constraint: row.constraint_fired ?? null,
    raan: Number(row.raan_deg),
    inc: Number(row.reached_inclination_deg),
    widthS: Number(row.window_width_s),
    p: Number(row.p_success),
    components: row.p_success_components ?? null,
    horizon: row.horizon_label ?? null,
    issued: row.forecast_issue_time ?? null,
    wx: weatherOf(row, includeWeather),
    track: null,
    trackNote: null,
    raw: row,
  };
}

/** RAAN at an instant, interpolated between the RAAN values the rows themselves carry. */
export function raanInterpolator(rows) {
  const points = rows
    .filter((row) => Number.isFinite(row.t) && Number.isFinite(row.raan))
    .map((row) => ({ t: row.t, raan: row.raan }))
    .sort((a, b) => a.t - b.t);
  if (points.length === 0) {
    return () => 0;
  }
  const unwrapped = [points[0]];
  for (let i = 1; i < points.length; i += 1) {
    const previous = unwrapped[i - 1].raan;
    let value = points[i].raan;
    while (value - previous > 180) value -= 360;
    while (value - previous < -180) value += 360;
    unwrapped.push({ t: points[i].t, raan: value });
  }
  return (ms) => {
    let value;
    if (ms <= unwrapped[0].t || unwrapped.length === 1) {
      value = unwrapped[0].raan;
    } else if (ms >= unwrapped[unwrapped.length - 1].t) {
      value = unwrapped[unwrapped.length - 1].raan;
    } else {
      let k = 0;
      while (unwrapped[k + 1].t < ms) k += 1;
      const a = unwrapped[k];
      const b = unwrapped[k + 1];
      value = a.raan + ((b.raan - a.raan) * (ms - a.t)) / (b.t - a.t);
    }
    return ((value % 360) + 360) % 360;
  };
}

export function normalizeResponse(response, { includeWeather = true } = {}) {
  const rows = Array.isArray(response?.windows) ? response.windows : [];
  const windows = rows
    .map((row) => normalizeRow(row, { includeWeather }))
    .filter((row) => Number.isFinite(row.t) && Number.isFinite(row.inj))
    .sort((a, b) => a.t - b.t);
  return {
    reachable: response?.reachable !== false,
    planeChangeDvMs: response?.plane_change_dv_ms ?? null,
    ssoWarning: response?.sso_consistency_warning ?? null,
    engineVersion: response?.engine_version ?? null,
    runId: response?.constants_block?.citation_id ?? null,
    windows,
    raanAt: raanInterpolator(windows),
  };
}

/**
 * Which usable window to recommend, and why. Ranking uses only response fields: usable
 * rows (hazard screen pass) with a positive `p_success`, highest `p_success` first, then the
 * wider window, then the earlier one. A "backup" is another usable row about one day later.
 */
export function recommend(windows, now) {
  const future = windows.filter((w) => w.close > now);
  const candidates = [];
  const removed = [];
  for (const w of future) {
    if (!w.ok) {
      continue;
    }
    if (!(w.p > 0)) {
      removed.push({ w, why: `p_success is ${Number.isFinite(w.p) ? w.p.toFixed(2) : 'not available'}, ${w.wx.r}` });
    } else {
      candidates.push(w);
    }
  }
  const blocked = future.filter((w) => !w.ok);
  const backup = (w) =>
    future.some((o) => o !== w && o.ok && o.p > 0 && Math.abs(o.t - w.t - DAY_MS) < 2 * 3600000);
  candidates.sort((a, b) => b.p - a.p || b.widthS - a.widthS || a.t - b.t);
  const top = candidates[0] ?? null;
  return {
    top,
    alts: candidates.slice(1, 3),
    removed,
    blocked,
    backup: top === null ? false : backup(top),
  };
}

/** The next window that is usable and not yet closed. */
export function nextUsable(windows, now) {
  return windows.find((w) => w.ok && w.close > now) ?? null;
}

/* ------------------------------------------------------------------ ascent track and viewing */

export function distanceToSiteKm(site, point) {
  return greatCircleDistanceKm(site.lat, site.lon, point.lat_deg, point.lon_deg);
}

/**
 * The ascent samples of a window from an ephemeris response, or the reason there are none.
 * The same acceptance rule as the `frontend/` trajectory screen: the first sample must lie on
 * the pad (`TRACK_START_TOLERANCE_KM`) at the liftoff instant, otherwise the track is a
 * stand-in that is not the ascent of this row and is not drawn.
 */
export function trackFromEphemeris(ephemeris, window, site) {
  if (ephemeris === null || ephemeris === undefined || !Array.isArray(ephemeris.points)) {
    return { ok: false, reason: 'no ephemeris response', samples: [] };
  }
  const ascent = ascentSamples(ephemeris.points, {
    t_liftoff_utc: new Date(window.t).toISOString().replace('.000Z', 'Z'),
    t_injection_utc: new Date(window.inj).toISOString().replace('.000Z', 'Z'),
  });
  if (ascent.covered !== true || ascent.samples.length < MIN_TRACK_SAMPLES) {
    return { ok: false, reason: 'the ephemeris does not cover the ascent of this window', samples: [] };
  }
  const first = ascent.samples[0];
  const offsetKm = distanceToSiteKm(site, first);
  if (!(offsetKm <= TRACK_START_TOLERANCE_KM)) {
    return {
      ok: false,
      reason:
        `the ephemeris starts ${Math.round(offsetKm).toLocaleString('en-US')} km from the pad at liftoff, ` +
        'so it is not the ascent of this window',
      samples: [],
      offsetKm,
    };
  }
  return {
    ok: true,
    reason: null,
    offsetKm,
    ephemeris,
    samples: ascent.samples,
    track: ascent.samples.map((sample) => ({
      lat: sample.lat_deg,
      lon: sample.lon_deg,
      alt: sample.alt_km,
      t: Date.parse(sample.t_utc),
    })),
  };
}

export function viewingFor({ track, centres, ephemeris, window }) {
  if (track === null || track === undefined || track.ok !== true) {
    return null;
  }
  return viewingReport({
    points: ephemeris.points,
    centres,
    ephemerisResponse: ephemeris,
    elevationMaskDeg: ELEVATION_MASK_DEG,
    ascent: {
      t_liftoff_utc: new Date(window.t).toISOString().replace('.000Z', 'Z'),
      t_injection_utc: new Date(window.inj).toISOString().replace('.000Z', 'Z'),
    },
  });
}

const COMPASS_8 = ['N', 'NE', 'E', 'SE', 'S', 'SW', 'W', 'NW'];
export function compass8(azimuthDeg) {
  return COMPASS_8[Math.round((((azimuthDeg % 360) + 360) % 360) / 45) % 8];
}

/* ------------------------------------------------------------------ the data source */

function messageOf(error) {
  return error instanceof Error ? error.message : String(error);
}

/**
 * Reads every resource the page shows, API first and committed fixture second. Each result
 * carries its origin ('api', 'api_stale' or 'fixture') so the page can show the offline
 * banner for exactly the resources that are not live.
 */
export function createPrototypeSource(options = {}) {
  const baseUrl = options.baseUrl ?? API_BASE;
  const fetchImpl = options.fetchImpl ?? globalThis.fetch;
  const timeoutMs = options.timeoutMs;
  const client =
    options.client ??
    createApiClient({ baseUrl, ...(timeoutMs === undefined ? {} : { timeoutMs }) });
  const perCall = fetchImpl === undefined ? {} : { fetchImpl };
  const fixtureCall = { ...perCall, ...(timeoutMs === undefined ? {} : { timeoutMs }) };
  const lastGood = { windows: null };

  const loadFixture = (name) => requestJson(fixtureUrl(name), fixtureCall);

  async function withFixture(name, liveCall) {
    try {
      return { value: await liveCall(), origin: 'api', error: null, fixtureError: null };
    } catch (liveError) {
      try {
        return { value: await loadFixture(name), origin: 'fixture', error: messageOf(liveError), fixtureError: null };
      } catch (fixtureError) {
        return {
          value: null,
          origin: null,
          error: messageOf(liveError),
          fixtureError: `${FIXTURES[name]}: ${messageOf(fixtureError)}`,
        };
      }
    }
  }

  return {
    client,
    baseUrl,

    async site() {
      const result = await withFixture('site', () => client.getSite(perCall));
      return { ...result, site: siteView(result.value, result.origin) };
    },

    async windows(request) {
      try {
        const response = await client.postWindows(request, perCall);
        lastGood.windows = { response, request };
        return { response, request, origin: 'api', error: null, fixtureError: null };
      } catch (liveError) {
        if (lastGood.windows !== null) {
          return {
            response: lastGood.windows.response,
            request: lastGood.windows.request,
            origin: 'api_stale',
            error: messageOf(liveError),
            fixtureError: null,
          };
        }
        try {
          const response = await loadFixture('windows');
          return { response, request: null, origin: 'fixture', error: messageOf(liveError), fixtureError: null };
        } catch (fixtureError) {
          return {
            response: null,
            request: null,
            origin: null,
            error: messageOf(liveError),
            fixtureError: `${FIXTURES.windows}: ${messageOf(fixtureError)}`,
          };
        }
      }
    },

    async ephemeris(orbitId, window) {
      const start = new Date(window.t).toISOString().replace('.000Z', 'Z');
      const end = new Date(window.inj).toISOString().replace('.000Z', 'Z');
      const live = orbitId === null
        ? () => Promise.reject(new Error('no orbit id for this target'))
        : () => client.getEphemeris(orbitId, { start, end, stepS: PROTOTYPE_TRACK_STEP_S }, perCall);
      return withFixture('ephemeris', live);
    },

    async skill() {
      return withFixture('skill', async () => {
        const recorded = await loadFixture('skill');
        const period = recorded?.period;
        if (!period?.start || !period?.end) {
          throw new Error(`the ${FIXTURES.skill} fixture declares no verification period to ask for`);
        }
        return client.getValidationSkill({ periodStart: period.start, periodEnd: period.end }, perCall);
      });
    },

    async centres() {
      try {
        const document_ = await requestJson(CENTRES_URL, fixtureCall);
        const centres = Array.isArray(document_?.centres) ? document_.centres : [];
        if (centres.length === 0) {
          throw new Error('centres.json declares no centres');
        }
        return { centres, flag: document_.flag ?? null, error: null };
      } catch (error) {
        return { centres: [], flag: null, error: messageOf(error) };
      }
    },
  };
}

/* ------------------------------------------------------------------ banner */

export function modeOf(origins) {
  return origins.some((origin) => origin === 'fixture' || origin === 'api_stale') ? MODE_OFFLINE : MODE_LIVE;
}

/**
 * The offline banner, worded like the one of `frontend/src/app.js` so a reader sees the same
 * sentence on both pages. `origins` maps a fixture name to 'api', 'api_stale' or 'fixture'.
 */
export function offlineBannerText({ origins, runId = null, error = null, failures = [] }) {
  const entries = Object.entries(origins);
  if (modeOf(entries.map(([, origin]) => origin)) !== MODE_OFFLINE && failures.length === 0) {
    return null;
  }
  const parts = [
    'OFFLINE PRECOMPUTED DATA, mode offline_precomputed',
    runId === null ? 'engine run identifier not available' : `engine run ${runId}`,
  ];
  const sources = entries.filter(([, origin]) => origin === 'fixture').map(([name]) => FIXTURES[name]);
  if (sources.length > 0) {
    parts.push(`source ${sources.join(', ')}`);
  }
  if (origins.windows === 'api_stale') {
    parts.push('showing the last successful API response');
  }
  if (origins.windows === 'fixture') {
    parts.push('the page inputs are not applied, the recorded request is shown');
  }
  if (error !== null && error !== undefined) {
    parts.push(`reason: ${error}`);
  }
  if (failures.length > 0) {
    parts.push(`fixtures unavailable: ${failures.join('; ')}`);
  }
  return parts.join('. ');
}

/** The honesty panel's validation lines, from `GET /v1/validation/skill` or its fixture. */
export function skillSummary(skill) {
  if (skill === null || skill === undefined) {
    return null;
  }
  const period = skill.period ?? null;
  return {
    period: period === null ? null : `${period.start} to ${period.end}`,
    source: skill.verification_source ?? null,
    reference: skill.reference_forecast ?? null,
    baseRate: Number.isFinite(Number(skill.base_rate)) ? Number(skill.base_rate) : null,
    horizonDays: skill.skill_horizon_measured_days ?? null,
    points: Array.isArray(skill.skill_series) ? skill.skill_series.length : 0,
    leads: Array.isArray(skill.skill_series)
      ? skill.skill_series
          .filter((point) => Number.isFinite(Number(point.bss)))
          .map((point) => ({ lead: point.lead_time_days, bss: Number(point.bss), n: point.n_cases ?? null }))
      : [],
  };
}
