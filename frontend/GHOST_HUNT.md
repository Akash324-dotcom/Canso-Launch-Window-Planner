# Ghost hunt, issue #27: inventory after the change

Every display on `Canso Launch Prototype.html` and in `frontend/` is listed once, with where its value comes from now.
Verdicts: **LIVE** (read from a `/v1` response), **FIXTURE** (committed file in `backend/fixtures`, offline banner shown), **LOCAL** (computed in the browser from live or fixture data), **CONFIG** (a labelled constant with no backend source), **RENDER** (scene drawing only, never shown as data), **REMOVED**. There is no GHOST row.

## The prototype page

The page used to make no data request at all. It carried a mock window list and a copy of the window engine inside the file. It now owns no numbers: `frontend/src/prototypeData.js` reads the API, falls back to the fixtures, and the page only draws.

| # | Display | Before | Now |
|---|---|---|---|
| P1 | Windows, countdown, card, table, dials | embedded mock (8 invented rows) | LIVE `POST /v1/windows`, FIXTURE `windows.json` offline |
| P2 | Weather chips and reasons | typed sentences ("Ground gusts 31 kt") | LIVE `p_success_components.weather` banded with `WEATHER_THRESHOLDS`; the reason shows the probability and `horizon_label` |
| P3 | "Best conditions this week" | ranking of P2 literals | LOCAL: highest `p_success` among rows whose hazard screen passes |
| P4 | high / medium / low confidence | invented lead-time rule | REMOVED, the row shows `p_success` and `horizon_label` instead |
| P5 | Silent switch from mock to engine copy | time bomb on 7 Oct | REMOVED, no second source exists |
| P6, P7 | Footer "shared/mock_windows.json", "production calls GET /windows" | false provenance | LIVE: "POST /v1/windows, run id, engine version", or "Offline fixture windows.json" |
| P8 | "Sat 3 Oct 23:55 ADT window, southbound 193.9" | static HTML | LIVE: follows the selected row |
| P9 | Seven towns with elevations | typed in | LOCAL: `viewingReport` over the ascent ephemeris and `centres.json` (CONFIG, flagged ASSUMPTION), or the stated reason there is no report |
| P10 to P12 | "Consistent with published windows for two real launches" | one static card, one computed against a private engine copy | REWIRED to `GET /v1/validation/skill` (weather hindcast). The comparison with published launches is REMOVED because no API field can support it |
| P13 to P16 | Site 45.10 N 61.02 W, corridor 82 to 195, header, pad label | typed | LIVE `GET /v1/site` (45.30 N 61.00 W, corridor and its flag) |
| P17 | "tan 45.1 / tan i", "above 45.1" | typed latitude | LIVE: site latitude, `reachable`, `plane_change_dv_ms` |
| P18 | "LEO 45.1 (Canso minimum)", button "Set 45.2" | typed, and 45.2 does not fix it | class inclinations from `config.js` `ORBIT_PRESETS`; the button sets site latitude plus 0.5 deg and says so |
| P19 | Start "now" (read only) | dead input | a date input sent as `date_range.start` |
| P20 | Climb to orbit, Downrange | changed nothing | REMOVED. "To orbit" is `t_injection_utc - t_liftoff_utc` of the row |
| P21 | Days, steering budget, weather while on the SSO preset | dead in mock mode | every remaining input reaches the request (checked in `prototype_e2e.mjs`) |
| P22 | "Weather limits: on, generic" | changed a label only | `include_weather` of the request |
| P23 | "What is simulated" | described a non-existent feature | rewritten to name the real sources |
| P24 | Orbit label forced to "SSO 98.1" | overwrote the inputs | from the row's `reached_inclination_deg`, altitude only when known |
| P25 | Ascent arc shape | drawn from a mock profile | LIVE or FIXTURE `GET /v1/orbits/{id}/ephemeris`, drawn only when the first sample is on the pad at liftoff, otherwise the page says why not |
| P26 | Window times from the page's own engine | second copy of the engine | REMOVED |
| P27 | three.js, gsap, Google Fonts from CDNs | blank offline | VENDORED in `vendor/prototype/`, no external request |
| P28 | Earth rotation angle and Sun direction | in the page | RENDER: drives the globe lighting and rotation, not a displayed number |
| P29 | Wedge length (8 deg of arc) and hoop radius when no altitude is known | in the page | RENDER: drawing scale. The wedge azimuths are LIVE. The page says so in the "Where the numbers come from" block |

Columns that were removed because the API has no field for them: "Earth's help" (spin boost) became "Reached inc." (`reached_inclination_deg`).

## `frontend/`

| # | Display | Verdict after |
|---|---|---|
| F1, F2 | Windows table, honesty panel, request inputs | LIVE or FIXTURE (unchanged, checked: no dead input) |
| F3 | Site picker label with typed coordinates | FIXED: label is "Canso, Spaceport Nova Scotia" |
| F4 | "Every number below is rendered from one POST /v1/windows response" | FIXED: names the other endpoints |
| F5 | Analysis heading "Every number below is read from ..." | FIXED: says the ascent duration is computed in the browser |
| F6 | Corridor wedge radius 1200 km | FIXED on screen: the trajectory note says the length is drawn, not data. The constant stays (a test and the map use it) |
| F7 | Weather thresholds citing a non-existent `config/weather.json` | FIXED: provenance string says the backend has no thresholds and they live in `config.js`. Values unchanged (`weatherPanel.test.js` asserts them) |
| F8 | Elevation mask 10 deg | CONFIG, already labelled ASSUMPTION on screen |
| F9 | Population centres | CONFIG, every row flagged ASSUMPTION |
| F10 | Ground track of the selected row | LIVE, but the API serves a stand-in track (backend issue, see below). The page rejects it and says so |
| F11 to F13 | Offline banner, skill panel, weather panel | LIVE or FIXTURE |

## What the live page still shows wrongly because of the backend

These are not display ghosts. They are recorded in `frontend/BROWSER_WALK.md` (items B1 to B6).

- **Both daily crossings carry the same azimuth** (`backend/engine/engine.py`, single `azimuth_for`). On `main` the page therefore lists northbound rows as "in corridor" and usable. With the one-line fix (`reachability.northbound_partner_deg` for the ascending branch) the page shows them as "outside corridor" with `p_success` 0 and recommends the southbound row. Checked on a scratch copy of the API.
- **Ephemeris is a recorded stand-in** that does not start at the pad, so the live page draws no ascent arc and no viewing table and says why. With the offline fixture (first fixture row) both render.
- **Weather is the first day's value for every row** (B3). The chips show what the API sends.
- **Corridor**: `GET /v1/site` says 90 to 200, the engine screens with 115 to 195. The wedge on the globe uses the API value.

## Run it

```
python -m uvicorn backend.api.app:create_app --factory --port 8000
python -m http.server 5500                       # from the repository root
# open http://localhost:5500/Canso%20Launch%20Prototype.html
```

A page opened as `file://` cannot load ES modules. `?api=http://host:port/v1` points the page at another API.

## Tests

- `cd frontend && npm test` includes `tests/prototype.test.js` (data layer, request mapping, fixtures, banner, and a static check of the page for ghost strings, external URLs and missing vendor files).
- `cd frontend && npm install --no-save puppeteer-core && node tools/prototype_e2e.mjs` drives real Chrome: table rows equal API rows, no request leaves the page origin and the API, offline reload banners and renders, every input reaches the request.
