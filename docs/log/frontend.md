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
---

# Session covering the fixtures, F6, F7, F8 and F9

Same branch, built on the F0 to F5 modules. `src/api.js`, `src/store.js`, `src/config.js` and the four existing screens were extended, not rewritten, and no existing test was changed or weakened. The 43 tests that existed at the start of this session still pass unchanged; 8 cases were added, for 51.

## Commands run

Fixture generation and its schema check, from the repository root:

```text
$ /Users/rafathossain/MDA_Mission_Accepted_Hackathon/.venv/bin/python frontend/tools/make_fixtures.py
```

```text
site canso at 45.3 N, -61.0 W (site.json)
target sso981 inclination 98.1 deg, 550.0 km circular
semi-major axis 6928137.0 m, period 5738.993 s, mean motion 0.001094824 rad/s
solved plane: RAAN 300.467797 deg, argument of latitude 134.113516 deg at the first liftoff 2026-10-05T11:42:17Z
inertial launch azimuth 191.5554 deg against the direct ascent azimuth 191.5554 deg of spec II.2; ground track heading in the rotating frame 194.1591 deg, the Earth rotation correction being 2.6036 deg
samples 192 over 11460 s, step 60 s, 2 orbits of 5738.993 s
first sample {'t_utc': '2026-10-05T11:42:17Z', 'lat_deg': 45.3, 'lon_deg': -61.0, 'alt_km': 550.0}
last sample {'t_utc': '2026-10-05T14:53:17Z', 'lat_deg': 46.40489, 'lon_deg': -108.553, 'alt_km': 550.0}
latitude span -81.89057 to 81.89564 deg, altitude span 0.000000 km
wrote /Users/rafathossain/MDA-frontend/backend/fixtures/windows.json and /Users/rafathossain/MDA-frontend/backend/fixtures/ephemeris.json
ephemeris.json validates against ephemeris_response.json
site.json validates against site_response.json
skill.json validates against skill_response.json
weather.json validates against weather_probability_response.json
windows.json validates against windows_response.json
the schema subset check accepted every good example and rejected every bad example of the five fixture schemas, 42 frozen examples
```

Idempotence, a second run over the files the first run wrote:

```text
$ before=$(git diff backend/fixtures | shasum) && /Users/rafathossain/MDA_Mission_Accepted_Hackathon/.venv/bin/python frontend/tools/make_fixtures.py > /dev/null && after=$(git diff backend/fixtures | shasum) && [ "$before" = "$after" ] && echo IDENTICAL
```

```text
IDENTICAL: a second run produced byte identical fixture files
```

Independent validation of the five fixtures with the real jsonschema through the frozen contract validator, not with the script's own subset check:

```text
$ /Users/rafathossain/MDA_Mission_Accepted_Hackathon/.venv/bin/python -c "... validator_for(schema).iter_errors(document) ..."
```

```text
windows.json windows_response OK
weather.json weather_probability_response OK
skill.json skill_response OK
site.json site_response OK
ephemeris.json ephemeris_response OK
```

Contract tests:

```text
$ /Users/rafathossain/MDA_Mission_Accepted_Hackathon/.venv/bin/python -m pytest tests/contract -q
```

```text
70 passed in 0.09s
```

Frontend tests, final run:

```text
$ cd frontend && npx vitest run
```

```text
 Test Files  9 passed (9)
      Tests  51 passed (51)
   Start at  20:22:10
   Duration  1.10s (environment 52%, tests 26%, transform 10%, import 6%, worker 1%)
```

Per file during development: `npx vitest run tests/analysis.test.js` reported 6 passed, `npx vitest run tests/offline.test.js` reported 2 passed, and the full suite after each change reported 51 passed with no failure at any intermediate state other than the recorded red states while writing a case.

## Files created

| Path | Purpose |
|---|---|
| `frontend/tools/make_fixtures.py` | Regenerates `backend/fixtures/windows.json` and `backend/fixtures/ephemeris.json` from one geometry, then validates all five fixtures against the frozen schemas. Standard library only, no network, no install |
| `frontend/src/export.js` | The client-side exports of spec V.6: the rendered window table as CSV, the Brier skill series as CSV, the reliability bins as CSV, the response as JSON, and `downloadText`, which turns a finished string into a file through an anchor |
| `frontend/src/screens/analysis.js` | Screen 5: the Brier skill table and chart, the vehicle duration per row, the reliability diagram and the ROC points, the constants block with sources, the criteria version, the config hash, the provenance panel with every declared source file, the four download buttons and the fixture links |
| `frontend/tests/analysis.test.js` | The F6 cases, 6 of them |
| `frontend/tests/offline.test.js` | The F7 cases, 2 of them, with the network blocked and the real fixture files read from disk |
| `frontend/SLIDE.md` | The slide text verbatim, checked character for character against the text this session was given |
| `frontend/REQUIREMENTS_MAP.md` | One row per slide requirement, each naming its component and its exact test name, with the one gap marked NOT DONE |
| `frontend/DONE.md` | What shipped, what is known unfinished, with the commands and results |

## Files changed

| Path | Change |
|---|---|
| `backend/fixtures/windows.json` | Regenerated. The only field that changed is `t_injection_utc` on each row, now exactly 600 s after `t_liftoff_utc`. Every other field, including `engine_version` `stub`, the constants and provenance blocks and `computation_ms`, is carried over byte for byte |
| `backend/fixtures/ephemeris.json` | Regenerated for `sso981`: 192 samples at 60 s from the first liftoff, two orbital periods, constant 550 km, `ground_track_valid` true, the first sample exactly on the site. The `constants_block` is carried over |
| `frontend/src/svgChart.js` | Added `renderReliabilityDiagram`, inline SVG from `reliability_bins`, with the perfect reliability diagonal and the base rate marked. `renderSkillCurve` and `renderElevationCurve` untouched |
| `frontend/src/app.js` | The optional `analysisHost`, the analysis screen in the render fan out and in `stop()`, nothing else changed |
| `frontend/src/main.js` | Passes `analysisHost` |
| `frontend/index.html` | The `screen-analysis` host |
| `frontend/styles.css` | Styles for the download buttons, the source file list and the two new chart rules |
| `frontend/tests/helpers.js` | `loadFixtureFile` reads a real file from `backend/fixtures`; `mountIndexMarkup` and `boot` return and pass `analysisHost` |
| `frontend/README.md` | Stack and why, how to run, the fixture path table, the countdown specification, the stubbed versus live table, the Screen 5 element table, the offline floor and the fixture conflicts reported below. The stale sentences about the fixture files not existing were corrected |
| `docs/log/frontend.md` | This section |

## Test to requirement map

| Requirement | Test |
|---|---|
| F6 download produces a file whose rows equal the rendered table | `tests/analysis.test.js` first case: the anchor href and `download` attribute captured, the Blob read back, the header row equal to the rendered headers and every data row equal to the rendered row cell by cell and, independently, to the formatted values of the response row |
| F6 the provenance panel shows every source file the run declared | `tests/analysis.test.js` second case: one `li[data-source-file]` per `provenance_block.source_files` entry, plus every constant value, every `source of` entry, the criteria version, the vehicle profile, the engine version and the config hash |
| F6 Brier skill table and chart | `tests/analysis.test.js` third case |
| F6 reliability diagram and ROC points | `tests/analysis.test.js` fourth case |
| F6 vehicle duration surfaced as `liftoff_instant_error_min` | `tests/analysis.test.js` fifth case, added because the F8 map row for the slide bonus names that number and the issue asks for it to be surfaced |
| F6 fixture links and claim status | `tests/analysis.test.js` sixth case |
| F7 with the network fully blocked the app loads, all screens render, the countdown works, the banner is present | `tests/offline.test.js` first case: every URL under `API_BASE` refused with a failed fetch, all five repository fixtures read from disk, five screens asserted element by element, the clock pinned so the countdown reads `1d 23:42:17` and `1d 23:42:15` two seconds later |
| F7 the fallback renders the same element tree as the live path | `tests/offline.test.js` second case: the same five documents served from the API in one run and from the fixtures in the other, then the tag and id signature of all five screen hosts and the rendered row cells compared for equality |

## Interpretations and open points

1. **The ephemeris starts at the site, so the RAAN is solved rather than declared.** A circular orbit at inclination 98.1 deg crossing latitude 45.3 deg on the southbound branch has the argument of latitude fixed, and the ECEF longitude at the first liftoff then fixes the RAAN in closed form. The solve gives 300.467797 deg. The window rows keep the stub run's declared `raan_deg` of 45.0, 45.99 and 46.97, so the two fixtures agree on inclination, altitude, site, heading and epoch but not on the RAAN value. No RAAN can satisfy both, because the site passage at that instant and the declared RAAN are independent. ENGINE's real ephemeris replaces both files at G1.
2. **The launch azimuth is checked in the inertial frame, and the rotating frame value is reported.** Spec II.2 gives cos(i) = cos(phi_s) sin(beta) for the inertial azimuth, and the fixture reproduces it to 0.0001 deg. The ground track heading of the same instant in the rotating frame is 194.1591 deg, 2.6036 deg larger, because the Earth turns under the vehicle during the ascent. Spec II.6 reports both, so the script checks the first and prints both rather than asserting the rotating frame value equals the inertial one.
3. **The injection offset is exactly 600 s and is an ASSUMPTION.** The instruction for this session fixed it, and it is a vehicle parameter that belongs to ENGINE at `backend/engine/data/vehicles/cyclone4m.json`, which does not exist on this branch. The number is the fixture's, and the screen names the owner.
4. **The window table CSV is read from the rendered table.** That is the literal reading of the acceptance test, and it makes the file the table the planner saw. The JSON download is the untouched response, so the exact values are still available without parsing a formatted string. The test compares the exported rows with the rendered rows cell by cell, and separately with the formatted values of the response row.
5. **The vehicle duration needed a screen to live on.** F8 asks for the slide bonus to be surfaced as the `liftoff_instant_error_min` number. That number is in the response but was in no table, so Screen 5 prints it per row beside `window_center_shift_s` and the ascent interval, with a test. The window table of Screen 1 keeps the eight spec V.1 columns unchanged.
6. **The schema check in the script is a documented subset, proved on every run.** `jsonschema` is not importable from the standard library, so the script implements the keywords the frozen schemas use and lists them in `SchemaSet.SUPPORTED`, printing a warning for any keyword it does not implement. It is proved non-vacuous by requiring, on every run, that it accepts all the good examples and rejects all the bad examples of the five fixture schemas, 42 files, which are the same examples the contract suite checks with jsonschema.
7. **The fixture set has a corridor conflict that is reported, not patched.** `backend/fixtures/site.json` declares corridor bounds of 100 to 140 deg marked `VERIFIED`; `backend/fixtures/windows.json` declares 90 to 200 marked `ASSUMPTION` for the same site; spec II.3 states the default corridor file ships 90 to 200. With bounds of 100 to 140 the reachable inclination tops out near 63 deg, so the 191.6 deg southbound SSO azimuth cannot satisfy them, and the Screen 2 guard consequently flags the correct southbound fixture track as leaving the corridor. The instruction for this session was to regenerate `windows.json` and `ephemeris.json` and to keep every other field of every other fixture, so `site.json` was not touched and no value was invented. The bounds are ENGINE data in `backend/engine/data/site_canso.json`, absent on this branch. This needs ENGINE or API.
8. **The offline test blocks the network rather than stubbing the loader.** Every URL under `API_BASE` is refused with a failed fetch and only a repository file can answer, so the test exercises the same code path a browser takes with the server down, including the fixture URLs resolved from `FIXTURE_BASE`.
9. **The clock is pinned in the offline test.** The fixture liftoffs are in October 2026, so asserting an exact countdown reading against `Date.now()` would expire. `vi.setSystemTime` fixes the clock and makes the assertion exact without weakening it: the value is still computed from the clock against the ISO string, and the tick still has to fire for the second reading to change.
10. **The provenance panel reads `constants_block.citation_id` as the config hash.** No field of the frozen schemas is named `config_hash`, so the run identifier that spec IV says is resolvable through `GET /v1/citation` is shown as the config hash, with the resolution route named. No new field was invented.
11. **One row of the requirements map is NOT DONE.** The slide line "a missed window can cost millions" is quantified as expected delay cost in spec II.9 (iv) and VI.3, in the decision layer, which is ENGINE's, and no frozen schema field carries a cost. Nothing was invented in the browser, so the row names no test and is marked NOT DONE.
12. **The verdict line of the analysis screen states the claim status.** The PROVED, SKETCHED and CONJECTURE marks of spec II.9 are printed next to the skill series, so a viewer cannot read positive Brier skill as a theorem.

## Not done in this session

`frontend/progress.md` is still not written, for the reason recorded above. No file outside `frontend/`, `backend/fixtures/*.json` and this log was created or edited, `Canso Launch Prototype.html` was not touched, nothing was committed, and no package was installed.

---

# Session covering the Screen 4 viewing fix (issue 5, F5)

Summary: the visibility of Screen 4 is now computed over the ascent of the selected window only, from the samples inside `[t_liftoff_utc, t_injection_utc]`, with the position at both endpoints interpolated when fewer than two samples fall inside, over a `VIEWING_MIN_ELEVATION_DEG = 5` threshold flagged ASSUMPTION, and the centres are ranked by that maximum so the screen names the best view. An ephemeris that does not reach the ascent now says so and marks no centre visible. Six cases were added to `tests/viewing.test.js`, two existing cases were adjusted, and none was weakened.

## Commands run

```text
$ cd frontend && npx vitest run
```

First run, after the geometry change and before the test file was touched, to record the red state of the two cases that asserted the old all-samples behaviour and the old mask wording:

```text
 Test Files  1 failed | 8 passed (9)
      Tests  2 failed | 49 passed (51)
AssertionError: expected '1Halifax, Nova Scotia44.6488-63.57529…' to contain 'visible above the 10 deg mask'
TypeError: Cannot read properties of undefined (reading 'vehicle_sunlit')
```

Final run:

```text
$ cd frontend && npx vitest run
```

```text
 Test Files  9 passed (9)
      Tests  57 passed (57)
   Duration  1.29s (environment 53%, tests 35%, transform 8%, import 4%)
```

Per file during development: `npx vitest run tests/viewing.test.js` reported 12 passed.

## Files changed

| Path | Change |
|---|---|
| `frontend/src/config.js` | Added `VIEWING_MIN_ELEVATION_DEG` of 5 with `VIEWING_MIN_ELEVATION_FLAG` and `VIEWING_MIN_ELEVATION_SOURCE`. `ELEVATION_MASK_DEG` and its flag and source are untouched |
| `frontend/src/viewing.js` | `ascentSamples()`, which restricts the ephemeris to the ascent of the selected row, interpolates the liftoff and injection positions between bracketing samples and reports coverage; `NO_ASCENT_COVERAGE`; `viewingReport()` gained `ascent` and `minElevationDeg`, reports the ascent window, the samples used, the interpolated count and the coverage message, ranks `report.centres` by max elevation with a `rank` per centre, takes `best_centre` as the top visible centre, and each sample now carries `index` and `interpolated`. `earthRadiusOf`, `topocentric` and `centreEntries` are unchanged |
| `frontend/src/screens/viewing.js` | Reads the selected row and passes its ascent interval, memoises on it, adds `p#viewing-ascent-note` and `p#viewing-min-elevation-note`, a rank column, `data-rank`, `data-best`, `data-peak-t-utc` and `data-peak-sunlit-in-darkness` on every row, names `VIEWING_MIN_ELEVATION_DEG` in the verdict text, and reports the missing coverage in the status, the sub line and the ascent note |
| `frontend/tests/viewing.test.js` | Six cases added, two adjusted, none weakened |
| `frontend/README.md` | The Screen 4 geometry section rewritten as eight numbered steps, with the ascent rule first, the two thresholds separated, the ranking and the best view stated, and a paragraph on what the shipped fixtures show through the new rule. Both test tables updated |
| `frontend/DONE.md` | The Screen 4 row and the recorded test count |
| `frontend/REQUIREMENTS_MAP.md` | The viewing map row, with the six new case names and the components they cover |
| `docs/log/frontend.md` | This section |

## Test to requirement map

| Requirement | Test |
|---|---|
| Visibility is computed over the ascent of the selected row, so a centre far from the ascent is not counted | `tests/viewing.test.js` / `does not count a centre that only the samples outside the ascent can see`: the same track puts Montreal at 90 deg and visible when every sample counts, and below the horizon and not visible once the ascent interval is applied, at the screen and in `viewingReport` |
| Samples outside `[t_liftoff_utc, t_injection_utc]` are ignored | `tests/viewing.test.js` / `ignores every sample outside the ascent interval of the selected row`: `sample_count` 3, `ascent_sample_count` 2, and every sample of every centre inside the interval with its peak time inside it |
| The liftoff and injection positions are interpolated when fewer than two samples fall inside | `tests/viewing.test.js` / `interpolates the liftoff and injection positions when fewer than two samples fall inside the ascent`: two bracketing samples, two interpolated endpoints, both flagged, liftoff at the midpoint of the bracketing latitude and longitude |
| A centre is visible only at or above `VIEWING_MIN_ELEVATION_DEG`, labelled ASSUMPTION on screen | `tests/viewing.test.js` / `honours the configured minimum elevation of the ascent`: St. Johns at 4.400 deg is not visible at the configured 5 and visible at an injected 4, `best_centre_id` follows, and the screen note carries the value, the flag and the source name |
| Centres are ranked by max elevation, descending, with the max elevation, its UTC time and the sunlit flag, and the best view is the top visible centre | `tests/viewing.test.js` / `ranks the centres by the maximum elevation of the ascent and calls the best view`: the report elevations are sorted descending, the ranks are 1 to 7, each peak time is the time of its maximum sample, the rendered rows carry the rank order with one `data-best`, and the chart note names the best view |
| A missing ephemeris coverage shows the message and marks no centre visible | `tests/viewing.test.js` / `says the ephemeris does not cover the ascent and marks no centre visible`: `coverage_message`, `ascent_covered` false, no best centre, the sentence in the ascent note, the sub line and the status, `visible centres 0 of 7`, and every row not visible with no elevation |
| The existing F5 cases still hold | `tests/viewing.test.js` first, second, fourth, fifth and sixth cases unchanged and passing, plus `tests/offline.test.js` |

## Interpretations and open points

1. **The ascent endpoints are interpolated, never clamped.** When fewer than two samples fall inside the ascent, the position at liftoff and at injection is interpolated linearly between the samples that bracket each instant. When the ephemeris has no sample on both sides of one of the two instants, the coverage fails and the screen says `Ephemeris does not cover the ascent of this window` rather than holding a position from far outside the ascent at the endpoint instant. Holding the nearest sample would have reported an invented position as an observation, and the phrase "at all" in the instruction is read as covering this case.
2. **`ELEVATION_MASK_DEG = 10` and `VIEWING_MIN_ELEVATION_DEG = 5` are two different numbers and both stay.** The verdict uses the new minimum of 5, because the slide asks which regions have the best view of the ascent and a 10 deg mask on a 10 minute ascent hides the low passes that the answer depends on. The 10 deg mask of spec V.4 stays what the specification calls it, the reference line drawn on the elevation chart, and its ASSUMPTION note is unchanged. Nothing about the chart changed.
3. **Two existing cases were adjusted, and neither was weakened.** `reports whether the vehicle is sunlit while an observer is in darkness` used a single ephemeris sample at 09:30 UTC, four hours before the ascent of the stub row, which the old all-samples code used and the new code must not. The row is shifted so that its ascent brackets that instant, the sample is replaced by the two samples that bracket it, and the assertions are unchanged in kind and stricter in extent: both ascent samples of every centre are asserted sunlit with a dark observer, so the count is 2 rather than 1. `shows visibility with an elevation number for a centre geometrically in view` asserted the verdict string `visible above the 10 deg mask`, which would now be a false statement on screen, so it asserts `visible above the 5 deg minimum elevation`; its elevation number, its `>= ELEVATION_MASK_DEG` check, its chart point and its mask line assertions are untouched.
4. **The rows are rendered in rank order, so the report order is the ranking.** `report.centres` is sorted by max elevation descending, with centres that have no ascent sample last and ties broken by id. The elevation chart is drawn for the top visible centre, and when no centre reaches the minimum the screen says so instead of drawing a series for a centre that is not visible.
5. **The shipped ephemeris fixture covers one row of three.** `backend/fixtures/ephemeris.json` spans two orbital periods from the first liftoff of 5 Oct, so only the 11 samples inside the 10 minute ascent of the first row count, and the rows of 6 and 7 Oct now state the coverage sentence. The old screen borrowed the first row's geometry for those rows. No fixture was changed, and ENGINE's per row ephemeris replaces it at G1.
6. **Nothing personal or unverifiable was invented.** The only new number is the 5 deg minimum elevation of issue F5, which is in `src/config.js` with its flag and source and is printed on the screen.

## Not done in this session

The 3D globe stays cut, the elevation mask of spec V.4 is not replaced anywhere else, no fixture, schema or backend file was touched, no package was installed, nothing was committed, and no file outside `frontend/` and this log was created or edited.
