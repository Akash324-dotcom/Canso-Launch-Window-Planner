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

---

# Session covering F3, F4 and F5

Same branch, built on the F0 to F2 modules. `src/api.js`, `src/store.js` and the Screen 1 renderer were extended, not rewritten, and no existing test was changed or weakened.

## Commands run

```text
$ cd frontend && npx vitest run
```

Final run:

```text
 Test Files  7 passed (7)
      Tests  43 passed (43)
   Duration  740ms (environment 56%, tests 25%, transform 10%, import 6%, worker 1%)
```

Per file, during development: `npx vitest run tests/trajectory.test.js` reported 7 passed, `npx vitest run tests/weatherPanel.test.js` reported 6 passed, `npx vitest run tests/viewing.test.js` reported 6 passed.

## Files created

| Path | Purpose |
|---|---|
| `frontend/src/geo.js` | Spherical geodesy and ECEF: `geodeticToEcef`, `greatCircleDistanceKm`, `initialBearingDeg`, `destinationPoint`, the corridor polygon, the hazard buffer and the corridor guard |
| `frontend/src/solar.js` | Solar position, Greenwich mean sidereal time, ECEF sun direction and the spherical shadow test, with the formula source cited in the module header |
| `frontend/src/viewing.js` | The topocentric geometry and the per centre visibility and illumination report |
| `frontend/src/weatherBands.js` | `weatherBand` and the threshold sentence, reading `WEATHER_THRESHOLDS` from `src/config.js` |
| `frontend/src/svgChart.js` | Inline SVG builders for the hindcast skill curve and the elevation against time chart, no chart library |
| `frontend/src/mapLeaflet.js` | The Leaflet loader from `node_modules` and the layer drawing for both maps |
| `frontend/src/centres.js` | Reads `src/data/centres.json` |
| `frontend/src/data/centres.json` | Halifax, Sydney NS, Moncton, Charlottetown, St. Johns, Boston, Montreal, every row flagged ASSUMPTION |
| `frontend/src/screens/trajectory.js` | Screen 2 |
| `frontend/src/screens/weather.js` | Screen 3 |
| `frontend/src/screens/viewing.js` | Screen 4 |
| `frontend/tests/trajectory.test.js` | The seven F3 cases |
| `frontend/tests/weatherPanel.test.js` | The six F4 cases |
| `frontend/tests/viewing.test.js` | The six F5 cases |

## Files changed

| Path | Change |
|---|---|
| `frontend/src/config.js` | `orbit_id` per orbit preset, `ORBIT_IDS_BY_TYPE`, `EPHEMERIS_STEP_S`, `WEATHER_THRESHOLDS`, `WEATHER_BAND_LABELS`, `ELEVATION_MASK_DEG` with its flag and source, `VEHICLE_FOOTPRINTS`, the corridor framing parameters, `DATA_BASE`, `CENTRES_FILE`, `LEAFLET_ESM`, `LEAFLET_STYLESHEET`, `EARTH_RADIUS_M` and its source, the J2000 epoch, `SOLAR_FORMULA_SOURCE` |
| `frontend/src/api.js` | `queryString`, `getSite`, `getEphemeris`, `getWeatherProbability`, `getValidationSkill`; `postWindows` untouched |
| `frontend/src/store.js` | New state slices for the selection, the site, ephemeris, weather, skill and centres responses with their origins and errors |
| `frontend/src/dom.js` | `SVG_NS`, `svgEl` and the shared `applyAttributes` |
| `frontend/src/time.js` | `formatIssueTime` in the spec V.3 wording |
| `frontend/src/app.js` | Row selection dispatch, `readResource` with the fixture fallback, the `RESOURCES` table, hosts for the three new screens, `autoMountMaps`, and a banner that names every fixture in use |
| `frontend/src/screens/windowEngine.js` | A click and keyboard listener per row, `data-selected`, `row-selected`, and the `onRowSelected` option |
| `frontend/src/main.js` | Passes the three new hosts and mounts the maps |
| `frontend/index.html` | Hosts for screens 2 to 4 and the Leaflet stylesheet from `node_modules` |
| `frontend/styles.css` | Styles for the new panels, bands, badges, charts, map layers and the selected row |
| `frontend/tests/helpers.js` | `installContractApi`, `loadCentresDocument`, `centres.json` in `fixtureResponseFor`, hosts in `mountIndexMarkup` and `boot` |
| `frontend/README.md` | Appended sections on screens 2 to 4, the viewing geometry, the fetch order and the new test map |

## Test to requirement map

| Requirement | Test |
|---|---|
| F3 selecting a row fetches and renders the matching track | `tests/trajectory.test.js` first case: one ephemeris call, `start` and `end` from the clicked row, every rendered point equal to the mocked response, the highlight on that row only |
| F3 corridor polygon from `/v1/site` | `tests/trajectory.test.js` second case, vertices and azimuth bounds, with the site flag |
| F3 hazard buffer | `tests/trajectory.test.js` second case measures every vertex 30 km from the track; third case asserts the buffer is not drawn and the owner is named when no width is declared |
| F3 site marker | `tests/trajectory.test.js` second case, `data-lat-deg` and `data-lon-deg` from `phi_s_deg` and `lambda_s_deg` |
| F3 per row highlight keyed to the window row | `tests/trajectory.test.js` first case, `data-selected` and `row-selected` |
| Bug 1 northbound track refused at the UI level | `tests/trajectory.test.js` fourth case, `data-inside` false and the HAZARD REJECTION text |
| F3 Leaflet from `node_modules`, offline | `tests/trajectory.test.js` fifth case, the real library mounted under jsdom, layers present, no `http` script or stylesheet in the document |
| F3 no ephemeris id for a CUSTOM target | `tests/trajectory.test.js` sixth case |
| F3 fixture fallback with the banner | `tests/trajectory.test.js` seventh case |
| F4 CLIMATOLOGY badge style differs from FORECAST | `tests/weatherPanel.test.js` first case, DOM class, `data-horizon-style`, and the two rules in `styles.css` |
| F4 skill chart renders a series with N points | `tests/weatherPanel.test.js` second case, `circle[data-lead-time-days]` count equals `skill_series` length |
| F4 thresholds from a config file, flagged ASSUMPTION | `tests/weatherPanel.test.js` fourth and third cases, every boundary of `WEATHER_THRESHOLDS` |
| F4 probability number, horizon badge and issue time adjacent to the colour | `tests/weatherPanel.test.js` third case |
| F4 per criterion breakdown with VERIFIED and PROXY | `tests/weatherPanel.test.js` fifth case |
| F4 grey state when no probability exists | `tests/weatherPanel.test.js` sixth case |
| F5 a centre below the horizon shows no visibility | `tests/viewing.test.js` first case, every centre `data-visible` false with a negative peak elevation |
| F5 a centre in view shows visibility with an elevation number | `tests/viewing.test.js` second case, `data-max-elevation-deg`, the printed `x.x deg`, the elevation chart point and the mask line |
| F5 sunlit vehicle with a dark observer | `tests/viewing.test.js` third case |
| F5 ECEF geometry against the mask | `tests/viewing.test.js` fourth case |
| F5 Leaflet viewing map, one circle per centre | `tests/viewing.test.js` fifth and sixth cases |

## Interpretations and open points

1. **The ephemeris is fetched per row, not per orbit class.** Spec V.2 says each row highlights "its own track" and IV.2 gives the query `?start=ISO&end=ISO&step_s=number`. The screen therefore sends `start` as `t_liftoff_utc` and `end` as `t_injection_utc` of the clicked row, which is what makes the fetched track match the row. `step_s` is sent as 300 s, the documented server default, so the URL is explicit.
2. **The CUSTOM target has no ephemeris id.** IV.2 says the engine creates a custom id implicitly and puts it in the response `orbit_id`, but the frozen `windows_response` schema has `additionalProperties: false` and no `orbit_id`. No id is invented: the screen asks for no track and names the gap. This needs a contract change, not a frontend guess.
3. **Two weather indicators, one threshold table.** Spec V.3 thresholds `p_launch`, issue F4 thresholds `p_success_components.weather`. Both are rendered, each with the same `WEATHER_THRESHOLDS`, so neither reading of the contract is hidden and each number stays traceable to one response field.
4. **The hazard buffer width is missing on this branch.** `hazard_half_width_km` is `null` in `src/config.js` for `cyclone4m`, because the value belongs to `backend/engine/data/vehicles/cyclone4m.json`, which ENGINE owns and which does not exist here. The buffer is implemented and tested through an injected value; the shipped default states the gap and names the owner. Nothing was invented.
5. **The frozen ephemeris example leaves the corridor.** `ephemeris_response_good_leo45.json` has a second sample at 48.11 N, which is north of Canso and outside the 100 to 140 deg corridor, so the guard rejects it. That is the northbound bug of the prototype appearing in the frozen example, and it is asserted as such rather than worked around.
6. **Population centre coordinates are ASSUMPTION.** No gazetteer was reachable offline, so every row of `src/data/centres.json` carries its own `flag` and the file carries a note. The screen prints the coordinates it uses and the file names them as unverified.
7. **The solar expression is cited from memory and flagged.** The formula source string in `src/config.js` names the Astronomical Almanac and the NOAA Solar Calculator and states that neither citation was resolved online. The accuracy claim is not made; the expression is flagged `ASSUMPTION` and printed on the screen.
8. **A sunlit vehicle cannot be strictly above a dark observer's horizon.** The shadow half angle `asin(R_e/(R_e+h))` and the horizon half angle `acos(R_e/(R_e+h))` sum to 90 degrees, so the only sunlit cases at a visible centre are twilight cases at or just above the depressed horizon. The test asserts such a sample, and asserts the elevations on both sides of the horizon, instead of asserting an impossible configuration.
9. **The site read is triggered by the first selection.** Screen 1 must issue exactly one POST per input change, and the F1 test counts the calls on load, so `GET /v1/site` is read with the rest of the row resources rather than on load. The fetch order is documented in `README.md` as spec V.7 requires.
10. **No tile layer.** Leaflet is drawn with vector layers only, because the demo runs with the network off and a tile request would fail visibly. Adding a tile layer is one line when a network is available.
11. **The 3D globe is cut.** Spec V.2 makes it optional and says to cut it before any 2D feature. The two tests of F3 assert the 2D map only.
12. **`centres.json` has no fixture fallback.** It is a repository file, not an API resource, so a read failure is reported on the screen. Every API read does fall back to its fixture.

## Not done in this session

F6 to F9: the scientific analysis view with the reliability diagram, the constants and provenance table and the CSV and JSON exports, the fixture content that API owns, `frontend/REQUIREMENTS_MAP.md`, `frontend/SLIDE.md`, `frontend/DONE.md` and `frontend/progress.md`. `frontend/AUDIT.md` is left as the F0 to F2 record; the F3 to F5 dispositions are in this file and in `frontend/README.md`.