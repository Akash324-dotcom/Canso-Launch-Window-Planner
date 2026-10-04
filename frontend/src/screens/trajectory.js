import {
  CORRIDOR_BEARING_TOLERANCE_DEG,
  CORRIDOR_FALLBACK_ARC_KM,
  MODE_OFFLINE,
  OMEGA_SID_RAD_S,
  OMEGA_SID_SOURCE,
  TRACK_START_TOLERANCE_FLAG,
  ORBIT_IDS_BY_TYPE,
  VEHICLE_FOOTPRINTS,
} from '../config.js';
import { el, replaceChildren } from '../dom.js';
import {
  corridorCheck,
  corridorPolygon,
  hazardBufferPolygon,
  siteOf,
} from '../geo.js';
import { clearLayers, createMapContainer, drawTrajectoryLayers, fitToModel, loadLeaflet } from '../mapLeaflet.js';
import { formatUtc } from '../time.js';

const ORBIT_ID_UNKNOWN =
  'The ephemeris id of a CUSTOM target is created implicitly by POST /v1/windows and is not named by ' +
  'any field of the frozen response schema, so no track is requested for this row. ENGINE to name it.';

function vertexList(id) {
  return el('ol', { class: 'vertex-list', id });
}

function vertexRow(vertex, extraAttributes) {
  return el('li', { class: 'vertex', ...extraAttributes }, [
    el('span', { text: `${Number(vertex.lat_deg).toFixed(4)} N, ${Number(vertex.lon_deg).toFixed(4)} E` }),
  ]);
}

function footprintFor(vehicleProfileId, registry = VEHICLE_FOOTPRINTS) {
  if (vehicleProfileId === null || vehicleProfileId === undefined) {
    return null;
  }
  const entry = registry[vehicleProfileId];
  return entry === undefined ? null : entry;
}

export function orbitIdFor(request) {
  if (request === null || request === undefined || request.target === undefined) {
    return null;
  }
  const orbitId = ORBIT_IDS_BY_TYPE[request.target.type];
  return orbitId === undefined ? null : orbitId;
}

export function createTrajectoryScreen({ root, store, footprintRegistry = VEHICLE_FOOTPRINTS }) {
  const mapHost = el('div', {
    class: 'map',
    id: 'trajectory-map',
    role: 'img',
    'aria-label': 'Corridor polygon, ground track, hazard buffer, site marker and population centres of the selected window',
    'data-leaflet': 'pending',
  });
  const status = el('p', { class: 'hint', id: 'trajectory-status' });
  const sub = el('p', { class: 'hint', id: 'trajectory-sub' });
  const mapNote = el('p', { class: 'hint', id: 'trajectory-map-note' });
  const corridorList = vertexList('corridor-vertices');
  const trackList = vertexList('trajectory-track');
  const bufferList = vertexList('hazard-buffer-vertices');
  const bufferNote = el('p', { class: 'hint', id: 'hazard-buffer-note' });
  const siteMarker = el('p', { class: 'hint', id: 'site-marker', 'data-lat-deg': '', 'data-lon-deg': '' });
  const corridorCheckLine = el('p', {
    class: 'hint',
    id: 'corridor-check',
    'data-available': 'false',
    'data-inside': '',
  });
  const centreList = el('ul', { class: 'chip-list', id: 'trajectory-centres' });

  root.replaceChildren(
    el('header', { class: 'panel-head' }, [
      el('h2', { text: 'Screen 2, trajectory of the selected window' }),
      sub,
    ]),
    el('p', { class: 'hint' }, [
      'The corridor polygon comes from GET /v1/site, the ground track from GET /v1/orbits/{id}/ephemeris for the ' +
      'lifter to the injection instant of the selected row, and the hazard buffer from the configured vehicle ' +
      'footprint. The 3D globe of the inherited prototype is not carried over: spec V.2 makes it optional and ' +
      'the 2D map is primary.',
    ]),
    status,
    mapHost,
    mapNote,
    el('h3', { text: 'Corridor polygon' }),
    corridorList,
    el('h3', { text: 'Ground track' }),
    trackList,
    el('h3', { text: 'Hazard buffer' }),
    bufferNote,
    bufferList,
    el('h3', { text: 'Site and population centres' }),
    siteMarker,
    centreList,
    el('h3', { text: 'Corridor guard' }),
    corridorCheckLine,
  );

  let library = null;
  let map = null;
  let mountStatus = 'pending';
  let mountPromise = null;
  let lastModel = null;

  function selectedRow(state) {
    const rows = state.engineResponse === null ? [] : state.engineResponse.windows ?? [];
    const index = state.selectedRowIndex;
    if (!Number.isInteger(index) || index < 0 || index >= rows.length) {
      return null;
    }
    return rows[index];
  }

  function footprintHalfWidthKm(state) {
    const vehicleProfileId =
      state.engineResponse === null || state.engineResponse === undefined
        ? null
        : state.engineResponse.provenance_block?.vehicle_profile_id ?? null;
    const footprint = footprintFor(vehicleProfileId, footprintRegistry);
    if (footprint === null) {
      return { half_width_km: null, source: null, flag: null, profile: vehicleProfileId };
    }
    return {
      half_width_km: footprint.hazard_half_width_km ?? null,
      source: footprint.source ?? null,
      flag: footprint.flag ?? null,
      profile: vehicleProfileId,
    };
  }

  function buildModel(state) {
    const row = selectedRow(state);
    const points = state.ephemerisResponse === null ? [] : state.ephemerisResponse.points ?? [];
    const site = siteOf(state.siteResponse);
    const ascent = row === null ? null : { start: row.t_liftoff_utc, end: row.t_injection_utc };
    const constants = state.ephemerisResponse === null ? null : (state.ephemerisResponse.constants_block ?? null);
    const check = corridorCheck(state.siteResponse, points, {
      toleranceDeg: CORRIDOR_BEARING_TOLERANCE_DEG,
      ascent,
      omegaSidRadS:
        constants !== null && Number.isFinite(constants.omega_sid_rad_s)
          ? constants.omega_sid_rad_s
          : OMEGA_SID_RAD_S,
    });
    // The wedge is sized to the ascent the guard accepted. A track that is not an ascent from
    // the site, or the orbit after injection, must not stretch the corridor round the Earth.
    const ascentPoints =
      check.available && check.starts_at_site !== false
        ? check.samples.map((sample) => ({ lat_deg: sample.lat_deg, lon_deg: sample.lon_deg }))
        : [];
    const corridor = corridorPolygon(state.siteResponse, {
      radiusKm: CORRIDOR_FALLBACK_ARC_KM,
      trackPoints: ascentPoints,
    });
    const footprint = footprintHalfWidthKm(state);
    const buffer = hazardBufferPolygon(points, footprint.half_width_km);
    const centres = Array.isArray(state.centres) ? state.centres : [];
    return {
      row,
      site,
      points,
      corridor,
      buffer,
      centres,
      footprint,
      check,
      orbitId: orbitIdFor(state.request),
    };
  }

  function renderStatus(state, model) {
    if (state.engineResponse === null) {
      status.textContent = 'No window response fetched yet.';
      return;
    }
    if (model.row === null) {
      status.textContent = 'Select a window row in the table above to fetch and draw its ground track.';
      return;
    }
    if (model.orbitId === null) {
      status.textContent = ORBIT_ID_UNKNOWN;
      return;
    }
    const parts = [
      `Row ${state.selectedRowIndex} of POST /v1/windows, liftoff ${formatUtc(model.row.t_liftoff_utc)}, ` +
        `orbit id ${model.orbitId}`,
    ];
    if (state.ephemerisOrigin === 'fixture') {
      parts.push(`offline fixture ${model.points.length} points`);
    } else if (state.ephemerisResponse === null) {
      parts.push(state.ephemerisError === null ? 'no ephemeris response yet' : state.ephemerisError);
    } else {
      parts.push(`${model.points.length} points, ground_track_valid ${state.ephemerisResponse.ground_track_valid}`);
    }
    if (state.mode === MODE_OFFLINE) {
      parts.push('mode offline_precomputed');
    }
    status.textContent = parts.join('. ');
  }

  function renderCorridor(model) {
    replaceChildren(
      corridorList,
      model.corridor.vertices.length === 0
        ? [el('li', { class: 'vertex-empty', text: 'No corridor polygon: the site response has not arrived.' })]
        : model.corridor.vertices.map((vertex, index) =>
            vertexRow(vertex, {
              'data-corridor-vertex': String(index),
              'data-lat-deg': String(vertex.lat_deg),
              'data-lon-deg': String(vertex.lon_deg),
            }),
          ),
    );
    sub.textContent =
      model.corridor.vertices.length === 0
        ? ''
        : `${model.corridor.vertices.length} vertices, ${model.corridor.basis}` +
          (model.corridor.bounds === null
            ? ''
            : `, azimuth ${model.corridor.bounds.a_min_deg} to ${model.corridor.bounds.a_max_deg} deg` +
              (model.corridor.bounds.flag === null ? '' : ` (${model.corridor.bounds.flag})`));
  }

  function renderTrack(model) {
    replaceChildren(
      trackList,
      model.points.length === 0
        ? [el('li', { class: 'vertex-empty', text: 'No ground track fetched for the selected row.' })]
        : model.points.map((point, index) =>
            el(
              'li',
              {
                class: 'vertex',
                'data-track-point': String(index),
                'data-lat-deg': String(point.lat_deg),
                'data-lon-deg': String(point.lon_deg),
                'data-alt-km': String(point.alt_km),
                'data-t-utc': point.t_utc,
              },
              [
                el('span', {
                  text: `${point.t_utc}, ${point.lat_deg} lat, ${point.lon_deg} lon, ${point.alt_km} km altitude`,
                }),
              ],
            ),
          ),
    );
  }

  function renderBuffer(model) {
    const footprint = model.footprint;
    if (footprint.half_width_km === null) {
      bufferNote.textContent =
        `The hazard buffer is not drawn: the vehicle footprint half width for ${footprint.profile ?? 'the vehicle profile'} ` +
        `is not declared in src/config.js VEHICLE_FOOTPRINTS on this branch. Owner: ${footprint.source ?? 'ENGINE'}. ` +
        'A buffer width is vehicle data, so no value is invented in the browser.';
      bufferNote.classList.add('caution');
    } else {
      bufferNote.textContent =
        `Hazard buffer half width ${footprint.half_width_km} km, ${footprint.flag}, owner ${footprint.source}.`;
      bufferNote.classList.remove('caution');
    }
    replaceChildren(
      bufferList,
      model.buffer.vertices.length === 0
        ? [el('li', { class: 'vertex-empty', text: 'No buffer polygon.' })]
        : model.buffer.vertices.map((vertex, index) =>
            vertexRow(vertex, {
              'data-buffer-vertex': String(index),
              'data-lat-deg': String(vertex.lat_deg),
              'data-lon-deg': String(vertex.lon_deg),
            }),
          ),
    );
  }

  function renderSiteAndCentres(model, state) {
    if (model.site === null) {
      siteMarker.textContent = 'No site response: the site marker needs GET /v1/site.';
      siteMarker.setAttribute('data-lat-deg', '');
      siteMarker.setAttribute('data-lon-deg', '');
    } else {
      siteMarker.textContent = `Site ${model.site.name} at ${model.site.lat_deg} lat, ${model.site.lon_deg} lon, ${model.site.alt_m} m altitude (phi_s_deg, lambda_s_deg, h_s_m).`;
      siteMarker.setAttribute('data-lat-deg', String(model.site.lat_deg));
      siteMarker.setAttribute('data-lon-deg', String(model.site.lon_deg));
    }
    const centres = model.centres;
    replaceChildren(
      centreList,
      centres.length === 0
        ? [el('li', { class: 'chip', text: 'No population centres loaded.' })]
        : centres.map((centre) =>
            el('li', {
              class: 'chip',
              'data-centre-id': String(centre.id),
              'data-lat-deg': String(centre.lat_deg),
              'data-lon-deg': String(centre.lon_deg),
              text: `${centre.name}, ${centre.lat_deg} lat, ${centre.lon_deg} lon`,
            }),
          ),
    );
    if (state.centresError !== null) {
      replaceChildren(centreList, [
        el('li', {
          class: 'chip',
          text: `Population centres unreadable from src/data/centres.json: ${state.centresError}`,
        }),
      ]);
    }
  }

  function renderGuard(model) {
    const check = model.check;
    corridorCheckLine.setAttribute(
      'data-starts-at-site',
      check.starts_at_site === null || check.starts_at_site === undefined ? '' : String(check.starts_at_site),
    );
    if (!check.available) {
      corridorCheckLine.setAttribute('data-available', 'false');
      corridorCheckLine.setAttribute('data-inside', '');
      corridorCheckLine.textContent =
        check.samples_outside_ascent > 0
          ? `The corridor guard has nothing to check: none of the ${check.samples_outside_ascent} ground track ` +
            'samples falls between the liftoff and the injection instant of the selected row.'
          : 'The corridor guard needs both the site corridor bounds and a ground track, so it has nothing to check yet.';
      return;
    }
    corridorCheckLine.setAttribute('data-available', 'true');
    corridorCheckLine.setAttribute('data-inside', String(check.inside));
    const scope =
      check.samples_outside_ascent > 0
        ? ` The guard checks the ${check.samples.length} sample(s) of the ascent, liftoff to injection; ` +
          `${check.samples_outside_ascent} sample(s) outside that interval are drawn and not checked.`
        : '';
    if (check.starts_at_site === false) {
      corridorCheckLine.classList.add('caution');
      corridorCheckLine.textContent =
        `TRACK REJECTED by the UI: the ground track is ${check.start_distance_km.toFixed(1)} km from the site at the ` +
        `liftoff instant ${check.start_t_utc}, so it is not an ascent from the site and it is not rendered as a ` +
        `corridor track. A sample within ${check.start_tolerance_km} km of the site counts as on the pad ` +
        `(${TRACK_START_TOLERANCE_FLAG}, src/config.js TRACK_START_TOLERANCE_KM).${scope}`;
      return;
    }
    if (check.inside && check.ground_bearings_inside === false) {
      const span = (low, high) =>
        low.toFixed(1) === high.toFixed(1) ? `${low.toFixed(1)} deg` : `${low.toFixed(1)} to ${high.toFixed(1)} deg`;
      corridorCheckLine.textContent =
        `Every sample of this ascent is consistent with a launch azimuth inside the corridor ` +
        `${check.bounds.a_min_deg} to ${check.bounds.a_max_deg} deg. Seen from the site on the ground the samples ` +
        `bear ${span(check.bearing_min_deg, check.bearing_max_deg)}, past the corridor, because the Earth turns ` +
        `${check.earth_rotation_deg.toFixed(2)} deg under the orbit plane between liftoff and ${check.plane_t_utc}. ` +
        `In the frame fixed at liftoff, the frame the corridor azimuth is stated in, the same samples lie on ` +
        `${span(check.plane_azimuth_min_deg, check.plane_azimuth_max_deg)}, and the last of them gives the plane ` +
        `the ascent reaches, ${check.plane_azimuth_deg.toFixed(1)} deg at the site. The drawn track therefore ` +
        `bends west of the corridor wedge without leaving the corridor. Rotation rate: ${OMEGA_SID_SOURCE}. ` +
        `A northbound track over land is refused by this guard.${scope}`;
      corridorCheckLine.classList.remove('caution');
      return;
    }
    if (check.inside) {
      const bearings =
        check.bearing_min_deg === null
          ? 'every sample is on the pad'
          : `bearings ${check.bearing_min_deg.toFixed(1)} to ${check.bearing_max_deg.toFixed(1)} deg`;
      corridorCheckLine.textContent =
        `Every sample of this track lies inside the corridor azimuth ${check.bounds.a_min_deg} to ` +
        `${check.bounds.a_max_deg} deg (${bearings}). ` +
        `A northbound track over land is refused by this guard.${scope}`;
      corridorCheckLine.classList.remove('caution');
      return;
    }
    const first = check.violations[0];
    corridorCheckLine.classList.add('caution');
    corridorCheckLine.textContent =
      `HAZARD REJECTION surfaced by the UI: ${check.violations.length} of ${check.samples.length} samples leave the ` +
      `corridor azimuth ${check.bounds.a_min_deg} to ${check.bounds.a_max_deg} deg, the first at ${first.t_utc} on ` +
      `bearing ${first.bearing_deg.toFixed(1)} deg, ${first.distance_km.toFixed(1)} km from the site` +
      `${first.plane_azimuth_deg === null || first.plane_azimuth_deg === undefined ? '' : `, azimuth ${first.plane_azimuth_deg.toFixed(1)} deg in the frame fixed at liftoff`}. ` +
      `From Canso the environmental assessment corridor runs south over the Atlantic, so this track is not rendered as a corridor track.${scope}`;
  }

  function draw(state) {
    lastModel = buildModel(state);
    renderStatus(state, lastModel);
    renderCorridor(lastModel);
    renderTrack(lastModel);
    renderBuffer(lastModel);
    renderSiteAndCentres(lastModel, state);
    renderGuard(lastModel);
    if (map !== null && library !== null) {
      clearLayers(map);
      drawTrajectoryLayers(library, map, {
        site: lastModel.site,
        trackPoints: lastModel.points,
        corridor: lastModel.corridor,
        buffer: lastModel.buffer,
        centres: lastModel.centres,
      });
      fitToModel(library, map, {
        site: lastModel.site,
        trackPoints: lastModel.points,
        corridor: lastModel.corridor,
      });
    }
    return lastModel;
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
          'Map drawn with Leaflet 1.9.4 loaded from frontend/node_modules. No tile layer is requested because the demo runs with the network off.';
        if (lastModel !== null) {
          draw(store.getState());
        }
        return mountStatus;
      },
      (error) => {
        mountStatus = 'unavailable';
        mapHost.setAttribute('data-leaflet', 'unavailable');
        mapNote.textContent =
          `The Leaflet map could not be mounted (${error instanceof Error ? error.message : String(error)}). ` +
          'The corridor vertices, the ground track and the hazard buffer below are the same geometry the map draws.';
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
    render: draw,
    destroy,
  };
}