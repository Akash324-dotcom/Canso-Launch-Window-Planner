import { CENTRES_FILE, DATA_BASE } from './config.js';
import { requestJson } from './api.js';

export const CENTRES_URL = `${DATA_BASE}${CENTRES_FILE}`;

/**
 * The population centre list of the viewing map. It is a file in this repository rather
 * than an API resource, so it has no fixture fallback: a failure is reported on screen.
 */
export async function loadCentres(options = {}) {
  const document_ = await requestJson(CENTRES_URL, options);
  const centres = Array.isArray(document_?.centres) ? document_.centres : null;
  if (centres === null || centres.length === 0) {
    throw new Error(`${CENTRES_URL} declares no centres`);
  }
  return { centres, flag: document_.flag ?? null, note: document_.note ?? null };
}