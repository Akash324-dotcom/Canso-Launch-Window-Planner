import { DAY_MS, EARTH_RADIUS_M, J2000_MS, SOLAR_FORMULA_SOURCE } from './config.js';
import { DEG, crossNorm, dot3, wrapDeg } from './geo.js';

/**
 * Solar position and the shadow test.
 *
 * Formula source: SOLAR_FORMULA_SOURCE in src/config.js, that is the low precision
 * solar coordinates of the Astronomical Almanac (US Naval Observatory) as reproduced by
 * the NOAA Solar Calculator, together with the IAU 1982 Greenwich mean sidereal time
 * polynomial that constants_block.gmst_model names. The expression is carried as an
 * ASSUMPTION because neither citation could be resolved from this offline branch.
 */

export const SOLAR_CITATION = SOLAR_FORMULA_SOURCE;

export function julianDate(ms) {
  return ms / DAY_MS + 2440587.5;
}

export function daysSinceJ2000(ms) {
  return (ms - J2000_MS) / DAY_MS;
}

/**
 * Greenwich mean sidereal time in degrees, IAU 1982 model as named by
 * constants_block.gmst_model.
 */
export function gmstDeg(ms) {
  const d = daysSinceJ2000(ms);
  const t = d / 36525;
  return wrapDeg(
    280.46061837 + 360.98564736629 * d + 0.000387933 * t * t - (t * t * t) / 38710000,
  );
}

export function solarPosition(ms) {
  const n = daysSinceJ2000(ms);
  const meanLongitude = wrapDeg(280.46 + 0.9856474 * n);
  const meanAnomaly = (357.528 + 0.9856003 * n) * DEG;
  const eclipticLongitude =
    (meanLongitude + 1.915 * Math.sin(meanAnomaly) + 0.02 * Math.sin(2 * meanAnomaly)) * DEG;
  const obliquity = (23.439 - 0.0000004 * n) * DEG;
  const rightAscensionDeg = wrapDeg(
    Math.atan2(Math.cos(obliquity) * Math.sin(eclipticLongitude), Math.cos(eclipticLongitude)) / DEG,
  );
  const declinationDeg = Math.asin(Math.sin(obliquity) * Math.sin(eclipticLongitude)) / DEG;
  const distanceAu = 1.00014 - 0.01671 * Math.cos(meanAnomaly) - 0.00014 * Math.cos(2 * meanAnomaly);
  return {
    right_ascension_deg: rightAscensionDeg,
    declination_deg: declinationDeg,
    distance_au: distanceAu,
    mean_longitude_deg: meanLongitude,
    obliquity_deg: obliquity / DEG,
  };
}

/**
 * The unit vector from the Earth centre to the Sun in ECEF, obtained by rotating the
 * equatorial unit vector by the Greenwich mean sidereal time at the same instant.
 */
export function sunEcefDirection(ms) {
  const solar = solarPosition(ms);
  const ra = solar.right_ascension_deg * DEG;
  const dec = solar.declination_deg * DEG;
  const equatorial = {
    x: Math.cos(dec) * Math.cos(ra),
    y: Math.cos(dec) * Math.sin(ra),
    z: Math.sin(dec),
  };
  const angle = gmstDeg(ms) * DEG;
  return rotateAboutZ(equatorial, -angle);
}

export function rotateAboutZ(vector, angleRad) {
  const cos = Math.cos(angleRad);
  const sin = Math.sin(angleRad);
  return {
    x: vector.x * cos - vector.y * sin,
    y: vector.x * sin + vector.y * cos,
    z: vector.z,
  };
}

/**
 * Shadow test on a spherical Earth of radius radiusM. A position is sunlit when it is on
 * the sunward side, or when the perpendicular distance from the Earth centre to the line
 * through the position towards the Sun exceeds the Earth radius, which is the penumbra
 * boundary of the spherical shadow.
 */
export function isSunlit(position, sunUnit, radiusM = EARTH_RADIUS_M) {
  const sunward = dot3(position, sunUnit);
  if (sunward > 0) {
    return { sunlit: true, reason: 'sunward hemisphere' };
  }
  const perpendicularKm = crossNorm(position, sunUnit) / 1000;
  if (perpendicularKm < radiusM / 1000) {
    return { sunlit: false, reason: 'inside the Earth shadow', perpendicular_km: perpendicularKm };
  }
  return { sunlit: true, reason: 'sunward of the shadow cylinder', perpendicular_km: perpendicularKm };
}

export function sunDistanceKm(sunUnit, distanceAu) {
  return distanceAu * 149597870.7;
}

export function illuminationAt(ms, position, radiusM = EARTH_RADIUS_M) {
  const sunUnit = sunEcefDirection(ms);
  const solar = solarPosition(ms);
  const verdict = isSunlit(position, sunUnit, radiusM);
  return {
    ...verdict,
    sun_right_ascension_deg: solar.right_ascension_deg,
    sun_declination_deg: solar.declination_deg,
    sun_distance_km: sunDistanceKm(sunUnit, solar.distance_au),
    gmst_deg: gmstDeg(ms),
    sun_unit: sunUnit,
  };
}