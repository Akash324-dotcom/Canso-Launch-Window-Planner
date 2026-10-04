# Browser walk of the live site

The walk of the issue "[FRONTEND-LIVE] browser walk": every item below was exercised in a real browser against a
running API, not in jsdom. It is recorded here because the scope of the issue is `frontend/` only.

## How it was run

| | |
|---|---|
| Date | 4 October 2026, 08:30 to 09:30 ADT |
| Browser | Google Chrome, headless, driven by `tools/browser_walk.mjs` (the eleven items) and `tools/browser_controls.mjs` (every control), puppeteer-core |
| Page | `http://localhost:8090/frontend/`, served by `python -m http.server 8090` from the repository root |
| API | `uvicorn backend.api.app:app`, from `main` at 8f00062 plus commit 52cc728 of `fix/three-confirmed-bugs` (the CORS change of issue #24, not yet on `main`) |
| Frontend | branch `feature-browser-Walk`, with the fixes of this record |
| Weather layer | live, `source: open_meteo`, forecast issued 2026-10-03T18:00Z |

Two things about the setup that a reader must know:

- **Issue #24 is a precondition.** On `main` without the CORS change the page cannot read the API from another
  origin and every screen falls back to the fixtures with the offline banner. The walk therefore ran against
  `main` plus that one commit. The merge order of the issue (24, then this walk) holds.
- **Port 8000 was occupied on the walk machine** by an unrelated container. The API listened on another port and
  Chrome was started with `--host-rules=MAP localhost:8000 127.0.0.1:<port>`. The page, its `API_BASE`
  (`http://localhost:8000/v1`) and every request are exactly as shipped; only the socket the browser connects to
  differs. `API_PORT=8000` (the default) runs the tool without the rule.

To repeat it: see the header of `tools/browser_walk.mjs`. Both tools exit with the result on the console.

## Result

| # | Item | Result | Control, file:line | Evidence |
|---|---|---|---|---|
| 1 | Window table fills from `POST /v1/windows`; engine is not the stub | PASS | `#window-table`, `src/screens/windowEngine.js:298` (`renderTable`); request sent by `src/app.js:245` (`dispatch`) | `POST /v1/windows -> 200`, `engine_version: engine-0.1.0`, 10 rows in the response and 10 in the table, banner hidden |
| 2 | Countdown ticks against a live `t_liftoff_utc` | PASS | `#countdown-value-text`, `src/countdown.js:45` (`renderReadout`) | three readings 15:19:13, 15:19:12, 15:19:11; target 2026-10-05T02:55:33Z, the earliest usable upcoming row of the response; reading equals liftoff minus clock to the second |
| 3 | Empty-result path: a message, not a blank table, not a crash | PASS after fix | `#window-rows` empty row, `src/screens/windowEngine.js:294`; `#countdown-reason`, `src/countdown.js:45`; `#honesty-explanation`, `src/screens/windowEngine.js:328` | see "Item 3" below |
| 4 | LEO 45.1: honesty panel with the plane-change penalty | PASS | `#honesty-panel`, `#honesty-plane-change-dv-ms`, `src/screens/windowEngine.js:328` (`renderHonesty`) | `reachable: false`, `plane_change_dv_ms: 26.768304218158054`; panel shows "26.768304218158054 m/s"; table "No windows returned for this request."; no error, banner hidden |
| 5 | Weather badge: probability, horizon label, skill curve, all live | PASS after fix | `#weather-launch-indicator`, `src/screens/weather.js:89`; `#weather-skill-curve-host`, `src/screens/weather.js:92`; request built in `src/app.js:344` (`readSkill`) | `GET /v1/weather/probability?date=2026-10-04&site=canso -> 200`: 60.8%, FORECAST, ensemble 82; `GET /v1/validation/skill?period_start=2026-04-02&period_end=2026-09-27 -> 200`, 10 points drawn; banner hidden |
| 6 | Analysis view from `/v1/validation/skill` and `/v1/citation` | PASS after fix | `#analysis-skill-rows`, `src/screens/analysis.js:312`; `#analysis-reliability-host`, `src/screens/analysis.js:338`; `#analysis-provenance-body` and `#analysis-config-hash`, `src/screens/analysis.js:172`; request in `src/app.js:215` (`readCitation`) | skill table 10 rows from the live response; reliability diagram drawn, 5 bins; `GET /v1/citation?id=run_20261004_c70d343fe413 -> 200`; constants origin "citation"; config hash ce4fb517...0d4a3a shown |
| 7 | CSV download: file rows equal table rows | PASS | `#download-window-csv`, `src/screens/analysis.js:114`; `src/export.js:41` (`renderedTableCsv`) | file `canso-windows-run_20261004_c70d343fe413.csv` downloaded by Chrome: 10 data rows, 10 table rows |
| 8 | Row select: trajectory on the map, southbound, inside the corridor | **FAIL, backend** | `#trajectory-map`, `#corridor-check`, `src/screens/trajectory.js:309` (`renderGuard`); `src/geo.js:272` (`corridorCheck`) | the ephemeris of the selected row is not an ascent from the site; see "Item 8" below. The page now refuses the track instead of calling it inside the corridor |
| 9 | Viewing map: a centre with elevation and sunlit or dark status | **FAIL, backend** | `#viewing-rows`, `src/screens/viewing.js:34` | 7 centres drawn, each with an elevation and an illumination status, but every peak elevation is -74 to -77 deg: the numbers are computed from the ephemeris of item 8 |
| 10 | Offline: API stopped, reload, fixtures, banner, countdown | PASS | `#mode-banner`, `src/app.js:49` (`renderBanner`); `src/app.js:186` (`switchToOffline`) | `POST /v1/windows` refused (connection refused); banner "OFFLINE PRECOMPUTED DATA ... source windows.json, site.json, ephemeris.json, weather.json, skill.json"; 3 rows; countdown 1d 00:02:21 then 1d 00:02:19; all five fixtures read; every screen rendered; no page error |
| 11 | No ghost writes | PASS after fix | whole page | 10 rows by 7 columns equal to `POST /v1/windows`; weather badge equal to `GET /v1/weather/probability`; skill table equal to `GET /v1/validation/skill`; constants equal to `GET /v1/citation`; see "Item 11" below |

Suites after the fixes: `vitest run` 81 passed (10 files); `pytest -q` 987 passed, 4 skipped, the same as before the change, since no file outside `frontend/` was touched.

## What failed in the frontend and was fixed here

Each has a regression test in `tests/browserWalk.test.js`, written before the fix and seen to fail.

1. **Items 5 and 6: the skill request was refused and switched the page to offline.** `GET /v1/validation/skill`
   was sent without a period; the service answers 422 (`/period_start: Field required`). The page then read
   `skill.json` and showed the offline banner on every row selection. Now `src/app.js` `readSkill` asks for the
   verification period of the recorded hindcast, read from the skill fixture, so no date is typed into the page.
   The analysis note states the request and whether the answer was live.
2. **Item 6: `/v1/citation` was never requested**, and the page labelled `constants_block.citation_id` "config
   hash". Now `src/app.js` `readCitation` reads the record of each live run; the analysis screen shows its
   `config_hash`, constants and sources, and says so. A failed or foreign answer is stated and nothing is
   substituted. In offline mode no citation is asked and no hash is shown.
3. **Item 3: the honesty panel said "the window list is empty"** for a corridor-blocked target whose ten rows
   were in the table, and "not computable" for a null plane change. It now states the number of rows and the
   constraint that stopped them, and "null in this response".
4. **Item 8: the corridor guard was wrong in both directions.** It accepted a track 16,812 km from the site at
   liftoff ("every sample lies inside the corridor"), and in offline mode it rejected the fixture's own ascent
   (the pad sample at 0.0 km counted as a violation, and the two orbits after injection were checked against a
   launch corridor). `src/geo.js` `corridorCheck` now checks the ascent of the selected row only, treats a sample
   on the pad as inside, and refuses a track that is not at the site at the liftoff instant. The pad tolerance is
   `TRACK_START_TOLERANCE_KM = 5` in `src/config.js`, flagged ASSUMPTION on the page.
5. **Item 2: the countdown froze after a liftoff had passed.** The interval was stopped at the liftoff instant and
   never restarted when a later target arrived, so the readout stayed on its first value. Found by reading the
   code during the walk and confirmed by a failing test with a simulated clock; `src/countdown.js` restarts it.
6. **Item 11: a statement nothing produced.** The vehicle duration note said the engine's vehicle file "does not
   exist on this branch". It exists. The note now reads the `t_to_inj_s` flag and source from `vehicle_rows` of
   the citation record.
7. **Console error on every load:** the browser asked the static server for `/favicon.ico` (404). `index.html`
   declares an empty icon.
8. **Control sweep: the LTAN field posted a time that does not exist.** `25:99` passed the page's check and was
   sent; the service answered 200. `src/request.js` now accepts 00:00 to 23:59 only and shows the reason.
9. **Control sweep: with the weather layer switched off the table showed "100.0%, CLIMATOLOGY"** and nothing said
   that weather was excluded. The table subtitle now states it, and that the label is the neutral value of the
   response, not a climatological probability.

Three existing tests counted or parsed every `fetch` call and so saw the new `GET /v1/citation`. They now count
and parse the `POST /v1/windows` calls, which is what they assert about (`tests/helpers.js` `windowsPosts`). No
assertion was removed.

## Control sweep

The eleven items do not touch every control, and the issue names dead controls and ignored parameters as the
risk. `tools/browser_controls.mjs` changes each control in the live page and compares the request and the answer.

| Control | What was done | Request sent | What the live service answered | Result |
|---|---|---|---|---|
| `#target-type` | POLAR | `{"type":"POLAR","raan_deg":null}` | 10 rows, reached inclination 87.9 | honoured |
| `#target-type`, `#target-altitude-km` | CUSTOM with no altitude | none | input error "h_t_km (target altitude in km) is required" | refused on the page |
| `#inclination-deg`, `#target-altitude-km` | 97.5 deg, 600 km | `{"type":"CUSTOM","h_t_km":600,"i_t_deg":97.5,"raan_deg":null}` | 10 rows, reached inclination 97.50 | honoured |
| `#raan-deg` | 120, then 200 | `raan_deg: 120`, then `200` | rows at RAAN 120.4 to 124.7; first liftoff 10:42:34Z against 05:03:46Z at 200 | honoured |
| `#ltan-hours` | 06:00 | `ltan_hours: "06:00"` | first liftoff 09:19:46Z against 02:55:51Z at 10:30 | honoured |
| `#ltan-hours` | 25:99 | none, after fix 8 | input error | refused on the page |
| `#plane-mode` | RAAN on the SSO preset | `raan_deg` in place of `ltan_hours` | 200 | honoured |
| `#include-weather` | unchecked | `include_weather: false` | weather factor 1, `forecast_issue_time` null | honoured; note added by fix 9 |
| `#date-start`, `#date-end` | item 3 | the range | rows of the range | honoured |
| `#corridor-a-min-deg`, `#corridor-a-max-deg` | item 3 | the override | `reachable: false`, rows with `hazard_area` | honoured with both bounds; one bound is B2 |
| `#site`, `#vehicle-profile` | one option each: canso, cyclone4m | | | nothing to switch |
| Window row | click, and keyboard focus plus Enter | the four reads of a row | | selected, `data-selected="true"` |
| `#download-window-csv` | item 7 | | 10 rows, 10 on the page | equal |
| `#download-skill-csv` | click | | 10 data rows, 10 on the page | equal |
| `#download-reliability-csv` | click | | 5 data rows, 5 on the page | equal |
| `#download-response-json` | click | | the live response, 10 windows, `engine-0.1.0` | equal |
| Fixture links | fetched | | `windows.json`, `weather.json`, `skill.json`, `site.json`, `ephemeris.json`: 200 | reachable |

No control is dead and no parameter is ignored by the service. No page error and no non-200 answer in the sweep.

## Item 3 in detail

With the live engine a reachable target has two plane crossings a day, so `reachable: true` with an empty list
cannot be forced by a date range. The three empty-result paths that exist were walked:

- Past range 2026-01-05 to 2026-01-06: 4 rows returned and shown; countdown "No window in range", reason "All 2
  returned windows have a liftoff instant earlier than the current clock."
- Corridor override 120 to 150: `reachable: false`, 10 rows, all rejected; countdown "No window in range", reason
  "Every returned window was rejected by the hazard screen."; honesty panel as fixed above.
- `reachable: true, windows: []`: the only synthetic step of the walk. The live response body was returned to
  the page with its rows removed. Table: "No windows returned for this request."; countdown "No window in range",
  reason "No crossing of the target plane in the requested date range within the RAAN tolerance."

No page error in any of the three.

## Failures whose cause is in the backend

Not fixed here, as the issue requires. Each is a transcript for the owning issue.

### B1. The ephemeris of a window row is not the ascent of that row (items 8 and 9). Owner: #4 API, #2 ENGINE

```
GET /v1/orbits/sso981/ephemeris?start=2026-10-04T02:55:51Z&end=2026-10-04T03:04:51Z&step_s=300 -> 200
{"orbit_id":"sso981","frame":"ECEF","points":[
  {"t_utc":"2026-10-04T02:55:51Z","lat_deg":-68.238589,"lon_deg":84.408706,"alt_km":674},
  {"t_utc":"2026-10-04T03:00:51Z","lat_deg":-50.750506,"lon_deg":101.479764,"alt_km":674}],
 "ground_track_valid":true, ...}
```

The row is `t_liftoff_utc 2026-10-04T02:55:51Z`, `t_injection_utc 2026-10-04T03:04:51Z` from Canso (45.3 N,
61.0 W). At the liftoff instant the answer places the vehicle at 68.2 S, 84.4 E, 16,812 km from the site, at
orbit altitude, moving north. The same holds for the other presets at 2026-10-05T02:55:33Z: `sso981` first point
18.97 N, 36.11 W; `polar879` 59.97 N, 74.72 W; `leo45` 37.45 N, 50.88 E, each at constant orbit altitude.
`backend.engine` exports no `ephemeris` function, so the API serves its recorded orbit segment, which is not
phased to the row. Needed: an ephemeris that starts on the pad at liftoff and reaches the injection point at
injection, as the offline fixture `ephemeris.json` already does.

Consequence on the page: the trajectory screen states "TRACK REJECTED by the UI: the ground track is 16811.9 km
from the site at the liftoff instant", and the viewing table shows every centre 74 to 77 deg below the horizon.

### B2. A corridor override with one bound returns HTTP 500. Owner: #4 API, #2 ENGINE

```
POST /v1/windows
{"target":{"type":"SSO","ltan_hours":"10:30"},"site":"canso","date_range":{"start":"2026-10-04","end":"2026-10-08"},
 "vehicle_profile_id":"cyclone4m","include_weather":true,"corridor":{"A_min_deg":120}}
-> 500 {"detail":"the service failed to answer this request; see the service log","error":"internal_error","exception":"ValueError"}
service log: backend/engine/reachability.py:36 ValueError: corridor requires numeric A_min_deg and A_max_deg
```

The frozen request schema allows either bound alone (both are optional and nullable). The page sends one bound
while the user is typing the second, the 500 carries no CORS header, the browser reports a CORS failure, and the
page switches to offline until the second bound is entered. The offline stub merges a partial override with the
site corridor; the live path does not.

### B3. Every row carries the weather of the first day of the range. Owner: #4 API

```
POST /v1/windows, date_range 2026-10-04 to 2026-10-08: p_success_components.weather of the usable rows
  2026-10-04T02:55:51Z 0.6078   2026-10-05T02:55:33Z 0.6078   2026-10-06T02:55:15Z 0.6078
  2026-10-07T02:54:57Z 0.6078   2026-10-08T02:54:40Z 0.6078      (all FORECAST, issued 2026-10-03T18:00:00Z)
GET /v1/weather/probability?date=<d>&site=canso
  2026-10-04 0.6078   2026-10-05 0.0   2026-10-06 0.6078   2026-10-07 0.9804   2026-10-08 0.549
```

The page prints what the response holds, so the `p_success` column is not date-resolved. Selecting a row shows
the correct per-date value in the weather panel, beside the row's own value, which then disagree.

### B4. The corridor the service reports is not the corridor the engine applies. Owner: #4 API, #2 ENGINE

`GET /v1/site` and `provenance_block.corridor` of every window response say `A_min_deg 90, A_max_deg 200, flag
ASSUMPTION`. `backend/engine/data/site_canso.json` on `main` holds `A_min_deg 115, A_max_deg 195`, flag DERIVED.
The trajectory screen draws its corridor wedge and runs its guard from `GET /v1/site`, so it shows 90 to 200.

### B5. Smaller findings

- `POST /v1/windows` with `"ltan_hours": "25:99"` answers 200 with windows. The page no longer sends it, but the
  service accepts a time that does not exist. Owner: #2, #4.
- With `include_weather: false` the response labels every row `horizon_label: "CLIMATOLOGY"` with weather factor
  1.0. The frozen schema needs a label; the page now says what it means. Owner: #4, for the choice of label.
- `GET /v1/validation/skill` without a period answers 422 with `"detail":"the request body could not be read as a
  JSON object","schema_name":"windows_request"`. The request is a GET with a missing query parameter. Owner: #4.
- The service offers no way to learn which verification period the hindcast supports; the page takes it from the
  skill fixture. A default period when none is given would remove that dependency. Owner: #4, #3.
- `provenance_block.row_flags` of a window response lists site and corridor rows only. The vehicle rows, with the
  `t_to_inj_s` flag, are in `GET /v1/citation` only, so the form hint under the vehicle selector still says that
  the response declares no flag. Owner: #4.
- The engine's vehicle file declares a hazard footprint (`hazard_footprint.cross_range_km`, DERIVED), but no
  endpoint returns its value, so the hazard buffer of the trajectory screen stays undrawn. Owner: #4, #2.

## Item 11: values on the page that no response produced

Every number in the table of results was compared with the response it is said to come from and found equal. The
values below are shown by the page and come from `src/config.js`, not from a computation of the service. Each is
already labelled on the page; they are listed for W4 as the issue asks, and none was changed silently.

| Value | Where | Label on the page |
|---|---|---|
| Weather band thresholds 0.70 and 0.40 | `src/config.js:90` `WEATHER_THRESHOLDS` | "Thresholds ASSUMPTION ... the defaults spec V.3 states" |
| Elevation mask 10 deg | `src/config.js:105` `ELEVATION_MASK_DEG` | "ASSUMPTION ... the default of spec V.4" |
| Pad tolerance 5 km (new) | `src/config.js:128` `TRACK_START_TOLERANCE_KM` | "ASSUMPTION, src/config.js TRACK_START_TOLERANCE_KM" |
| Earth radius 6378137 m fallback | `src/config.js:140` `EARTH_RADIUS_M` | named as the fallback when the ephemeris response has no `R_e` |
| Seven population centres | `src/data/centres.json` | "a repository file" |
| Hazard buffer half width | `src/config.js:111` `VEHICLE_FOOTPRINTS`, null for cyclone4m | "The hazard buffer is not drawn ... no value is invented in the browser" |

## Coordination

- #24 must merge first: without it the live page shows the offline banner on every screen.
- #26 (researcher layer) adds controls for the skill period and provenance. This branch wires the two requests
  those controls will drive (`readSkill`, `readCitation`). New controls from #26 have to pass this walk again;
  `tools/browser_walk.mjs` is the way to run it.
