import {
  CORRIDOR_ARC_SAMPLES,
  EARTH_RADIUS_M,
  OMEGA_SID_RAD_S,
  TRACK_START_TOLERANCE_KM,
} from './config.js';

export const DEG = Math.PI / 180;

export function wrapDeg(value) {
  return ((value % 360) + 360) % 360;
}

export function clamp(value, low, high) {
  return Math.min(high, Math.max(low, value));
}

/**
 * Geodetic to ECEF on a sphere of the given radius, WGS84 longitude positive east.
 * The ephemeris altitude is treated as height above that sphere, which is the
 * simplification stated in frontend/README.md.
 */
export function geodeticToEcef(latDeg, lonDeg, altM = 0, radiusM = EARTH_RADIUS_M) {
  const lat = latDeg * DEG;
  const lon = lonDeg * DEG;
  const r = radiusM + altM;
  return {
    x: r * Math.cos(lat) * Math.cos(lon),
    y: r * Math.cos(lat) * Math.sin(lon),
    z: r * Math.sin(lat),
  };
}

export function dot3(a, b) {
  return a.x * b.x + a.y * b.y + a.z * b.z;
}

export function norm3(a) {
  return Math.hypot(a.x, a.y, a.z);
}

export function subtract3(a, b) {
  return { x: a.x - b.x, y: a.y - b.y, z: a.z - b.z };
}

export function crossNorm(a, b) {
  return Math.hypot(a.y * b.z - a.z * b.y, a.z * b.x - a.x * b.z, a.x * b.y - a.y * b.x);
}

export function localFrame(latDeg, lonDeg) {
  const lat = latDeg * DEG;
  const lon = lonDeg * DEG;
  return {
    east: { x: -Math.sin(lon), y: Math.cos(lon), z: 0 },
    north: { x: -Math.sin(lat) * Math.cos(lon), y: -Math.sin(lat) * Math.sin(lon), z: Math.cos(lat) },
    up: { x: Math.cos(lat) * Math.cos(lon), y: Math.cos(lat) * Math.sin(lon), z: Math.sin(lat) },
  };
}

export function greatCircleDistanceKm(lat1, lon1, lat2, lon2, radiusM = EARTH_RADIUS_M) {
  const centralAngle = Math.acos(
    clamp(
      Math.sin(lat1 * DEG) * Math.sin(lat2 * DEG) +
        Math.cos(lat1 * DEG) * Math.cos(lat2 * DEG) * Math.cos((lon2 - lon1) * DEG),
      -1,
      1,
    ),
  );
  return (centralAngle * radiusM) / 1000;
}

export function initialBearingDeg(lat1, lon1, lat2, lon2) {
  const p1 = lat1 * DEG;
  const p2 = lat2 * DEG;
  const dLon = (lon2 - lon1) * DEG;
  const y = Math.sin(dLon) * Math.cos(p2);
  const x = Math.cos(p1) * Math.sin(p2) - Math.sin(p1) * Math.cos(p2) * Math.cos(dLon);
  return wrapDeg(Math.atan2(y, x) / DEG);
}

export function destinationPoint(latDeg, lonDeg, bearingDeg, distanceKm, radiusM = EARTH_RADIUS_M) {
  const angular = (distanceKm * 1000) / radiusM;
  const p1 = latDeg * DEG;
  const l1 = lonDeg * DEG;
  const bearing = bearingDeg * DEG;
  const p2 = Math.asin(
    Math.sin(p1) * Math.cos(angular) + Math.cos(p1) * Math.sin(angular) * Math.cos(bearing),
  );
  const l2 =
    l1 +
    Math.atan2(
      Math.sin(bearing) * Math.sin(angular) * Math.cos(p1),
      Math.cos(angular) - Math.sin(p1) * Math.sin(p2),
    );
  return { lat_deg: p2 / DEG, lon_deg: l2 / DEG };
}

export function siteOf(siteResponse) {
  if (siteResponse === null || siteResponse === undefined) {
    return null;
  }
  return {
    name: siteResponse.name,
    lat_deg: siteResponse.phi_s_deg,
    lon_deg: siteResponse.lambda_s_deg,
    alt_m: siteResponse.h_s_m,
    corridor: siteResponse.corridor ?? null,
  };
}

export function corridorBounds(siteResponse) {
  const corridor = siteResponse === null || siteResponse === undefined ? null : siteResponse.corridor;
  if (corridor === null || corridor === undefined) {
    return null;
  }
  if (!Number.isFinite(corridor.A_min_deg) || !Number.isFinite(corridor.A_max_deg)) {
    return null;
  }
  return {
    a_min_deg: corridor.A_min_deg,
    a_max_deg: corridor.A_max_deg,
    source: corridor.source ?? null,
    flag: corridor.flag ?? null,
  };
}

/**
 * The corridor polygon of spec V.2. The site response is written in prose without field
 * names for the hazard-test vertices, so declared vertices are used when the response
 * carries them and the azimuth wedge A_min_deg to A_max_deg is drawn otherwise.
 */
export function corridorPolygon(siteResponse, options = {}) {
  const {
    radiusKm = null,
    samples = CORRIDOR_ARC_SAMPLES,
    trackPoints = [],
  } = options;
  const site = siteOf(siteResponse);
  const bounds = corridorBounds(siteResponse);
  if (site === null || bounds === null) {
    return { vertices: [], basis: 'unavailable', radius_km: null, bounds: null };
  }
  const declared = readDeclaredCorridorVertices(siteResponse);
  if (declared !== null) {
    return { vertices: declared, basis: 'response vertices', radius_km: radiusKm, bounds };
  }
  const extent = trackExtentKm(site, trackPoints);
  const span = radiusKm === null ? (extent === null ? null : extent) : Math.max(radiusKm, extent ?? 0);
  if (span === null) {
    return { vertices: [], basis: 'azimuth wedge without a radius', radius_km: null, bounds };
  }
  const vertices = [{ lat_deg: site.lat_deg, lon_deg: site.lon_deg }];
  const step = (bounds.a_max_deg - bounds.a_min_deg) / Math.max(1, samples - 1);
  for (let index = 0; index < samples; index += 1) {
    vertices.push(destinationPoint(site.lat_deg, site.lon_deg, bounds.a_min_deg + step * index, span));
  }
  return { vertices, basis: 'azimuth wedge from corridor.A_min_deg and A_max_deg', radius_km: span, bounds };
}

function readDeclaredCorridorVertices(siteResponse) {
  if (siteResponse === null || siteResponse === undefined) {
    return null;
  }
  const candidates = [siteResponse.corridor_polygon, siteResponse.corridor_polygon_vertices];
  for (const candidate of candidates) {
    if (!Array.isArray(candidate) || candidate.length < 3) {
      continue;
    }
    const vertices = [];
    for (const entry of candidate) {
      if (Array.isArray(entry) && entry.length >= 2) {
        vertices.push({ lat_deg: Number(entry[0]), lon_deg: Number(entry[1]) });
      } else if (entry !== null && typeof entry === 'object') {
        vertices.push({ lat_deg: Number(entry.lat_deg ?? entry.lat), lon_deg: Number(entry.lon_deg ?? entry.lon) });
      }
    }
    if (vertices.length >= 3 && vertices.every((v) => Number.isFinite(v.lat_deg) && Number.isFinite(v.lon_deg))) {
      return vertices;
    }
  }
  return null;
}

export function trackExtentKm(site, trackPoints) {
  if (site === null || !Array.isArray(trackPoints) || trackPoints.length === 0) {
    return null;
  }
  let longest = 0;
  for (const point of trackPoints) {
    longest = Math.max(longest, greatCircleDistanceKm(site.lat_deg, site.lon_deg, point.lat_deg, point.lon_deg));
  }
  return longest;
}

export function trackBearingAt(points, index) {
  if (!Array.isArray(points) || points.length < 2) {
    return null;
  }
  const last = points.length - 1;
  const clampedIndex = clamp(index, 0, last);
  const from = points[clampedIndex === 0 ? 0 : clampedIndex - 1];
  const to = points[clampedIndex === last ? last : clampedIndex + 1];
  if (from === undefined || to === undefined || from === to) {
    return null;
  }
  return initialBearingDeg(from.lat_deg, from.lon_deg, to.lat_deg, to.lon_deg);
}

/**
 * The hazard buffer of spec V.2: a band of the configured vehicle footprint half width
 * drawn either side of the nominal track. Without a declared half width no polygon is
 * returned, because a buffer width is vehicle data and not a browser default.
 */
export function hazardBufferPolygon(trackPoints, halfWidthKm, options = {}) {
  const { radiusM = EARTH_RADIUS_M, toleranceKm = 0.05 } = options;
  if (!Number.isFinite(halfWidthKm) || halfWidthKm <= 0) {
    return { vertices: [], half_width_km: null };
  }
  if (!Array.isArray(trackPoints) || trackPoints.length < 2) {
    return { vertices: [], half_width_km: halfWidthKm };
  }
  const port = [];
  const starboard = [];
  for (let index = 0; index < trackPoints.length; index += 1) {
    const point = trackPoints[index];
    const bearing = trackBearingAt(trackPoints, index);
    if (bearing === null) {
      continue;
    }
    port.push(destinationPoint(point.lat_deg, point.lon_deg, bearing - 90, halfWidthKm, radiusM));
    starboard.push(destinationPoint(point.lat_deg, point.lon_deg, bearing + 90, halfWidthKm, radiusM));
  }
  if (port.length < 2) {
    return { vertices: [], half_width_km: halfWidthKm };
  }
  const left = port.map((point, index) => ({ lat_deg: point.lat_deg, lon_deg: point.lon_deg }));
  const right = starboard
    .map((point) => ({ lat_deg: point.lat_deg, lon_deg: point.lon_deg }))
    .reverse();
  const vertices = [...left, ...right];
  return { vertices, half_width_km: halfWidthKm, tolerance_km: toleranceKm };
}

export function withinCorridor(bearingDeg, bounds, toleranceDeg = 0) {
  if (bounds === null) {
    return true;
  }
  const low = bounds.a_min_deg - toleranceDeg;
  const high = bounds.a_max_deg + toleranceDeg;
  const bearing = wrapDeg(bearingDeg);
  if (low <= 0 && high >= 360) {
    return true;
  }
  const crossesNorth = low < 0 || high >= 360;
  if (crossesNorth) {
    return bearing >= low + 360 || bearing <= high;
  }
  return bearing >= low && bearing <= high;
}

/**
 * Whether any azimuth between two bearings lies inside the corridor. The two bearings are the
 * ends of the short arc between them; the arc meets the corridor when either end is inside
 * it or when a corridor bound lies on the arc.
 */
export function bracketMeetsCorridor(firstDeg, secondDeg, bounds, toleranceDeg = 0) {
  if (bounds === null) {
    return true;
  }
  if (withinCorridor(firstDeg, bounds, toleranceDeg) || withinCorridor(secondDeg, bounds, toleranceDeg)) {
    return true;
  }
  const sweep = ((secondDeg - firstDeg + 540) % 360) - 180;
  const onArc = (angleDeg) => {
    const offset = ((angleDeg - firstDeg + 540) % 360) - 180;
    return sweep >= 0 ? offset >= 0 && offset <= sweep : offset <= 0 && offset >= sweep;
  };
  return onArc(bounds.a_min_deg - toleranceDeg) || onArc(bounds.a_max_deg + toleranceDeg);
}

/**
 * The UI level guard for the northbound bug of the inherited prototype: every ground track
 * sample of the ascent must lie inside the azimuth wedge of the site corridor, so a track
 * running north over Quebec is refused and surfaced rather than drawn as a corridor track.
 *
 * Three rules, each from a defect met against a running API:
 *
 * - With `ascent` (the liftoff and injection instants of the selected row) only the samples
 *   of that interval are checked. The corridor is a launch corridor; an orbit that goes on
 *   round the Earth after injection cannot stay inside an azimuth wedge from the site.
 * - A sample within `startToleranceKm` of the site is on the pad and is inside. The bearing
 *   from a point to itself is undefined, and the pad is where every ascent begins.
 * - The sample at the liftoff instant must be on the pad. A track that is somewhere else at
 *   liftoff is not an ascent from the site, whatever its bearing from the site happens to be.
 *   `starts_at_site` is null when the track has no sample at the liftoff instant.
 *
 * And a fourth, from the first real ascent the API served. The corridor bounds the launch
 * azimuth, the direction of the orbit plane at the site in the frame fixed at liftoff. A
 * ground track is drawn on the turning Earth, which moves east under that plane by
 * omega_sid * (t - t_liftoff): 2.26 deg over a 540 s ascent, enough to put the injection
 * point of a launch on azimuth 191.6 deg at bearing 198.3 deg from Canso. The launch azimuth
 * of a sample cannot be read from its position alone, because it depends on how much of the
 * Earth's rotation the vehicle still carries. It is bracketed by two bearings from the site:
 * `bearing_deg`, the sample where it is on the ground, which is the azimuth if the vehicle
 * were still fixed to the Earth, and `plane_azimuth_deg`, the sample with the Earth turned
 * back to the liftoff instant, which is the azimuth if it had been in a plane fixed in
 * space since liftoff. A sample is refused only when the whole bracket lies outside the
 * corridor. The bracket needs the liftoff instant, so without `ascent` the ground bearing
 * alone decides, as before. `plane_azimuth_deg` of the result is that of the last sample of
 * the ascent, the plane the ascent reaches.
 */
export function corridorCheck(siteResponse, trackPoints, options = {}) {
  const {
    toleranceDeg = 0,
    ascent = null,
    startToleranceKm = TRACK_START_TOLERANCE_KM,
    omegaSidRadS = OMEGA_SID_RAD_S,
  } = options;
  const omegaDegPerS = (Number.isFinite(omegaSidRadS) ? omegaSidRadS : OMEGA_SID_RAD_S) * (180 / Math.PI);
  const site = siteOf(siteResponse);
  const bounds = corridorBounds(siteResponse);
  const all = Array.isArray(trackPoints) ? trackPoints : [];
  const startMs = ascent === null ? null : Date.parse(ascent.start);
  const endMs = ascent === null ? null : Date.parse(ascent.end);
  const checked =
    ascent === null
      ? all
      : all.filter((point) => {
          const at = Date.parse(point.t_utc);
          return Number.isFinite(at) && at >= startMs && at <= endMs;
        });
  const outside = all.length - checked.length;
  if (site === null || checked.length === 0) {
    return {
      available: false,
      inside: null,
      bounds,
      samples: [],
      violations: [],
      samples_outside_ascent: outside,
      starts_at_site: null,
      start_distance_km: null,
    };
  }
  const samples = [];
  const violations = [];
  for (const point of checked) {
    const distanceKm = greatCircleDistanceKm(site.lat_deg, site.lon_deg, point.lat_deg, point.lon_deg);
    const bearingDeg = initialBearingDeg(site.lat_deg, site.lon_deg, point.lat_deg, point.lon_deg);
    const onPad = distanceKm <= startToleranceKm;
    const rotationDeg =
      ascent === null ? null : (omegaDegPerS * (Date.parse(point.t_utc) - startMs)) / 1000;
    const planeAzimuthDeg =
      rotationDeg === null
        ? null
        : initialBearingDeg(site.lat_deg, site.lon_deg, point.lat_deg, point.lon_deg + rotationDeg);
    const groundInside = withinCorridor(bearingDeg, bounds, toleranceDeg);
    const inside =
      onPad ||
      (planeAzimuthDeg === null
        ? groundInside
        : bracketMeetsCorridor(bearingDeg, planeAzimuthDeg, bounds, toleranceDeg));
    const sample = {
      t_utc: point.t_utc ?? null,
      lat_deg: point.lat_deg,
      lon_deg: point.lon_deg,
      bearing_deg: bearingDeg,
      plane_azimuth_deg: planeAzimuthDeg,
      earth_rotation_deg: rotationDeg,
      ground_inside: onPad || groundInside,
      distance_km: distanceKm,
      on_pad: onPad,
      inside,
    };
    samples.push(sample);
    if (!inside) {
      violations.push(sample);
    }
  }
  const atLiftoff =
    ascent === null ? null : (samples.find((sample) => Date.parse(sample.t_utc) === startMs) ?? null);
  const startsAtSite = atLiftoff === null ? null : atLiftoff.on_pad;
  const offPad = samples.filter((sample) => !sample.on_pad);
  const bearings = offPad.map((sample) => sample.bearing_deg);
  const planeAzimuths = offPad
    .map((sample) => sample.plane_azimuth_deg)
    .filter((value) => value !== null);
  const reached = ascent === null || offPad.length === 0 ? null : offPad[offPad.length - 1];
  return {
    available: true,
    inside: violations.length === 0 && startsAtSite !== false,
    ground_bearings_inside: samples.every((sample) => sample.ground_inside),
    plane_azimuth_deg: reached === null ? null : reached.plane_azimuth_deg,
    plane_t_utc: reached === null ? null : reached.t_utc,
    earth_rotation_deg: reached === null ? null : reached.earth_rotation_deg,
    plane_azimuth_min_deg: planeAzimuths.length === 0 ? null : Math.min(...planeAzimuths),
    plane_azimuth_max_deg: planeAzimuths.length === 0 ? null : Math.max(...planeAzimuths),
    bounds,
    samples,
    violations,
    samples_outside_ascent: outside,
    starts_at_site: startsAtSite,
    start_distance_km: atLiftoff === null ? null : atLiftoff.distance_km,
    start_t_utc: atLiftoff === null ? null : atLiftoff.t_utc,
    start_tolerance_km: startToleranceKm,
    bearing_min_deg: bearings.length === 0 ? null : Math.min(...bearings),
    bearing_max_deg: bearings.length === 0 ? null : Math.max(...bearings),
    distance_max_km: Math.max(...samples.map((sample) => sample.distance_km)),
  };
}
