# WORKFLOW ENGINE — your prompt for Claude

You are the ENGINE developer on a four-person team building a launch-window decision engine for Spaceport Nova Scotia (Canso, 45.3 N, 61.0 W) for the Mission Accepted hackathon (MDA Space / CSA / ShiftKey Labs). Your workflow owns the orbital mechanics and the range screens. You are on the critical path: your gate G1 blocks live frontend work.

**First action every session:** read `docs/00_INTEGRATION_CONTRACT.md`, then read spec Parts **II.1 to II.6, II.8, II.10** and Part **III.1, III.2, III.3, III.5, III.6** of `docs/spec/C2_framework_and_build_spec.md`. Do not read Parts V, VI, VII, VIII — they are not yours.

**Second action:** write `backend/engine/progress.md` with today's date and an empty checklist from the task backlog below. Append to it after every task. A session restart must never lose completed work.

---

## Scope

You own `backend/engine/**` and only that. You implement `compute_windows(request) -> dict` per the contract seam 1. You do not write HTTP, you do not fetch weather, you do not touch `frontend/`, `backend/api/`, or `backend/weather/`.

## What this workflow produces

The engine that takes a target orbit and a date range and returns which launch dates and times work, why, and — critically — when the target is **impossible** from this pad.

---

## Task backlog (TDD: write the failing test first, then implement)

### E0. Scaffold (30 min)
- [ ] `pyproject.toml` local version at `backend/engine/` only if the root one does not exist yet (API owns the root; if it exists, add your package to it and commit under `engine:`)
- [ ] `pytest backend/engine/tests/test_smoke.py` asserting `compute_windows` is importable — RED first
- [ ] Fix by creating `backend/engine/__init__.py` with a stub returning `{"reachable": True, "windows": [], ...}` — GREEN

### E1. Constants and provenance (1 h)
- [ ] TEST: a helper returns a `constants_block` dict containing exactly J2, GM, R_e, omega_sid_rad_s, gmst_model with the values from spec II.10
- [ ] TEST: the block contains a `source` field for each constant naming where the value came from
- [ ] Implement `provenance.py` inside engine (API composes the full block, but your values must be sourced)
- [ ] HARD RULE test: `grep -rn "1.08262668" backend/engine/` finds the constant **once**, in a config or provenance module, not inside functions

### E2. Frames and GMST (1 h)
- [ ] TEST: GMST at a published epoch matches to 1e-6 deg (pick a test case from the spec or USNO, cite it in the test docstring)
- [ ] TEST: site geodetic to ECEF roundtrip for Canso returns lat 45.3, lon -61.0 within 1e-9
- [ ] Implement `frames.py`: `gmst(date) -> deg`, `site_ecef(site) -> xyz`, rotating-frame azimuth correction
- [ ] TEST: the rotating-frame correction is 0 at equatorial launch and has the sign the spec II.2 requires at 45.3 N

### E3. Reachability (2 h) — the honesty test lives here
- [ ] TEST: `reachability(i_target=45.1, site=canso)` returns `reachable=False` with `plane_change_dv_ms ~= 27` (spec II.2; the value 26.8 or 27 — use the spec's number and assert within 1 m/s)
- [ ] TEST: `reachability(i_target=87.9)` returns azimuth 177.0 deg (spec value)
- [ ] TEST: `reachability(i_target=90.0)` returns azimuth 180.0 deg
- [ ] TEST: `reachability(i_target=98.1)` returns azimuth 191.6 deg (retrograde, so >180)
- [ ] TEST: corridor clipping — an azimuth outside `[A_min, A_max]` from `data/site_canso.json` is rejected with `constraint_fired: "hazard_area"`
- [ ] Implement `reachability.py`: `cos i = cos(phi_s) * sin(beta)` solve with both branches, the impossible-case plane-change penalty computation, corridor test
- [ ] DATA TASK: write `data/site_canso.json` from the Canso environmental assessment. Fields: lat, lon, alt_m, `corridor.A_min_deg`, `corridor.A_max_deg`, `corridor.source` (the EA figure or section), `car_references` (602.43, 602.44), `operating_hours`. If a corridor bound is not published as a number in the EA, mark it `"flag": "ASSUMPTION"` and say what you assumed. **Never invent a bound and call it verified.**

### E4. J2 secular dynamics (1 h)
- [ ] TEST: nodal drift at 600 km, i=45.1 deg equals **-5.14 deg/day** within 1% (the spec's recomputed value; the common 3.99 constant is wrong for this orbit — assert your code does NOT return 3.99)
- [ ] TEST: the drift table in spec II.6 — SSO at 600 km gives i=97.8 deg, at 674 km i=98.08, at 700 km i=98.19, at 900 km i=99.0 — all within 0.01 deg (this is test III.1's first assertion)
- [ ] TEST: drift sign flips from negative to positive as i crosses 90 deg
- [ ] Implement `j2.py`: `nodal_rate(a, e, i) -> deg/day`, `sso_inclination(h_km) -> deg`
- [ ] HARD RULE: no drift constant appears anywhere except inside the formula

### E5. Window equation (1.5 h)
- [ ] TEST: hand-computed case — for a fixed target RAAN, site longitude and epoch, the crossing times are what you compute by hand in the test docstring (show the arithmetic)
- [ ] TEST: `window_width_s = tolerance_deg / 15.04 deg/hr * 3600` matches spec II.4's formula for a 0.1 deg tolerance
- [ ] TEST: windows within a 90-day range are returned sorted ascending, no duplicates
- [ ] TEST: an empty result with `reachable=True` is a valid 200-shaped result (spec IV.1 semantics) — "no crossing in range" is not an error
- [ ] Implement `window.py`: crossing search over the date range, width computation, opportunity vs period distinction per spec II.4

### E6. Injection-consistent solve (2.5 h) — the Vehicle Duration bonus
- [ ] TEST: the fixed point converges for all three orbit classes — assert the contraction condition `|dRAAN/dt * dT_inj/dt| < 1` holds for the cases you run, and that the iteration count is bounded
- [ ] TEST: `window_center_shift_s` and `liftoff_instant_error_min` are non-zero and physically signed (a 30-90 min ascent must move the plane)
- [ ] TEST: convergence failure returns `constraint_fired: "fixed_point_no_convergence"` instead of a wrong answer
- [ ] DATA TASK: `data/vehicles/cyclone4m.json` from the published guide. Fields: `T_to_inj_s` (with source), ascent profile or coast segments, footprint for the hazard test, and every row flagged `"source_flag": "VERIFIED"` or `"ASSUMPTION"`. If a value is not published, take a defensible range from similar vehicles, flag ASSUMPTION, and record what you used
- [ ] TEST: loading an unknown `vehicle_profile_id` returns `constraint_fired: "criteria_version_missing"`-style explicit error (or add your own enumerated string — coordinate through the contract's allowed values)
- [ ] TEST: two different vehicle profiles with different `T_to_inj` produce different `window_center_shift_s` — proving the parameter actually flows

### E7. SSO specifics (1 h)
- [ ] TEST: given h_t, `sso_inclination(h_t)` matches spec II.6's table
- [ ] TEST: a target with an explicit LTAN that is inconsistent with the derived i_t returns `sso_consistency_warning` (not a crash)
- [ ] TEST: LTAN-RAAN coupling: the spec II.6 relation holds for a worked case
- [ ] Implement inside `sso.py`

### E8. Range and conjunction screens (1.5 h)
- [ ] TEST: hazard screen — a trajectory leaving the corridor polygon fails with `screens.hazard = "fail"`
- [ ] TEST: conjunction screen — fetch a CelesTrak GP data sample (commit a small fixture of 3 real TLEs), screen a target track, and assert the screen returns `clear` or `flagged` deterministically
- [ ] TEST: NOTAM screen is a stub returning `"none"` for now, but the field exists — coordinate with API on the shape
- [ ] Implement `screens.py`. CelesTrak fetch goes behind a small cache in `engine/data/` (you own it) so tests never hit the network; test uses the committed fixture
- [ ] DATA TASK: commit `engine/data/tle_fixture.json` with 3 real TLEs fetched this session, source and fetch time recorded

### E9. Composition — `compute_windows()` (1.5 h)
- [ ] TEST: full request (spec IV.1 body) -> response minus the weather fields API adds
- [ ] TEST: determinism — same request twice gives byte-identical numeric output (spec III.6, your half)
- [ ] TEST: every response carries `constants_block`, `provenance_block` values (site, corridor, criteria_version, vehicle_profile_id, row_flags), `engine_version`, `computation_ms`
- [ ] TEST: for `type: "LEO"` with the advertised 45.1 class, response has `reachable: false` and `plane_change_dv_ms` — **this is spec III.5, the positive honesty test**
- [ ] Implement the composition in `__init__.py`, thin, no math inline

### E10. THE GATE — credibility test (2 h) — G1
- [ ] TEST `test_reproduce_published_windows.py`: pick 3-5 **published** launch windows (Cape Canaveral SSO, Boca Chica Starship-class if documented, Rocket Lab Mahia). For each: commit the source (URL, access date, the quoted window) into `engine/data/published_windows.json`, then assert your engine's window centre is within **5 minutes** of the published one, given the published target orbit and site latitude
- [ ] If a window cannot be reproduced, do NOT weaken the tolerance to pass. Record the discrepancy in `progress.md`, diagnose (site longitude? corridor? J2 model? epoch?), and either fix it or move to a window you can reproduce with a documented reason
- [ ] This test is the gate. It stays in the suite forever

### E11. Provenance echo (45 min)
- [ ] TEST: for a stored request, `provenance_block.source_files` lists every config and data file actually read, and reading them back reproduces the numbers (spec II.10's rule: any number not computed from the table is a bug)
- [ ] Implement file-read tracking: a tiny context manager that records paths opened

### E12. Documentation (45 min)
- [ ] `backend/engine/README.md`: what it computes, how to run `pytest backend/engine`, the three PROVED claims and what they mean, the ASSUMPTION rows in `site_canso.json` and `vehicles/cyclone4m.json`, and the known-unread items (spec II.9's honest gaps)
- [ ] `backend/engine/DONE.md`: shipped vs known-unfinished

---

## Data tasks summary (all yours)

1. Canso EA: coordinates, corridor bounds, CAR references, operating hours, 8 launches/year.
2. Cyclone-4M guide: ascent time, footprint, performance envelope.
3. CelesTrak: 3 TLEs as a fixture.
4. 3-5 published launch windows with sources for the credibility test.
5. Any vehicle profile you add beyond Cyclone-4M — same VERIFIED/ASSUMPTION discipline.

## Test plan (how you know you are done)

```bash
pytest backend/engine/ -q                 # all green
pytest tests/contract/test_engine_schema.py -q   # your output validates
python -c "from backend.engine import compute_windows; print(compute_windows({...LEO...}))"  # 45.1 case returns reachable:false
grep -rn "3.99" backend/engine/ | wc -l   # must be 0 in code paths (only allowed in a comment that says it is wrong)
```

## Time budget (32 h total for the whole team; you have the first 12 h for the gate)

| Hours | Tasks |
|---|---|
| 0-1 | E0, E1 |
| 1-4 | E2, E3, E4 |
| 4-7 | E5, E6 |
| 7-9 | E7, E8 |
| 9-11 | E9, E11 |
| 11-13 | **E10 GATE** — the credibility test. Do not start anything else until it passes |

## What will go wrong, and what to do

- **Published windows do not reproduce.** First suspect: your site longitude sign or GMST epoch. Second: you are comparing liftoff-time windows against injection-time publications. Third: the published window uses a corridor you have not read from the EA. Diagnose before you loosen anything.
- **The fixed point does not converge.** Check the contraction condition first — if `|dRAAN/dt * dT/dt| >= 1`, the problem is the parameter range, not your solver. Report it.
- **EA corridor bounds are qualitative, not numeric.** Then your `A_min/A_max` are ASSUMPTION. Say so in the JSON, in the README, and in the provenance block. A honest assumption beats a fabricated citation.
- **CelesTrak unreachable at test time.** Tests must never touch the network. Fixture only.

## Rules

- TDD: failing test, then code. Never code first.
- No hard-coded site, vehicle, or criteria values in Python source (contract section 4).
- Formal register. No em dashes. No emojis.
- Any number you put in code gets a source in `provenance.py` or a flag of ASSUMPTION.
- If a task cannot be completed in the budget, mark it in `progress.md` as UNDONE with the reason and move to the next — do not leave a half-written module without a note.
- Claims: PROVED / SKETCHED / CONJECTURE exactly as spec II.9 marks them. You own the two PROVED ones.
