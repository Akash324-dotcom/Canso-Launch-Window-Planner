import { API_BASE, REQUEST_TIMEOUT_MS } from './config.js';

export class ApiError extends Error {
  constructor(message, kind, status = null) {
    super(message);
    this.name = 'ApiError';
    this.kind = kind;
    this.status = status;
  }
}

export async function requestJson(url, options = {}) {
  const {
    method = 'GET',
    body = null,
    timeoutMs = REQUEST_TIMEOUT_MS,
    fetchImpl = globalThis.fetch,
  } = options;
  const controller = new AbortController();
  const timer = setTimeout(() => {
    controller.abort(new ApiError(`request timed out after ${timeoutMs} ms`, 'timeout'));
  }, timeoutMs);
  try {
    const response = await fetchImpl(url, {
      method,
      signal: controller.signal,
      headers: body === null ? undefined : { 'content-type': 'application/json' },
      body: body === null ? undefined : JSON.stringify(body),
    });
    if (response.ok !== true) {
      throw new ApiError(`HTTP ${response.status}`, 'http', response.status);
    }
    return await response.json();
  } catch (error) {
    if (error instanceof ApiError) {
      throw error;
    }
    const reason = controller.signal.reason;
    if (reason instanceof ApiError) {
      throw reason;
    }
    const detail = error instanceof Error ? error.message : String(error);
    throw new ApiError(`network failure: ${detail}`, 'network');
  } finally {
    clearTimeout(timer);
  }
}

export function createApiClient(options = {}) {
  const baseUrl = options.baseUrl ?? API_BASE;
  const timeoutMs = options.timeoutMs ?? REQUEST_TIMEOUT_MS;
  return {
    baseUrl,
    timeoutMs,
    windowsUrl: `${baseUrl}/windows`,
    postWindows(request, perCall = {}) {
      return requestJson(`${baseUrl}/windows`, {
        method: 'POST',
        body: request,
        timeoutMs,
        ...perCall,
      });
    },
  };
}
