import { afterEach, describe, expect, it } from 'vitest';
import { EPHEMERIS_STEP_S, VEHICLE_FOOTPRINTS } from '../src/config.js';
import { greatCircleDistanceKm } from '../src/geo.js';
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
const CLIMATOLOGY = 'windows_response_good_climatology_constraint_fired.json';
const SITE = 'site_response_good_canso_verified_corridor.json';
const EPHEMERIS = 'ephemeris_response_good_leo45.json';
const SKILL = 'skill_response_good_brier_skill_series.json';
const WEATHER = 'weather_probability_response_good_forecast.json';
const NORTHBOUND_EPHEMERIS = 'ephemeris_response_good_leo45.json';

const ROW_SHIFT_S = 3600;

function isoRow(row, shiftS) {
  const copy = clone(row);
  copy.t_liftoff_utc = shiftIso(row.t_liftoff_utc, shiftS);
  copy.t_injection_utc = shiftIso(row.t_injection_utc, shiftS);
  copy.constraint_fired = null;
  copy.screens = { hazard: 'pass', conjunction: 'clear', notam: 'none' };
  return copy;
}

function shiftIso(instant, shiftS) {
  return new Date(Date.parse(instant) + shiftS * 1000).toISOString().replace('.000Z', 'Z');
}

function twoRowResponse() {
  const base = loadExample(STUB);
  const second = isoRow(loadExample(CLIMATOLOGY).windows[0], ROW_SHIFT_S);
  return { ...clone(base), windows: [clone(base.windows[0]), second] };
}

/**
 * Two southbound tracks, both inside the corridor azimuth 100 to 140 deg from Canso, on
 * the great circle bearings 118 and 122 deg. The coordinates are literals so that the
 * screen is tested against geometry it did not compute itself.
 */
function southTrack(orbitId, startIso, points) {
  const example = loadExample(EPHEMERIS);
  return {
    ...clone(example),
    orbit_id: orbitId,
    points: points.map((point, index) => ({
      t_utc: new Date(Date.parse(startIso) + index * 155000).toISOString(),
      lat_deg: point[0],
      lon_deg: point[1],
      alt_km: point[2],
    })),
  };
}

function trackA() {
  return southTrack('sso981', '2026-10-05T13:42:11Z', [
    [45.2956, -60.9882, 8.0],
    [45.2779, -60.941, 95.0],
    [45.2558, -60.882, 180.0],
  ]);
}

function trackB() {
  return southTrack('sso981', '2026-10-05T14:42:11Z', [
    [45.295, -60.9887, 6.0],
    [45.2751, -60.9433, 88.0],
    [45.2501, -60.8867, 176.0],
  ]);
}

function trackHandler(overrides = {}) {
  return (url) => {
    const target = String(url);
    if (target.endsWith('/windows')) {
      return jsonResponse(overrides.response ?? twoRowResponse());
    }
    if (target.includes('/ephemeris')) {
      if (overrides.ephemeris !== undefined) {
        return jsonResponse(overrides.ephemeris);
      }
      const start = new URL(target).searchParams.get('start');
      return jsonResponse(start === '2026-10-05T13:42:11Z' ? trackA() : trackB());
    }
    if (target.includes('/site')) {
      return jsonResponse(loadExample(SITE));
    }
    if (target.includes('/weather/probability')) {
      return jsonResponse(loadExample(WEATHER));
    }
    if (target.includes('/validation/skill')) {
      return jsonResponse(loadExample(SKILL));
    }
    return jsonResponse({ detail: 'unrouted' }, 404);
  };
}

async function settle() {
  await flush();
  await flush();
}

function trackPoints() {
  return [...document.querySelectorAll('#trajectory-track li[data-track-point]')];
}

afterEach(() => {
  document.body.innerHTML = '';
});

describe('F3 screen 2 trajectory', () => {
  it('fetches and renders the matching track when a window row is selected', async () => {
    const fetchMock = installContractApi(trackHandler());
    const { app } = boot();

    app.start();
    await settle();

    const rows = document.querySelectorAll('#window-rows tr[data-liftoff-utc]');
    expect(rows).toHaveLength(2);
    expect(fetchMock.mock.calls.filter((call) => String(call[0]).includes('/ephemeris'))).toHaveLength(0);
    expect(textOf('#trajectory-track')).toBe('No ground track fetched for the selected row.');
    expect(rows[0].getAttribute('data-selected')).toBe('false');

    rows[1].dispatchEvent(new Event('click', { bubbles: true }));
    await settle();

    const ephemerisCalls = fetchMock.mock.calls.filter((call) => String(call[0]).includes('/ephemeris'));
    expect(ephemerisCalls).toHaveLength(1);
    const requested = new URL(ephemerisCalls[0][0]);
    expect(requested.pathname).toBe('/v1/orbits/sso981/ephemeris');
    expect(String(ephemerisCalls[0][0])).toContain(encodeURIComponent('2026-10-05T14:42:11Z'));
    expect(requested.searchParams.get('start')).toBe('2026-10-05T14:42:11Z');
    expect(requested.searchParams.get('end')).toBe('2026-10-05T14:47:26Z');
    expect(requested.searchParams.get('step_s')).toBe(String(EPHEMERIS_STEP_S));

    const state = app.store.getState();
    expect(state.selectedRowIndex).toBe(1);
    expect(state.ephemerisOrigin).toBe('api');
    expect(state.ephemerisResponse.orbit_id).toBe('sso981');

    const rendered = trackPoints();
    expect(rendered).toHaveLength(trackB().points.length);
    trackB().points.forEach((point, index) => {
      expect(rendered[index].getAttribute('data-lat-deg')).toBe(String(point.lat_deg));
      expect(rendered[index].getAttribute('data-lon-deg')).toBe(String(point.lon_deg));
      expect(rendered[index].getAttribute('data-alt-km')).toBe(String(point.alt_km));
      expect(rendered[index].getAttribute('data-t-utc')).toBe(point.t_utc);
    });
    expect(rendered[0].getAttribute('data-lat-deg')).not.toBe(String(trackA().points[0].lat_deg));

    const selectedRows = document.querySelectorAll('#window-rows tr[data-selected="true"]');
    expect(selectedRows).toHaveLength(1);
    expect(selectedRows[0].getAttribute('data-index')).toBe('1');
    expect(selectedRows[0].className).toContain('row-selected');

    app.stop();
  });

  it('draws the corridor polygon, the site marker and the hazard buffer around the selected track', async () => {
    installContractApi(trackHandler());
    const { app } = boot({
      footprints: {
        cyclone4m: { hazard_half_width_km: 30, source: 'test registry', flag: 'VERIFIED' },
      },
    });

    app.start();
    await settle();
    document.querySelectorAll('#window-rows tr[data-liftoff-utc]')[0].dispatchEvent(
      new Event('click', { bubbles: true }),
    );
    await settle();

    const site = loadExample(SITE);
    const siteMarker = document.getElementById('site-marker');
    expect(siteMarker.getAttribute('data-lat-deg')).toBe(String(site.phi_s_deg));
    expect(siteMarker.getAttribute('data-lon-deg')).toBe(String(site.lambda_s_deg));

    const corridorVertices = [...document.querySelectorAll('#corridor-vertices li[data-corridor-vertex]')];
    expect(corridorVertices.length).toBeGreaterThanOrEqual(3);
    expect(corridorVertices[0].getAttribute('data-lat-deg')).toBe(String(site.phi_s_deg));
    expect(corridorVertices[0].getAttribute('data-lon-deg')).toBe(String(site.lambda_s_deg));
    expect(textOf('#trajectory-sub')).toContain(`${site.corridor.A_min_deg}`);
    expect(textOf('#trajectory-sub')).toContain(`${site.corridor.A_max_deg}`);
    expect(textOf('#trajectory-sub')).toContain(site.corridor.flag);

    const bufferVertices = [...document.querySelectorAll('#hazard-buffer-vertices li[data-buffer-vertex]')];
    expect(bufferVertices).toHaveLength(trackA().points.length * 2);
    for (const vertex of bufferVertices) {
      const lat = Number(vertex.getAttribute('data-lat-deg'));
      const lon = Number(vertex.getAttribute('data-lon-deg'));
      const nearest = Math.min(
        ...trackA().points.map((point) => greatCircleDistanceKm(lat, lon, point.lat_deg, point.lon_deg)),
      );
      expect(nearest).toBeGreaterThan(29);
      expect(nearest).toBeLessThan(31);
    }
    expect(textOf('#hazard-buffer-note')).toContain('30 km');
    expect(textOf('#hazard-buffer-note')).toContain('VERIFIED');

    const guard = document.getElementById('corridor-check');
    expect(guard.getAttribute('data-available')).toBe('true');
    expect(guard.getAttribute('data-inside')).toBe('true');
    expect(guard.textContent).toContain('northbound track over land is refused by this guard');

    app.stop();
  });

  it('states that the hazard buffer is not drawn when the vehicle footprint width is not declared', async () => {
    installContractApi(trackHandler());
    const { app } = boot();

    app.start();
    await settle();
    document.querySelectorAll('#window-rows tr[data-liftoff-utc]')[0].dispatchEvent(
      new Event('click', { bubbles: true }),
    );
    await settle();

    expect(VEHICLE_FOOTPRINTS.cyclone4m.hazard_half_width_km).toBeNull();
    const note = textOf('#hazard-buffer-note');
    expect(note).toContain('not drawn');
    expect(note).toContain(VEHICLE_FOOTPRINTS.cyclone4m.source);
    expect(document.querySelectorAll('#hazard-buffer-vertices li[data-buffer-vertex]')).toHaveLength(0);

    app.stop();
  });

  it('surfaces a hazard rejection when the fetched track leaves the southbound corridor', async () => {
    installContractApi(
      trackHandler({ ephemeris: loadExample(NORTHBOUND_EPHEMERIS) }),
    );
    const { app } = boot();

    app.start();
    await settle();
    document.querySelectorAll('#window-rows tr[data-liftoff-utc]')[0].dispatchEvent(
      new Event('click', { bubbles: true }),
    );
    await settle();

    const guard = document.getElementById('corridor-check');
    expect(guard.getAttribute('data-inside')).toBe('false');
    expect(guard.textContent).toContain('HAZARD REJECTION');
    expect(guard.textContent).toContain('south over the Atlantic');
    expect(trackPoints()).toHaveLength(loadExample(NORTHBOUND_EPHEMERIS).points.length);
    expect(trackPoints()[1].getAttribute('data-lat-deg')).toBe('48.11');

    app.stop();
  });

  it('mounts the Leaflet map from node_modules and draws the same layers as the data below', async () => {
    installContractApi(trackHandler());
    const { app } = boot({
      footprints: { cyclone4m: { hazard_half_width_km: 30, source: 'test registry', flag: 'VERIFIED' } },
    });

    app.start();
    await settle();
    document.querySelectorAll('#window-rows tr[data-liftoff-utc]')[0].dispatchEvent(
      new Event('click', { bubbles: true }),
    );
    await settle();

    const mountStatus = await app.trajectory.leafletReady;
    expect(mountStatus).toBe('loaded');
    const mapHost = document.getElementById('trajectory-map');
    expect(mapHost.getAttribute('data-leaflet')).toBe('loaded');
    expect(mapHost.className).toContain('leaflet-container');
    expect(mapHost.querySelectorAll('svg path').length).toBeGreaterThanOrEqual(3);
    expect(mapHost.querySelectorAll('path.layer-track').length).toBeGreaterThanOrEqual(1);
    expect(mapHost.querySelectorAll('path.layer-corridor').length).toBe(1);
    expect(mapHost.querySelectorAll('path.layer-buffer').length).toBe(1);
    expect(document.querySelectorAll('link[rel="stylesheet"][href^="http"]')).toHaveLength(0);
    expect(document.querySelectorAll('script[src^="http"]')).toHaveLength(0);

    app.stop();
  });

  it('does not request an ephemeris for a CUSTOM target because no frozen field names its orbit id', async () => {
    const response = twoRowResponse();
    const fetchMock = installContractApi(trackHandler({ response }));
    const { app } = boot();

    app.start();
    await settle();
    document.getElementById('target-type').value = 'CUSTOM';
    document.getElementById('target-type').dispatchEvent(new Event('change', { bubbles: true }));
    document.getElementById('target-altitude-km').value = '700';
    document.getElementById('target-altitude-km').dispatchEvent(new Event('change', { bubbles: true }));
    document.getElementById('inclination-deg').value = '82.5';
    document.getElementById('inclination-deg').dispatchEvent(new Event('change', { bubbles: true }));
    await settle();

    document.querySelectorAll('#window-rows tr[data-liftoff-utc]')[0].dispatchEvent(
      new Event('click', { bubbles: true }),
    );
    await settle();

    expect(fetchMock.mock.calls.filter((call) => String(call[0]).includes('/ephemeris'))).toHaveLength(0);
    expect(textOf('#trajectory-status')).toContain('CUSTOM');
    expect(textOf('#trajectory-status')).toContain('not named by any field of the frozen response schema');

    app.stop();
  });

  it('falls back to the offline ephemeris fixture and shows the banner when the ephemeris call fails', async () => {
    const handler = trackHandler();
    installContractApi((url) => {
      if (String(url).includes('/ephemeris')) {
        throw new TypeError('fetch failed');
      }
      return handler(url);
    });
    const { app } = boot();

    app.start();
    await settle();
    document.querySelectorAll('#window-rows tr[data-liftoff-utc]')[0].dispatchEvent(
      new Event('click', { bubbles: true }),
    );
    await settle();

const state = app.store.getState();
expect(state.ephemerisOrigin).toBe('fixture');
    expect(state.ephemerisResponse.orbit_id).toBe(loadExample(EPHEMERIS).orbit_id);
    expect(trackPoints()).toHaveLength(loadExample(EPHEMERIS).points.length);
    expect(document.getElementById('mode-banner').hidden).toBe(false);
    expect(textOf('#mode-banner')).toContain('offline_precomputed');
    expect(textOf('#mode-banner')).toContain('ephemeris.json');
    expect(textOf('#trajectory-status')).toContain('offline fixture');

    app.stop();
  });
});