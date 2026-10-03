import { createApiClient } from './api.js';
import {
  COUNTDOWN_INTERVAL_MS,
  FIXTURES,
  MODE_LIVE,
  MODE_OFFLINE,
} from './config.js';
import { createCountdown } from './countdown.js';
import { loadFixtures } from './fixtures.js';
import { buildWindowsRequest, RequestValidationError } from './request.js';
import { createWindowEngineScreen } from './screens/windowEngine.js';
import { createStore, INITIAL_STATE } from './store.js';

function describeError(error) {
  if (error === null || error === undefined) {
    return 'unknown failure';
  }
  return error instanceof Error ? error.message : String(error);
}

function runIdOf(response) {
  if (response === null || response === undefined) {
    return null;
  }
  if (response.constants_block !== null && response.constants_block !== undefined) {
    return response.constants_block.citation_id ?? null;
  }
  return null;
}

function renderBanner(host, state) {
  if (host === null || host === undefined) {
    return;
  }
  if (state.mode !== MODE_OFFLINE) {
    host.hidden = true;
    host.textContent = '';
    return;
  }
  const runId = runIdOf(state.engineResponse);
  const parts = [
    'OFFLINE PRECOMPUTED DATA, mode offline_precomputed',
    runId === null ? 'engine run identifier not available' : `engine run ${runId}`,
  ];
  if (state.engineResponseOrigin === 'fixture') {
    parts.push(`source ${FIXTURES.windows}`);
  } else if (state.engineResponseOrigin === 'api_stale') {
    parts.push('showing the last successful API response');
  }
  if (state.error !== null) {
    parts.push(`reason: ${state.error}`);
  }
  if (state.fixtureFailures.length > 0) {
    parts.push(
      `fixtures unavailable: ${state.fixtureFailures
        .map((failure) => `${failure.name} (${failure.reason})`)
        .join('; ')}`,
    );
  }
  host.hidden = false;
  host.textContent = parts.join('. ');
}

export function createApp(options = {}) {
  const {
    root,
    bannerHost = null,
    store = createStore(INITIAL_STATE),
    client = createApiClient(),
    fixtureNames = Object.keys(FIXTURES),
    now = () => Date.now(),
    intervalMs = COUNTDOWN_INTERVAL_MS,
  } = options;

  if (root === null || root === undefined) {
    throw new Error('createApp requires a root element');
  }

  let requestSequence = 0;
  let stopped = false;

  const screen = createWindowEngineScreen({
    root,
    store,
    onInputsChanged: () => {
      dispatch();
    },
  });
  const countdown = createCountdown({
    host: screen.countdownHost,
    store,
    intervalMs,
    now,
  });

  const unsubscribe = store.subscribe((state) => {
    screen.render(state);
    renderBanner(bannerHost, state);
  });
  screen.render(store.getState());
  renderBanner(bannerHost, store.getState());

  async function switchToOffline(error, sequence) {
    const previous = store.getState();
    const { loaded, failures } = await loadFixtures(fixtureNames);
    if (stopped || sequence !== requestSequence) {
      return;
    }
    const keepLive = previous.engineResponseOrigin === 'api' && previous.engineResponse !== null;
    const engineResponse = keepLive ? previous.engineResponse : (loaded.windows ?? null);
    store.setState({
      mode: MODE_OFFLINE,
      status: engineResponse === null ? 'error' : 'degraded',
      engineResponse,
      engineResponseOrigin: keepLive ? 'api_stale' : engineResponse === null ? null : 'fixture',
      error: describeError(error),
      fixtureFailures: failures,
    });
  }

  async function dispatch() {
    if (stopped) {
      return;
    }
    let request;
    try {
      request = buildWindowsRequest(screen.readInputs());
    } catch (error) {
      if (error instanceof RequestValidationError) {
        store.setState({ inputError: error.message, request: null });
      } else {
        store.setState({ inputError: describeError(error) });
      }
      return;
    }
    const sequence = ++requestSequence;
    store.setState({ status: 'loading', request, inputError: null });
    try {
      const response = await client.postWindows(request);
      if (stopped || sequence !== requestSequence) {
        return;
      }
      store.setState({
        mode: MODE_LIVE,
        status: 'ready',
        engineResponse: response,
        engineResponseOrigin: 'api',
        error: null,
        fixtureFailures: [],
        fetchedAt: now(),
      });
    } catch (error) {
      if (stopped || sequence !== requestSequence) {
        return;
      }
      await switchToOffline(error, sequence);
    }
  }

  function start() {
    countdown.start();
    return dispatch();
  }

  function stop() {
    stopped = true;
    countdown.destroy();
    unsubscribe();
  }

  return { store, screen, countdown, dispatch, start, stop };
}
