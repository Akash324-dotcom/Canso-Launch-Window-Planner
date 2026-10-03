import {
  ELEVATION_MASK_DEG,
  ELEVATION_MASK_FLAG,
  ELEVATION_MASK_SOURCE,
  EARTH_RADIUS_SOURCE,
} from '../config.js';
import { el, replaceChildren } from '../dom.js';
import { clearLayers, createMapContainer, drawViewingLayers, loadLeaflet } from '../mapLeaflet.js';
import { SOLAR_CITATION } from '../solar.js';
import { renderElevationCurve } from '../svgChart.js';
import { formatUtc } from '../time.js';
import { illuminationSummary, viewingReport } from '../viewing.js';

function elevationText(value) {
  return value === null || value === undefined ? 'no sample' : `${value.toFixed(1)} deg`;
}

export function createViewingScreen({ root, store, elevationMaskDeg = ELEVATION_MASK_DEG }) {
  const mapHost = el('div', {
    class: 'map',
    id: 'viewing-map',
    role: 'img',
    'aria-label': 'Population centres with the geometric visibility of the ascent track',
    'data-leaflet': 'pending',
  });
  const mapNote = el('p', { class: 'hint', id: 'viewing-map-note' });
  const sub = el('p', { class: 'hint', id: 'viewing-sub' });
  const maskNote = el('p', {
    class: 'hint',
    id: 'elevation-mask-note',
    'data-mask-deg': String(elevationMaskDeg),
  });
  const tbody = el('tbody', { id: 'viewing-rows' });
  const chartHost = el('div', { class: 'chart-host', id: 'viewing-elevation-chart' });
  const chartNote = el('p', { class: 'hint', id: 'viewing-chart-note' });
  const illuminationNote = el('p', { class: 'hint', id: 'viewing-illumination' });
  const geometryNote = el('p', { class: 'hint', id: 'viewing-geometry-note' });
  const status = el('p', { class: 'hint', id: 'viewing-status' });

  root.replaceChildren(
    el('header', { class: 'panel-head' }, [
      el('h2', { text: 'Screen 4, viewing map of the ascent from the population centres' }),
      sub,
    ]),
    status,
    mapHost,
    mapNote,
    maskNote,
    el('div', { class: 'table-wrap' }, [
      el('table', { class: 'window-table', id: 'viewing-table' }, [
        el('thead', {}, el('tr', {}, [
          el('th', { scope: 'col', text: 'centre' }),
          el('th', { scope: 'col', text: 'lat_deg' }),
          el('th', { scope: 'col', text: 'lon_deg' }),
          el('th', { scope: 'col', text: 'peak elevation' }),
          el('th', { scope: 'col', text: 'peak time' }),
          el('th', { scope: 'col', text: 'verdict' }),
        ])),
        tbody,
      ]),
    ]),
    el('h3', { text: 'Elevation against time for the best centre' }),
    chartHost,
    chartNote,
    illuminationNote,
    geometryNote,
  );

  maskNote.textContent = `Elevation mask ${elevationMaskDeg} deg, ${ELEVATION_MASK_FLAG}. Source: ${ELEVATION_MASK_SOURCE}.`;
  geometryNote.textContent = `Geometry: ECEF on a sphere of the radius ${EARTH_RADIUS_SOURCE}; topocentric elevation is the ` +
    'angle between the line of sight and the local vertical, so Earth curvature is included and atmospheric refraction is not. ' +
    `Illumination: ${SOLAR_CITATION}`;

  let library = null;
  let map = null;
  let mountStatus = 'pending';
  let mountPromise = null;
  let lastReport = null;
  let memo = null;

  function reportFrom(state) {
    const points = state.ephemerisResponse === null ? [] : state.ephemerisResponse.points ?? [];
    const centres = Array.isArray(state.centres) ? state.centres : [];
    if (
      memo !== null &&
      memo.ephemerisResponse === state.ephemerisResponse &&
      memo.centres === centres &&
      memo.maskDeg === elevationMaskDeg
    ) {
      return memo.report;
    }
    const report = viewingReport({
      points,
      centres,
      ephemerisResponse: state.ephemerisResponse,
      elevationMaskDeg,
    });
    memo = { ephemerisResponse: state.ephemerisResponse, centres, maskDeg: elevationMaskDeg, report };
    return report;
  }

  function renderStatus(state, report) {
    if (state.engineResponse === null) {
      status.textContent = 'No window response fetched yet.';
      return;
    }
    if (state.ephemerisResponse === null) {
      status.textContent = 'Select a window row to fetch the ground track the visibility is computed from.';
      return;
    }
    const parts = [
      `${report.sample_count} ephemeris samples, ${report.centres.length} population centres, ` +
        `Earth radius ${report.earth_radius_m} m.`,
    ];
    if (state.ephemerisOrigin === 'fixture') {
      parts.push('track from the offline ephemeris fixture');
    }
    sub.textContent =
      `Track epoch ${report.sample_count === 0 ? 'unknown' : state.ephemerisResponse.points[0].t_utc}, ` +
      `visible centres ${report.centres.filter((centre) => centre.visible).length} of ${report.centres.length}.`;
    status.textContent = parts.join('. ');
  }

  function renderRows(report) {
    replaceChildren(
      tbody,
      report.centres.length === 0
        ? [
            el('tr', {}, [
              el('td', {
                colspan: '6',
                text: 'No population centre rows: the ephemeris or src/data/centres.json has not been read.',
              }),
            ]),
          ]
        : report.centres.map((centre) =>
            el(
              'tr',
              {
                'data-centre-id': centre.id,
                'data-visible': String(centre.visible),
                'data-max-elevation-deg':
                  centre.max_elevation_deg === null ? '' : Number(centre.max_elevation_deg.toFixed(4)),
                'data-above-horizon': String(centre.above_horizon),
                'data-sunlit-in-darkness-samples': String(centre.sunlit_in_darkness_samples),
              },
              [
                el('td', { text: centre.name }),
                el('td', { class: 'num', text: String(centre.lat_deg) }),
                el('td', { class: 'num', text: String(centre.lon_deg) }),
                el('td', {
                  class: 'num',
                  'data-elevation-text': elevationText(centre.max_elevation_deg),
                  text: elevationText(centre.max_elevation_deg),
                }),
                el('td', { text: centre.peak_t_utc === null ? 'no sample' : formatUtc(centre.peak_t_utc) }),
                el('td', {}, [
                  el('span', {
                    class: `badge badge-${centre.visible ? 'forecast' : 'climatology'}`,
                    'data-verdict': centre.visible ? 'visible' : 'not visible',
                    text: centre.visible
                      ? `visible above the ${elevationMaskDeg} deg mask`
                      : centre.max_elevation_deg !== null && centre.max_elevation_deg > 0
                        ? 'above the horizon but below the mask'
                        : 'below the horizon',
                  }),
                  el('span', {
                    class: 'secondary',
                    text: centre.sunlit_in_darkness_samples === 0
                      ? 'no sunlit sample seen in darkness'
                      : `sunlit seen in darkness at ${centre.sunlit_in_darkness_samples} sample(s)`,
                  }),
                ]),
              ],
            ),
          ),
    );
  }

  function renderChart(report) {
    if (report.best_centre === null) {
      replaceChildren(chartHost, [
        el('p', { class: 'chart-empty', id: 'viewing-chart-empty', text: 'No elevation series to draw.' }),
      ]);
      chartNote.textContent = 'The chart of elevation against time appears once a track is fetched.';
      return;
    }
    const { element, points } = renderElevationCurve(report.best_centre, { elevationMaskDeg });
    replaceChildren(chartHost, [element]);
    chartNote.textContent =
      `Best centre ${report.best_centre.name}, peak elevation ${elevationText(report.best_centre.max_elevation_deg)} ` +
      `at ${report.best_centre.peak_t_utc ?? 'no sample'}, range ${report.best_centre.peak_range_km === null ? 'no sample' : `${report.best_centre.peak_range_km.toFixed(0)} km`}, ` +
      `${points.length} samples.`;
  }

  function draw(state) {
    const report = reportFrom(state);
    lastReport = report;
    renderStatus(state, report);
    renderRows(report);
    renderChart(report);
    illuminationNote.textContent = illuminationSummary(report).text;
    root.setAttribute('data-centre-count', String(report.centres.length));
    if (map !== null && library !== null) {
      clearLayers(map);
      drawViewingLayers(library, map, {
        centres: Array.isArray(state.centres) ? state.centres : [],
        report,
      });
    }
    return report;
  }

  function mountMap() {
    if (mountPromise !== null) {
      return mountPromise;
    }
    mountPromise = loadLeaflet().then(
      (L) => {
        library = L;
        mountStatus = 'loaded';
        map = createMapContainer(mapHost, L);
        mapHost.setAttribute('data-leaflet', 'loaded');
        mapNote.textContent =
          'Circles mark every centre: a filled circle is a centre with an elevation above the mask, an open circle is one below it. Leaflet is loaded from frontend/node_modules, not from a CDN.';
        if (lastReport !== null) {
          draw(store.getState());
        }
        return mountStatus;
      },
      (error) => {
        mountStatus = 'unavailable';
        mapHost.setAttribute('data-leaflet', 'unavailable');
        mapNote.textContent =
          `The Leaflet map could not be mounted (${error instanceof Error ? error.message : String(error)}). ` +
          'The table below carries the same visibility verdicts and elevations.';
        return mountStatus;
      },
    );
    return mountPromise;
  }

  function destroy() {
    if (map !== null) {
      map.remove();
      map = null;
    }
    library = null;
    mountStatus = 'pending';
    mountPromise = null;
    root.replaceChildren();
  }

  return {
    element: root,
    mapHost,
    mountMap,
    get mapMountStatus() {
      return mountStatus;
    },
    get leafletReady() {
      return mountMap();
    },
    get report() {
      return lastReport;
    },
    render: draw,
    destroy,
  };
}