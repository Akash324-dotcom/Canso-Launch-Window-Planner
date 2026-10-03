import { EARTH_RADIUS_M, ELEVATION_MASK_DEG, VIEWING_MIN_ELEVATION_DEG } from './config.js';
import {
  DEG,
  dot3,
  geodeticToEcef,
  localFrame,
  norm3,
  subtract3,
  wrapDeg,
} from './geo.js';
import { illuminationAt } from './solar.js';

/**
 * The viewing geometry of spec V.4: for every population centre and every ephemeris
 * sample of the ASCENT of the selected window, the topocentric elevation and azimuth
 * from the centre to the vehicle, and whether the vehicle is sunlit while the observer
 * is in the Earth shadow. The geometry is stated in frontend/README.md.
 */

export const NO_ASCENT_COVERAGE = 'Ephemeris does not cover the ascent of this window';

export function earthRadiusOf(ephemerisResponse, fallback = EARTH_RADIUS_M) {
  const constants =
    ephemerisResponse === null || ephemerisResponse === undefined
      ? null
      : ephemerisResponse.constants_block;
  if (constants === null || constants === undefined) {
    return fallback;
  }
  const value = Number(constants.R_e);
  return Number.isFinite(value) && value > 0 ? value : fallback;
}

export function topocentric(observer, vehicle, frame) {
  const range = subtract3(vehicle, observer);
  const distanceM = norm3(range);
  if (distanceM === 0) {
    return { range_m: 0, range_km: 0, elevation_deg: null, azimuth_deg: null };
  }
  const unit = { x: range.x / distanceM, y: range.y / distanceM, z: range.z / distanceM };
  const up = dot3(unit, frame.up);
  const east = dot3(unit, frame.east);
  const north = dot3(unit, frame.north);
  return {
    range_m: distanceM,
    range_km: distanceM / 1000,
    elevation_deg: Math.asin(Math.min(1, Math.max(-1, up))) / DEG,
    azimuth_deg: wrapDeg(Math.atan2(east, north) / DEG),
  };
}

export function centreEntries(centres) {
  if (!Array.isArray(centres)) {
    return [];
  }
  return centres
    .filter(
      (centre) =>
        centre !== null &&
        typeof centre === 'object' &&
        Number.isFinite(Number(centre.lat_deg)) &&
        Number.isFinite(Number(centre.lon_deg)),
    )
    .map((centre) => ({
      id: String(centre.id),
      name: String(centre.name),
      lat_deg: Number(centre.lat_deg),
      lon_deg: Number(centre.lon_deg),
      alt_m: Number.isFinite(Number(centre.alt_m)) ? Number(centre.alt_m) : 0,
      flag: centre.flag === undefined ? null : centre.flag,
      source: centre.source === undefined ? null : centre.source,
    }));
}

function timeMsOf(value) {
  const parsed = Date.parse(value);
  return Number.isFinite(parsed) ? parsed : null;
}

/**
 * The ephemeris samples that carry a readable instant and a readable position, in time
 * order. A sample that fails either test cannot enter the geometry, because one NaN
 * would poison every maximum it takes part in.
 */
function timedSamples(points) {
  const list = Array.isArray(points) ? points : [];
  const entries = [];
  for (let index = 0; index < list.length; index += 1) {
    const point = list[index];
    if (point === null || typeof point !== 'object') {
      continue;
    }
    const timeMs = timeMsOf(point.t_utc);
    if (
      timeMs === null ||
      !Number.isFinite(Number(point.lat_deg)) ||
      !Number.isFinite(Number(point.lon_deg)) ||
      !Number.isFinite(Number(point.alt_km))
    ) {
      continue;
    }
    entries.push({ point, index, time_ms: timeMs });
  }
  entries.sort((a, b) => a.time_ms - b.time_ms || a.index - b.index);
  return entries;
}

/**
 * Latitude, longitude and altitude at an instant the ephemeris does not sample, taken
 * linearly between the two samples that bracket it. The result is marked interpolated so
 * that no caller can present it as an ephemeris sample.
 */
function interpolatedSample(lower, upper, timeMs) {
  const span = upper.time_ms - lower.time_ms;
  const fraction = span === 0 ? 0 : (timeMs - lower.time_ms) / span;
  const mix = (from, to) => Number(from) + (Number(to) - Number(from)) * fraction;
  return {
    t_utc: new Date(timeMs).toISOString(),
    lat_deg: mix(lower.point.lat_deg, upper.point.lat_deg),
    lon_deg: mix(lower.point.lon_deg, upper.point.lon_deg),
    alt_km: mix(lower.point.alt_km, upper.point.alt_km),
  };
}

/**
 * The position at one instant: the sample itself when the ephemeris has one, otherwise a
 * linear interpolation between the bracketing samples. Null when the ephemeris has
 * nothing on both sides of the instant, which is the one case that cannot be resolved
 * without inventing a position.
 */
function positionAt(entries, timeMs) {
  const exact = entries.find((entry) => entry.time_ms === timeMs);
  if (exact !== undefined) {
    return { point: exact.point, index: exact.index, interpolated: false };
  }
  let lower = null;
  let upper = null;
  for (const entry of entries) {
    if (entry.time_ms <= timeMs) {
      lower = entry;
    }
    if (entry.time_ms >= timeMs && upper === null) {
      upper = entry;
    }
  }
  if (lower === null || upper === null) {
    return null;
  }
  return { point: interpolatedSample(lower, upper, timeMs), index: null, interpolated: true };
}

function untimedWindow() {
  return {
    restricted: false,
    covered: false,
    liftoff_utc: null,
    injection_utc: null,
    total_count: 0,
    first_t_utc: null,
    last_t_utc: null,
    samples: [],
    interpolated_count: 0,
  };
}

/**
 * The samples the visibility of the ascent is computed from, which is the point of the
 * fix for issue 5 F5: an ephemeris can carry two full orbits, and every centre then sees
 * something somewhere in the track. Only the samples with t_utc inside [t_liftoff_utc,
 * t_injection_utc] of the selected row count, both ends included. When fewer than two of
 * them do, the position at liftoff and at injection is interpolated from the bracketing
 * samples so there are always at least those two points. When the ephemeris has no sample
 * on one side of the ascent interval the coverage fails and the caller says so instead of
 * guessing.
 */
export function ascentSamples(points, ascent = null) {
  const entries = timedSamples(points);
  const window = ascent === null || ascent === undefined ? {} : ascent;
  const liftoffMs = timeMsOf(window.t_liftoff_utc);
  const injectionMs = timeMsOf(window.t_injection_utc);
  const span = {
    first_t_utc: entries.length === 0 ? null : entries[0].point.t_utc,
    last_t_utc: entries.length === 0 ? null : entries[entries.length - 1].point.t_utc,
  };
  if (liftoffMs === null || injectionMs === null) {
    return {
      ...untimedWindow(),
      ...span,
      covered: entries.length > 0,
      total_count: entries.length,
      samples: entries.map((entry) => ({ ...entry.point, index: entry.index, interpolated: false })),
    };
  }
  const base = {
    ...untimedWindow(),
    ...span,
    restricted: true,
    liftoff_utc: window.t_liftoff_utc,
    injection_utc: window.t_injection_utc,
    total_count: entries.length,
  };
  const inside = entries.filter((entry) => entry.time_ms >= liftoffMs && entry.time_ms <= injectionMs);
  if (inside.length >= 2) {
    return {
      ...base,
      covered: true,
      samples: inside.map((entry) => ({ ...entry.point, index: entry.index, interpolated: false })),
    };
  }
  const start = positionAt(entries, liftoffMs);
  const end = positionAt(entries, injectionMs);
  if (start === null || end === null) {
    return { ...base, covered: false };
  }
  const byTime = new Map();
  const ordered = [start, ...inside, end].sort(
    (a, b) => timeMsOf(a.point.t_utc) - timeMsOf(b.point.t_utc),
  );
  for (const entry of ordered) {
    const timeMs = timeMsOf(entry.point.t_utc);
    if (!byTime.has(timeMs)) {
      byTime.set(timeMs, entry);
    }
  }
  const samples = [...byTime.values()]
    .sort((a, b) => timeMsOf(a.point.t_utc) - timeMsOf(b.point.t_utc))
    .map((entry) => ({ ...entry.point, index: entry.index, interpolated: entry.interpolated }));
  return {
    ...base,
    covered: true,
    samples,
    interpolated_count: samples.filter((sample) => sample.interpolated).length,
  };
}

function byMaxElevationDescending(a, b) {
  const left = a.max_elevation_deg;
  const right = b.max_elevation_deg;
  if (left === null && right === null) {
    return a.id.localeCompare(b.id);
  }
  if (left === null) {
    return 1;
  }
  if (right === null) {
    return -1;
  }
  if (right !== left) {
    return right - left;
  }
  return a.id.localeCompare(b.id);
}

export function viewingReport(options = {}) {
  const {
    points = [],
    centres = [],
    ephemerisResponse = null,
    elevationMaskDeg = ELEVATION_MASK_DEG,
    minElevationDeg = VIEWING_MIN_ELEVATION_DEG,
    ascent = null,
  } = options;
  const radiusM = earthRadiusOf(ephemerisResponse);
  const window = ascentSamples(points, ascent);
  const samples = window.samples;
  const entries = centreEntries(centres);
  const report = {
    elevation_mask_deg: elevationMaskDeg,
    min_elevation_deg: minElevationDeg,
    earth_radius_m: radiusM,
    sample_count: window.total_count,
    first_sample_t_utc: window.first_t_utc,
    last_sample_t_utc: window.last_t_utc,
    ascent_restricted: window.restricted,
    ascent_covered: window.covered,
    ascent_t_liftoff_utc: window.liftoff_utc,
    ascent_t_injection_utc: window.injection_utc,
    ascent_sample_count: samples.length,
    interpolated_sample_count: window.interpolated_count,
    coverage_message: window.restricted && !window.covered ? NO_ASCENT_COVERAGE : null,
    centres: [],
    ranked_centre_ids: [],
    best_centre_id: null,
    best_centre: null,
  };
  if (entries.length === 0) {
    return report;
  }
  for (const centre of entries) {
    const observer = geodeticToEcef(centre.lat_deg, centre.lon_deg, centre.alt_m, radiusM);
    const frame = localFrame(centre.lat_deg, centre.lon_deg);
    const samplesForCentre = [];
    let maxElevationDeg = null;
    let peakSample = null;
    for (let index = 0; index < samples.length; index += 1) {
      const point = samples[index];
      const timeMs = Date.parse(point.t_utc);
      if (!Number.isFinite(timeMs)) {
        continue;
      }
      const vehicle = geodeticToEcef(point.lat_deg, point.lon_deg, point.alt_km * 1000, radiusM);
      const angles = topocentric(observer, vehicle, frame);
      const vehicleIllumination = illuminationAt(timeMs, vehicle, radiusM);
      const observerIllumination = illuminationAt(timeMs, observer, radiusM);
      const aboveHorizon = angles.elevation_deg !== null && angles.elevation_deg > 0;
      const sample = {
        t_utc: point.t_utc,
        index: point.index ?? null,
        interpolated: point.interpolated === true,
        lat_deg: point.lat_deg,
        lon_deg: point.lon_deg,
        alt_km: point.alt_km,
        elevation_deg: angles.elevation_deg,
        azimuth_deg: angles.azimuth_deg,
        range_km: angles.range_km,
        above_horizon: aboveHorizon,
        vehicle_sunlit: vehicleIllumination.sunlit,
        observer_dark: !observerIllumination.sunlit,
        sunlit_in_darkness: vehicleIllumination.sunlit && !observerIllumination.sunlit,
      };
      samplesForCentre.push(sample);
      if (
        angles.elevation_deg !== null &&
        (maxElevationDeg === null || angles.elevation_deg > maxElevationDeg)
      ) {
        maxElevationDeg = angles.elevation_deg;
        peakSample = sample;
      }
    }
    const visible = maxElevationDeg !== null && maxElevationDeg >= minElevationDeg;
    const entry = {
      ...centre,
      max_elevation_deg: maxElevationDeg,
      peak_index: peakSample === null ? null : peakSample.index,
      peak_t_utc: peakSample === null ? null : peakSample.t_utc,
      peak_range_km: peakSample === null ? null : peakSample.range_km,
      peak_azimuth_deg: peakSample === null ? null : peakSample.azimuth_deg,
      peak_interpolated: peakSample === null ? false : peakSample.interpolated,
      peak_sunlit_in_darkness: peakSample === null ? null : peakSample.sunlit_in_darkness,
      rank: null,
      visible,
      above_horizon: maxElevationDeg !== null && maxElevationDeg > 0,
      sunlit_in_darkness_samples: samplesForCentre.filter((sample) => sample.sunlit_in_darkness).length,
      peak_observer_dark: peakSample === null ? null : peakSample.observer_dark,
      peak_vehicle_sunlit: peakSample === null ? null : peakSample.vehicle_sunlit,
      samples: samplesForCentre,
    };
    report.centres.push(entry);
  }
  const ranked = [...report.centres].sort(byMaxElevationDescending);
  ranked.forEach((entry, position) => {
    entry.rank = position + 1;
  });
  report.centres = ranked;
  report.ranked_centre_ids = ranked.map((entry) => entry.id);
  const best = ranked.find((entry) => entry.visible === true);
  report.best_centre_id = best === undefined ? null : best.id;
  report.best_centre = best === undefined ? null : best;
  return report;
}

export function illuminationSummary(report) {
  const sunlitInDarkness = report.centres.filter(
    (centre) => centre.sunlit_in_darkness_samples > 0,
  );
  const text = sunlitInDarkness.map((centre) => `${centre.name} at ${centre.sunlit_in_darkness_samples} sample(s)`);
  return {
    sunlit_in_darkness_centre_ids: sunlitInDarkness.map((centre) => centre.id),
    text:
      sunlitInDarkness.length === 0
        ? 'No centre sees a sunlit vehicle while in darkness at any ascent sample of this window.'
        : `Sunlit vehicle seen in darkness by ${text.join(', ')}.`,
  };
}
