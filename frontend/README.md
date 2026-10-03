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

1. Every ephemeris sample becomes an ECEF position on a sphere of radius `constants_block.R_e` from the ephemeris response, falling back to the spec II.10 value 6378137.0 m: `x = (R + h) cos(lat) cos(lon)`, `y = (R + h) cos(lat) sin(lon)`, `z = (R + h) sin(lat)`, with `h` from `alt_km`. The altitude is treated as height above that sphere; the ellipsoidal height of the ephemeris is approximated as a spherical one, which is the simplification the response constants allow.
2. Each centre of `src/data/centres.json` becomes an observer position the same way, at its declared latitude and longitude with altitude 0 m, because the file declares no altitude. The local east, north and up unit vectors of the observer are formed from its latitude and longitude.
3. The topocentric elevation is `asin` of the line of sight dotted with the local up, and the azimuth is `atan2` of the east and north components, both from the observer. Earth curvature is therefore included by construction and atmospheric refraction is not: the mask, not refraction, decides visibility.
4. Visibility is `max elevation over the samples at or above ELEVATION_MASK_DEG = 10`, the spec V.4 default, flagged `ASSUMPTION` and shown with its source. Centres below the mask and centres below the horizon are marked not visible with their peak elevation number.
5. Illumination: the Sun position is the low precision solar coordinate series (mean longitude, mean anomaly, ecliptic longitude, obliquity) with the IAU 1982 Greenwich mean sidereal time polynomial that `constants_block.gmst_model` names, rotated into ECEF. A position is sunlit when it is on the sunward side, or when the perpendicular distance from the Earth centre to the Sun line through it is at least `R_e`. The same test is applied to the vehicle and to the observer, so the panel can report a sunlit vehicle seen by an observer in darkness.
6. The honest consequence of steps 3 and 5, which the geometry forces: the shadow cone half angle from the anti-solar point is `asin(R_e / (R_e + h))` and the horizon half angle is `acos(R_e / (R_e + h))`, and the two sum to 90 degrees. A vehicle therefore cannot be both above the horizon of an observer in the umbra and outside the umbra. The sunlit cases the panel finds are twilight cases, where the vehicle is at or just above the depressed horizon of a dark observer; `tests/viewing.test.js` asserts one such sample and asserts that every centre in that sample is dark while the vehicle is lit.

Formula source: `SOLAR_FORMULA_SOURCE` in `src/config.js`, that is the Astronomical Almanac of the US Naval Observatory as reproduced by the NOAA Solar Calculator. Neither citation could be resolved from this branch, which has no network, so the expression is carried as `ASSUMPTION` pending verification and is named on the screen.

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
| `tests/viewing.test.js` | a centre below the horizon shows no visibility; a centre in view shows visibility with an elevation number and the elevation chart; a sunlit vehicle seen by observers in darkness; the ECEF geometry against the mask for every centre and sample; the Leaflet viewing map with one circle per centre |

The Leaflet assertions run against the real library under jsdom: the map container is a `leaflet-container` and the layers are `path.layer-track`, `path.layer-corridor`, `path.layer-buffer`, `path.layer-site`, `path.layer-centre`, `path.layer-centre-visible` and `path.layer-centre-dark`. No canvas pixel is inspected.

## What is stubbed versus live, screens 2 to 4

| Area | State |
|---|---|
| `GET /v1/site` | Live client. Polygon vertices are read from the response when it declares them, otherwise the azimuth wedge is computed from `A_min_deg` and `A_max_deg` |
| `GET /v1/orbits/{id}/ephemeris` | Live client, `start` and `end` from the selected row and `step_s` 300 s from `src/config.js`. No track is requested for a CUSTOM target because no frozen field names its id |
| `GET /v1/weather/probability` | Live client, `date` from the selected row and `site` from the request |
| `GET /v1/validation/skill` | Live client with no query parameters, so the server defaults of spec IV.4 apply |
| Leaflet 1.9.4 | Loaded from `frontend/node_modules/leaflet/dist/leaflet-src.esm.js` by dynamic import, stylesheet from `node_modules/leaflet/dist/leaflet.css`. No tile layer is requested, because the demo runs with the network off |
| Vehicle hazard footprint | `null` in `src/config.js`, owned by ENGINE. The buffer renders when a half width is declared |
| Population centre coordinates | `src/data/centres.json`, every row flagged `ASSUMPTION` |
| Solar position | Low precision series, formula source named in `src/config.js`, carried as `ASSUMPTION` pending citation verification |
| 3D globe | Cut, as spec V.2 permits |
| Screens 5 and the exports | F6, not built |