# [INTEGRATION] Final pull gate: everything works together, end to end — GATE G5

**Assigned to:** Anand (GitHub: @anandlo) — the consolidation issue.

**Owner:** the final integrator (you). **Runs after:** G0, G1, G2, G3, G4 are all reported done.
**This issue is the definition of "the framework works".** Nothing is complete until this passes on a clean clone.

---

## The rule

You pull `main`. You do not fix other people's code unless you are the owner of that path. If something fails, you reopen the owning issue with the exact failing command and output. This issue closes only when every check below passes.

---

## Preconditions (each must be reported complete in its issue)

| Gate | Issue | Evidence required |
|---|---|---|
| G0 contract frozen | [CONTRACT][G0] | tag `g0-contract-frozen`, `pytest tests/contract/` green |
| G1 engine credible | [ENGINE] | the published-window reproduction test passing, with the recorded result |
| G2 weather honest | [WEATHER] | `backend/weather/HINDCAST.md` with a BSS number and sample sizes, positive or negative stated plainly |
| G3 API live | [API] | determinism and provenance tests green against real ENGINE and WEATHER |
| G4 frontend complete | [FRONTEND] | `frontend/REQUIREMENTS_MAP.md` with a test per slide feature |

---

## The checklist (run in this order, on a clean clone)

### 1. Clean clone and install
```bash
cd /tmp && rm -rf g5check && git clone <repo-url> g5check && cd g5check
python3 -m venv .venv && . .venv/bin/activate
pip install -e .
```
- [ ] Install completes with no error.
- [ ] `python -c "import launchwin"` works.

### 2. Test suites, all four workflows
```bash
pytest tests/contract/ -q
pytest backend/engine/ -q
pytest backend/weather/ -q
pytest backend/api/ -q
pytest frontend/ -q            # or the frontend's declared test command
```
- [ ] Every suite green. Any failure reopens that workflow's issue.

### 3. The integration harness
```bash
python scripts/integration_test.py
```
- [ ] Exits 0.
- [ ] Its output shows: fixtures valid; app boots; SSO, POLAR and LEO requests answered; **the LEO 45.1 case returns `reachable: false` with a plane-change penalty**; site, weather and skill endpoints respond; a citation id resolves; determinism holds.

### 4. The engine's own gate, re-run
- [ ] `pytest backend/engine/tests/test_reproduce_published_windows.py -q` green (G1 still true after merge, not just when it was written).

### 5. The model's validations, re-run
- [ ] The hindcast runs end to end and reproduces the numbers in `HINDCAST.md`. **Open the file and compare the BSS value to the fresh run.** They must match or the file must state why not.
- [ ] The SSO inclination table, the Canso azimuths (177.0, 180.0, 191.6), the J2 drift (-5.14 deg/day at 600 km i=45.1) and the 45.1 impossibility are all covered by tests that run in this pull.

### 6. API surface, exercised by hand
```bash
uvicorn backend.api.app:app --port 8000 &
curl -s localhost:8000/v1/site | head -20
curl -s "localhost:8000/v1/weather/probability?date=$(date -v+3d +%F)&site=canso" | head -20
curl -s "localhost:8000/v1/validation/skill?period_start=2024-01-01&period_end=2025-01-01" | head -20
curl -s -X POST localhost:8000/v1/windows -H 'content-type: application/json' \
  -d '{"target":{"type":"LEO"},"site":"canso","vehicle_profile_id":"cyclone4m","date_range":{"start":"2026-10-04","end":"2026-11-04"},"include_weather":true}'
```
- [ ] The LEO call returns HTTP 200 with `reachable: false` and a non-null `plane_change_dv_ms`.
- [ ] Every response carries `constants_block` and `provenance_block`.
- [ ] The weather call carries `horizon_label`, and `CLIMATOLOGY` beyond day 10, `FORECAST` inside it.
- [ ] The skill call returns a `skill_series` with `n_cases` per lead.
- [ ] Take a `citation_id` from the POST and fetch `/v1/citation?id=...`; the constants match the POST response exactly.

### 7. The website, both paths
- [ ] With the API running, open the frontend. The window table fills from the engine. The **countdown ticks against a real `t_liftoff_utc`** and shows "No window in range" for an empty result. The weather badge shows colour plus probability plus horizon label plus the skill curve.
- [ ] For the LEO 45.1 case the honesty panel shows the penalty, not an error.
- [ ] Select a row: the trajectory renders on the map, southbound, inside the corridor.
- [ ] The viewing map shows at least one centre with an elevation and a sunlit/dark status.
- [ ] The scientific analysis view shows the skill table, reliability diagram, constants, and the download buttons; a downloaded CSV row count equals the table row count.
- [ ] **Disconnect the network. Reload.** All screens render from fixtures with the `offline_precomputed` banner, and the countdown still works.
- [ ] `frontend/REQUIREMENTS_MAP.md`: walk every row and confirm the named test exists and passes. Any row without a passing test reopens the frontend issue.

### 8. Provenance and honesty spot checks
- [ ] Pick one number displayed in the UI. Trace it: to the API response, to `provenance_block.source_files`, to the config or data file. If it cannot be traced, it is a bug.
- [ ] `grep -rn "3.99" backend/engine/*.py` returns zero in code paths.
- [ ] Every data file with an `ASSUMPTION` flag is surfaced somewhere the reader can see it (README or the provenance block).
- [ ] No workflow's README claims a result its tests do not produce.

### 9. The claim discipline check
- [ ] Read the four READMEs and `HINDCAST.md`. Confirm every strong claim is marked PROVED / SKETCHED / CONJECTURE as spec II.9 requires, and that no one claims ascent-aware windows or probabilistic weather as novel (both are pre-empted and must be cited as prior art in the relevant README).
- [ ] The skill horizon is still labelled SKETCHED unless the hindcast result supports a narrower statement, which is stated with its period and sample size.

### 10. Tag and freeze
```bash
git tag -a submission -m "Mission Accepted Challenge 2 submission"
git push origin submission
```
- [ ] Tag pushed. This is the artifact of record.

---

## Close criteria

Every box above is checked, with the command output pasted into this issue as a comment. If any box fails, the owning workflow's issue is reopened and a comment here links to it.

## What you do NOT do in this issue

- Do not fix physics, weather logic or frontend features yourself.**You are the integrator, not the fifth developer.** Your edits are limited to: the integration harness if it is wrong, the tag, and this issue's comments.

## Anti-corner-cutting law

- A green test suite is not evidence if the test asserts nothing. Spot-check three tests per workflow and confirm each asserts a real value, not merely that a function returns.
- A passing run on stubs is not G5. Check `engine_version` is not `"stub"` in the responses you exercised.
- A fixture-only demo is not G5 either. The live path must work with the API up.
- If a workflow reports done but its evidence is missing, reopen it. The submission is judged on the working artifact, not on the report of it.
- You are the integrator, not an extra developer. If you are tempted to fix another workflow's code to make this pass, that is the signal to reopen their issue instead.
