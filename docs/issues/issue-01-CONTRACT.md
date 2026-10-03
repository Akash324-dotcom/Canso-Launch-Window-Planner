# [CONTRACT][G0] Freeze the /v1 API contract: schemas, shared objects, fixture shapes

**Assigned to:** Rafat (GitHub: TBD). **Backup:** Anand. **This is the first issue of the project: nothing else starts until it is merged and tagged.**

**Owner role:** API developer. **Blocks:** ENGINE, WEATHER, FRONTEND all build against this.
**Gate:** G0. Nothing else starts until this is merged and tagged.

---

## Context

We are building a launch-window decision engine for Spaceport Nova Scotia (Canso, 45.3 N, 61.0 W) for the Mission Accepted hackathon (MDA Space / CSA / ShiftKey Labs, submission Sunday 4 Oct 13:30 ADT). Four developers work in parallel; this issue defines the interface that makes that possible. Full scientific specification is the `C2_framework_and_build_spec.md` document (891 lines) in the team drive; Part IV is the authoritative source for every schema below.

## What you deliver

1. `tests/contract/schemas/*.json` - JSON Schema files for all six endpoints, transcribed **verbatim** from spec Part IV.
2. `tests/contract/test_schemas.py` - tests proving the schemas accept good examples and reject bad ones.
3. `docs/00_INTEGRATION_CONTRACT.md` - committed to the repo (a copy exists in the team drive).
4. Root `pyproject.toml` - package `launchwin`, python >=3.11, deps fastapi, uvicorn, pydantic, httpx, pytest.
5. Tag `g0-contract-frozen` on the merge commit.

## The six schemas, with the fields you must include

### 1. `windows_request.json` - POST /v1/windows body
```
target: { type: "LEO"|"POLAR"|"SSO"|"CUSTOM", h_t_km: number|null,
          i_t_deg: number|null, raan_deg: number|null, ltan_hours: string|null }
site: string                      (default "canso")
date_range: { start: "YYYY-MM-DD", end: "YYYY-MM-DD" }
vehicle_profile_id: string
corridor: { A_min_deg: number|null, A_max_deg: number|null }   (optional)
criteria_version: string|null
raan_tolerance_deg: number|null
include_weather: boolean          (default true)
```
`h_t_km` and `i_t_deg` required when type=CUSTOM. All numerics are JSON numbers (float64). Dates are ISO strings.

### 2. `windows_response.json` - POST /v1/windows response (HTTP 200 ALWAYS for well-formed requests, including unreachable targets)
```
reachable: boolean
plane_change_dv_ms: number|null          (non-null iff reachable=false and penalty computable)
sso_consistency_warning: object|null
windows: [ {
  t_liftoff_utc: ISO-8601 string
  t_injection_utc: ISO-8601 string
  raan_deg: number
  azimuth_deg: number                    (inertial)
  azimuth_compass_deg: number            (rotating frame)
  reached_inclination_deg: number
  window_width_s: number
  window_center_shift_s: number          (fixed-point term)
  liftoff_instant_error_min: number      (the Vehicle Duration bonus, quantified)
  p_success: number                      [0,1]
  p_success_components: { weather: number, range: number, conjunction: number }
  horizon_label: "FORECAST"|"CLIMATOLOGY"
  forecast_issue_time: ISO-8601|null
  constraint_fired: string|null          enum: fixed_point_no_convergence | hazard_area |
                                          conjunction_flagged | criteria_version_missing
  screens: { hazard: "pass"|"fail", conjunction: "clear"|"flagged", notam: "none"|"active" }
} ]
constants_block: {...}                   (see shared object below)
provenance_block: {...}                  (see shared object below)
engine_version: string
computation_ms: number
```
Semantics to encode in tests: empty `windows` with `reachable: true` means "no crossing in range within tolerance" and is a valid result, not an error.

### 3. `constants_block.json` - shared object, on every result-bearing response
```
J2: 1.08262668e-3
GM: 3.986004418e14
R_e: 6378137.0
omega_sid_rad_s: 7.292115e-5
gmst_model: "IAU_1982"
citation_id: "run_YYYYMMDD_..."
source: { each constant: source document }
```

### 4. `provenance_block.json` - shared object
```
site: object, corridor: object, criteria_version: string,
vehicle_profile_id: string, row_flags: object, source_files: [string]
```

### 5. `ephemeris_response.json` - GET /v1/orbits/{id}/ephemeris?start=&end=&step_s=300
```
orbit_id: string
frame: "ECEF"
points: [ { t_utc: ISO-8601, lat_deg: number, lon_deg: number, alt_km: number } ]
ground_track_valid: boolean              (false beyond 3-day horizon for conjunction-derived tracks)
constants_block: {...}
```
Valid ids: `leo45`, `polar879`, `sso981`, plus custom ids created implicitly by POST /v1/windows.

### 6. `weather_probability_response.json` - GET /v1/weather/probability?date=&site=
```
date: "YYYY-MM-DD", site: "canso"
p_launch: number
horizon_label: "FORECAST"|"CLIMATOLOGY"
forecast_issue_time: ISO-8601|null
ensemble_size: number|null               (null in CLIMATOLOGY)
criteria_version: string
components: [ { criterion_id: string, p_violation: number, flag: "VERIFIED"|"PROXY" } ]
source: "open_meteo"|"gdps"|"era5_climatology"|"snapshot_cache"
```

### 7. `skill_response.json` - GET /v1/validation/skill?period_start=&period_end=&lead_max=10
```
period: { start, end }
verification_source: "era5"
reference_forecast: "climatology_base_rate"
base_rate: number
skill_series: [ { lead_time_days: number, bs: number, bs_ref: number, bss: number, n_cases: number } ]
reliability_bins: [ { p_center: number, observed_freq: number, n: number } ]
```

### 8. `site_response.json` - GET /v1/site
```
name, lat, lon, alt_m,
corridor: { A_min_deg, A_max_deg, source, flag }    (flag ASSUMPTION where the EA is qualitative)
operating_hours, car_references: [ "602.43", "602.44" ]
```

## The error model (encode as tests in the API issue, document here)

- Rule 1: any physics outcome returns **200** with the body above. `reachable:false`, empty windows, `constraint_fired` are domain answers, NEVER HTTP errors.
- Rule 2: HTTP 4xx reserved for malformed input: 422 schema violation, 404 unknown orbit/site/run id, 429 rate limit, 503 upstream outage (with Retry-After and the offline fixture path active).
- Rule 3: constraint outcomes live in the body, never as HTTP status.

## The three seams (these are the compatibility guarantees)

**Seam 1 - function signatures, frozen:**
```python
# backend/engine/__init__.py
def compute_windows(request: dict) -> dict:
    """Spec IV.1 request body -> response body MINUS:
    p_success, p_success_components.weather, horizon_label, forecast_issue_time,
    constants_block, provenance_block. Pure. No network."""

# backend/weather/__init__.py
def probability(date_iso: str, site: str, criteria_version: str | None = None) -> dict
def hindcast(period_start: str, period_end: str, lead_max: int = 10) -> dict
```
**Seam 2 - the schemas above are the source of truth.** ENGINE and WEATHER validate their own output against them; schema changes are announced before merge.
**Seam 3 - fixtures.** `backend/fixtures/{windows,weather,skill,site,ephemeris}.json` are the demo floor. API owns the directory, FRONTEND owns the content, ENGINE/WEATHER keep them representative.

## Task list (TDD)

- [ ] Create `tests/contract/` and a failing test that loads a schema file - RED
- [ ] Write all schema files from the spec, section by section. Commit in two batches: windows first (blocks ENGINE), then the rest
- [ ] Write `good/*.json` and `bad/*.json` examples per schema; tests assert accept/reject
- [ ] Root `pyproject.toml`; verify `pip install -e .` in a clean venv
- [ ] Commit `docs/00_INTEGRATION_CONTRACT.md` (copy from the team drive if needed)
- [ ] Merge, tag `g0-contract-frozen`, announce to the other three with the tag name
- [ ] Open a short comment in this issue listing the tag SHA and any field you had to interpret (the spec is authoritative; ambiguity is resolved here, once, in writing)

## Definition of done

1. `pytest tests/contract/` green.
2. All six endpoint schemas exist with all fields above.
3. `pyproject.toml` installs clean in a fresh venv.
4. Tag pushed; a comment on this issue states the tag and lists interpretations.
5. `docs/00_INTEGRATION_CONTRACT.md` is in the repo.

## Time budget: 1.5 hours. This is the first task of the whole project - do it before anything else.

## Rules

- Transcribe the spec; do not improvise field names. If a field is genuinely ambiguous, choose the spec-consistent reading, write your interpretation in the issue comment, and message the team.
- No em dashes. No emojis. Formal register.
- The `engine_version` field must let a stub be distinguishable: stub responses carry `"engine_version": "stub"`.

## Subagent dispatch and anti-corner-cutting law (applies to every task above)

- Dispatch each task to a subagent with this issue's text plus that task's exact acceptance test. The subagent sees nothing else, so quote into its prompt the context it needs: the spec section, the frozen signature, the expected values.
- A subagent may not close a task on the strength of "it runs". The acceptance test is the closing criterion; paste its output into progress.md.
- No partial development. A module is done when its tests pass and its README states what it does and does not claim. Anything half-written is marked UNDONE in progress.md and must not be merged.
- No test weakening. If a test fails, fix the code or reopen the spec question. Never loosen a tolerance, delete an assertion, or skip a failing test to make a suite green.
- No hard-coded values where the contract requires configuration.
- No TODO placeholders in merged code. Cut the feature and record it in DONE.md.
- Every claim is marked PROVED, SKETCHED or CONJECTURE per spec II.9. Every citation is resolved by title via Crossref, never from memory.
- Every task update appends to progress.md with the exact command run and its observed output.
