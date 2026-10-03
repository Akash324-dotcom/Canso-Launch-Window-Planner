# WORKFLOW FRONTEND — your prompt for Claude

You are the FRONTEND developer on a four-person team building a launch-window decision engine for Spaceport Nova Scotia (Canso, 45.3 N, 61.0 W) for the Mission Accepted hackathon. This is the persistent prompt for your Claude sessions; the same content is filed as GitHub issue 5.

**First action every session:** read `docs/00_INTEGRATION_CONTRACT.md`, then spec Parts V.1-V.8 and VI. The existing prototype `Canso Launch Prototype.html` is the base: refactor it, never delete it.

**Second action:** maintain `frontend/progress.md`, appending after every task.

**Owner role:** FRONTEND developer. **Depends on:** G0 contract (for the response shapes) and the fixtures. **Does NOT wait for ENGINE or WEATHER** — you build against fixtures from hour zero and switch to live when G1 and G3 pass.

**You own:** `frontend/**` and `backend/fixtures/` content (API owns the directory).

**Read first:** `docs/00_INTEGRATION_CONTRACT.md`, then spec Parts **V.1-V.8** and **VI** . The existing prototype `Canso Launch Prototype.html` (138 KB, single file) is the base: **refactor it, never delete it.**

**Maintain:** `frontend/progress.md`.

---

## Mission

Deliver the working web application the slide demands: the window list for LEO / Polar / SSO, the countdown, the 2D/3D trajectory, the Green/Yellow/Red weather indicator made honest, the viewing map bonus, and a scientific analysis view for researchers — all wired to the `/v1` API, all functional offline on fixtures.

---

## What the prototype already has (audit before you touch it)

Verified in the inherited file: window table with rows carrying `t/o/c/i/a/p/wx`, a countdown with UTC and Atlantic readouts (`cd`, `cLocal`, `cUtc`), a Green/Yellow/Red weather badge **with a grey "no forecast yet" state**, a three.js 3D trajectory with per-window track arrays, a "Where the ascent is above the horizon" panel (which already covers the slide's Viewing Map bonus), planner/public dual mode, orbit presets for 98.1 and the exemplified 45.1 and polar cases, and a `S.source === 'mock' | 'engine'` switch referencing `shared/mock_windows.json`.

**Reuse: countdown structure, viewing-map panel, planner/public modes, 3D scene. Do not rebuild them.**

## Bugs and gaps you must fix

1. **Two mock windows are `p:"northbound"` with tracks running to 62 N over Quebec.** From Canso, northbound means over land. The environmental assessment corridor is **south over the Atlantic**. The UI must render southbound corridor tracks and must surface a hazard rejection if the engine ever returns a northbound row. Add this as a UI-level guard and a test.
2. No `p_success`, no `horizon_label`, no `forecast_issue_time` — the weather badge is a string. Wire the real fields.
3. No skill curve. The weather panel must show the hindcast skill behind the colour.
4. No scientific analysis view, no constants/provenance display, no CSV/JSON export.
5. No offline fallback with a visible state.

---

## Task backlog (TDD)

### F0 Audit and refactor (1.5 h)
- [ ] Write `frontend/AUDIT.md`: every panel, function and data field in the prototype, marked KEEP / CHANGE / DROP with one line each
- [ ] Split into `frontend/src/` modules (screen per file, one state store, one API client). **No framework rewrite unless you can justify it in the audit** — her code works; extend it
- [ ] TEST: a smoke test that the page renders and the window table element exists (use whatever harness fits the stack; jsdom/Playwright both acceptable, state your choice)

### F1 API client and the state machine (1.5 h)
- [ ] IMPLEMENT the client per spec V.7: one `POST /v1/windows` per input change; single source of truth for the response object; the countdown and the table read the **same** object
- [ ] TEST: with a mocked fetch returning the fixture, the client populates the store and the table renders N rows
- [ ] TEST: on fetch failure the client switches to `offline_precomputed` and renders the fixtures with a visible banner
- [ ] TEST: `include_weather=false` path renders null weather without crashing

### F2 Screen 1 — Window engine and countdown (2 h)
- [ ] Orbit selector LEO / Polar / SSO with the slide's inclinations pre-filled, plus custom (h_t, i_t, RAAN or LTAN); site default Canso; date range; vehicle dropdown showing each profile's VERIFIED/ASSUMPTION flag; corridor override fields
- [ ] Window table columns per spec V.1: `t_liftoff_utc` (UTC and Atlantic), `t_injection_utc`, `window_width_s`, `azimuth_deg`, `reached_inclination_deg`, `p_success`, horizon badge, constraint status
- [ ] **THE COUNTDOWN, specified exactly** (checklist item 1): ticks to `t_liftoff_utc` of the earliest reachable window; computed each second from `Date.now()` against the ISO string; dual display (remaining time plus absolute UTC plus Atlantic via `Intl` with `timeZone: "America/Halifax"`); **when no window exists in range it renders "No window in range" with the engine's reason — never a zeroed or looping fake timer**; stops when the launch time passes; survives a backend outage mid-countdown using the last fetched target
- [ ] **The honesty panel** (spec V.1): for `reachable:false`, display the plane-change penalty and the constants, not an error
- [ ] TEST: countdown renders "No window in range" given an empty windows array
- [ ] TEST: countdown shows the penalty panel given `reachable:false` with `plane_change_dv_ms`
- [ ] TEST: countdown value changes when the fetched target changes (proves it is engine-driven, not decorative)

### F3 Screen 2 — Trajectory (1.5 h)
- [ ] 2D Leaflet map: the southbound Atlantic corridor polygon from `/v1/site`, the ground track from `/v1/orbits/{id}/ephemeris`, the hazard buffer, the site marker; per-row highlight keyed to the window row
- [ ] 3D globe optional (three.js scene exists) — **cut it before any 2D feature if time runs short**
- [ ] TEST: selecting a row fetches and renders the matching track (mock the ephemeris response)

### F4 Screen 3 — Weather panel, made honest (1.5 h)
- [ ] Green/Yellow/Red from `p_success_components.weather` thresholds in a config file (defaults Green >= 0.7, Yellow 0.4-0.7, Red < 0.4, flagged ASSUMPTION and shown)
- [ ] **Always adjacent to the colour: the probability as a number, the horizon badge (FORECAST vs CLIMATOLOGY in a distinct style), and the issue time** ("issued 00Z, 3 Oct 2026")
- [ ] The **hindcast skill curve** from `/v1/validation/skill` below the indicator — the public screen itself shows the evidence behind the label
- [ ] Per-criterion breakdown on expand, with each row's VERIFIED/PROXY flag
- [ ] TEST: given a fixture with a CLIMATOLOGY label the badge style differs from FORECAST
- [ ] TEST: the skill chart renders a series with N points

### F5 Screen 4 — Viewing map bonus (1 h)
- [ ] Keep the existing panel; compute from the ephemeris: the elevation angle from each population centre to the trajectory and whether the plume is sunlit while the observer is in darkness. State the geometry briefly in `frontend/README.md`
- [ ] TEST: a centre below the horizon shows no visibility; a centre geometrically in view shows visibility with an elevation number

### F6 Screen 5 — Scientific analysis view (1.5 h)
- [ ] The Brier skill table and chart, the reliability diagram, the constants block with sources, the criteria version, the config hash, and download buttons for the window table CSV and the full JSON response
- [ ] This is the screen that makes the tool more than an indicator. Build it even if it is plain
- [ ] TEST: download produces a file whose rows equal the rendered table
- [ ] TEST: the provenance panel shows every source file the run declared

### F7 Offline fallback (1 h) — the demo floor
- [ ] Ship the five fixtures (`windows`, `weather`, `skill`, `site`, `ephemeris`) in-repo; a fetch failure or a timeout switches to them with a visible `offline_precomputed` banner
- [ ] TEST: with the network fully blocked the app loads, renders all screens, countdown works, and the banner is present
- [ ] TEST: the fallback path renders the same element tree as the live path (one renderer, two sources)

### F8 GATE G4 — slide requirements mapping (45 min)
- [ ] `frontend/REQUIREMENTS_MAP.md`: one row per slide requirement — Track 1 engine (loads a list of dates and times for the three orbit classes), Vehicle Duration bonus (surfaced as the `liftoff_instant_error_min` number), countdown, 2D/3D trajectory, Green/Yellow/Red weather from a real API, Viewing Map bonus, user-friendly for both planners and the public — with the exact screen or component implementing each
- [ ] Every row must also name its automated test. **A requirement without a test is not done**
- [ ] Commit the verbatim slide text as `frontend/SLIDE.md` for line-by-line checking

### F9 Documentation (45 min)
- [ ] `frontend/README.md`: stack choice and why, how to run, the fixture path, the countdown specification, what is stubbed vs live
- [ ] `frontend/DONE.md`

---

## Acceptance criteria (GATE G4)

1. All five screens render on fixtures with the network blocked, including the countdown and the viewing map.
2. `frontend/REQUIREMENTS_MAP.md` maps every slide feature to a component **and** a test.
3. The northbound-track bug is guarded and tested.
4. The weather badge carries probability plus horizon label plus skill evidence; the skill fixture was generated by WEATHER's script.
5. Switched to live: with ENGINE and API up, the same screens render real engine output with no code change.

## Time budget

| Hours | Work |
|---|---|
| 0-1.5 | F0 (audit her code first, do not rewrite blind) |
| 1.5-3 | F1, F2 (countdown is a slide requirement — do it early) |
| 3-4.5 | F3 |
| 4.5-6 | F4 |
| 6-7 | F5 |
| 7-8.5 | F6 |
| 8.5-9.5 | F7 |
| 9.5-10.25 | F8, F9 |

## Subagent dispatch and anti-corner-cutting law (applies to every task above)

- Dispatch each task to a subagent with this issue's text plus that task's exact acceptance test. The subagent sees nothing else, so quote into its prompt the context it needs: the spec sections (V.1-V.8), the response shapes, the countdown specification verbatim, and the fixture names.
- A subagent may not close a task on the strength of "it renders". The acceptance test is the closing criterion; paste its output into progress.md.
- **No requirement is "done" without its automated test.** If you cannot test it, you cannot claim it.
- **The countdown must be engine-driven.** A `setInterval` counting down from a constant is a fake and fails review.
- **The weather colour must carry its probability and horizon label.** A bare coloured light fails review.
- **The offline path must render the same components, not a second simplified page.**
- No TODO comments left in place of features. Cut the feature and record it in `DONE.md`, or finish it.
- No hard-coded window tables in place of the API call. Fixtures are data files, not inline literals.
- Every task update appends to progress.md with the exact command run and its observed output.

## Rules

- TDD: write the failing test first. State your test harness in the audit.
- Formal register. No em dashes. No emojis.
- Never edit files outside `frontend/` except: you may propose fixture content by PR comment to API, who owns the directory.
- If a backend field is missing, open an issue; do not invent an API.
