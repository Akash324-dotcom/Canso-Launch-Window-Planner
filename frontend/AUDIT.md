# Frontend audit of the inherited prototype

Source audited: `Canso Launch Prototype.html` at the repository root, 1041 lines, single file, never edited and never deleted by this refactor. Everything below is a disposition for the modular application in `frontend/src/`.

Verdicts: **KEEP** the idea and the structure, carried into the new module. **CHANGE** the idea survives but the implementation is replaced, with the reason stated. **DROP** it does not ship, with the reason stated.

## 0. Test harness decision (required by the issue before any code)

| Decision | Value |
|---|---|
| Harness | vitest 5 with the jsdom environment, run from `frontend/` with `npx vitest run` |
| Why jsdom and not Playwright | No browser binary and no network are available on this branch, and the whole of F0 to F2 is DOM construction plus one POST per input change, which jsdom asserts directly |
| Why not a framework | The issue forbids a rewrite unless justified in this audit. Nothing here justifies it: the app is one response object and a dozen renderers, so plain ES modules with no build step keep the judging path free of bundler failure, which is the reason spec V.7 gives for the static stack |
| Where the tests live | `frontend/tests/`, one file per task: `smoke.test.js` (F0), `api.test.js` (F1), `countdown.test.js` and `windowEngine.test.js` (F2) |
| Mock payloads | The frozen examples in `tests/contract/examples/good/`, because `backend/fixtures/` does not exist on this branch and the integration contract gives API ownership of that directory |
| Why the prototype is refactored rather than reformatted | It computes launch windows in the browser (`findWindows`), which the contract makes the engine's job, and it has no transport layer, so there is nothing to keep behind an API client |

## 1. Panels and regions

| Prototype element | Verdict | One line |
|---|---|---|
| `#stage` WebGL canvas | CHANGE | The 3D globe is optional per spec V.2 and is deferred to F3 behind the 2D Leaflet map, which is the primary. |
| `#labels` projected labels | CHANGE | Belongs to the 3D scene, so it moves to F3 with the scene. |
| `#tip` hover tooltip | CHANGE | Reads 3D hover state, so it moves to F3. |
| Header HUD `.hud.top` | KEEP | The wordmark and audience framing stay, and the coordinate line moves to `GET /v1/site` so it stops being a hard-coded literal. |
| `#mPublic` and `#mPlanner` audience toggle | CHANGE | Planner and public both ship, but as routes per spec V.6 and V.8 rather than as a CSS class that hides panels, and the analysis view arrives in F6. |
| `#cUtc` and `#cLocal` clock toggle | DROP | Spec V.1 requires the UTC and the Atlantic instant always, so a toggle that hides one of them is replaced by the mandatory dual display in F2. |
| `#clkL` and `#clkU` wall clock | DROP | A live wall clock is traceable to no response object, which spec V.7 forbids on screen. |
| `#mockBanner` mock data banner | CHANGE | Becomes the `offline_precomputed` banner of spec V.5, which names the engine run id. |
| `#changed` what changed banner | CHANGE | Its content survives as a comparison of two responses and lands with the analysis view in F6, because it is not a slide requirement. |
| `#card` next launch opportunity card | KEEP | The card is the right container for the countdown and becomes the countdown panel above the table, per spec V.1. |
| `#cd`, `#cdPre`, `#cdUnits` countdown readout | KEEP | The dual readout is exactly what spec V.1 asks for; only the target changes from window close to `t_liftoff_utc` of the earliest reachable window. |
| `#when` and `#whenU` absolute times | KEEP | The UTC plus Atlantic pair is kept and now comes from `Intl` with `timeZone: America/Halifax`. |
| `#cardWx` weather chip | CHANGE | A coloured chip alone fails review; F4 adds the probability number, the `horizon_label` badge and `forecast_issue_time` beside it. |
| `#best` best conditions this week | CHANGE | It is the decision layer, which spec II.9 marks SKETCHED, so the ranking moves to the analysis view in F6 instead of claiming a verdict on the public screen. |
| `#why` why this time reveal | CHANGE | The scripted three-step camera reveal becomes the engine reason text that spec V.1 requires next to an empty window list. |
| `#watch` where can I see it | CHANGE | Becomes the entry point to the viewing map in F5. |
| `#cardfoot` disclaimers | KEEP | The wording that this is a computed opportunity and not a go or no-go decision is required by the honesty rules and is kept. |
| `#src` source line | CHANGE | It names the mode, the `citation_id` and the `engine_version` of the response instead of naming a file that does not exist. |
| `#dials` circular dials | CHANGE | Three of the four dials duplicate table columns and are dropped; the T-minus dial becomes the countdown block. |
| `#dials` spin help dial | DROP | It rendered a `v_orb` and `v_rot` velocity bonus that is not a field of any frozen schema, so it cannot be shown. |
| `#towns` viewing panel | CHANGE | The panel is the right feature for F5, but its rows were hard-coded numbers and must come from the ephemeris. |
| `#townsB` hard-coded centre rows | DROP | Seven literal rows of elevation and bearing are not traceable to a response and are replaced by computed geometry in F5. |
| `#rail` input rail | CHANGE | The five fieldsets become the Screen 1 form of spec V.1 with contract field names. |
| `#preset` orbit options | CHANGE | Replaced by LEO, POLAR, SSO and CUSTOM with the slide inclinations 45.1, 87.9 and 98.1 pre-filled. |
| `#preset` join RCM plane 97.74 option | DROP | A specific mission plane is not a slide requirement and becomes a CUSTOM entry. |
| `#preset` too low 30 deg option | DROP | The unreachable verdict is now an engine answer shown in the honesty panel, so a scripted failure example is redundant. |
| `#inc` inclination | KEEP | Kept as the pre-filled inclination that switches the request to CUSTOM when edited. |
| `#alt` altitude | CHANGE | Becomes `h_t_km`, optional for presets and required for CUSTOM. |
| `#pmode`, `#ltan`, `#raan` plane selectors | KEEP | `ltan_hours` and `raan_deg` are contract fields and are kept, with the LTAN field hidden when the plane is set by RAAN. |
| `#start` and `#days` time span | CHANGE | Replaced by an explicit `date_range` start and end, which is what the frozen request schema declares. |
| `#asc` climb to orbit minutes | DROP | `T_to_inj` belongs to the ENGINE vehicle profile file, so a planner input that invents it is a correctness hazard. |
| `#down` downrange kilometres | DROP | Downrange is footprint data in the vehicle profile and is not a request field. |
| `#yaw` steering budget | DROP | The steering budget is engine data that widens `window_width_s`; exposing it as an input would let a user fake a window. |
| `#wxon` weather toggle | KEEP | It is `include_weather`, a real request field, and it is kept with the contract name shown. |
| `#run` button and the 500 ms debounce | CHANGE | Spec V.7 requires one POST per input change, so the form commits on change with no debounce and no button. |
| `#ex30` and `#exPolar` guided example buttons | DROP | Buttons that overwrite the inputs to stage a demo are removed; the same cases are reachable from the orbit selector. |
| `.fs.sim` what is simulated panel | KEEP | The disclosure that the ascent path is drawn rather than simulated moves into the README and the provenance footer. |
| `#rec` recommendation panel | CHANGE | The ranking moves to the analysis view in F6, because spec II.9 marks the opportunity-process decision layer SKETCHED. |
| `#right` and `#ev1` evidence panel | DROP | Two hard-coded third-party launch facts are not traceable to a response and are replaced by the constants and provenance footer. |
| `#tablep` and `#rows` window table | CHANGE | The eight columns of spec V.1 replace the prototype columns, and every cell comes from the response. |
| `#unreach` unreachable panel | CHANGE | Becomes the honesty panel of spec V.1: `reachable: false`, the computed `plane_change_dv_ms` and the constants. |
| `#fix45` and `#backSso` fix buttons | DROP | Hard-coded inclination fixups replaced by the honesty panel text. |
| `#caption` scripted captions | DROP | Captions that narrate a camera animation are not a Track 1 output. |
| `#scrub` time scrubber and slider | DROP | The scrubber drives a 3D scene and has no contract field; the honest part of it, the daily clock-time drift, becomes table-derived text in F6. |
| `#play`, `#nowB`, `#nextDay` and the speed buttons | DROP | Playback controls for the 3D globe, deferred with the scene rather than promised. |

## 2. Functions

| Function | Verdict | One line |
|---|---|---|
| `findWindows` | DROP | The in-browser window solver is the ENGINE job; the app now posts the request and reads the answer. |
| `compute` | DROP | The local solver wrapper disappears with `findWindows`. |
| `fromMock` | CHANGE | Becomes the fixture loader, which serves the same renderer from `backend/fixtures/windows.json`. |
| `synthTrack` | DROP | Track synthesis from a drawn profile is replaced by the ephemeris endpoint in F3. |
| `PROFILE` | DROP | A derived ascent shape is not a contract field. |
| `dest` | CHANGE | Survives as the great-circle destination helper used by F3 for the corridor polygon and F5 for the track. |
| `gcAng` | CHANGE | The great-circle angle helper is kept for the F5 elevation geometry. |
| `gmst` | DROP | Greenwich mean sidereal time is engine work; the response prints `gmst_model` and the constants instead. |
| `sunRA` | DROP | The Sun right ascension approximation exists only to solve for a node time locally. |
| `normalV` and `siteV` | DROP | Frame vectors for the local solver. |
| `dot3` and `cross3` | DROP | Vector helpers for the local solver. |
| `readInputs` | CHANGE | Kept as the screen `readInputs()` that feeds `buildWindowsRequest`, which validates against the frozen request schema. |
| `syncFields` and `syncFieldsMode` | CHANGE | Merged into `syncPlaneFields` in the screen module. |
| `applyPreset` | CHANGE | Kept, but its presets are the three slide orbit classes plus CUSTOM. |
| `run` | CHANGE | Becomes the single `dispatch()` in `app.js`: build the request, POST once, keep the response in the store. |
| `renderAll` | CHANGE | Replaced by store subscriptions: every renderer subscribes and no renderer calls another. |
| `renderTable` | CHANGE | Same name, new columns and new data source. |
| `renderCard` | CHANGE | Split into the countdown component and the honesty panel. |
| `tick` | CHANGE | Kept as the countdown ticker, now computed from `Date.now()` against `t_liftoff_utc` only. |
| `renderDials` | DROP | Replaced by the table columns and the countdown. |
| `renderRec` | CHANGE | Deferred to F6. |
| `renderEvidence` | DROP | It compared against hard-coded 2019 and 2022 launch facts. |
| `highlightRow` | CHANGE | Row selection becomes the per-row track highlight of F3, keyed to the window row index. |
| `nextUsable` | CHANGE | Becomes `countdownTarget` in `selectors.js`, with the hazard rejection rule from the contract fields. |
| `recommend` | CHANGE | Deferred to F6 as the decision layer. |
| `driftCaption` | CHANGE | Deferred to F6 as table-derived text. |
| `caption` | DROP | Scripted captions. |
| `onCrossing` | CHANGE | The crossing notification becomes a store update when a window instant passes, in F3. |
| `setMode` | CHANGE | Planner and public become routes in F6. |
| `selectWindow` | CHANGE | Selecting a row becomes the F3 ephemeris fetch keyed to the row index. |
| `tweenSim` | DROP | Scene animation tween. |
| `setPlayIcon`, `setSim`, `setRange`, `drawTicks` | DROP | Playback controls for the 3D globe. |
| `buildCrossings`, `strike`, `buildGap`, `buildGapLazy` | CHANGE | The crossing sprites and the unreachable wedge move to F3 as annotations on the map. |
| `drawArc`, `setArrow`, `trackPts`, `buildWedge` | CHANGE | The ascent arc is replaced by the ephemeris ground track in F3. |
| `layout`, `fitDistance`, `lookDir`, `flyTo` | DROP | Camera framing for the 3D scene. |
| `project`, `occluded`, `place`, `mkLabel`, `pick`, `showTip` | DROP | 3D picking and projection; replaced by Leaflet interaction in F3. |
| `frame` | DROP | The requestAnimationFrame render loop of the 3D scene. |
| `line`, `setLine`, `spr`, `tex`, `pxScale`, `basis`, `orientHoop` | DROP | three.js line, sprite and orientation helpers. |
| `intro`, `end` | DROP | The 3 second camera intro, which also blocked first paint. |

## 3. Data fields

| Field | Verdict | One line |
|---|---|---|
| `DATA.land` | CHANGE | The base64 land mask belongs to the 3D globe in F3, not to screen 1. |
| `DATA.mock.windows[].t` | CHANGE | Becomes `t_liftoff_utc`, ISO-8601 with a Z suffix, parsed with `Date`. |
| `DATA.mock.windows[].o` and `.c` | CHANGE | Become `window_width_s` plus `t_liftoff_utc`, since the contract states no separate open and close instants. |
| `DATA.mock.windows[].i` | CHANGE | Becomes `t_injection_utc`. |
| `DATA.mock.windows[].p` northbound or southbound | CHANGE | Replaced by `azimuth_deg`, `azimuth_compass_deg` and the `screens.hazard` verdict, and the two northbound mock rows are the bug the hazard guard now blocks. |
| `DATA.mock.windows[].a` | CHANGE | Becomes `azimuth_deg`. |
| `DATA.mock.windows[].ok` | CHANGE | Replaced by `screens.hazard` and `constraint_fired`, which is where the contract puts the hazard verdict. |
| `DATA.mock.windows[].e` velocity bonus | DROP | Not a field of any frozen schema. |
| `DATA.mock.windows[].r` | CHANGE | Becomes `raan_deg`. |
| `DATA.mock.windows[].wx.s` colour | CHANGE | Replaced by `p_success_components.weather` with thresholds in a config file, in F4. |
| `DATA.mock.windows[].wx.r` free text | CHANGE | Replaced by the per-criterion `p_violation` list with VERIFIED or PROXY flags, in F4. |
| `DATA.mock.windows[].tr` track arrays | CHANGE | Replaced by `GET /v1/orbits/{id}/ephemeris` points in F3. |
| `DATA.mock.orbit`, `.inc`, `.alt`, `.ltan` | DROP | Echoes of the request, replaced by the request the user actually made. |
| `SITE.lat`, `SITE.lon` | CHANGE | Replaced by `phi_s_deg`, `lambda_s_deg` and `h_s_m` from `GET /v1/site`. |
| `SITE.corr` corridor bounds | CHANGE | Replaced by the `corridor` object with `A_min_deg`, `A_max_deg`, `source` and `flag`, and overridable per request. |
| `VAFB` | DROP | A second hard-coded site used only for the evidence panel. |
| `COL` colour constants | KEEP | Became the CSS custom properties in `frontend/styles.css`, so the palette is still in one place. |
| `REDUCE` reduced motion flag | KEEP | Kept as the reason F3 and later skip scene animation. |
| `PRESETS` | CHANGE | Replaced by `ORBIT_PRESETS` in `src/config.js` carrying the slide inclinations. |
| `S.source` mock or engine switch | CHANGE | Replaced by the store `mode`, which is `live_engine` or `offline_precomputed`. |
| `S.windows` | CHANGE | The only window data is `engineResponse.windows`, the single object both the table and the countdown read. |
| `S.rec`, `S.sel` | CHANGE | Selection stays for F3; the recommendation moves to F6. |
| `S.inc`, `S.alt`, `S.pmode`, `S.ltan`, `S.raan`, `S.days`, `S.asc`, `S.down`, `S.yaw`, `S.wx` | CHANGE | Replaced by the request built from the form, where the vehicle fields are removed and the rest are contract names. |
| `S.nSol` and `S.x` reachability scalars | DROP | Reachability is the engine verdict, returned as `reachable` with `plane_change_dv_ms`. |
| `S.live`, `S.simT`, `S.playing`, `S.speed`, `S.range0` | DROP | Scene playback state with no contract field. |
| `findWindows` window object `t`, `gaz`, `pass`, `ok`, `boost`, `open`, `close`, `inj`, `raan` | CHANGE | Replaced one for one by the frozen `windows[]` row fields. |
| `findWindows` return `nSol`, `x`, `raanAt` | DROP | Local solver state. |
| `fromMock` window object `wx.s`, `wx.r`, `track` | CHANGE | Replaced by the fixture response, which is already contract shaped. |
| `TZ` and the `Intl` formatters | KEEP | Kept in `src/time.js`, including `America/Halifax` for ADT and AST. |
| `zone`, `utcHMS`, `utcDay`, `localMin`, `pad2` | CHANGE | Merged into the formatters of `src/time.js`, which is the single formatting module. |
| `WXW`, `WXC`, `GL`, `GLK`, `wxChip`, `rangePill` | CHANGE | Replaced by the `horizon_label` badge and the hazard screen verdict, both with their contract values. |
| `conf` confidence tiers | CHANGE | Dropped: a confidence label invented in the browser is not evidence; F4 shows the skill curve instead. |
| `esc` | DROP | Unnecessary once renderers build nodes and set `textContent`. |
| `compass` | CHANGE | Kept as a label helper for `azimuth_deg` in F3. |

## 4. What is deliberately absent from F0 to F2

Not stubbed and not promised: the trajectory map and the 3D globe (F3), the weather panel with the skill curve (F4), the viewing map (F5), the analysis view and exports (F6), and the fixture content, which API owns and which does not exist on this branch. Leaflet is present in `node_modules` and will be imported from there by F3 so the demo works offline; F0 to F2 render no map and therefore load no mapping library.