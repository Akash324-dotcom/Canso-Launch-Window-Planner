import { T_TO_INJ_FLAG_PATTERN } from './config.js';

export function windowRows(response) {
  return response === null || response === undefined || !Array.isArray(response.windows)
    ? []
    : response.windows;
}

export function isHazardRejected(row) {
  if (row === null || row === undefined) {
    return false;
  }
  if (row.constraint_fired === 'hazard_area') {
    return true;
  }
  return row.screens !== null && row.screens !== undefined && row.screens.hazard === 'fail';
}

export function usableRows(response) {
  return windowRows(response).filter((row) => !isHazardRejected(row));
}

export function emptyWindowsReason(response) {
  if (response.reachable === false) {
    return 'The engine reports that the requested target is not reachable from the site by direct ascent.';
  }
  const warning = response.sso_consistency_warning;
  if (warning !== null && warning !== undefined) {
    const reason = typeof warning.reason === 'string' ? warning.reason : JSON.stringify(warning);
    const detail = typeof warning.detail === 'string' ? warning.detail : '';
    return `Engine consistency warning: ${reason}. ${detail}`.trim();
  }
  return 'No crossing of the target plane in the requested date range within the RAAN tolerance.';
}

export function countdownTarget(response, nowMs) {
  if (response === null || response === undefined) {
    return { row: null, reason: null };
  }
  const rows = windowRows(response);
  if (rows.length === 0) {
    return { row: null, reason: emptyWindowsReason(response) };
  }
  const usable = usableRows(response);
  if (usable.length === 0) {
    return { row: null, reason: 'Every returned window was rejected by the hazard screen.' };
  }
  const upcoming = usable.filter((row) => Date.parse(row.t_liftoff_utc) > nowMs);
  if (upcoming.length === 0) {
    return {
      row: null,
      reason: `All ${usable.length} returned windows have a liftoff instant earlier than the current clock.`,
    };
  }
  const row = upcoming.reduce((earliest, candidate) =>
    Date.parse(candidate.t_liftoff_utc) < Date.parse(earliest.t_liftoff_utc) ? candidate : earliest,
  );
  return { row, reason: null };
}

export function planeChangeText(response) {
  const value = response.plane_change_dv_ms;
  if (value === null || value === undefined) {
    return 'not computable for this target';
  }
  return `${value} m/s`;
}

export function rowFlags(response) {
  const provenance = response === null || response === undefined ? null : response.provenance_block;
  if (provenance === null || provenance === undefined) {
    return {};
  }
  const flags = provenance.row_flags;
  return flags === null || flags === undefined || typeof flags !== 'object' ? {} : flags;
}

export function vehicleTToInjFlag(response) {
  const flags = rowFlags(response);
  const matching = Object.entries(flags).find(
    ([key, value]) => T_TO_INJ_FLAG_PATTERN.test(key) && typeof value === 'string',
  );
  return matching === undefined ? null : matching[1];
}

export function constantsOf(response) {
  if (response === null || response === undefined) {
    return null;
  }
  return response.constants_block ?? null;
}

export function siteNameOf(response, fallback) {
  const provenance = response === null || response === undefined ? null : response.provenance_block;
  const site = provenance === null || provenance === undefined ? null : provenance.site;
  if (site !== null && site !== undefined && typeof site.name === 'string') {
    return site.name;
  }
  return fallback;
}
