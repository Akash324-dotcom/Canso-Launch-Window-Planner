import { DEFAULT_SITE } from './config.js';

export class RequestValidationError extends Error {
  constructor(messages) {
    super(messages.join('; '));
    this.name = 'RequestValidationError';
    this.messages = messages;
  }
}

function optionalNumber(value, label, messages) {
  if (value === null || value === undefined || String(value).trim() === '') {
    return null;
  }
  const parsed = Number(value);
  if (!Number.isFinite(parsed)) {
    messages.push(`${label} must be a number`);
    return null;
  }
  return parsed;
}

function requiredNumber(value, label, messages) {
  if (value === null || value === undefined || String(value).trim() === '') {
    messages.push(`${label} is required`);
    return null;
  }
  const parsed = Number(value);
  if (!Number.isFinite(parsed)) {
    messages.push(`${label} must be a number`);
    return null;
  }
  return parsed;
}

function requiredDate(value, label, messages) {
  if (value === null || value === undefined || String(value).trim() === '') {
    messages.push(`${label} is required`);
    return null;
  }
  return String(value);
}

export function buildWindowsRequest(inputs) {
  const messages = [];
  const target = { type: inputs.target_type };

  if (inputs.target_type === 'CUSTOM') {
    const hT = requiredNumber(inputs.h_t_km, 'h_t_km (target altitude in km)', messages);
    const iT = requiredNumber(inputs.i_t_deg, 'i_t_deg (target inclination in deg)', messages);
    if (hT !== null) {
      target.h_t_km = hT;
    }
    if (iT !== null) {
      target.i_t_deg = iT;
    }
  }

  if (inputs.plane_mode === 'ltan') {
    const ltan = inputs.ltan_hours === null || inputs.ltan_hours === undefined
      ? ''
      : String(inputs.ltan_hours).trim();
    if (ltan !== '' && !/^\d{1,2}:\d{2}$/.test(ltan)) {
      messages.push('ltan_hours must look like 10:30');
    }
    target.ltan_hours = ltan === '' ? null : ltan;
  } else {
    target.raan_deg = optionalNumber(inputs.raan_deg, 'raan_deg', messages);
  }

  const start = requiredDate(inputs.date_start, 'date_range.start', messages);
  const end = requiredDate(inputs.date_end, 'date_range.end', messages);
  if (start !== null && end !== null && start > end) {
    messages.push('date_range.start must not be later than date_range.end');
  }

  const vehicleProfileId = requiredDate(inputs.vehicle_profile_id, 'vehicle_profile_id', messages);

  const aMin = optionalNumber(inputs.corridor_a_min_deg, 'corridor A_min_deg', messages);
  const aMax = optionalNumber(inputs.corridor_a_max_deg, 'corridor A_max_deg', messages);
  const corridor = {};
  if (aMin !== null) {
    corridor.A_min_deg = aMin;
  }
  if (aMax !== null) {
    corridor.A_max_deg = aMax;
  }
  if (corridor.A_min_deg !== undefined && corridor.A_max_deg !== undefined) {
    if (corridor.A_min_deg > corridor.A_max_deg) {
      messages.push('corridor A_min_deg must not exceed A_max_deg');
    }
  }

  if (messages.length > 0) {
    throw new RequestValidationError(messages);
  }

  const request = {
    target,
    site: inputs.site === undefined || inputs.site === null || inputs.site === '' ? DEFAULT_SITE : inputs.site,
    date_range: { start, end },
    vehicle_profile_id: vehicleProfileId,
    include_weather: inputs.include_weather !== false,
  };
  if (Object.keys(corridor).length > 0) {
    request.corridor = corridor;
  }
  return request;
}
