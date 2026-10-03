# [ENGINE] Orbital mechanics: reachability, J2 windows, injection-consistent solve, screens - GATE G1

**Assigned to:** Anand (GitHub: @anandlo).

**Credential dependency (crosses workflows):** Het (@HetJivani04) holds the **Space-Track** account, which the conjunction screen (E8) can consume for a deeper pre-screen than CelesTrak alone. **Do not block E8 on it.** Build the screen against CelesTrak first, which needs no key, and switch the Space-Track path on only if Het's key arrives and the screen is already passing. Ask Het in the issue thread rather than waiting on it. Record which source the screen used in the provenance block either way.

**Owner role:** ENGINE developer. **Depends on:** G0 contract (schemas). **Blocks:** live frontend data, API composition.
**You own:** `backend/engine/**` and nothing else. Do not touch `backend/weather/`, `backend/api/`, `frontend/`.

**Read first:** `docs/00_INTEGRATION_CONTRACT.md`, then spec Parts **II.1-II.6, II.8, II.10** and **III.1, III.2, III.3, III.5, III.6** (`C2_framework_and_build_spec.md`). Do not read Parts V-VIII.

**Maintain:** `backend/engine/progress.md` - append after every task, so a session restart loses nothing.

---

## Mission

Implement the engine that turns a target orbit plus a date range into launch dates and times, with an honest verdict when the target is impossible from this pad. You are the critical path: nothing real can be demoed until your gate passes.

Frozen signature (contract Seam 1):
```python
# backend/engine/__init__.py
def compute_windows(request: dict) -> dict:
    """spec IV.1 request -> response body MINUS the weather fields and the
    constants/provenance blocks (API adds those). Pure function. No network.
    No I/O beyond backend/engine/data/."""
```

---

## Task backlog (TDD: failing test first, always)

### E0 Scaffold (30 min)
- [ ] `backend/engine/tests/test_smoke.py` asserting `compute_windows` imports - RED
- [ ] `backend/engine/__init__.py` stub returning a well-formed empty response - GREEN
- [ ] `conftest.py` if shared fixtures are needed

### E1 Constants and their sources (1 h)
- [ ] TEST: a helper returns the constants block with exactly J2=1.08262668e-3, GM=3.986004418e14, R_e=6378137.0, omega_sid_rad_s=7.292115e-5, gmst_model="IAU_1982", each with a `source` string
- [ ] TEST (the hard rule): the literal `1.08262668` appears in exactly one file under `backend/engine/`, and that file is the constants/provenance module - enforce by test, not convention
- [ ] Implement `provenance.py`

### E2 Frames and GMST (1 h)
- [ ] TEST: GMST at a published epoch matches to 1e-6 deg; put the reference and its source in the test docstring
- [ ] TEST: Canso geodetic (45.3, -61.0) to ECEF and back returns the input within 1e-9
- [ ] TEST: the rotating-frame azimuth correction has the sign spec II.2 requires at 45.3 N and is zero at the equator
- [ ] Implement `frames.py`

### E3 Reachability, including the honesty case (2 h)
- [ ] TEST: `i_target=45.1` returns `reachable=False` with `plane_change_dv_ms` within 1 m/s of the spec value (~27; the spec computes 26.8)
- [ ] TEST: `i_target=87.9` gives azimuth **177.0 deg** (spec value)
- [ ] TEST: `i_target=90.0` gives azimuth **180.0 deg**
- [ ] TEST: `i_target=98.1` gives azimuth **191.6 deg** (retrograde, greater than 180)
- [ ] TEST: an azimuth outside the corridor in `data/site_canso.json` sets `constraint_fired: "hazard_area"`
- [ ] Implement `reachability.py`: `cos i = cos(phi_s) * sin(beta)` with both branches, the impossible-case penalty, the corridor test
- [ ] DATA: write `data/site_canso.json` from the Canso environmental assessment: lat, lon, alt_m, `corridor.A_min_deg`, `corridor.A_max_deg`, `corridor.source` (which figure or section), `car_references` (602.43, 602.44), `operating_hours`. **If a corridor bound is not published as a number, mark it `"flag": "ASSUMPTION"` and state what you assumed and why. Never fabricate a bound and label it verified.**

### E4 J2 secular dynamics (1 h)
- [ ] TEST: nodal drift at 600 km, i=45.1 is **-5.14 deg/day** within 1 percent - and explicitly assert the function does NOT return the commonly quoted 3.99 (that constant is wrong for this orbit; the spec recomputed it)
- [ ] TEST: the SSO table from spec II.6 - i=**97.8** at 600 km, **98.08** at 674 km, **98.19** at 700 km, **99.0** at 900 km - all within 0.01 deg (this is the first assertion of spec III.1)
- [ ] TEST: drift changes sign as i crosses 90 deg
- [ ] Implement `j2.py`: `nodal_rate(a, e, i)`, `sso_inclination(h_km)`
- [ ] HARD RULE: the drift constant exists only inside the formula, nowhere else

### E5 Window equation (1.5 h)
- [ ] TEST: one fully hand-computed case - fixed target RAAN, site longitude, epoch; the crossing times asserted against your hand arithmetic shown in the docstring
- [ ] TEST: `window_width_s` equals `tolerance_deg / 15.04 * 3600` for a 0.1 deg tolerance (spec II.4)
- [ ] TEST: a 90-day search returns windows sorted ascending with no duplicates
- [ ] TEST: empty windows with `reachable=True` is a valid result (spec IV.1 semantics) - no exception
- [ ] Implement `window.py`

### E6 Injection-consistent solve - the Vehicle Duration bonus (2.5 h)
- [ ] TEST: convergence for all three orbit classes; assert the contraction condition `|dRAAN/dt * dT_inj/dt| < 1` holds for your cases and the iteration count is bounded
- [ ] TEST: `window_center_shift_s` and `liftoff_instant_error_min` are non-zero with the physically correct sign (a 30-90 minute ascent must move the plane)
- [ ] TEST: non-convergence returns `constraint_fired: "fixed_point_no_convergence"`, never a wrong number
- [ ] TEST: two vehicle profiles with different `T_to_inj` produce different `window_center_shift_s` - proving the parameter flows through
- [ ] DATA: `data/vehicles/cyclone4m.json` from the published Cyclone-4M guide: `T_to_inj_s` with source, ascent/coast segments, hazard footprint, and every row flagged `VERIFIED` or `ASSUMPTION`. For unpublished values, use a defensible value from a similar vehicle, flag ASSUMPTION, and record the choice
- [ ] Implement `injection.py`

### E7 SSO specifics (1 h)
- [ ] TEST: `sso_inclination(h_t)` matches the E4 table
- [ ] TEST: an explicit LTAN inconsistent with the derived inclination produces `sso_consistency_warning`, not a crash
- [ ] TEST: the LTAN-RAAN coupling relation holds for a worked case (spec II.6)
- [ ] Implement `sso.py`

### E8 Range and conjunction screens (1.5 h)
- [ ] TEST: a trajectory leaving the corridor polygon sets `screens.hazard = "fail"`
- [ ] TEST: the conjunction screen over a committed 3-TLE fixture returns `clear` or `flagged` deterministically
- [ ] TEST: the NOTAM screen returns `"none"` as a stub while keeping the field present
- [ ] DATA: commit `data/tle_fixture.json` - 3 real TLEs from CelesTrak, fetched this session, with fetch time and source recorded. **Tests never touch the network**
- [ ] Implement `screens.py` with the CelesTrak fetch behind a cache you own

### E9 Composition (1.5 h)
- [ ] TEST: a full spec IV.1 request returns the full spec IV.1 response minus the API-added fields
- [ ] TEST (spec III.6, your half): the same request twice gives byte-identical numerics
- [ ] TEST: every response carries the values for site, corridor, `criteria_version`, `vehicle_profile_id`, `row_flags`, `engine_version`, `computation_ms`
- [ ] TEST (spec III.5, the honesty test): type=LEO with the advertised 45.1 class returns `reachable: false` plus `plane_change_dv_ms`
- [ ] Implement the composition thin, no math inline

### E10 GATE G1 - reproduce published launch windows (2 h)
- [ ] Commit `data/published_windows.json`: 3-5 **published** windows (for example Cape Canaveral, Boca Chica, Mahia) each with URL, access date and the quoted window
- [ ] TEST `test_reproduce_published_windows.py`: for each, given the published target orbit and site latitude, the engine's window centre lands **within 5 minutes** of the published one
- [ ] **If a window cannot be reproduced, do not loosen the tolerance.** Record it in `progress.md`, diagnose (longitude sign, GMST epoch, liftoff vs injection comparison, corridor), fix, or drop to a window you can reproduce and state why
- [ ] This test stays in the suite permanently. **No frontend work on live data starts until it passes**

### E11 Provenance echo (45 min)
- [ ] TEST: `provenance_block.source_files` lists every config and data file actually read for that run, and re-reading them reproduces the numbers (spec II.10: any number not traceable to a row is a bug)
- [ ] Implement a small file-read tracker

### E12 Documentation (45 min)
- [ ] `backend/engine/README.md`: what it computes, how to run the tests, the two PROVED claims, every ASSUMPTION row in the data files, and the known-unread items
- [ ] `backend/engine/DONE.md`: shipped vs unfinished

---

## Acceptance criteria (the issue closes when)

1. `pytest backend/engine/ -q` green on a clean clone after `pip install -e .`.
2. `pytest tests/contract/test_engine_schema.py -q` green (API's schema validates your output).
3. The G1 credibility test passes with a recorded result.
4. The 45.1 honesty test returns `reachable: false` with the penalty.
5. `grep -rn "3.99" backend/engine/*.py` returns 0 in code paths.
6. README and DONE.md exist.

## Time budget

| Hours | Work |
|---|---|
| 0-1 | E0, E1 |
| 1-4 | E2, E3, E4 |
| 4-7 | E5, E6 |
| 7-9 | E7, E8 |
| 9-11 | E9, E11 |
| 11-13 | **E10 GATE - nothing else until it passes** |

## What will go wrong

- **Published windows do not reproduce.** Suspect in order: longitude sign, GMST epoch, comparing liftoff-time to injection-time publications, an unread corridor constraint. Diagnose; do not loosen the tolerance.
- **The fixed point does not converge.** Check the contraction condition first; if it genuinely exceeds 1 in your parameter range, that is a finding - report it, do not hide it with more iterations.
- **The EA gives qualitative corridor bounds.** Then they are ASSUMPTION: say so in the JSON, the README, and the provenance block.
- **CelesTrak flaky at test time.** Tests use the committed fixture. Always.

## Rules

- TDD: red, green, refactor. Never code before a failing test.
- Nothing site-, vehicle- or criteria-dependent hard-coded in Python (contract section 4).
- Formal register. No em dashes. No emojis.
- Mark claims PROVED / SKETCHED / CONJECTURE exactly as spec II.9 does; you own the two PROVED ones.
- If a citation is needed, resolve it by title via Crossref. Never from memory - three phantom citations have already been caught in this project.

## Subagent dispatch and anti-corner-cutting law (applies to every task above)

- Dispatch each task to a subagent with this issue's text plus that task's exact acceptance test. The subagent sees nothing else, so quote into its prompt the context it needs: the spec section, the expected numeric values (177.0, 180.0, 191.6, -5.14, the 97.8/98.08/98.19/99.0 table), and the frozen signature.
- A subagent may not close a task on the strength of "it runs". The acceptance test is the closing criterion; paste its output into progress.md.
- No partial development. A module is done when its tests pass and its README states what it does and does not claim. Anything half-written is marked UNDONE in progress.md and must not be merged.
- No test weakening. If the published-window reproduction test fails, you diagnose and fix. You never widen the 5-minute tolerance, and you never delete the test. If a case is genuinely unreproducible, you document why in progress.md and substitute a case you can reproduce.
- No hard-coded values where the contract requires configuration. The one permitted literal is the shared constants module, enforced by its own test.
- No TODO placeholders in merged code. Cut the feature and record it in DONE.md.
- Every claim is marked PROVED, SKETCHED or CONJECTURE per spec II.9. You own the two PROVED ones; do not upgrade a SKETCHED claim.
- Every task update appends to progress.md with the exact command run and its observed output.
