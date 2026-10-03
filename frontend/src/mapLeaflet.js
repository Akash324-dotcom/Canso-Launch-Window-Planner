import { LEAFLET_ESM } from './config.js';

let leafletPromise = null;

/**
 * Leaflet is loaded from frontend/node_modules, never from a CDN, so the application works
 * with the network off. The dynamic import keeps the library out of the path of screens
 * that render no map and out of the module graph of a jsdom test that does not need it.
 */
export function loadLeaflet() {
  if (leafletPromise === null) {
    leafletPromise = import(LEAFLET_ESM).then((module) => {
      const library = module.default === undefined ? module : module.default;
      if (typeof library.map !== 'function') {
        throw new Error('the Leaflet ES module did not expose a map factory');
      }
      return library;
    });
  }
  return leafletPromise;
}

export function createMapContainer(host, L, options = {}) {
  const map = L.map(host, {
    center: options.center ?? [45.3, -61.0],
    zoom: options.zoom ?? 5,
    zoomControl: options.zoomControl ?? true,
    attributionControl: false,
    preferCanvas: false,
  });
  return map;
}

export function clearLayers(map) {
  const layers = [];
  map.eachLayer((layer) => layers.push(layer));
  for (const layer of layers) {
    map.removeLayer(layer);
  }
}

/**
 * Draws the corridor polygon, the hazard buffer, the ground track, the site marker and the
 * population centre markers of the viewing map. No tile layer is requested, because the
 * demo runs with the network off.
 */
export function drawTrajectoryLayers(L, map, model) {
  const drawn = { corridor: null, buffer: null, track: null, site: null, centres: [] };
  const { site, trackPoints = [], corridor, buffer, centres = [] } = model;
  if (corridor !== null && corridor !== undefined && corridor.vertices.length >= 3) {
    drawn.corridor = L.polygon(
      corridor.vertices.map((vertex) => [vertex.lat_deg, vertex.lon_deg]),
      { className: 'layer-corridor', color: '#14507a', weight: 1, fillOpacity: 0.08, interactive: false },
    ).addTo(map);
  }
  if (buffer !== null && buffer !== undefined && buffer.vertices.length >= 3) {
    drawn.buffer = L.polygon(
      buffer.vertices.map((vertex) => [vertex.lat_deg, vertex.lon_deg]),
      {
        className: 'layer-buffer',
        color: '#8a5b06',
        weight: 1,
        dashArray: '4 4',
        fillOpacity: 0.06,
        interactive: false,
      },
    ).addTo(map);
  }
  if (trackPoints.length >= 2) {
    drawn.track = L.polyline(
      trackPoints.map((point) => [point.lat_deg, point.lon_deg]),
      { className: 'layer-track', color: '#14507a', weight: 3, interactive: false },
    ).addTo(map);
  }
  if (site !== null && site !== undefined) {
    drawn.site = L.circleMarker([site.lat_deg, site.lon_deg], {
      className: 'layer-site',
      radius: 7,
      color: '#14161a',
      weight: 2,
      fillColor: '#ffffff',
      fillOpacity: 1,
      interactive: false,
    }).addTo(map);
  }
  for (const centre of centres) {
    drawn.centres.push(
      L.circleMarker([centre.lat_deg, centre.lon_deg], {
        className: 'layer-centre',
        radius: 5,
        color: '#1f6f43',
        weight: 2,
        fillColor: '#ffffff',
        fillOpacity: 1,
        interactive: false,
      }).addTo(map),
    );
  }
  return drawn;
}

export function drawViewingLayers(L, map, model) {
  const { centres = [], report = null } = model;
  const drawn = [];
  for (const centre of centres) {
    const entry =
      report === null ? null : report.centres.find((candidate) => candidate.id === centre.id) ?? null;
    const visible = entry !== null && entry.visible === true;
    drawn.push(
      L.circleMarker([centre.lat_deg, centre.lon_deg], {
        className: visible ? 'layer-centre-visible' : 'layer-centre-dark',
        radius: visible ? 8 : 5,
        color: visible ? '#1f6f43' : '#56606c',
        weight: 2,
        fillColor: visible ? '#1f6f43' : '#9aa5b1',
        fillOpacity: visible ? 0.35 : 0.15,
        interactive: false,
      }).addTo(map),
    );
  }
  return drawn;
}

export function fitToModel(L, map, model) {
  const latLngs = [];
  for (const point of model.trackPoints ?? []) {
    latLngs.push([point.lat_deg, point.lon_deg]);
  }
  for (const vertex of model.corridor?.vertices ?? []) {
    latLngs.push([vertex.lat_deg, vertex.lon_deg]);
  }
  if (model.site !== null && model.site !== undefined) {
    latLngs.push([model.site.lat_deg, model.site.lon_deg]);
  }
  if (latLngs.length === 0) {
    return false;
  }
  map.fitBounds(L.latLngBounds(latLngs).pad(0.15), { animate: false });
  return true;
}