import { MODE_LIVE } from './config.js';

export const INITIAL_STATE = {
  mode: MODE_LIVE,
  status: 'idle',
  request: null,
  inputs: null,
  engineResponse: null,
  engineResponseOrigin: null,
  error: null,
  inputError: null,
  fixtureFailures: [],
  fetchedAt: null,
  selectedRowIndex: null,
  selectedRowOrigin: null,
  siteResponse: null,
  siteOrigin: null,
  siteError: null,
  ephemerisResponse: null,
  ephemerisOrigin: null,
  ephemerisError: null,
  weatherResponse: null,
  weatherOrigin: null,
  weatherError: null,
  skillResponse: null,
  skillOrigin: null,
  skillError: null,
  centres: null,
  centresOrigin: null,
  centresError: null,
};

export function createStore(initialState = INITIAL_STATE) {
  let state = Object.freeze({ ...INITIAL_STATE, ...initialState });
  const listeners = new Set();

  function notify(previous, next) {
    for (const listener of [...listeners]) {
      listener(next, previous);
    }
  }

  return {
    getState() {
      return state;
    },
    setState(patch) {
      const previous = state;
      const next = typeof patch === 'function' ? patch(previous) : patch;
      state = Object.freeze({ ...previous, ...next });
      notify(previous, state);
      return state;
    },
    subscribe(listener) {
      listeners.add(listener);
      return () => {
        listeners.delete(listener);
      };
    },
  };
}