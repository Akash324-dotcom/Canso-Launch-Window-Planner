import {
  ELEVATION_MASK_DEG,
  ELEVATION_MASK_FLAG,
  ELEVATION_MASK_SOURCE,
  EARTH_RADIUS_SOURCE,
  VIEWING_MIN_ELEVATION_DEG,
  VIEWING_MIN_ELEVATION_FLAG,
  VIEWING_MIN_ELEVATION_SOURCE,
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

export function createViewingScreen({
  root,
  store,
  elevationMaskDeg = ELEVATION_MASK_DEG,
  minElevationDeg = VIEWING_MIN_ELEVATION_DEG,
}) {
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
  const minNote = el('p', {
    class: 'hint',
    id: 'viewing-min-elevation-note',
    'data-min-elevation-deg': String(minElevationDeg),
  });
  const ascentNote = el('p', { class: 'hint', id: 'viewing-ascent-note' });
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
    ascentNote,
    minNote,
    el('div', { class: 'table-wrap' }, [
      el('table', { class: 'window-table', id: 'viewing-table' }, [
        el('thead', {}, el('tr', {}, [
          el('th', { scope: 'col', text: 'rank' }),
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
  minNote.textContent =
    `Minimum elevation of the ascent for a centre to count as visible ${minElevationDeg} deg, ${VIEWING_MIN_ELEVATION_FLAG}. ` +
    `Source: ${VIEWING_MIN_ELEVATION_SOURCE}.`;
  geometryNote.textContent = `Geometry: ECEF on a sphere of the radius ${EARTH_RADIUS_SOURCE}; topocentric elevation is the ` +
    'angle between the line of sight and the local vertical, so Earth curvature is included and atmospheric refraction is not. ' +
    `Illumination: ${SOLAR_CITATION}`;

  let library = null;
  let map = null;
  let mountStatus = 'pending';
  let mountPromise = null;
  let lastReport = null;
  let memo = null;

  function ascentWindow(state) {
    const rows = state.engineResponse === null ? [] : state.engineResponse.windows ?? [];
    const index = state.selectedRowIndex;
    if (!Number.isInteger(index) || index < 0 || index >= rows.length) {
      return null;
    }
    return {
      t_liftoff_utc: rows[index].t_liftoff_utc,
      t_injection_utc: rows[index].t_injection_utc,
    };
  }

  function reportFrom(state) {
    const points = state.ephemerisResponse === null ? [] : state.ephemerisResponse.points ?? [];
    const centres = Array.isArray(state.centres) ? state.centres : [];
    const ascent = ascentWindow(state);
    const liftoff = ascent === null ? null : ascent.t_liftoff_utc;
    const injection = ascent === null ? null : ascent.t_injection_utc;
    if (
      memo !== null &&
      memo.ephemerisResponse === state.ephemerisResponse &&
      memo.centres === centres &&
      memo.maskDeg === elevationMaskDeg &&
      memo.minDeg === minElevationDeg &&
      memo.liftoff === liftoff &&
      memo.injection === injection
    ) {
      return memo.report;
    }
    const report = viewingReport({
      points,
      centres,
      ephemerisResponse: state.ephemerisResponse,
      elevationMaskDeg,
      minElevationDeg,
      ascent,
    });
    memo = {
      ephemerisResponse: state.ephemerisResponse,
      centres,
      maskDeg: elevationMaskDeg,
      minDeg: minElevationDeg,
      liftoff,
      injection,
      report,
    };
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
      `${report.sample_count} ephemeris samples, ${report.ascent_sample_count} of them in the ascent of the ` +
        `selected row, ${report.centres.length} population centres, Earth radius ${report.earth_radius_m} m.`,
    ];
    if (report.interpolated_sample_count > 0) {
      parts.push(`${report.interpolated_sample_count} ascent sample(s) interpolated between bracketing samples`);
    }
    if (report.coverage_message !== null) {
      parts.push(report.coverage_message);
    }
    if (state.ephemerisOrigin === 'fixture') {
      parts.push('track from the offline ephemeris fixture');
    }
    const coverage = report.coverage_message === null ? '' : ` ${report.coverage_message}.`;
    sub.textContent =
      `Track epoch ${report.first_sample_t_utc ?? 'unknown'}, ` +
      `visible centres ${report.centres.filter((centre) => centre.visible).length} of ${report.centres.length}.` +
      coverage;
    status.textContent = parts.join('. ');
  }

  function renderAscentNote(report) {
    if (!report.ascent_restricted) {
      ascentNote.textContent =
        'Select a window row: the visibility is computed over the samples inside the ascent of that row, ' +
        'from t_liftoff_utc to t_injection_utc inclusive.';
      return;
    }
    const window = `liftoff ${formatUtc(report.ascent_t_liftoff_utc)} to injection ${formatUtc(report.ascent_t_injection_utc)}`;
    if (!report.ascent_covered) {
      const span =
        report.first_sample_t_utc === null
          ? 'the ephemeris carries no sample with a readable instant'
          : `its samples run from ${formatUtc(report.first_sample_t_utc)} to ${formatUtc(report.last_sample_t_utc)}`;
      ascentNote.textContent =
        `Ascent of the selected row, ${window}. ${report.coverage_message}: ${span}, so no centre is marked visible.`;
      return;
    }
    const interpolated =
      report.interpolated_sample_count === 0
        ? ''
        : `, of which ${report.interpolated_sample_count} interpolated at the endpoints from the bracketing samples`;
    ascentNote.textContent =
      `Visibility uses only the ${report.ascent_sample_count} ephemeris sample(s) of the ascent, ${window}` +
      `${interpolated}. Samples outside that interval are ignored, so the verdict is about the ascent and not ` +
      'about a later pass of the same orbit.';
  }

  function renderRows(report) {
    replaceChildren(
      tbody,
      report.centres.length === 0
        ? [
            el('tr', {}, [
              el('td', {
                colspan: '7',
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
                'data-rank': String(centre.rank),
                'data-best': String(report.best_centre_id === centre.id),
                'data-max-elevation-deg':
                  centre.max_elevation_deg === null ? '' : Number(centre.max_elevation_deg.toFixed(4)),
                'data-above-horizon': String(centre.above_horizon),
                'data-peak-t-utc': centre.peak_t_utc === null ? '' : centre.peak_t_utc,
                'data-peak-sunlit-in-darkness': String(centre.peak_sunlit_in_darkness === true),
                'data-sunlit-in-darkness-samples': String(centre.sunlit_in_darkness_samples),
              },
              [
                el('td', { class: 'num', text: String(centre.rank) }),
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
                      ? `visible above the ${minElevationDeg} deg minimum elevation`
                      : centre.max_elevation_deg === null
                        ? 'no ascent sample, so not visible'
                        : centre.max_elevation_deg > 0
                          ? 'above the horizon but below the minimum elevation'
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
      chartNote.textContent = report.ascent_covered
        ? `No centre reaches the ${minElevationDeg} deg minimum elevation during the ascent of this window, so there is no best view to draw.`
        : 'The elevation chart appears once an ephemeris covers the ascent of the selected window.';
      return;
    }
    const { element, points } = renderElevationCurve(report.best_centre, { elevationMaskDeg });
    replaceChildren(chartHost, [element]);
    chartNote.textContent =
      `Best view ${report.best_centre.name}, max elevation ${elevationText(report.best_centre.max_elevation_deg)} ` +
      `at ${report.best_centre.peak_t_utc === null ? 'no sample' : formatUtc(report.best_centre.peak_t_utc)}, ` +
      `range ${report.best_centre.peak_range_km === null ? 'no sample' : `${report.best_centre.peak_range_km.toFixed(0)} km`}, ` +
      `${points.length} ascent samples.`;
  }

  function draw(state) {
    const report = reportFrom(state);
    lastReport = report;
    renderStatus(state, report);
    renderAscentNote(report);
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
          `Circles mark every centre: a filled circle is a centre that reaches the ${minElevationDeg} deg minimum ` +
          'elevation during the ascent, an open circle is one that does not. Leaflet is loaded from ' +
          'frontend/node_modules, not from a CDN.';
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