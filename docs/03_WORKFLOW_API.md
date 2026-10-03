# WORKFLOW API - your prompt for Claude

You are the API developer on a four-person team building a launch-window decision engine for Spaceport Nova Scotia (Canso, 45.3 N, 61.0 W) for the Mission Accepted hackathon (MDA Space / CSA / ShiftKey Labs). You own the HTTP layer, the frozen contract, the provenance machinery, the Python client, and the final integration gate. You unblock everyone else: your gate G0 must land first.

**First action every session:** read `docs/00_INTEGRATION_CONTRACT.md`, then spec Parts **IV.1-IV.6** (full, this is your bible), **II.10** (provenance), **III.6**, and Part **V.5** (offline fallback). Do not read Parts II.1-II.8 derivation sections, III.1-III.5, VI.

**Second action:** write `backend/api/progress.md` with today's date and the backlog below. Append after every task.

---

## Scope

You own `backend/api/**`, `tests/contract/**`, `backend/fixtures/**` (directory), `scripts/integration_test.py`, and the root `pyproject.toml`. You do not implement orbital mechanics (ENGINE) or weather probabilities (WEATHER). You define the schemas they must satisfy, and you compose their outputs with provenance.

## What this workflow produces

The `/v1` REST surface that the frontend calls, the JSON Schemas that freeze the contract, the citation endpoint a researcher uses to reproduce a run, a three-line Python client, and the test that proves a clean clone works.

---

## Task backlog (TDD)

### A0. Scaffold and G0 (1.5 h) - FIRST TASK, OTHERS ARE WAITING
- [ ] TEST: `pytest tests/contract/` runs and collects - RED (empty)
- [ ] Write `tests/contract/schemas/windows_request.json` and `windows_response.json` **verbatim from spec IV.1** - every field, every type, every enum. The two shared objects (`constants_block`, `provenance_block`) are separate schema files reused by `$ref`
- [ ] Write schemas for IV.2 ephemeris, IV.3 weather probability, IV.4 skill, IV.5 site, IV.6 citation
- [ ] TEST: a minimal valid example validates against each schema; an example missing a required field fails; an example with a wrong type fails
- [ ] **GATE G0: `pytest tests/contract/` green with schemas only.** Commit immediately, tag the commit `g0-contract-frozen`, announce in the team channel. ENGINE and WEATHER now build against it
- [ ] Root `pyproject.toml`: package `launchwin`, python >=3.11, deps `fastapi`, `uvicorn`, `pydantic`, `httpx`, `pytest`. Editable install must work: `pip install -e .` from a clean clone

### A1. Provenance machinery (2 h)
- [ ] TEST: `constants_block` is returned on every result-bearing response and contains J2, GM, R_e, omega_sid_rad_s, gmst_model, citation_id - with sources
- [ ] TEST: `provenance_block` contains site, corridor, criteria_version, vehicle_profile_id, row_flags, source_files - all populated from what was actually read
- [ ] TEST: `citation_id` for a given request is reproducible - same request, same id (deterministic hash of the constants + config, not a random uuid; spec III.6 requires `GET /v1/citation` to reproduce the constants of a stored run)
- [ ] IMPLEMENT `provenance.py`: the block builders, the deterministic citation id, the config-hash. Coordinate with ENGINE via a issue: they supply `site`, `corridor`, `row_flags` from their data files; you assemble
- [ ] TEST: a response that is missing any provenance field fails (write it as a schema-adjacent assertion in your own tests too)

### A2. App skeleton and the error model (1.5 h)
- [ ] TEST: `POST /v1/windows` with a well-formed body returns **200**, including `reachable: false` cases (spec IV.8 rule 1)
- [ ] TEST: `POST /v1/windows` with a malformed body (missing target fields) returns **422**, not 500 (rule 2)
- [ ] TEST: unknown orbit id returns **404**; rate limit returns 429 with `Retry-After`; upstream weather outage returns 503 with `Retry-After` **and activates the offline fixture path** (spec V.5)
- [ ] TEST: a physics outcome that "looks like an error" - unreachable target, empty windows, `constraint_fired` - is NEVER an HTTP error
- [ ] IMPLEMENT `app.py` with FastAPI, `/v1` router, the exception handlers that map domain outcomes to 200-with-body and malformed input to 4xx
- [ ] TEST: OpenAPI at `/v1/openapi.json` serves and is consistent with your schemas (spot-check one path)

### A3. Wire ENGINE behind a stub, then live (2 h)
- [ ] TEST (against stub): `POST /v1/windows` returns the full spec IV.1 response shape with `windows[]` filled from `backend/fixtures/windows.json`
- [ ] Implement `routes/windows.py` calling `backend.engine.compute_windows`, composing `constants_block`, `provenance_block`, and then merging the weather fields
- [ ] TEST (against engine, when ENGINE's function exists - gate on import, skip gracefully with `pytest.mark.skipif` if not): the composition is correct, and weather fields are `null` when `include_weather=false`
- [ ] Until ENGINE lands: the stub must be **shape-complete** - every field present with plausible values from the fixture, so FRONTEND can build against reality. Mark stub responses with `"engine_version": "stub"` so nobody mistakes them for real output
- [ ] TEST: `engine_version` reflects stub vs real

### A4. Wire WEATHER behind a stub, then live (1.5 h)
- [ ] TEST: `GET /v1/weather/probability?date=&site=` returns spec IV.3 shape from fixture
- [ ] TEST: `GET /v1/validation/skill?period_start=&period_end=&lead_max=` returns spec IV.4 shape from fixture
- [ ] IMPLEMENT calling `backend.weather.probability` and `backend.weather.hindcast`
- [ ] TEST: when `include_weather=true` and the weather layer raises or is unreachable, windows still return (weather fields null or `source: "snapshot_cache"`) **or** you return 503 with Retry-After and the fixture path activates - pick one, document it in your README, and test that branch. Never a 500
- [ ] Cache: responses keyed on `forecast_issue_time` for weather-bearing results (spec IV.9). TEST that a cached weather response survives a weather-layer outage

### A5. Ephemeris and site endpoints (1.5 h)
- [ ] TEST: `GET /v1/orbits/{id}/ephemeris` with `id="sso981"` returns ECEF points, `frame: "ECEF"`, `ground_track_valid: true` within 3 days
- [ ] TEST: beyond 3-day horizon for conjunction-derived tracks, `ground_track_valid: false` (spec IV.2)
- [ ] TEST: unknown id 404; `step_s` honored
- [ ] TEST: `GET /v1/site` returns Canso geometry, corridor bounds **with their source and flag** (ASSUMPTION where the EA was qualitative), CAR references
- [ ] IMPLEMENT both, delegating the propagation math to ENGINE's `ephemeris()` if it exists, fixture otherwise

### A6. The citation endpoint - the researcher interface (1.5 h)
- [ ] TEST: `GET /v1/citation?id=<citation_id>` returns the constants block, config hash, criteria version, vehicle rows with flags, source files, and `engine_version` for a **stored** run
- [ ] TEST: two runs with the same request produce the same id; different criteria_version produces a different id
- [ ] IMPLEMENT: store results in `backend/api/data/runs/<citation_id>.json` (you own this directory), written on each `POST /v1/windows`
- [ ] TEST: a citation for an unknown id returns 404 with a message that says the run was not found (this is a genuine resource miss, not a domain outcome)

### A7. Caching and rate limits (1 h)
- [ ] TEST: identical requests within a TTL hit cache and are faster; a cache flush changes nothing about the returned numbers (spec III.6 determinism)
- [ ] TEST: exceeding the rate limit returns 429 with `Retry-After`
- [ ] IMPLEMENT per spec IV.9; make the TTL and limit config values, not literals

### A8. The Python client (1.5 h)
- [ ] Implement `backend/client/launchwin.py` per spec IV.10: `from launchwin import windows; df = windows(target="SSO", site="canso", dates=("2026-10-04","2027-01-01"))` returns a DataFrame with the window columns
- [ ] TEST: client round-trips against a running app (use FastAPI's `TestClient`, not a live server)
- [ ] TEST: the client works **against the fixtures-only app** (no network beyond localhost) - this is the demo path
- [ ] TEST: `pip install -e .` then `python -c "from launchwin import windows"` works from a directory outside the repo (a researcher's notebook path)
- [ ] DEPENDENCY: pandas is acceptable as a client extra (`pip install launchwin[client]`), but the core API must not import pandas. TEST that `import launchwin` without pandas installed only fails at `windows()`, not at import - or just make pandas a hard dependency and document it. Choose and test one.

### A9. Determinism and provenance test - GATE G3 (1 h)
- [ ] TEST spec III.6, your half: run the same request twice, byte-compare all numeric fields, assert identical
- [ ] TEST: run after a cache flush, assert identical
- [ ] TEST: every response object carries constants_block, site and corridor values, criteria_version, vehicle_profile_id with row flags, and for weather-bearing ones `forecast_issue_time` and `horizon_label`
- [ ] TEST: `GET /v1/citation` for a stored run id reproduces exactly the constants used
- [ ] **GATE G3: all of the above green against the real ENGINE and WEATHER implementations (not stubs)**

### A10. Integration test - GATE G5 scaffold (1 h)
- [ ] Write `scripts/integration_test.py`: on a clean-clone assumption, it (1) verifies the fixtures validate, (2) boots the app with `TestClient`, (3) issues the canonical `POST /v1/windows` for SSO/POLAR/LEO, (4) asserts the LEO 45.1 case returns `reachable: false` with a plane-change penalty, (5) fetches site, weather and skill endpoints, (6) fetches citation for the run, (7) checks determinism, (8) exits non-zero on any failure with a readable message
- [ ] TEST: the script itself is tested by running it in CI-style locally: `python scripts/integration_test.py` must pass on fixtures even when ENGINE and WEATHER are stubs - so it is runnable from hour one and becomes the real gate as they land
- [ ] This is what you hand the final integrator for G5

### A11. Documentation (1 h)
- [ ] `backend/api/README.md`: how to run (`uvicorn backend.api.app:app`), the endpoint table, the error model in one paragraph, how to get a citation id, the fixture path, and the explicit statement of what is stubbed vs real at this commit
- [ ] `backend/api/DONE.md`: shipped vs known-unfinished

---

## Data tasks summary

1. `tests/contract/schemas/*.json` - the frozen contract. Source: spec Part IV, verbatim.
2. `backend/api/data/runs/` - stored citation records (generated).
3. Fixture wiring: you own the directory, FRONTEND owns the content, you validate theirs.

## Test plan

```bash
pytest tests/contract/ -q                # G0 and after
pytest backend/api/ -q                   # all green
python scripts/integration_test.py       # G5 gate, works on fixtures
python -c "from launchwin import windows; print(windows(target='SSO', site='canso', dates=('2026-10-04','2026-11-01')))"  # researcher path
# error model spot checks
curl -s -o /dev/null -w "%{http_code}" -X POST localhost:8000/v1/windows -d '{"target":{}}'   # 422
# then with a valid LEO 45.1 body: expect 200 with reachable:false
```

## Time budget

| Hours | Tasks |
|---|---|
| 0-2 | **A0 - GATE G0. Everything else is queued behind this. Do it first, commit, announce.** |
| 2-4 | A1, A2 |
| 4-6 | A3 (stub first), A4 (stub first) - unblocks FRONTEND to go live |
| 6-8 | A5, A6 |
| 8-9 | A7, A8 |
| 9-10 | A9 - G3 (needs ENGINE + WEATHER landed) |
| 10-11 | A10, A11 |

## What will go wrong

- **The schema drifts as ENGINE and WEATHER implement.** Rule: you change a schema only with a stated reason, you announce it before merging, and you check the other two workflows' output against it. A silent schema change breaks two people at once.
- **You are tempted to return 400 because a target is unreachable.** You may not. It is a domain answer: 200 with `reachable: false`. Test IV.8 rule 1 protects this.
- **ENGINE or WEATHER slips.** Your stubs keep the system demoable. The `engine_version` field and the fixture path exist so nobody presents stub output as real. Never let a stub ship without that marker.
- **503 during judging.** The fixture path must activate. Test the outage branch explicitly (A4).

## Rules

- TDD: failing test, then code. Never code first.
- Spec Part IV is the contract. Where the spec and reality conflict, open an issue; do not silently diverge.
- No credentials in code; the app reads reads paths and keys from environment.
- Formal register. No em dashes. No emojis.
- You are the one who will run `scripts/integration_test.py` for the final integrator. Make its failure messages tell a developer exactly what broke.
