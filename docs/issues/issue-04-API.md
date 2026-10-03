# [API] FastAPI service, provenance, citation endpoint, Python client, integration harness - GATES G0, G3, G5

**Assigned to:** Rafat (GitHub: TBD) - owns both the schemas and the service that serves them.

**Owner role:** API developer. **Depends on:** nothing (you own the contract). **Blocks:** everyone at G0; the final pull at G5.
**You own:** `backend/api/**`, `tests/contract/**`, the `backend/fixtures/` directory, `scripts/integration_test.py`, root `pyproject.toml`.

**Read first:** `docs/00_INTEGRATION_CONTRACT.md`, then spec Parts **IV.1-IV.6** (your bible, verbatim), **II.10**, **III.6**, **V.5** (offline fallback).

**Maintain:** `backend/api/progress.md`.

---

## Mission

Own the HTTP surface, the frozen contract, the machinery that makes every number traceable, and the test that proves a clean clone works. You are also the person who unblocks everyone: G0 is the first task in the whole project.

---

## Task backlog (TDD)

### A0 GATE G0 - freeze the contract (1.5 h) - FIRST TASK IN THE PROJECT
- [ ] `pytest tests/contract/` collects - RED
- [ ] Write all six endpoint schemas verbatim from spec IV: `windows_request`, `windows_response` (plus `constants_block`, `provenance_block` as shared `$ref` schemas), `ephemeris_response`, `weather_probability_response`, `skill_response`, `site_response`. Every field, type and enum
- [ ] `good/*.json` and `bad/*.json` examples; tests assert accept and reject per schema
- [ ] Root `pyproject.toml`: package `launchwin`, python >=3.11, deps fastapi, uvicorn, pydantic, httpx, pytest; `pip install -e .` works in a clean venv
- [ ] **Merge, tag `g0-contract-frozen`, announce the tag to ENGINE, WEATHER and FRONTEND.** A comment on this issue lists the tag SHA and every field interpretation you had to make

### A1 Provenance machinery (2 h)
- [ ] TEST: `constants_block` on every result-bearing response, containing J2, GM, R_e, omega_sid_rad_s, gmst_model, citation_id, and per-constant source
- [ ] TEST: `provenance_block` contains site, corridor, criteria_version, vehicle_profile_id, row_flags, source_files, all populated from what was actually read
- [ ] TEST: `citation_id` is deterministic for a given request (a hash of constants plus config), not a random uuid - spec III.6 requires `GET /v1/citation` to reproduce a stored run exactly
- [ ] IMPLEMENT `provenance.py`, assembling what ENGINE and WEATHER supply
- [ ] TEST: a response missing any provenance field fails your own assertion suite

### A2 App skeleton and the error model (1.5 h)
- [ ] TEST: well-formed POST /v1/windows returns **200** including `reachable: false` cases (spec IV.8 rule 1)
- [ ] TEST: malformed body returns **422**, not 500
- [ ] TEST: unknown orbit id 404; rate limit 429 with Retry-After; upstream outage 503 with Retry-After **and the offline fixture path active** (spec V.5)
- [ ] TEST: domain outcomes (unreachable, empty windows, `constraint_fired`) are never HTTP errors
- [ ] IMPLEMENT `app.py` with the `/v1` router and the exception handlers
- [ ] TEST: `/v1/openapi.json` serves and matches your schemas on one spot-checked path

### A3 Wire ENGINE - stub first, then live (2 h)
- [ ] TEST (stub): full spec IV.1 response shape filled from `backend/fixtures/windows.json`
- [ ] IMPLEMENT `routes/windows.py` calling `backend.engine.compute_windows`, then composing constants and provenance
- [ ] TEST: composition correct; weather fields null when `include_weather=false`
- [ ] **The stub must be shape-complete** - every field present with plausible values so FRONTEND can build against reality - and every stub response carries `"engine_version": "stub"` so nobody mistakes it for real output
- [ ] TEST: `engine_version` distinguishes stub from real
- [ ] TEST (`pytest.mark.skipif` until ENGINE lands): the live path produces schema-valid output

### A4 Wire WEATHER - stub first, then live (1.5 h)
- [ ] TEST: `/v1/weather/probability` and `/v1/validation/skill` return spec IV.3 and IV.4 shapes from fixtures
- [ ] IMPLEMENT the calls
- [ ] TEST: when the weather layer raises or is unreachable, choose and test ONE behaviour - either windows still return with null weather fields, or 503 with Retry-After and the fixture path active. Document the choice in your README. Never a 500
- [ ] TEST: weather-bearing responses are cached on `forecast_issue_time` (spec IV.9), and a cached response survives an outage

### A5 Ephemeris and site endpoints (1.5 h)
- [ ] TEST: `/v1/orbits/sso981/ephemeris` returns ECEF points, `frame: "ECEF"`, `ground_track_valid: true` within 3 days
- [ ] TEST: beyond the 3-day horizon `ground_track_valid: false` (spec IV.2)
- [ ] TEST: unknown id 404; `step_s` honoured
- [ ] TEST: `/v1/site` returns Canso geometry, corridor bounds with **source and flag** (ASSUMPTION where the EA is qualitative), CAR references
- [ ] IMPLEMENT both, delegating propagation to ENGINE where it exists, fixture otherwise

### A6 Citation endpoint - the researcher interface (1.5 h)
- [ ] TEST: `/v1/citation?id=<citation_id>` returns constants, config hash, criteria version, vehicle rows with flags, source files, engine version, for a **stored** run
- [ ] TEST: same request gives the same id; a different criteria_version gives a different id
- [ ] IMPLEMENT storage in `backend/api/data/runs/<citation_id>.json`, written on every POST
- [ ] TEST: unknown id returns 404 stating the run was not found (a genuine resource miss, distinct from a domain outcome)

### A7 Caching and rate limits (1 h)
- [ ] TEST: identical requests within TTL hit cache; a cache flush changes no numbers (spec III.6 determinism)
- [ ] TEST: exceeding the limit returns 429 with Retry-After
- [ ] IMPLEMENT per spec IV.9 with TTL and limit as config values

### A8 Python client (1.5 h)
- [ ] IMPLEMENT `backend/client/launchwin.py` per spec IV.10
- [ ] TEST: `from launchwin import windows; df = windows(target="SSO", site="canso", dates=("2026-10-04","2027-01-01"))` returns a DataFrame, tested against FastAPI `TestClient`
- [ ] TEST: the client works against the fixtures-only app (the demo path)
- [ ] TEST: after `pip install -e .`, importing and calling works from a directory outside the repo
- [ ] TEST: `import launchwin` succeeds without pandas installed, or pandas is a declared hard dependency - pick one and test it

### A9 GATE G3 - determinism and provenance (1 h, needs ENGINE and WEATHER landed)
- [ ] TEST: same request twice, byte-compare all numeric fields, identical
- [ ] TEST: identical after a cache flush
- [ ] TEST: every response carries constants, site, corridor, criteria_version, vehicle_profile_id with row flags, and for weather-bearing ones `forecast_issue_time` and `horizon_label`
- [ ] TEST: `/v1/citation` for a stored run reproduces the constants exactly

### A10 GATE G5 scaffold - integration harness (1 h)
- [ ] IMPLEMENT `scripts/integration_test.py`: (1) fixtures validate, (2) app boots via TestClient, (3) POST for SSO, POLAR and LEO, (4) the LEO 45.1 case returns `reachable: false` with a penalty, (5) site, weather and skill endpoints respond, (6) citation for the run, (7) determinism check, (8) non-zero exit with a readable message on any failure
- [ ] TEST: runnable from hour one on stubs, so it becomes the real gate as ENGINE and WEATHER land
- [ ] This is what the final integrator runs. Its failure messages must say exactly what broke

### A11 Documentation (1 h)
- [ ] `backend/api/README.md`: how to run, the endpoint table, the error model in one paragraph, how to get a citation id, the fixture path, and an explicit statement of what is stubbed vs real at this commit
- [ ] `backend/api/DONE.md`

---

## Acceptance criteria

1. `pytest tests/contract/ -q` and `pytest backend/api/ -q` green on a clean clone.
2. `python scripts/integration_test.py` passes (on fixtures from hour one; on live after G1/G2).
3. The error model behaves per spec IV.8, proven by tests.
4. Every response carries provenance; `citation_id` is reproducible.
5. README and DONE.md exist, and the README states the stub/real boundary at the merge commit.

## Time budget

| Hours | Work |
|---|---|
| 0-2 | **A0 - GATE G0. First task in the project.** |
| 2-4 | A1, A2 |
| 4-6 | A3, A4 (stubs unblock FRONTEND) |
| 6-8 | A5, A6 |
| 8-9 | A7, A8 |
| 9-10 | A9 - G3 |
| 10-11 | A10, A11 |

## What will go wrong

- **Schema drift.** You change a schema only with a stated reason, announced before merge. A silent change breaks two developers at once.
- **You are tempted to return 400 for an unreachable target.** You may not. 200 with `reachable: false` (spec IV.8 rule 1). The test protects this.
- **A stub ships without provenance.** Every response, stub or real, carries the constants and provenance blocks; stubs carry `engine_version: "stub"`.
- **503 during judging.** The fixture path must activate; test that branch explicitly.

## Rules

- TDD: red, green, refactor.
- Spec Part IV is the contract; conflict with reality is an issue, not a silent divergence.
- No credentials in code or commits.
- Formal register. No em dashes. No emojis.
- You run this harness for the final integrator. Make it explain its own failures.

## Subagent dispatch and anti-corner-cutting law (applies to every task above)

- Dispatch each task to a subagent with this issue's text plus that task's exact acceptance test. The subagent sees nothing else, so quote into its prompt the context it needs: the spec Part IV schemas, the error model rules, and the frozen signatures from the contract.
- A subagent may not close a task on the strength of "it runs". The acceptance test is the closing criterion; paste its output into progress.md.
- No partial development. An endpoint is done when it validates against its schema, has a test for its success path and its failure path, and is documented in the README's stub-versus-real statement. Anything half-written is marked UNDONE and must not be merged.
- No test weakening. Guard the error model above all: if a test asserting 200-with-`reachable:false` fails because a subagent returned 400, fix the handler, never the test.
- No stub shipped as real. Every stub response carries `"engine_version": "stub"`, and the README states at each merge what is stubbed.
- No fabricated schema. Every field is transcribed from spec IV; an interpretation is recorded in this issue, not invented silently.
- No TODO placeholders in merged code. Cut the feature and record it in DONE.md.
- Every task update appends to progress.md with the exact command run and its observed output.
