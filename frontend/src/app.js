import { createApiClient } from './api.js';
import {
  COUNTDOWN_INTERVAL_MS,
  FIXTURES,
  MODE_LIVE,
  MODE_OFFLINE,
} from './config.js';
import { loadCentres } from './centres.js';
import { createCountdown } from './countdown.js';
import { loadFixture, loadFixtures } from './fixtures.js';
import { buildWindowsRequest, RequestValidationError } from './request.js';
import { createAnalysisScreen } from './screens/analysis.js';
import { orbitIdFor, createTrajectoryScreen } from './screens/trajectory.js';
import { createViewingScreen } from './screens/viewing.js';
import { createWeatherScreen } from './screens/weather.js';
import { createWindowEngineScreen } from './screens/windowEngine.js';
import { windowRows } from './selectors.js';
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

function fixtureSourcesOf(state) {
  return [
    ['windows', state.engineResponseOrigin],
    ['site', state.siteOrigin],
    ['ephemeris', state.ephemerisOrigin],
    ['weather', state.weatherOrigin],
    ['skill', state.skillOrigin],
  ]
    .filter(([, origin]) => origin === 'fixture')
    .map(([name]) => FIXTURES[name]);
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
  const sources = fixtureSourcesOf(state);
  if (sources.length > 0) {
    parts.push(`source ${sources.join(', ')}`);
  }
  if (state.engineResponseOrigin === 'api_stale') {
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

/**
 * Every resource read for a selected row, with the store key it fills and the offline
 * fixture it falls back to. `src/data/centres.json` is a repository file rather than an
 * API resource, so it has no fixture.
 */
const RESOURCES = {
  site: { key: 'siteResponse', fixtureName: 'site' },
  ephemeris: { key: 'ephemerisResponse', fixtureName: 'ephemeris' },
  weather: { key: 'weatherResponse', fixtureName: 'weather' },
  skill: { key: 'skillResponse', fixtureName: 'skill' },
  centres: { key: 'centres', fixtureName: null },
};

export function createApp(options = {}) {
  const {
    root,
    bannerHost = null,
    trajectoryHost = null,
    weatherHost = null,
    viewingHost = null,
    analysisHost = null,
    store = createStore(INITIAL_STATE),
    client = createApiClient(),
    fixtureNames = Object.keys(FIXTURES),
    now = () => Date.now(),
    intervalMs = COUNTDOWN_INTERVAL_MS,
    autoMountMaps = false,
  } = options;

  if (root === null || root === undefined) {
    throw new Error('createApp requires a root element');
  }

  let requestSequence = 0;
  let selectionSequence = 0;
  let stopped = false;

  const screen = createWindowEngineScreen({
    root,
    store,
    onInputsChanged: () => {
      dispatch();
    },
    onRowSelected: (index) => {
      selectRow(index);
    },
  });
  const countdown = createCountdown({
    host: screen.countdownHost,
    store,
    intervalMs,
    now,
  });
  const trajectory =
    trajectoryHost === null
      ? null
      : createTrajectoryScreen({ root: trajectoryHost, store, footprintRegistry: options.footprints });
  const weather = weatherHost === null ? null : createWeatherScreen({ root: weatherHost, store });
  const viewing = viewingHost === null ? null : createViewingScreen({ root: viewingHost, store });
  const analysis = analysisHost === null ? null : createAnalysisScreen({ root: analysisHost, store });

  const unsubscribe = store.subscribe((state) => {
    screen.render(state);
    if (trajectory !== null) {
      trajectory.render(state);
    }
    if (weather !== null) {
      weather.render(state);
    }
    if (viewing !== null) {
      viewing.render(state);
    }
    if (analysis !== null) {
      analysis.render(state);
    }
    renderBanner(bannerHost, state);
  });
  screen.render(store.getState());
  if (trajectory !== null) {
    trajectory.render(store.getState());
  }
  if (weather !== null) {
    weather.render(store.getState());
  }
  if (viewing !== null) {
    viewing.render(store.getState());
  }
  if (analysis !== null) {
    analysis.render(store.getState());
  }
  renderBanner(bannerHost, store.getState());

  function noteOffline(message) {
    const current = store.getState();
    if (current.mode === MODE_OFFLINE) {
      const parts = [current.error, message].filter((part) => part !== null && part !== '');
      store.setState({ error: parts.join('; ') });
      return;
    }
    store.setState({ mode: MODE_OFFLINE, status: current.status === 'ready' ? 'degraded' : current.status, error: message });
  }

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

  /**
   * A resource read for the selected window row. Every read goes through the API client and
   * falls back to the offline fixture named in src/config.js FIXTURES, which switches the
   * banner to offline_precomputed, exactly as spec V.5 requires of the windows POST.
   */
  async function readResource(resource, loader, sequence) {
    const { key, fixtureName } = RESOURCES[resource];
    const fixtureFile = fixtureName === null ? null : FIXTURES[fixtureName];
    try {
      const value = await loader();
      if (stopped || sequence !== selectionSequence) {
        return;
      }
      store.setState({ [key]: value, [`${resource}Origin`]: 'api', [`${resource}Error`]: null });
    } catch (error) {
      if (stopped || sequence !== selectionSequence) {
        return;
      }
      let value = null;
      let failure = null;
      if (fixtureName !== null) {
        try {
          value = await loadFixture(fixtureName);
        } catch (fixtureError) {
          failure = `${fixtureFile}: ${describeError(fixtureError)}`;
        }
      }
      if (stopped || sequence !== selectionSequence) {
        return;
      }
      const patch = {
        [key]: value,
        [`${resource}Origin`]: value === null ? null : 'fixture',
        [`${resource}Error`]: describeError(error),
      };
      if (failure !== null) {
        store.setState({
          ...patch,
          fixtureFailures: [...store.getState().fixtureFailures, { name: fixtureFile, reason: failure }],
        });
      } else {
        store.setState(patch);
      }
      if (value !== null) {
        noteOffline(`${resource}: ${describeError(error)}, served from the ${fixtureFile} fixture`);
      }
    }
  }

  async function selectRow(index) {
    if (stopped) {
      return;
    }
    const state = store.getState();
    const rows = windowRows(state.engineResponse);
    if (!Number.isInteger(index) || index < 0 || index >= rows.length) {
      return;
    }
    const row = rows[index];
    const sequence = ++selectionSequence;
    store.setState({ selectedRowIndex: index, selectedRowOrigin: 'user' });
    const siteId = state.request === null ? 'canso' : state.request.site;
    const orbitId = orbitIdFor(state.request);
    const reads = [
      readResource('site', () => client.getSite(), sequence),
      readResource(
        'weather',
        () => client.getWeatherProbability({ date: row.t_liftoff_utc.slice(0, 10), site: siteId }),
        sequence,
      ),
      readResource('skill', () => client.getValidationSkill(), sequence),
      readResource(
        'centres',
        async () => {
          const loaded = await loadCentres();
          return loaded.centres;
        },
        sequence,
      ),
    ];
    if (orbitId !== null) {
      reads.push(
        readResource(
          'ephemeris',
          () =>
            client.getEphemeris(orbitId, {
              start: row.t_liftoff_utc,
              end: row.t_injection_utc,
            }),
          sequence,
        ),
      );
    }
    await Promise.all(reads);
  }

  function start() {
    countdown.start();
    const maps = [trajectory, viewing].filter((screen_) => screen_ !== null);
    if (autoMountMaps) {
      for (const mapScreen of maps) {
        mapScreen.mountMap();
      }
    }
    return dispatch();
  }

  function stop() {
    stopped = true;
    countdown.destroy();
    unsubscribe();
    if (trajectory !== null) {
      trajectory.destroy();
    }
    if (weather !== null) {
      weather.destroy();
    }
    if (viewing !== null) {
      viewing.destroy();
    }
    if (analysis !== null) {
      analysis.destroy();
    }
  }

  return {
    store,
    screen,
    countdown,
    trajectory,
    weather,
    viewing,
    analysis,
    dispatch,
    selectRow,
    start,
    stop,
  };
}