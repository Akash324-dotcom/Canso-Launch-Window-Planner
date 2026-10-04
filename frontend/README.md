# Frontend

The launch window decision engine for Spaceport Nova Scotia (Canso): five screens, one countdown, the offline fallback layer, and the fixture set the demo floor stands on. Tasks F0 to F9 of issue 5 are covered; `DONE.md` lists what shipped and what is known unfinished, and `REQUIREMENTS_MAP.md` maps every slide requirement to a component and a test.

## Stack and why

- Plain ES modules, no framework, no bundler, no build step. Spec V recommends the static path because a build step is a demo failure mode at judging, and this branch has no network and no registry access, so a toolchain could not be installed anyway.
- No framework rewrite of the inherited prototype. The audit in `AUDIT.md` records the decision and the evidence; the whole application is a handful of renderers reading one response object each, which plain functions express directly.
- Leaflet 1.9.4 for the two maps, imported from `frontend/node_modules/leaflet/dist/leaflet-src.esm.js`, never from a CDN, so the maps work with the network off. No tile layer is requested.
- Charts are inline SVG built in `src/svgChart.js`. No chart library, so nothing to install and nothing that can fail to load at judging.
- vitest with jsdom for the tests, for the reason recorded in `AUDIT.md` section 0.
- The fixture generator is Python 3 standard library only, so it runs anywhere the contract tests run and needs no install.

The walk of the live site in a real browser, with its PASS and FAIL table, is `BROWSER_WALK.md`; `tools/browser_walk.mjs` repeats it.

## How to run

Serve the repository root, not this directory, so that the relative offline fixture paths resolve:

```bash
python -m http.server 8000
```

Then open `http://localhost:8000/frontend/`. The app posts to `http://localhost:8000/v1/windows` by default, which is `API_BASE` in `src/config.js`. With no API running the request fails, the mode switches to `offline_precomputed`, and the banner names the engine run and every fixture in use. To point the app at a live API, change `API_BASE` in `src/config.js`.

## The fixture path

| What | Where |
|---|---|
| The five shipped fixtures | `backend/fixtures/windows.json`, `weather.json`, `skill.json`, `site.json`, `ephemeris.json`, read through `src/fixtures.js` from `FIXTURE_BASE`, which is `../backend/fixtures/` relative to `frontend/` |
| Population centres | `frontend/src/data/centres.json`, a repository file with no fixture fallback |
| Leaflet | `frontend/node_modules/leaflet/dist/leaflet-src.esm.js` and `node_modules/leaflet/dist/leaflet.css` |
| Regeneration | `python frontend/tools/make_fixtures.py`, which rewrites `windows.json` and `ephemeris.json` and then validates all five files against `tests/contract/schemas/` |

`tools/make_fixtures.py` is a fixture approximation, not the ENGINE: it places one circular two-body orbit at 98.1 deg and 550 km so that the ground track starts over Canso at the first liftoff instant and runs south over the Atlantic, it models the ascent between liftoff and injection as altitude `h(t) = 550 * (t/600)^1.5` km and downrange distance `d(t) = D * (t/600)^2` km along the `azimuth_compass_deg` of the first row, and it restates the window rows with injection exactly 600 s after liftoff. `D` is not a free number: it is the ground distance the same orbit covers in those 600 s, 4236.045 km, so that the modelled ascent is the same length as the arc the orbit flies. `D` and both exponents are ASSUMPTIONs of this fixture and are named as such in the script header and in `docs/log/frontend.md`. The script prints the geometry it solved (semi-major axis, period, mean motion, RAAN, argument of latitude, the inertial launch azimuth against the spec II.2 value, the rotating frame heading, the ascent profile and `D`) and refuses to write if the plane misses the direct ascent azimuth, if the track is not southbound, if the orbit does not hold altitude after injection, if any ascent sample misses its profile or its 30 s grid, if the first sample is not on the pad over the site, or if the ascent hands over to the orbit more than a fifth of `D` away. That last bound matters: a great circle on the compass azimuth of the row and the curved sub-satellite track of the orbit do not meet exactly, and the shipped numbers leave a gap of about 456 km at the handover, which the script prints. The ephemeris therefore carries 202 samples: 21 on the 30 s ascent grid from liftoff to injection and 181 on the 60 s orbit grid for the two orbital periods that follow. Its schema check is a documented subset of JSON Schema 2020-12, and it is proved non-vacuous on every run by requiring that it accepts all the good examples and rejects all the bad examples of the five fixture schemas, 42 frozen files in total.

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
| `tests/trajectory.test.js` | F3: the ground track per row, the corridor polygon, the site marker, the hazard buffer, the northbound rejection, the Leaflet map from `node_modules`, the CUSTOM target with no ephemeris id, the ephemeris fixture fallback |
| `tests/weatherPanel.test.js` | F4: the CLIMATOLOGY and FORECAST badges, the skill curve, the probability beside the colour, the thresholds, the per-criterion flags, the grey state |
| `tests/viewing.test.js` | F5: visibility per centre over the ascent of the selected row only, the elevation numbers and chart, the illumination test, the ECEF geometry against the mask, the Leaflet viewing map, the centre a later pass would have counted, the ignored samples outside the ascent, the interpolated endpoints, the elevation mask threshold, the ranking by max elevation and the missing coverage message |
| `tests/analysis.test.js` | F6: the CSV and JSON downloads, the provenance panel and its source files, the vehicle duration per row, the Brier skill table and chart, the reliability diagram and the ROC points |
| `tests/offline.test.js` | F7: the app with the network fully blocked on the shipped fixtures, all screens rendering, the countdown ticking, the banner, and the identical element tree against the live path |

Mock payloads are the frozen examples in `tests/contract/examples/good/`, except in `tests/offline.test.js`, which reads the real `backend/fixtures/` files from disk because that test is about the shipped fixtures.

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
| `POST /v1/windows` | Live client, one request per input change, 8000 ms timeout from `src/config.js`. The engine behind it is `engine_version: "stub"` until GATE G1, so every fixture and every stub response is labelled as such |
| The other four endpoints | Live clients with fixture fallbacks, see the fetch order below |
| Offline fixtures | Shipped and regenerated by `tools/make_fixtures.py`, content owned by FRONTEND, directory owned by API |
| Vehicle `T_to_inj` flag | Read from the response `provenance_block.row_flags`; the value and its VERIFIED or ASSUMPTION flag are ENGINE data at `backend/engine/data/vehicles/cyclone4m.json` and are absent on this branch, so the screen names the owner instead of showing a flag |
| Vehicle hazard footprint | `hazard_half_width_km` is `null` in `src/config.js`, owned by ENGINE, so the buffer is implemented and tested through an injected value and states the gap on screen |
| Population centre coordinates | `src/data/centres.json`, every row flagged `ASSUMPTION` |
| Solar position | Low precision series, formula source named in `src/config.js`, carried as `ASSUMPTION` pending citation verification |
| 3D globe | Cut, as spec V.2 permits |
| Expected delay cost | Built in the engine (`backend/engine/decision.py`) and served by `GET /v1/decision/delay-cost`; shown by the "Expected delay" panel of the prototype page, which computes nothing itself. The daily cost is entered by the user and has no default. The planner screens of this app do not show it yet |
| Network | Never used except the API calls and the reads of the repository fixture files |

# Screens 2, 3 and 4 (F3, F4 and F5)

Added on top of Screen 1 without changing its contract: `src/api.js`, `src/store.js`, `src/selectors.js`, `src/countdown.js` and the Screen 1 renderer keep their F0 to F2 behaviour, and every new read goes through `src/api.js` with a fixture fallback. The sections above describe the F0 to F2 session and are left as written; where the "Screens 2 to 5: not built" row above disagrees with this section, this section is the current state and Screen 5 is the only screen still unbuilt.

## Screen 2, trajectory (`src/screens/trajectory.js`, `src/geo.js`)

| Layer | Source | Rendered as |
|---|---|---|
| Corridor polygon | `GET /v1/site`, `corridor.A_min_deg` and `A_max_deg`, and `phi_s_deg`, `lambda_s_deg` when the response declares no vertex list | Leaflet polygon, plus the vertex list with its `data-lat-deg` and `data-lon-deg` |
| Ground track | `GET /v1/orbits/{id}/ephemeris?start=<t_liftoff_utc>&end=<t_injection_utc>&step_s=300` for the selected row | Leaflet polyline, plus one `li[data-track-point]` per point of `points[]` with `lat_deg`, `lon_deg`, `alt_km` and `t_utc` |
| Hazard buffer | `VEHICLE_FOOTPRINTS[vehicle_profile_id].hazard_half_width_km` in `src/config.js` | Leaflet polygon offset `hazard_half_width_km` either side of the nominal track |
| Site marker | `GET /v1/site` | Leaflet circle marker |
| Population centres | `src/data/centres.json` | Leaflet circle markers and a chip list |
| Corridor guard | bearings from the site to every track point against the corridor azimuth | `p#corridor-check` with `data-inside` |

Notes on the corridor polygon and the guard:

- Spec V.2 asks for "the corridor polygon from GET /v1/site", and the frozen schema leaves the body open because the specification IV.5 states the fields in prose. Declared vertices are used when the response carries a `corridor_polygon` or `corridor_polygon_vertices` array; otherwise the wedge between `corridor.A_min_deg` and `corridor.A_max_deg` is drawn. The wedge radius is the greatest site to track distance, with `CORRIDOR_FALLBACK_ARC_KM = 1200` as a map framing minimum only.
- The guard is the UI level northbound fix of the inherited prototype: it computes the initial great circle bearing from the site to every track point and refuses any point outside the corridor azimuth. A rejected track is still listed with its geometry and is labelled a `HAZARD REJECTION`, because the frozen `ephemeris_response_good_leo45.json` example itself contains a sample at 48.11 N that leaves the corridor.
- The 3D globe is not carried over. Spec V.2 makes it optional and says to cut it before any 2D feature; the 2D map, the corridor, the buffer and the per row highlight are the parts that are tested.
- `hazard_half_width_km` is `null` for `cyclone4m` in `src/config.js`, so the buffer is not drawn by default. The footprint half width is vehicle data owned by ENGINE at `backend/engine/data/vehicles/cyclone4m.json`, which does not exist on this branch, so the screen states the missing value and names the owning file instead of inventing a width. A test supplies the value through `createApp({ footprints: ... })` and asserts the drawn offsets.
- The ephemeris id of a CUSTOM target is not named by any field of the frozen `windows_response` schema, although spec IV.2 says the engine creates one implicitly. For a CUSTOM request the screen therefore asks for no track and says so.

## Screen 3, weather panel (`src/screens/weather.js`, `src/weatherBands.js`, `src/svgChart.js`)

- The band is `weatherBand()` applied to `p_success_components.weather` of the selected row, and the same function is applied to `p_launch` of `GET /v1/weather/probability?date=&site=`, because spec V.3 thresholds `p_launch` and issue F4 thresholds the row component. Both are shown so that neither reading of the contract is hidden.
- Thresholds live in `src/config.js` `WEATHER_THRESHOLDS` (Green at or above 0.70, Yellow 0.40 to 0.70, Red below 0.40), are flagged `ASSUMPTION`, and the panel prints them with their source line.
- Always adjacent to the colour: the probability as a percentage, the `horizon_label` badge and the issue time as `issued 09:00Z, 3 Oct 2026` through `Intl`. `FORECAST` uses a solid `badge-forecast` rule and `CLIMATOLOGY` a dashed `badge-climatology` rule, and a test compares both the DOM class and the stylesheet rule.
- A response with no probability renders the grey `no probability available` state inherited from the prototype, never a colour.
- The hindcast skill curve is inline SVG built by `src/svgChart.js`, no chart library: `bss` against `lead_time_days`, a zero line labelled `no skill`, the measured skill horizon as a vertical annotation, and one `circle[data-lead-time-days]` per point of `skill_series`.
- The per-criterion breakdown is a `details` element listing `criterion_id`, `p_violation` and the `VERIFIED` or `PROXY` flag of every `components[]` row.

## Screen 4, viewing map (`src/screens/viewing.js`, `src/viewing.js`, `src/solar.js`)

Geometry, stated once here and printed on the screen:

1. Only the ascent of the selected window is measured. The samples used are the ephemeris points whose `t_utc` lies inside `[t_liftoff_utc, t_injection_utc]` of the clicked row, both ends included. An ephemeris can carry two full orbits, and computing the visibility over every sample of it made every centre report as visible, which answers a different question from the slide one. When fewer than two samples fall inside the interval, the latitude, longitude and altitude at liftoff and at injection are interpolated linearly from the samples that bracket each instant, so there are always at least those two points, and the screen says how many of them are interpolated. When the ephemeris has no sample on one side of the ascent interval, nothing is interpolated and nothing is claimed: the screen prints `Ephemeris does not cover the ascent of this window`, names the span of the samples it does have, and marks no centre visible. `ascentSamples()` in `src/viewing.js` is that rule, in one function.
2. Every ephemeris sample of the ascent becomes an ECEF position on a sphere of radius `constants_block.R_e` from the ephemeris response, falling back to the spec II.10 value 6378137.0 m: `x = (R + h) cos(lat) cos(lon)`, `y = (R + h) cos(lat) sin(lon)`, `z = (R + h) sin(lat)`, with `h` from `alt_km`. The altitude is treated as height above that sphere; the ellipsoidal height of the ephemeris is approximated as a spherical one, which is the simplification the response constants allow.
3. Each centre of `src/data/centres.json` becomes an observer position the same way, at its declared latitude and longitude with altitude 0 m, because the file declares no altitude. The local east, north and up unit vectors of the observer are formed from its latitude and longitude.
4. The topocentric elevation is `asin` of the line of sight dotted with the local up, and the azimuth is `atan2` of the east and north components, both from the observer. Earth curvature is therefore included by construction and atmospheric refraction is not: the mask, not refraction, decides visibility.
5. Visibility is `max elevation over the ascent samples at or above ELEVATION_MASK_DEG = 10` from `src/config.js`, the spec V.4 default, flagged `ASSUMPTION` and printed next to the table with its source. That is the only threshold on the screen: the same number decides the verdict and draws the reference line on the elevation chart. Centres below the mask, centres with no ascent sample and centres below the horizon are all marked not visible, each with its max elevation number or the statement that there is no sample.
6. The table is ranked by that maximum, descending, and shows the rank, the max elevation to 1 dp, the UTC time at which it happens and whether the vehicle was sunlit while the observer was in the Earth shadow at that sample. The best view is the top visible centre, `best_centre_id`, which is what the elevation chart is drawn for. A centre with no ascent sample has no maximum and sorts last; ties are broken by id so the order is stable.
7. Illumination: the Sun position is the low precision solar coordinate series (mean longitude, mean anomaly, ecliptic longitude, obliquity) with the IAU 1982 Greenwich mean sidereal time polynomial that `constants_block.gmst_model` names, rotated into ECEF. A position is sunlit when it is on the sunward side, or when the perpendicular distance from the Earth centre to the Sun line through it is at least `R_e`. The same test is applied to the vehicle and to the observer, so the panel can report a sunlit vehicle seen by an observer in darkness.
8. The honest consequence of steps 4 and 7, which the geometry forces: the shadow cone half angle from the anti-solar point is `asin(R_e / (R_e + h))` and the horizon half angle is `acos(R_e / (R_e + h))`, and the two sum to 90 degrees. A vehicle therefore cannot be both above the horizon of an observer in the umbra and outside the umbra. The sunlit cases the panel finds are twilight cases, where the vehicle is at or just above the depressed horizon of a dark observer; `tests/viewing.test.js` asserts one such sample and asserts that every centre in that sample is dark while the vehicle is lit.

Formula source: `SOLAR_FORMULA_SOURCE` in `src/config.js`, that is the Astronomical Almanac of the US Naval Observatory as reproduced by the NOAA Solar Calculator. Neither citation could be resolved from this branch, which has no network, so the expression is carried as `ASSUMPTION` pending verification and is named on the screen.

What the shipped fixtures show through this geometry: the ephemeris fixture models the ascent of the first window row with 21 samples at 30 s, so every verdict on that row is read from the rise from the pad rather than from a pass already at 550 km. The result discriminates: Halifax is the only centre that reaches the 10 deg mask, at 14.0 deg at 11:44:47 UTC, Sydney NS peaks at 8.9 deg and Charlottetown at 8.2 deg, and the other four are between 1.3 and 7.3 deg, so the answer to the slide question is one region rather than seven. The second and third rows of `windows.json` are on the following days, which that ephemeris does not reach, so selecting them states the coverage sentence instead of borrowing the first row's geometry. ENGINE's ephemeris, fetched per row over `[t_liftoff_utc, t_injection_utc]`, replaces both files at G1.

## Population centres

`src/data/centres.json` lists Halifax, Sydney NS, Moncton, Charlottetown, St. Johns, Boston and Montreal with WGS84 city centre coordinates. Spec V.4 names the first four and the Canso area; Boston and Montreal are added because they lie inside the viewing geometry of an Atlantic corridor ascent. Every row is flagged `ASSUMPTION` because no authoritative gazetteer was reachable from this branch. The file is read through `src/centres.js` with `requestJson`, and because it is a repository file rather than an API resource it has no fixture fallback: a read failure is reported on the screen instead of switching the mode.

## Fetch order and failure transitions

1. On load and on every committed input change: `POST /v1/windows` only. Nothing else is requested, so the "one POST per input change" rule and the countdown tests of F1 and F2 are unaffected.
2. On the first window row selection: `GET /v1/site`, `GET /v1/weather/probability?date=<liftoff date>&site=<request site>`, `GET /v1/validation/skill`, `src/data/centres.json`, and `GET /v1/orbits/{id}/ephemeris?start=&end=&step_s=` for the selected row. A later selection repeats all of them except `centres`, which is read again only because the read is cheap and the failure has to surface.
3. Any failure of a GET falls back to the fixture named for that resource in `src/config.js` `FIXTURES` and sets `mode` to `offline_precomputed`, which raises the banner naming the engine run and every fixture in use. A failure of `src/data/centres.json` is reported on the screen only.
4. A late response for a superseded request or selection is discarded by its sequence number, so a slow answer cannot overwrite a newer one.

## Tests for F3, F4 and F5

| File | Covers |
|---|---|
| `tests/trajectory.test.js` | selecting a row fetches the ephemeris of that row and renders its points and its per row highlight; the corridor polygon, the site marker and the hazard buffer offsets; the missing footprint width statement; the northbound hazard rejection; the Leaflet map mounted from `node_modules` with no CDN asset; the CUSTOM target with no ephemeris id; the ephemeris fixture fallback and the banner |
| `tests/weatherPanel.test.js` | the CLIMATOLOGY badge differs from the FORECAST badge in the DOM and in `styles.css`; the skill chart renders one SVG point per `skill_series` entry with the measured skill horizon; the probability number, the horizon badge and the issue time beside the colour; every band boundary of the configured thresholds; the per-criterion VERIFIED and PROXY flags on expand; the grey no-probability state |
| `tests/viewing.test.js` | a centre below the horizon shows no visibility; a centre in view shows visibility with an elevation number and the elevation chart; a sunlit vehicle seen by observers in darkness; the ECEF geometry against the mask for every centre and sample; the Leaflet viewing map with one circle per centre; Montreal is not visible when only the samples outside the ascent would have made it so; samples outside `[t_liftoff_utc, t_injection_utc]` are ignored; the endpoints are interpolated when fewer than two samples fall inside; the `ELEVATION_MASK_DEG` threshold is honoured and flagged `ASSUMPTION`; the centres are ranked by max elevation and the best view is named; an ephemeris that misses the ascent prints the coverage sentence and marks no centre visible |

The Leaflet assertions run against the real library under jsdom: the map container is a `leaflet-container` and the layers are `path.layer-track`, `path.layer-corridor`, `path.layer-buffer`, `path.layer-site`, `path.layer-centre`, `path.layer-centre-visible` and `path.layer-centre-dark`. No canvas pixel is inspected.

## What is stubbed versus live, screens 2 to 4

| Area | State |
|---|---|
| `GET /v1/site` | Live client. Polygon vertices are read from the response when it declares them, otherwise the azimuth wedge is computed from `A_min_deg` and `A_max_deg` |
| `GET /v1/orbits/{id}/ephemeris` | Live client, `start` and `end` from the selected row and `step_s` 300 s from `src/config.js`. No track is requested for a CUSTOM target because no frozen field names its id |
| `GET /v1/weather/probability` | Live client, `date` from the selected row and `site` from the request |
| `GET /v1/validation/skill` | Live client with `period_start` and `period_end`: the service answers 422 without a period. The period is the one of the recorded hindcast, read from `skill.json` (`src/app.js` `readSkill`) |
| `GET /v1/citation?id=<run>` | Read after every live `POST /v1/windows` (`src/app.js` `readCitation`): config hash, constants with sources, vehicle rows. No fixture; a failure is stated on the analysis screen |
| Leaflet 1.9.4 | Loaded from `frontend/node_modules/leaflet/dist/leaflet-src.esm.js` by dynamic import, stylesheet from `node_modules/leaflet/dist/leaflet.css`. No tile layer is requested, because the demo runs with the network off |
| Vehicle hazard footprint | `null` in `src/config.js`, owned by ENGINE. The buffer renders when a half width is declared |
| Population centre coordinates | `src/data/centres.json`, every row flagged `ASSUMPTION` |
| Solar position | Low precision series, formula source named in `src/config.js`, carried as `ASSUMPTION` pending citation verification |
| 3D globe | Cut, as spec V.2 permits |

# Screen 5 and the fixture floor (F6, F7, F8, F9)

The sections above describe F0 to F5 as they were written and are left as written, except for the stale sentences about the fixture files, which this section replaces. The current state: five screens, five shipped fixtures regenerated by a script, two offline tests, the requirements map, and the slide text.

## Screen 5, scientific analysis (`src/screens/analysis.js`, `src/export.js`, `src/svgChart.js`)

| Element | Source | Rendered as |
|---|---|---|
| Brier skill table | `skill_series[]` of `GET /v1/validation/skill` | `#analysis-skill-rows`, one `tr[data-lead-time-days]` per lead time with `bs`, `bs_ref`, `bss`, `n_cases` |
| Brier skill chart | the same series, `renderSkillCurve` | `#analysis-skill-curve`, inline SVG with the measured skill horizon annotated |
| Reliability diagram | `reliability_bins[]`, `renderReliabilityDiagram` | `#analysis-reliability-diagram`, inline SVG, observed frequency against forecast probability, with the perfect reliability diagonal and the base rate marked, plus `#analysis-reliability-rows` |
| ROC points | `roc_points[]` | `#analysis-roc-rows`, one `tr[data-threshold]` per point with `pod` and `far` |
| Vehicle duration | every row of the loaded window response | `#analysis-duration-rows`, `t_liftoff_utc`, `t_injection_utc`, `window_center_shift_s`, `liftoff_instant_error_min` and the ascent interval in seconds |
| Constants block | `constants_block` of the window response | definition list, every constant with its `source` string from the response |
| Criteria version | `provenance_block.criteria_version` | `#analysis-criteria-version`, beside the vehicle profile |
| Config hash | `config_hash` of `GET /v1/citation` for the run `constants_block.citation_id` | `#analysis-config-hash`, with the run identifier and the gmst model; says so when no citation record is available, and shows no hash then |
| Provenance table | `provenance_block`, including `site`, `corridor`, `row_flags` and `vehicle_profile_id` | definition list plus `#analysis-source-files`, one `li[data-source-file]` per declared file |
| Downloads | the loaded response objects | four buttons: the window table as CSV, the Brier skill series as CSV, the reliability bins as CSV, and the full JSON response |

Notes on the exports:

- The window table CSV is read from the rendered table, one column per rendered cell with the rendered headers as the header row, so the file is what the planner saw. The test compares every exported row with the rendered row cell by cell.
- The JSON download is the untouched response object, so a researcher has the exact values without parsing a formatted string. The test asserts the round trip equals the response.
- The file names carry the `citation_id` of the run, so an exported file names the run that produced it.

## The offline floor (F7)

- All five fixtures are committed under `backend/fixtures/` and are read through `src/fixtures.js`. Any API failure, HTTP error or timeout switches the mode to `offline_precomputed` and raises the banner naming the engine run and every fixture in use.
- There is one renderer. The live path and the fallback path pass the same response objects into the same five screen renderers; `tests/offline.test.js` asserts that the element tree of all five screens is identical between the two paths and that the rendered rows are identical, with the same five documents served from disk in both cases.
- The offline test blocks the network rather than stubbing the loader: every URL under `API_BASE` is refused with a failed fetch, and only a repository file can answer.
- The first test pins the clock with `vi.setSystemTime`, which is what makes the countdown assertion possible offline: it checks the exact remaining time `1d 23:42:17` against the first fixture liftoff and then that two seconds later it reads `1d 23:42:15`.

## Fetch order and failure transitions, unchanged from F3 to F5

1. On load and on every committed input change: `POST /v1/windows` only.
2. On the first window row selection: `GET /v1/site`, `GET /v1/weather/probability`, `GET /v1/validation/skill`, `src/data/centres.json`, and `GET /v1/orbits/{id}/ephemeris` for the selected row.
3. Any failure of a GET falls back to the fixture named for that resource in `src/config.js` `FIXTURES` and sets the mode to `offline_precomputed`. A failure of `src/data/centres.json` is reported on the screen only.
4. A late response for a superseded request or selection is discarded by its sequence number.

## Known conflicts in the shipped fixture set, reported not worked around

1. The corridor bounds disagree between fixtures. `backend/fixtures/site.json` declares `A_min_deg` 100 and `A_max_deg` 140 marked `VERIFIED`, while `backend/fixtures/windows.json` declares 90 and 200 for the same run marked `ASSUMPTION`, and spec II.3 states the default corridor file ships 90 and 200. With the 100 to 140 bounds the reachable inclination set tops out near 63 deg, so no honest southbound SSO track from Canso can satisfy them: the corridor guard on Screen 2 therefore flags the correct southbound fixture track as leaving the corridor. The bounds come from the ENGINE corridor file, `backend/engine/data/site_canso.json`, which does not exist on this branch, so no value was invented here. This needs ENGINE or API to publish the EA bounds.
2. `raan_deg` in the window rows is 45.0, 45.99 and 46.97, the declared launch plane of the stub run. The ephemeris plane is solved for the southbound crossing of the site latitude to be over Canso at the first liftoff instant, which fixes the plane to a RAAN of 300.47 deg at that instant. The two agree on inclination, altitude, site, heading and epoch; they do not agree on the RAAN value, because no RAAN satisfies both the declared value and a site passage at that instant. ENGINE's real ephemeris replaces both files.
3. The two fixtures carry different `citation_id` values (`run_20261005_5f2c9d1a77b4` in the window response, `run_20261003_7f3a91c2` in the ephemeris and skill responses) because they were frozen in separate runs by API. They are carried over untouched.