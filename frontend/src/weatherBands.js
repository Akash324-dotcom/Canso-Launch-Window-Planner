import { WEATHER_BAND_LABELS, WEATHER_THRESHOLDS } from './config.js';

/**
 * The Green, Yellow and Red bands of spec V.3. The thresholds live in src/config.js
 * because the spec keeps them in a configuration file rather than in code, and they are
 * an ASSUMPTION that the panel shows on screen next to the colour.
 */
export function weatherBand(probability, thresholds = WEATHER_THRESHOLDS) {
  if (probability === null || probability === undefined || !Number.isFinite(Number(probability))) {
    return {
      band: 'GREY',
      label: WEATHER_BAND_LABELS.GREY,
      reason: 'the response carries no probability for this row',
    };
  }
  const value = Number(probability);
  if (value >= thresholds.green_min) {
    return { band: 'GREEN', label: WEATHER_BAND_LABELS.GREEN, reason: 'at or above green_min' };
  }
  if (value >= thresholds.yellow_min) {
    return { band: 'YELLOW', label: WEATHER_BAND_LABELS.YELLOW, reason: 'between yellow_min and green_min' };
  }
  return { band: 'RED', label: WEATHER_BAND_LABELS.RED, reason: 'below yellow_min' };
}

export function thresholdsText(thresholds = WEATHER_THRESHOLDS) {
  return (
    `Thresholds ${thresholds.flag}: Green at or above ${thresholds.green_min.toFixed(2)}, ` +
    `Yellow ${thresholds.yellow_min.toFixed(2)} to ${thresholds.green_min.toFixed(2)}, ` +
    `Red below ${thresholds.yellow_min.toFixed(2)}. Source: ${thresholds.source}.`
  );
}