# Frontend log

Session covering GitHub issue 5 tasks F0, F1 and F2 only. Every line below is an exact command and its observed output.

## Commands run

```text
$ cd frontend && npx vitest run
```

First run, before `src/` existed, to record the red state:

```text
 Test Files  4 failed (4)
      Tests  no tests
Error: Failed to resolve import "../src/config.js" from "tests/windowEngine.test.js". Does the file exist?
```

Final run:

```text
 Test Files  4 passed (4)
      Tests  24 passed (24)
   Duration  403ms (environment 71%, tests 14%, transform 10%, import 5%, worker 1%)
```

## Files created

| Path | Purpose |
|---|---|
| `frontend/AUDIT.md` | Every panel, function and data field of `Canso Launch Prototype.html` with a KEEP, CHANGE or DROP verdict and the harness decision |
| `frontend/index.html` | Shell with the `mode-banner` host, the `screen-window-engine` host and the `src/main.js` module entry |
| `frontend/styles.css` | Palette carried over from the prototype `COL` constants, now CSS custom properties |
| `frontend/vitest.config.js` | jsdom environment, `tests/**/*.test.js` |
| `frontend/src/config.js` | `API_BASE`, timeout, mode names, fixture names, orbit presets, vehicle ids, table columns |
| `frontend/src/store.js` | One store, `getState`, `setState`, `subscribe` |
| `frontend/src/api.js` | `requestJson` with `AbortController` and the timeout, `ApiError` with a `kind` of `timeout`, `http` or `network` |
| `frontend/src/fixtures.js` | `fixtureUrl`, `loadFixture`, `loadFixtures` for the five offline names |
| `frontend/src/request.js` | `buildWindowsRequest`, the pure request builder with validation against the frozen request schema |
| `frontend/src/selectors.js` | `windowRows`, `isHazardRejected`, `countdownTarget`, `planeChangeText`, `vehicleTToInjFlag`, `constantsOf`, `siteNameOf` |
| `frontend/src/countdown.js` | The countdown component, one second interval, `start`, `stop`, `tick`, `targetRow` |
| `frontend/src/screens/windowEngine.js` | Screen 1: the form, the table, the honesty panel, the constants and provenance footer |
| `frontend/src/app.js` | Wiring: one `dispatch` per committed input change, the offline switch, the banner |
| `frontend/src/main.js` | Browser entry point |
| `frontend/tests/helpers.js` | Fixture loaders, fetch mocks, index markup mount |
| `frontend/tests/smoke.test.js`, `api.test.js`, `countdown.test.js`, `windowEngine.test.js` | The tests |
| `frontend/README.md` | Stack, how to run, how to test, the countdown specification, stubbed versus live |
| `docs/log/frontend.md` | This file |

## Test to requirement map

| Requirement | Test |
|---|---|
| F0 smoke test, page renders and the window table element exists | `tests/smoke.test.js` both cases |
| F1 one POST per input change | `tests/api.test.js` first case, `toHaveBeenCalledTimes(2)` after one change |
| F1 mocked response populates the store and renders N rows | `tests/api.test.js` second case, N taken from the payload |
| F1 countdown and table read the same response object | `tests/api.test.js` third case, identity of `countdown.targetRow` |
| F1 fetch failure switches to `offline_precomputed` with a visible banner and loads the five fixtures | `tests/api.test.js` fourth case |
| F1 timeout switches mode | `tests/api.test.js` fifth case, fake timers advancing `REQUEST_TIMEOUT_MS` |
| F1 `include_weather=false` renders null weather without crashing | `tests/api.test.js` sixth case |
| F1 HTTP error surfaces as the banner reason | `tests/api.test.js` eighth case |
| Bug 1 northbound hazard rejection is guarded | `tests/api.test.js` seventh case |
| F2 countdown renders `No window in range` for an empty windows array | `tests/countdown.test.js` second case |
| F2 penalty panel for `reachable:false` with `plane_change_dv_ms` | `tests/countdown.test.js` third case |
| F2 countdown value changes when the fetched target changes | `tests/countdown.test.js` fourth case |
| F2 dual display, UTC and Atlantic through `Intl` | `tests/countdown.test.js` first case |
| F2 countdown stops when the launch time passes | `tests/countdown.test.js` fifth case |
| F2 countdown survives an outage with the last fetched target | `tests/countdown.test.js` sixth case |
| F2 orbit selector with the slide inclinations pre-filled | `tests/windowEngine.test.js` first case |
| F2 preset versus CUSTOM request shape | `tests/windowEngine.test.js` second case |
| F2 incomplete CUSTOM refused before any POST | `tests/windowEngine.test.js` third case |
| F2 corridor override | `tests/windowEngine.test.js` fourth case |
| F2 site default and date range | `tests/windowEngine.test.js` fifth case |
| F2 vehicle dropdown flag | `tests/windowEngine.test.js` sixth case |
| F2 spec V.1 table columns and field values | `tests/windowEngine.test.js` seventh and eighth cases |

## Interpretations and open points

1. **Earliest reachable window.** Spec V.1 says the countdown ticks to the earliest row with reachable windows. Reachability is a response level field, so a row is taken to be reachable when the response is `reachable` and the row carries no hazard rejection. A row with `constraint_fired: hazard_area` or `screens.hazard: fail` is refused as a countdown target, which is the UI level guard the issue asks for against the northbound rows in the prototype mocks.
2. **Engine reason for an empty list.** The frozen response has no `reason` field on the response and none on an empty `windows` array. The reason rendered is therefore taken from `sso_consistency_warning` when the engine sends one, otherwise from the documented meaning of an empty array in `tests/contract/schemas/windows_response.json`, otherwise from `reachable: false`. Nothing is invented. If API wants a `reason` string on the response, this needs a contract change, not a frontend guess.
3. **Preset altitude is not pre-filled.** `h_t_km` is not required for the LEO, POLAR and SSO types, and the three sources disagree on its value: the prototype used 700 km, `windows_request_good_sso_full.json` uses 550 km and spec VI.2 shows 600 km. The screen therefore leaves it empty with the label `backend default`, and only CUSTOM requires a value. No altitude default was invented.
4. **Vehicle flag is read, not declared.** The T_to_inj VERIFIED or ASSUMPTION flag belongs to `backend/engine/data/vehicles/cyclone4m.json`, which ENGINE owns and which does not exist on this branch. The screen reads it from `provenance_block.row_flags` and, when the response declares none, names the owning file instead of showing a flag. This is the one F2 sub item that cannot show a flag on this branch.
5. **Outage with a previous live response.** On a failed re-fetch the app keeps the last successful response and marks it `api_stale` rather than overwriting it with fixtures, because spec V.1 requires the countdown to survive an outage using the last fetched target. The `offline_precomputed` banner and mode are set either way. The fixture data is used when no live response has arrived yet.
6. **One POST per committed change.** The form listens for `change`, so every committed edit posts exactly once, with a request sequence number so a late response cannot overwrite a newer one. The prototype debounce is dropped because it is neither needed nor permitted by the one POST per input change rule.
7. **Editing the inclination switches to CUSTOM.** Inherited from the prototype. Since `ltan_hours` is SSO only in the frozen schema, the plane selector switches to RAAN at the same time.
8. **Corridor override needs one bound to be sent.** The schema allows either bound to be null, so the screen sends whichever bound is filled and sends no corridor key when both are empty.
9. **No Leaflet import in F0 to F2.** No in scope screen renders a map, so the library is not loaded. F3 will import `frontend/node_modules/leaflet/dist/leaflet.js` and its stylesheet from the repository rather than a CDN, which is recorded in `README.md`.
10. **Clock widget and confidence tiers dropped.** The wall clock is traceable to no response object and the confidence tiers were invented in the browser, so both are dropped in the audit rather than carried forward.
11. **Tests use `tests/contract/examples/good/`.** `backend/fixtures/` does not exist on this branch and API owns it, so no fixture was created and the frozen examples serve as the mock payloads.

## Not done in this session

F3 to F9 are untouched: the trajectory map and the 3D scene, the weather panel and the skill curve, the viewing map, the analysis view and the exports, the fixture content, the requirements map, and `frontend/DONE.md`. `frontend/progress.md` was not written because this session was instructed to limit writes to `frontend/` deliverables and `docs/log/frontend.md`; this file carries the log the workflow doc asks for.