# Frontend

Screen 1 of the launch window decision engine for Spaceport Nova Scotia (Canso). This directory currently ships the refactor of the inherited prototype for tasks F0, F1 and F2: the input form, the window table, the engine-driven countdown, the honesty panel, the constants and provenance footer, and the offline fallback layer.

## Stack and why

- Plain ES modules, no framework, no bundler, no build step. Spec V.7 recommends the static path because a build step is a demo failure mode at judging, and this branch has no network and no registry access, so a toolchain could not be installed anyway.
- No framework rewrite. The audit in `AUDIT.md` records the decision and the evidence; the whole of F0 to F2 is one response object and a handful of renderers, which plain functions express directly.
- Leaflet is present in `frontend/node_modules/leaflet` for F3. It will be imported from that path, never from a CDN, so the demo works with the network off. F0 to F2 render no map and therefore load no mapping library.
- vitest with jsdom for the tests, for the reason recorded in `AUDIT.md` section 0.

## How to run

Serve the repository root, not this directory, so that the relative offline fixture paths resolve:

```bash
python -m http.server 8000
```

Then open `http://localhost:8000/frontend/`. The app posts to `http://localhost:8000/v1/windows` by default, which is `API_BASE` in `src/config.js`. With no API running the request fails, the mode switches to `offline_precomputed`, and the banner names the fixtures. The five fixture files themselves live in `backend/fixtures/` and do not exist on this branch, because API owns that directory.

To point the app at a live API, change `API_BASE` in `src/config.js`.

## How to test

```bash
cd frontend
npx vitest run
```

| File | Covers |
|---|---|
| `tests/smoke.test.js` | F0: the page renders and the window table element exists |
| `tests/api.test.js` | F1: one POST per input change, the store and the table read the same response, the offline switch and its banner, the timeout, the `include_weather: false` path, the hazard rejection guard |
| `tests/countdown.test.js` | F2: the three required countdown tests plus the dual display, the stop at liftoff and the survival of an outage, using vitest fake timers |
| `tests/windowEngine.test.js` | F2: the orbit presets and their pre-filled inclinations, the CUSTOM request, corridor override, site and date defaults, the vehicle flag, and the spec V.1 table columns |

Mock payloads are the frozen examples in `tests/contract/examples/good/`.

## The countdown specification as implemented

- Source of truth: `t_liftoff_utc` of the earliest usable row of the single `engineResponse` object in the store. A row is usable when neither `constraint_fired` is `hazard_area` nor `screens.hazard` is `fail`.
- The value is recomputed every second from `Date.now()` against that ISO string, so nothing is counted down from a constant. A new response with a new earliest row changes the value immediately.
- Dual display always: the remaining time as `2d 04:16:33`, the absolute instant as `T- 2026-10-05 13:42:11Z`, and the Atlantic instant through `Intl` with `timeZone: "America/Halifax"`, which resolves ADT and AST itself.
- With no usable window the block renders `No window in range` plus the reason: the unreachability verdict, the engine `sso_consistency_warning`, or the documented meaning of an empty `windows` array. It never renders a zeroed or looping timer.
- When the liftoff instant passes, the block renders `Liftoff time passed`, states the instant it stopped at, and the interval is cleared so the value cannot restart.
- On an outage the last fetched target is kept, the banner switches to `offline_precomputed`, and a line states that the countdown is holding the last fetched target.

## What is stubbed versus live

| Area | State |
|---|---|
| `POST /v1/windows` | Live client, one request per input change, 8000 ms timeout from `src/config.js` |
| Offline fixtures | Registry and loader for the five names `windows`, `weather`, `skill`, `site`, `ephemeris`; the files themselves are API's to write |
| Vehicle `T_to_inj` flag | Read from the response `provenance_block.row_flags`; the value and its VERIFIED or ASSUMPTION flag are ENGINE's data at `backend/engine/data/vehicles/cyclone4m.json` and are absent on this branch, so the screen names the owner instead of showing a flag |
| Screens 2 to 5 | Not built. Trajectory, weather, viewing map and analysis view are F3 to F6 |
| Network | Never used except the API call and the fixture reads |