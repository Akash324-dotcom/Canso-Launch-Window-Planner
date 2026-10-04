import { COUNTDOWN_INTERVAL_MS, MODE_LIVE } from './config.js';
import { el, replaceChildren } from './dom.js';
import { formatAtlantic, formatUtc, remainingText } from './time.js';
import { countdownTarget } from './selectors.js';

export const NO_WINDOW_MESSAGE = 'No window in range';
export const PASSED_MESSAGE = 'Liftoff time passed';

export function createCountdown({ host, store, intervalMs = COUNTDOWN_INTERVAL_MS, now = () => Date.now() }) {
  let timer = null;
  let started = false;
  let targetRow = null;
  let reason = null;
  let passed = false;

  const nodes = {
    value: el('p', { class: 'countdown-value', id: 'countdown-value', text: '...' }),
    utc: el('p', { class: 'countdown-absolute', id: 'countdown-utc', text: '...' }),
    atlantic: el('p', { class: 'countdown-absolute', id: 'countdown-atlantic', text: '...' }),
    reason: el('p', { class: 'countdown-reason', id: 'countdown-reason', hidden: true }),
    stale: el('p', { class: 'countdown-stale', id: 'countdown-stale', hidden: true }),
  };

  host.replaceChildren(
    el('div', { class: 'panel-head' }, [
      el('h2', { text: 'Countdown to the earliest reachable window' }),
      el('p', { class: 'hint', id: 'countdown-target-note' }),
    ]),
    el('div', { class: 'countdown-readout', role: 'timer', 'aria-live': 'off' }, [
      nodes.value,
      nodes.utc,
      nodes.atlantic,
    ]),
    nodes.reason,
    nodes.stale,
  );

  function setTargetFrom(response) {
    const selection = countdownTarget(response, now());
    targetRow = selection.row;
    reason = selection.reason;
    passed = false;
  }

  function renderReadout() {
    const state = store.getState();
    if (state.engineResponse === null) {
      replaceChildren(nodes.value, 'No response fetched yet.');
      nodes.utc.textContent = '';
      nodes.atlantic.textContent = '';
      nodes.reason.hidden = true;
      return;
    }
    if (targetRow === null) {
      const heading = state.status === 'loading' ? 'Fetching windows' : NO_WINDOW_MESSAGE;
      replaceChildren(nodes.value, el('span', { id: 'countdown-value-text', text: heading }));
      nodes.utc.textContent = '';
      nodes.atlantic.textContent = '';
      nodes.reason.textContent = reason === null ? '' : reason;
      nodes.reason.hidden = reason === null;
      return;
    }
    const targetMs = Date.parse(targetRow.t_liftoff_utc);
    const remainingMs = targetMs - now();
    if (remainingMs <= 0) {
      passed = true;
      replaceChildren(nodes.value, el('span', { id: 'countdown-value-text', text: PASSED_MESSAGE }));
      nodes.utc.textContent = `Liftoff ${formatUtc(targetRow.t_liftoff_utc)}`;
      nodes.atlantic.textContent = `Atlantic ${formatAtlantic(targetRow.t_liftoff_utc)}`;
      nodes.reason.textContent = `The countdown stopped at the liftoff instant ${formatUtc(
        targetRow.t_liftoff_utc,
      )} and is not restarted from zero.`;
      nodes.reason.hidden = false;
      return;
    }
    replaceChildren(
      nodes.value,
      el('span', { id: 'countdown-value-text', text: remainingText(remainingMs) }),
    );
    nodes.utc.textContent = `T- ${formatUtc(targetRow.t_liftoff_utc)}`;
    nodes.atlantic.textContent = formatAtlantic(targetRow.t_liftoff_utc);
    nodes.reason.hidden = true;
  }

  function renderStale(state) {
    const stale = state.status === 'degraded' && state.engineResponseOrigin === 'api_stale';
    nodes.stale.hidden = !stale;
    if (stale) {
      nodes.stale.textContent =
        'The API is unreachable, so the countdown is holding the last fetched target.';
    }
  }

  function render(state) {
    setTargetFrom(state.engineResponse);
    renderReadout();
    renderStale(state);
  }

  function tick() {
    if (targetRow === null) {
      renderReadout();
      return;
    }
    renderReadout();
    if (passed) {
      stop();
    }
  }

  function start() {
    started = true;
    if (timer !== null) {
      return;
    }
    render(store.getState());
    timer = setInterval(tick, intervalMs);
  }

  function stop() {
    if (timer === null) {
      return;
    }
    clearInterval(timer);
    timer = null;
  }

  const unsubscribe = store.subscribe((state) => {
    render(state);
    if (passed) {
      stop();
    } else if (started && timer === null && targetRow !== null) {
      // The interval was stopped when an earlier liftoff passed. A new target has arrived
      // since, so the clock has to run again or the readout stays frozen on its first value.
      timer = setInterval(tick, intervalMs);
    }
  });

  return {
    host,
    get targetRow() {
      return targetRow;
    },
    get targetMs() {
      return targetRow === null ? null : Date.parse(targetRow.t_liftoff_utc);
    },
    get mode() {
      return store.getState().mode;
    },
    get isLive() {
      return store.getState().mode === MODE_LIVE;
    },
    start,
    stop,
    tick,
    render,
    destroy() {
      started = false;
      stop();
      unsubscribe();
    },
  };
}
