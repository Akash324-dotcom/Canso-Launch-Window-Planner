# DONE

What this branch ships, and what is known unfinished. Gate G4 of issue 5 is the acceptance point; `REQUIREMENTS_MAP.md` maps every slide requirement to a component and a test, and `docs/log/frontend.md` carries the commands and their observed output.

## Shipped

| Item | Where | Test |
|---|---|---|
| Screen 1, window engine: orbit selector with the slide inclinations, site, date range, vehicle profile, corridor override, the spec V.1 table, the honesty panel, the constants and provenance footer | `src/screens/windowEngine.js`, `src/request.js`, `src/selectors.js` | `tests/windowEngine.test.js`, 8 cases |
| The countdown: engine driven from `t_liftoff_utc`, dual UTC and Atlantic display, `No window in range` with the engine reason, stop at liftoff, survival of an outage | `src/countdown.js` | `tests/countdown.test.js`, 6 cases |
| The API client and the state machine: one POST per input change, one response object for the table and the countdown, timeout, HTTP error, offline switch | `src/api.js`, `src/app.js`, `src/store.js` | `tests/api.test.js`, 8 cases |
| Screen 2, trajectory: corridor polygon, ground track per row, hazard buffer, site marker, population centres, corridor guard, Leaflet from `node_modules` | `src/screens/trajectory.js`, `src/geo.js`, `src/mapLeaflet.js` | `tests/trajectory.test.js`, 7 cases |
| Screen 3, weather panel: Green, Yellow and Red from configured thresholds with the probability, the horizon badge and the issue time beside the colour, the hindcast skill curve, the per-criterion breakdown with its flags, the grey state | `src/screens/weather.js`, `src/weatherBands.js`, `src/svgChart.js` | `tests/weatherPanel.test.js`, 6 cases |
| Screen 4, viewing map: max elevation per population centre over the ascent of the selected row, the elevation mask, the ranking and the best view, the illumination test, Leaflet circles, the elevation chart | `src/screens/viewing.js`, `src/viewing.js`, `src/solar.js` | `tests/viewing.test.js`, 12 cases |
| Screen 5, scientific analysis: Brier skill table and chart, reliability diagram, ROC points, vehicle duration per row, constants with sources, criteria version, config hash, provenance with every declared source file, CSV and JSON downloads, fixture links, claim status | `src/screens/analysis.js`, `src/export.js` | `tests/analysis.test.js`, 6 cases |
| The offline floor: five fixtures shipped, the `offline_precomputed` banner, one renderer for both sources | `src/fixtures.js`, `src/app.js`, `backend/fixtures/*.json` | `tests/offline.test.js`, 2 cases |
| The fixture generator, standard library only, with a schema subset check that is proved against every frozen good and bad example | `tools/make_fixtures.py` | `tests/offline.test.js` reads the regenerated files; the schema check runs in the script and the contract suite passes on the same files |
| The slide text verbatim, and the requirements map | `SLIDE.md`, `REQUIREMENTS_MAP.md` | none, these are documents |

Command and result:

```text
$ cd frontend && npx vitest run
```

```text
 Test Files  9 passed (9)
      Tests  57 passed (57)
```

```text
$ /Users/rafathossain/MDA_Mission_Accepted_Hackathon/.venv/bin/python -m pytest tests/contract -q
```

```text
70 passed in 0.08s
```

## Known unfinished

1. **Expected delay cost, the slide line "a missed window can cost millions", is not implemented.** Spec II.9 (iv) and VI.3 place the cost of a delay in the decision layer, which is ENGINE's, and no field of the frozen `windows_response` schema carries it. Nothing is invented in the browser. Listed as NOT DONE in `REQUIREMENTS_MAP.md`.
2. **The 3D globe is cut.** Spec V.2 makes it optional and says to cut it before any 2D feature. Screen 2 is the 2D Leaflet map only.
3. **No tile layer on either map.** The demo runs with the network off, so no tile request is made. Adding one is a single line in `src/mapLeaflet.js` when a network is available.
4. **The hazard buffer is not drawn by default.** `hazard_half_width_km` is `null` in `src/config.js` because the value is ENGINE vehicle data at `backend/engine/data/vehicles/cyclone4m.json`, which does not exist on this branch. The buffer renders and is tested through an injected width, and the screen states the gap.
5. **The vehicle `T_to_inj` flag is named, not shown.** Same missing owner file. The screen reads `provenance_block.row_flags` and prints the owner when the response declares no flag.
6. **Population centre coordinates are ASSUMPTION.** No gazetteer was reachable offline, so every row of `src/data/centres.json` carries its own flag.
7. **The solar expression is cited from memory and flagged.** The formula source string names the Astronomical Almanac and the NOAA Solar Calculator and states that neither citation was resolved from this branch. The expression is printed as `ASSUMPTION`.
8. **The ephemeris id of a CUSTOM target is not requested.** Spec IV.2 says the engine creates one implicitly, but no field of the frozen `windows_response` schema names it, so the screen asks for no track and names the gap. This needs a contract change, not a frontend guess.
9. **The corridor bounds in the fixture set conflict, as recorded in `README.md`.** `site.json` declares 100 to 140 `VERIFIED` while `windows.json` and spec II.3 declare 90 to 200 `ASSUMPTION`, and the 100 to 140 bounds cannot admit the southbound SSO azimuth of 191.6 deg. The corridor guard therefore flags the correct southbound fixture track. The bounds are ENGINE data in `backend/engine/data/site_canso.json`, absent on this branch, so no value was invented and no fixture outside the two named files was edited.
10. **The ephemeris plane RAAN differs from the declared `raan_deg`.** The plane is solved for a southbound site passage at the first liftoff instant, which fixes the RAAN at that instant; the declared `raan_deg` of the stub run cannot hold at the same time. Details in `README.md`.
11. **`frontend/progress.md` is not written.** The workflow doc asks the developer to maintain it; this session was instructed to write only the issue deliverables under `frontend/` and the log in `docs/log/frontend.md`, and the log carries the same record.
12. **`weather.json` and `skill.json` were not regenerated.** The regeneration instruction for this session named `windows.json` and `ephemeris.json` only, and the skill series is specified to be WEATHER's own hindcast output rather than a frontend fabrication. Both files are carried over untouched, validate against the frozen schemas and are rendered offline.