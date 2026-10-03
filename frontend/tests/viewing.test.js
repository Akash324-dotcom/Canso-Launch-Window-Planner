import { afterEach, describe, expect, it } from 'vitest';
import { ELEVATION_MASK_DEG } from '../src/config.js';
import { geodeticToEcef } from '../src/geo.js';
import { SOLAR_CITATION } from '../src/solar.js';
import { viewingReport } from '../src/viewing.js';
import {
  boot,
  clone,
  flush,
  installContractApi,
  jsonResponse,
  loadCentresDocument,
  loadExample,
  textOf,
} from './helpers.js';

const STUB = 'windows_response_good_stub.json';
const SITE = 'site_response_good_canso_verified_corridor.json';
const SKILL = 'skill_response_good_brier_skill_series.json';
const FORECAST = 'weather_probability_response_good_forecast.json';

const TRACK_START = '2026-10-05T13:42:11Z';

async function settle() {
  await flush();
  await flush();
}

/**
 * A single sample directly above Halifax at 400 km. The point is 60 km from the site on
 * bearing 305 deg, so the site to Halifax distance is about 300 km and a 400 km pass puts
 * Halifax well above the mask.
 */
function overheadHalifaxTrack() {
  return {
    ...clone(loadExample('ephemeris_response_good_leo45.json')),
    orbit_id: 'sso981',
    points: [
      { t_utc: TRACK_START, lat_deg: 45.3108, lon_deg: -61.0219, alt_km: 400 },
      { t_utc: '2026-10-05T13:47:26Z', lat_deg: 44.6488, lon_deg: -63.5752, alt_km: 400 },
    ],
  };
}

/** A low sample far downrange over the Atlantic: below the horizon of every centre. */
function farLowTrack() {
  return {
    ...clone(loadExample('ephemeris_response_good_leo45.json')),
    orbit_id: 'sso981',
    points: [
      { t_utc: TRACK_START, lat_deg: 42.0, lon_deg: -50.0, alt_km: 12 },
      { t_utc: '2026-10-05T13:47:26Z', lat_deg: 41.0, lon_deg: -48.0, alt_km: 20 },
    ],
  };
}

function contractHandler(ephemeris) {
  return (url) => {
    const target = String(url);
    if (target.endsWith('/windows')) {
      return jsonResponse(loadExample(STUB));
    }
    if (target.includes('/ephemeris')) {
      return jsonResponse(ephemeris);
    }
    if (target.includes('/site')) {
      return jsonResponse(loadExample(SITE));
    }
    if (target.includes('/weather/probability')) {
      return jsonResponse(loadExample(FORECAST));
    }
    if (target.includes('/validation/skill')) {
      return jsonResponse(loadExample(SKILL));
    }
    return jsonResponse({ detail: 'unrouted' }, 404);
  };
}

async function startWithTrack(track) {
  installContractApi(contractHandler(track));
  const { app } = boot();
  app.start();
  await settle();
  document.querySelectorAll('#window-rows tr[data-liftoff-utc]')[0].dispatchEvent(
    new Event('click', { bubbles: true }),
  );
  await settle();
  return app;
}

function viewingRow(centreId) {
  return document.querySelector(`#viewing-rows tr[data-centre-id="${centreId}"]`);
}

afterEach(() => {
  document.body.innerHTML = '';
});

describe('F5 screen 4 viewing map', () => {
  it('shows no visibility for a centre below the horizon', async () => {
    const app = await startWithTrack(farLowTrack());

    const rows = [...document.querySelectorAll('#viewing-rows tr[data-centre-id]')];
    expect(rows).toHaveLength(loadCentresDocument().centres.length);
    for (const row of rows) {
      expect(row.getAttribute('data-visible')).toBe('false');
      expect(row.getAttribute('data-max-elevation-deg')).not.toBe('');
      expect(Number(row.getAttribute('data-max-elevation-deg'))).toBeLessThan(0);
      expect(row.textContent).toContain('below the horizon');
      expect(row.querySelector('[data-verdict]').getAttribute('data-verdict')).toBe('not visible');
    }
    expect(textOf('#viewing-sub')).toContain('visible centres 0 of');
    expect(textOf('#viewing-illumination')).toContain(
      'No centre sees a sunlit vehicle while in darkness',
    );

    app.stop();
  });

  it('shows visibility with an elevation number for a centre geometrically in view', async () => {
    const app = await startWithTrack(overheadHalifaxTrack());

    const halifax = viewingRow('halifax');
    expect(halifax).not.toBeNull();
    expect(halifax.getAttribute('data-visible')).toBe('true');
    expect(halifax.getAttribute('data-above-horizon')).toBe('true');
    const elevation = Number(halifax.getAttribute('data-max-elevation-deg'));
    expect(elevation).toBeGreaterThanOrEqual(ELEVATION_MASK_DEG);
    expect(halifax.querySelector('[data-elevation-text]').textContent).toBe(
      `${elevation.toFixed(1)} deg`,
    );
    expect(halifax.textContent).toContain(`visible above the ${ELEVATION_MASK_DEG} deg mask`);
    expect(halifax.textContent).toContain('2026-10-05 13:47:26Z');

    const chart = document.querySelector('#viewing-elevation-chart svg');
    expect(chart.getAttribute('data-centre-id')).toBe('halifax');
    expect(Number(chart.querySelectorAll('circle[data-elevation-deg]')[1].getAttribute('data-elevation-deg')))
      .toBeCloseTo(elevation, 1);
    expect(chart.querySelector('line[data-elevation-mask-deg]').getAttribute('data-elevation-mask-deg')).toBe(
      String(ELEVATION_MASK_DEG),
    );
    expect(textOf('#elevation-mask-note')).toContain('ASSUMPTION');
    expect(textOf('#viewing-geometry-note')).toContain('atmospheric refraction is not');

    app.stop();
  });

  it('reports whether the vehicle is sunlit while an observer is in darkness', async () => {
    const twilightTrack = {
      ...overheadHalifaxTrack(),
      points: [{ t_utc: '2026-10-05T09:30:00Z', lat_deg: 45.0, lon_deg: -30.0, alt_km: 400 }],
    };
    const app = await startWithTrack(twilightTrack);

    const report = app.viewing.report;
    for (const centre of report.centres) {
      const sample = centre.samples[0];
      expect(sample.vehicle_sunlit).toBe(true);
      expect(sample.observer_dark).toBe(true);
      expect(sample.sunlit_in_darkness).toBe(true);
      expect(centre.sunlit_in_darkness_samples).toBe(1);
    }
    expect(report.centres.map((centre) => centre.id)).toContain('st_johns');
    expect(viewingRow('st_johns').textContent).toContain('sunlit seen in darkness at 1 sample');
    expect(textOf('#viewing-illumination')).toContain('St. Johns');

    const halifax = report.centres.find((centre) => centre.id === 'halifax');
    const stJohns = report.centres.find((centre) => centre.id === 'st_johns');
    expect(halifax.samples[0].elevation_deg).toBeLessThan(0);
    expect(stJohns.samples[0].elevation_deg).toBeGreaterThan(0);
    expect(stJohns.samples[0].elevation_deg).toBeLessThan(ELEVATION_MASK_DEG);
    expect(stJohns.visible).toBe(false);

    app.stop();
  });

  it('keeps the ECEF geometry self consistent with the mask for every centre', async () => {
    const centres = loadCentresDocument().centres;
    const report = viewingReport({
      points: overheadHalifaxTrack().points,
      centres,
      ephemerisResponse: overheadHalifaxTrack(),
      elevationMaskDeg: ELEVATION_MASK_DEG,
    });

    expect(report.earth_radius_m).toBe(
      loadExample('ephemeris_response_good_leo45.json').constants_block.R_e,
    );
    for (const centre of report.centres) {
      expect(centre.visible).toBe(centre.max_elevation_deg >= ELEVATION_MASK_DEG);
      for (const sample of centre.samples) {
        const observer = geodeticToEcef(centre.lat_deg, centre.lon_deg, 0, report.earth_radius_m);
        expect(sample.range_km).toBeGreaterThan(0);
        expect(sample.elevation_deg).toBeLessThanOrEqual(90);
        expect(sample.azimuth_deg).toBeGreaterThanOrEqual(0);
        expect(sample.azimuth_deg).toBeLessThan(360);
        expect(sample.above_horizon).toBe(sample.elevation_deg > 0);
        expect(typeof sample.vehicle_sunlit).toBe('boolean');
        expect(typeof sample.observer_dark).toBe('boolean');
        expect(sample.sunlit_in_darkness).toBe(
          sample.vehicle_sunlit === true && sample.observer_dark === true,
        );
        expect(observer.x).not.toBe(NaN);
      }
    }
    expect(report.best_centre_id).not.toBeNull();
  });

  it('mounts the Leaflet viewing map and cites the solar formula it uses', async () => {
    const app = await startWithTrack(overheadHalifaxTrack());

    const mountStatus = await app.viewing.leafletReady;
    expect(mountStatus).toBe('loaded');
    const mapHost = document.getElementById('viewing-map');
    expect(mapHost.getAttribute('data-leaflet')).toBe('loaded');
    expect(mapHost.className).toContain('leaflet-container');
    const circles = mapHost.querySelectorAll('path.layer-centre-visible, path.layer-centre-dark');
    expect(circles).toHaveLength(loadCentresDocument().centres.length);
    expect(mapHost.querySelectorAll('path.layer-centre-visible').length).toBeGreaterThanOrEqual(1);
    expect(textOf('#viewing-geometry-note')).toContain(SOLAR_CITATION);
    expect(textOf('#viewing-map-note')).toContain('frontend/node_modules');

    app.stop();
  });

  it('marks every centre below the mask with an open circle on the mounted map', async () => {
    const app = await startWithTrack(farLowTrack());

    expect(await app.viewing.leafletReady).toBe('loaded');
    const mapHost = document.getElementById('viewing-map');
    expect(mapHost.querySelectorAll('path.layer-centre-visible')).toHaveLength(0);
    expect(mapHost.querySelectorAll('path.layer-centre-dark')).toHaveLength(
      loadCentresDocument().centres.length,
    );

    app.stop();
  });
});