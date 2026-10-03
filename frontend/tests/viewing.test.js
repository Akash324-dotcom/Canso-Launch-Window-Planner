import { afterEach, describe, expect, it } from 'vitest';
import { ELEVATION_MASK_DEG, VIEWING_MIN_ELEVATION_DEG } from '../src/config.js';
import { geodeticToEcef } from '../src/geo.js';
import { SOLAR_CITATION } from '../src/solar.js';
import { NO_ASCENT_COVERAGE, viewingReport } from '../src/viewing.js';
import {
  boot,
  clone,
  flush,
  installContractApi,
  jsonResponse,
  loadCentresDocument,
  loadExample,
  textOf,
  withLiftoffShifted,
} from './helpers.js';

const STUB = 'windows_response_good_stub.json';
const SITE = 'site_response_good_canso_verified_corridor.json';
const SKILL = 'skill_response_good_brier_skill_series.json';
const FORECAST = 'weather_probability_response_good_forecast.json';

const TRACK_START = '2026-10-05T13:42:11Z';
const TRACK_END = '2026-10-05T13:47:26Z';
const LATER_PASS = '2026-10-05T14:30:00Z';

/** The ascent interval of the first row of the frozen stub response. */
const ASCENT = {
  t_liftoff_utc: TRACK_START,
  t_injection_utc: TRACK_END,
};

/**
 * The stub window moved so that its ascent brackets 09:30 to 09:35 UTC, the instant at
 * which the eastern centres are in darkness and a vehicle far downrange over the Atlantic
 * is still sunlit. Shifting the row is the only way to reach that geometry, because the
 * ascent is now the only interval the viewing screen looks at.
 */
const TWILIGHT_STUB = withLiftoffShifted(loadExample(STUB), -15131000);

const TWILIGHT_ASCENT = {
  t_liftoff_utc: TWILIGHT_STUB.windows[0].t_liftoff_utc,
  t_injection_utc: TWILIGHT_STUB.windows[0].t_injection_utc,
};

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
      { t_utc: TRACK_END, lat_deg: 44.6488, lon_deg: -63.5752, alt_km: 400 },
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
      { t_utc: TRACK_END, lat_deg: 41.0, lon_deg: -48.0, alt_km: 20 },
    ],
  };
}

/**
 * A low southbound ascent over the Atlantic, plus a later pass of the same orbit directly
 * over Montreal at 400 km. Montreal is 90 deg up at that later pass and below the horizon
 * during the ascent, which is the bug of issue 5 F5 in one track.
 */
function montrealLaterPassTrack() {
  return {
    ...clone(loadExample('ephemeris_response_good_leo45.json')),
    orbit_id: 'sso981',
    points: [
      { t_utc: TRACK_START, lat_deg: 45.3108, lon_deg: -61.0219, alt_km: 5 },
      { t_utc: TRACK_END, lat_deg: 44.6488, lon_deg: -63.5752, alt_km: 30 },
      { t_utc: LATER_PASS, lat_deg: 45.5019, lon_deg: -73.5674, alt_km: 400 },
    ],
  };
}

/** Two samples bracketing an ascent that neither of them falls inside. */
function bracketingTwilightTrack() {
  return {
    ...clone(loadExample('ephemeris_response_good_leo45.json')),
    orbit_id: 'sso981',
    points: [
      { t_utc: '2026-10-05T09:20:00Z', lat_deg: 44.0, lon_deg: -32.0, alt_km: 400 },
      { t_utc: '2026-10-05T09:40:00Z', lat_deg: 46.0, lon_deg: -28.0, alt_km: 400 },
    ],
  };
}

/** An ephemeris that starts only after the injection of the selected row. */
function afterTheAscentTrack() {
  return {
    ...clone(loadExample('ephemeris_response_good_leo45.json')),
    orbit_id: 'sso981',
    points: [
      { t_utc: '2026-10-05T14:00:00Z', lat_deg: 45.3108, lon_deg: -61.0219, alt_km: 550 },
      { t_utc: '2026-10-05T14:05:00Z', lat_deg: 44.6488, lon_deg: -63.5752, alt_km: 550 },
    ],
  };
}

function contractHandler(ephemeris, windows = STUB) {
  return (url) => {
    const target = String(url);
    if (target.endsWith('/windows')) {
      return jsonResponse(typeof windows === 'string' ? loadExample(windows) : windows);
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

async function startWithTrack(track, windows = STUB) {
  installContractApi(contractHandler(track, windows));
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
    // The verdict names VIEWING_MIN_ELEVATION_DEG, the threshold the verdict actually uses.
    expect(halifax.textContent).toContain(
      `visible above the ${VIEWING_MIN_ELEVATION_DEG} deg minimum elevation`,
    );
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
    const app = await startWithTrack(bracketingTwilightTrack(), TWILIGHT_STUB);

    const report = app.viewing.report;
    expect(report.ascent_t_liftoff_utc).toBe(TWILIGHT_ASCENT.t_liftoff_utc);
    for (const centre of report.centres) {
      expect(centre.samples).toHaveLength(2);
      for (const sample of centre.samples) {
        expect(sample.vehicle_sunlit).toBe(true);
        expect(sample.observer_dark).toBe(true);
        expect(sample.sunlit_in_darkness).toBe(true);
      }
      expect(centre.sunlit_in_darkness_samples).toBe(2);
    }
    expect(report.centres.map((centre) => centre.id)).toContain('st_johns');
    expect(viewingRow('st_johns').textContent).toContain('sunlit seen in darkness at 2 sample');
    expect(textOf('#viewing-illumination')).toContain('St. Johns');

    const halifax = report.centres.find((centre) => centre.id === 'halifax');
    const stJohns = report.centres.find((centre) => centre.id === 'st_johns');
    expect(halifax.samples[0].elevation_deg).toBeLessThan(0);
    expect(stJohns.samples[0].elevation_deg).toBeGreaterThan(0);
    expect(stJohns.samples[0].elevation_deg).toBeLessThan(VIEWING_MIN_ELEVATION_DEG);
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

  it('does not count a centre that only the samples outside the ascent can see', async () => {
    const track = montrealLaterPassTrack();
    const centres = loadCentresDocument().centres;

    // The old behaviour, kept here as the contrast: with no ascent interval every sample
    // of the track counts, so the later pass puts Montreal at 90 deg and reports visible.
    const everySample = viewingReport({
      points: track.points,
      centres,
      ephemerisResponse: track,
    });
    expect(everySample.ascent_restricted).toBe(false);
    expect(everySample.centres.find((centre) => centre.id === 'montreal').max_elevation_deg).toBeCloseTo(
      90,
      3,
    );
    expect(everySample.centres.find((centre) => centre.id === 'montreal').visible).toBe(true);

    const app = await startWithTrack(track);

    const report = app.viewing.report;
    const montreal = report.centres.find((centre) => centre.id === 'montreal');
    expect(montreal.max_elevation_deg).toBeLessThan(VIEWING_MIN_ELEVATION_DEG);
    expect(montreal.visible).toBe(false);
    expect(montreal.peak_t_utc).not.toBe(LATER_PASS);
    const row = viewingRow('montreal');
    expect(row.getAttribute('data-visible')).toBe('false');
    expect(row.getAttribute('data-peak-t-utc')).not.toBe(LATER_PASS);
    expect(textOf('#viewing-ascent-note')).toContain('Samples outside that interval are ignored');

    app.stop();
  });

  it('ignores every sample outside the ascent interval of the selected row', async () => {
    const track = montrealLaterPassTrack();
    const app = await startWithTrack(track);

    const report = app.viewing.report;
    const liftoffMs = Date.parse(ASCENT.t_liftoff_utc);
    const injectionMs = Date.parse(ASCENT.t_injection_utc);
    expect(report.ascent_restricted).toBe(true);
    expect(report.ascent_covered).toBe(true);
    expect(report.sample_count).toBe(3);
    expect(report.ascent_sample_count).toBe(2);
    expect(report.interpolated_sample_count).toBe(0);
    for (const centre of report.centres) {
      expect(centre.samples.map((sample) => sample.t_utc)).toEqual([ASCENT.t_liftoff_utc, ASCENT.t_injection_utc]);
      for (const sample of centre.samples) {
        const timeMs = Date.parse(sample.t_utc);
        expect(timeMs).toBeGreaterThanOrEqual(liftoffMs);
        expect(timeMs).toBeLessThanOrEqual(injectionMs);
        expect(sample.interpolated).toBe(false);
      }
      if (centre.peak_t_utc !== null) {
        expect(Date.parse(centre.peak_t_utc)).toBeLessThanOrEqual(injectionMs);
      }
    }

    app.stop();
  });

  it('interpolates the liftoff and injection positions when fewer than two samples fall inside the ascent', async () => {
    const track = bracketingTwilightTrack();
    const app = await startWithTrack(track, TWILIGHT_STUB);

    const report = app.viewing.report;
    expect(report.ascent_covered).toBe(true);
    expect(report.sample_count).toBe(2);
    expect(report.ascent_sample_count).toBe(2);
    expect(report.interpolated_sample_count).toBe(2);
    for (const centre of report.centres) {
      const times = centre.samples.map((sample) => sample.t_utc);
      expect(times).toEqual([TWILIGHT_ASCENT.t_liftoff_utc, TWILIGHT_ASCENT.t_injection_utc]);
      for (const sample of centre.samples) {
        expect(sample.interpolated).toBe(true);
        expect(sample.index).toBeNull();
      }
    }
    // Liftoff sits halfway between the two bracketing samples, so it interpolates to the
    // midpoint of their latitude and longitude.
    const [liftoff] = report.centres[0].samples;
    expect(liftoff.lat_deg).toBeCloseTo(45, 9);
    expect(liftoff.lon_deg).toBeCloseTo(-30, 9);
    expect(liftoff.alt_km).toBeCloseTo(400, 9);
    expect(textOf('#viewing-ascent-note')).toContain('interpolated');

    app.stop();
  });

  it('honours the configured minimum elevation of the ascent', async () => {
    const track = bracketingTwilightTrack();
    const centres = loadCentresDocument().centres;

    const strict = viewingReport({
      points: track.points,
      centres,
      ephemerisResponse: track,
      ascent: TWILIGHT_ASCENT,
    });
    expect(strict.min_elevation_deg).toBe(VIEWING_MIN_ELEVATION_DEG);
    const stJohns = strict.centres.find((centre) => centre.id === 'st_johns');
    expect(stJohns.max_elevation_deg).toBeGreaterThan(0);
    expect(stJohns.max_elevation_deg).toBeLessThan(VIEWING_MIN_ELEVATION_DEG);
    expect(stJohns.visible).toBe(false);
    expect(strict.best_centre_id).toBeNull();
    for (const centre of strict.centres) {
      expect(centre.visible).toBe(centre.max_elevation_deg >= VIEWING_MIN_ELEVATION_DEG);
    }

    const lenient = viewingReport({
      points: track.points,
      centres,
      ephemerisResponse: track,
      ascent: TWILIGHT_ASCENT,
      minElevationDeg: 4,
    });
    const lenientStJohns = lenient.centres.find((centre) => centre.id === 'st_johns');
    expect(lenientStJohns.visible).toBe(true);
    expect(lenient.best_centre_id).toBe('st_johns');

    const app = await startWithTrack(track, TWILIGHT_STUB);
    const note = textOf('#viewing-min-elevation-note');
    expect(note).toContain(String(VIEWING_MIN_ELEVATION_DEG));
    expect(note).toContain('ASSUMPTION');
    expect(note).toContain('VIEWING_MIN_ELEVATION_DEG');
    const row = viewingRow('st_johns');
    expect(row.getAttribute('data-visible')).toBe('false');
    expect(row.textContent).toContain('above the horizon but below the minimum elevation');

    app.stop();
  });

  it('ranks the centres by the maximum elevation of the ascent and calls the best view', async () => {
    const app = await startWithTrack(overheadHalifaxTrack());

    const report = app.viewing.report;
    const elevations = report.centres.map((centre) => centre.max_elevation_deg);
    expect(elevations).toEqual([...elevations].sort((a, b) => b - a));
    expect(report.centres.map((centre) => centre.rank)).toEqual([1, 2, 3, 4, 5, 6, 7]);
    expect(report.ranked_centre_ids).toEqual(report.centres.map((centre) => centre.id));
    expect(report.best_centre_id).toBe('halifax');
    expect(report.best_centre.rank).toBe(1);
    for (const centre of report.centres) {
      const peak = centre.samples.reduce((best, sample) =>
        sample.elevation_deg > (best === null ? sample.elevation_deg : best.elevation_deg) ? sample : best,
      );
      expect(centre.peak_t_utc).toBe(peak.t_utc);
      expect(centre.peak_sunlit_in_darkness).toBe(peak.sunlit_in_darkness);
      expect(centre.max_elevation_deg).toBeCloseTo(peak.elevation_deg, 9);
    }

    const rows = [...document.querySelectorAll('#viewing-rows tr[data-centre-id]')];
    expect(rows.map((row) => row.getAttribute('data-centre-id'))).toEqual(report.ranked_centre_ids);
    expect(rows.map((row) => row.getAttribute('data-rank'))).toEqual(['1', '2', '3', '4', '5', '6', '7']);
    expect(rows.filter((row) => row.getAttribute('data-best') === 'true')).toHaveLength(1);
    expect(rows[0].getAttribute('data-centre-id')).toBe('halifax');
    expect(textOf('#viewing-chart-note')).toContain('Best view Halifax, Nova Scotia');

    app.stop();
  });

  it('says the ephemeris does not cover the ascent and marks no centre visible', async () => {
    const app = await startWithTrack(afterTheAscentTrack());

    const report = app.viewing.report;
    expect(report.ascent_restricted).toBe(true);
    expect(report.ascent_covered).toBe(false);
    expect(report.coverage_message).toBe(NO_ASCENT_COVERAGE);
    expect(report.ascent_sample_count).toBe(0);
    expect(report.best_centre_id).toBeNull();
    expect(report.best_centre).toBeNull();
    for (const centre of report.centres) {
      expect(centre.visible).toBe(false);
      expect(centre.samples).toEqual([]);
      expect(centre.max_elevation_deg).toBeNull();
    }

    expect(textOf('#viewing-ascent-note')).toContain(NO_ASCENT_COVERAGE);
    expect(textOf('#viewing-sub')).toContain(NO_ASCENT_COVERAGE);
    expect(textOf('#viewing-sub')).toContain('visible centres 0 of 7');
    expect(textOf('#viewing-status')).toContain(NO_ASCENT_COVERAGE);
    expect(document.querySelector('#viewing-chart-empty')).not.toBeNull();
    for (const row of document.querySelectorAll('#viewing-rows tr[data-centre-id]')) {
      expect(row.getAttribute('data-visible')).toBe('false');
      expect(row.getAttribute('data-max-elevation-deg')).toBe('');
      expect(row.textContent).toContain('no ascent sample');
    }

    app.stop();
  });
});
