import { EARTH_RADIUS_M, ELEVATION_MASK_DEG } from './config.js';
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
 * sample, the topocentric elevation and azimuth from the centre to the vehicle, and
 * whether the vehicle is sunlit while the observer is in the Earth shadow. The geometry
 * is stated in frontend/README.md.
 */

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

export function viewingReport(options = {}) {
  const {
    points = [],
    centres = [],
    ephemerisResponse = null,
    elevationMaskDeg = ELEVATION_MASK_DEG,
  } = options;
  const radiusM = earthRadiusOf(ephemerisResponse);
  const samples = Array.isArray(points) ? points : [];
  const entries = centreEntries(centres);
  const report = {
    elevation_mask_deg: elevationMaskDeg,
    earth_radius_m: radiusM,
    sample_count: samples.length,
    centres: [],
    best_centre_id: null,
    best_centre: null,
  };
  if (samples.length === 0 || entries.length === 0) {
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
        index,
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
    const visible = maxElevationDeg !== null && maxElevationDeg >= elevationMaskDeg;
    const entry = {
      ...centre,
      max_elevation_deg: maxElevationDeg,
      peak_index: peakSample === null ? null : peakSample.index,
      peak_t_utc: peakSample === null ? null : peakSample.t_utc,
      peak_range_km: peakSample === null ? null : peakSample.range_km,
      peak_azimuth_deg: peakSample === null ? null : peakSample.azimuth_deg,
      visible,
      above_horizon: maxElevationDeg !== null && maxElevationDeg > 0,
      sunlit_in_darkness_samples: samplesForCentre.filter((sample) => sample.sunlit_in_darkness).length,
      peak_observer_dark: peakSample === null ? null : peakSample.observer_dark,
      peak_vehicle_sunlit: peakSample === null ? null : peakSample.vehicle_sunlit,
      samples: samplesForCentre,
    };
    report.centres.push(entry);
  }
  const ranked = [...report.centres]
    .filter((entry) => entry.max_elevation_deg !== null)
    .sort((a, b) => b.max_elevation_deg - a.max_elevation_deg);
  report.best_centre_id = ranked.length === 0 ? null : ranked[0].id;
  report.best_centre = ranked.length === 0 ? null : ranked[0];
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
        ? 'No centre sees a sunlit vehicle while in darkness at any sample of this track.'
        : `Sunlit vehicle seen in darkness by ${text.join(', ')}.`,
  };
}