# API workflow log

Appended after every task, as required by `docs/00_INTEGRATION_CONTRACT.md` section 8, so that a
session restart loses nothing.

## G0 contract

Issue: `docs/issues/issue-01-CONTRACT.md`, "[CONTRACT][G0] Freeze the /v1 API contract".
Date of this entry: 3 October 2026. Status: schemas written, contract suite green, nothing committed
and nothing tagged by this session. The tag `g0-contract-frozen` and the issue comment are still
outstanding and are listed under item 27 below.

### What shipped

| Path | Purpose |
|---|---|
| `tests/contract/schemas/windows_request.json` | POST /v1/windows request body, spec IV.1 |
| `tests/contract/schemas/windows_response.json` | POST /v1/windows response body, spec IV.1 |
| `tests/contract/schemas/constants_block.json` | shared constants object, spec IV |
| `tests/contract/schemas/provenance_block.json` | shared provenance object, spec IV |
| `tests/contract/schemas/ephemeris_response.json` | GET /v1/orbits/{id}/ephemeris, spec IV.2 |
| `tests/contract/schemas/weather_probability_response.json` | GET /v1/weather/probability, spec IV.3 |
| `tests/contract/schemas/skill_response.json` | GET /v1/validation/skill, spec IV.4 |
| `tests/contract/schemas/site_response.json` | GET /v1/site, spec IV.5 |
| `tests/contract/examples/good/*.json` | 20 accepted examples, at least 2 per schema |
| `tests/contract/examples/bad/*.json` | 43 rejected examples, at least 3 per schema, one broken rule each |
| `tests/contract/test_schemas.py` | schema validity, example acceptance and rejection, auto-discovered |
| `pyproject.toml` | package `launchwin` 0.1.0, python >=3.11, runtime deps, dev extra, pytest testpaths |
| `backend/__init__.py`, `backend/api/__init__.py` | empty package markers so that setuptools discovers `backend*` |

Nothing outside those paths was created or edited. `docs/00_INTEGRATION_CONTRACT.md` was already in
the repository, so definition-of-done item 5 of the issue is satisfied by the existing file.

### Commands run and their output

Contract suite, the G0 acceptance command:

```
$ .venv/bin/python -m pytest tests/contract -q
......................................................................   [100%]
70 passed in 0.07s
```

Whole repository with the configured testpaths, which proves `testpaths = ["tests", "backend"]`
resolves and that the empty `backend` package collects nothing yet:

```
$ .venv/bin/python -m pytest -q
......................................................................   [100%]
70 passed in 0.07s
```

Per bad example rejection audit, showing that every bad example is rejected and that each one
breaks a single rule (the site car_references case reports two array items of the same rule):

```
$ .venv/bin/python -c "import sys; sys.path.insert(0, 'tests/contract'); import test_schemas as t; [print(p.name, 'errors=%d' % len(list(t.validator_for(t.schema_name_for(p.name, sorted(t.load_schemas()[0]))).iter_errors(t.load_example(p))))) for p in sorted(t.BAD_DIR.glob('*.json'))]"
constants_block_bad_extra_field.json errors=1
constants_block_bad_gmst_model_enum.json errors=1
constants_block_bad_j2_wrong_type.json errors=1
constants_block_bad_missing_citation_id.json errors=1
ephemeris_response_bad_frame_enum.json errors=1
ephemeris_response_bad_missing_ground_track_valid.json errors=1
ephemeris_response_bad_point_extra_field.json errors=1
ephemeris_response_bad_point_latitude_out_of_range.json errors=1
ephemeris_response_bad_point_t_utc_format.json errors=1
provenance_block_bad_extra_field.json errors=1
provenance_block_bad_missing_criteria_version.json errors=1
provenance_block_bad_row_flags_wrong_type.json errors=1
provenance_block_bad_source_files_item_type.json errors=1
site_response_bad_car_references_item_type.json errors=2
site_response_bad_corridor_extra_field.json errors=1
site_response_bad_corridor_missing_a_max.json errors=1
site_response_bad_latitude_out_of_range.json errors=1
site_response_bad_missing_operating_hours.json errors=1
skill_response_bad_bs_out_of_range.json errors=1
skill_response_bad_extra_field.json errors=1
skill_response_bad_missing_base_rate.json errors=1
skill_response_bad_period_end_date_format.json errors=1
skill_response_bad_verification_source_enum.json errors=1
weather_probability_response_bad_component_flag_enum.json errors=1
weather_probability_response_bad_component_p_violation_out_of_range.json errors=1
weather_probability_response_bad_date_format.json errors=1
weather_probability_response_bad_extra_field.json errors=1
weather_probability_response_bad_p_launch_out_of_range.json errors=1
weather_probability_response_bad_source_enum.json errors=1
windows_request_bad_custom_target_missing_i_t_deg.json errors=1
windows_request_bad_custom_target_null_i_t_deg.json errors=1
windows_request_bad_date_range_start_format.json errors=1
windows_request_bad_extra_field.json errors=1
windows_request_bad_missing_vehicle_profile_id.json errors=1
windows_request_bad_target_type_enum.json errors=1
windows_response_bad_component_weather_out_of_range.json errors=1
windows_response_bad_constraint_fired_enum.json errors=1
windows_response_bad_extra_field.json errors=1
windows_response_bad_horizon_label_enum.json errors=1
windows_response_bad_missing_computation_ms.json errors=1
windows_response_bad_p_success_out_of_range.json errors=1
windows_response_bad_screens_hazard_enum.json errors=1
windows_response_bad_t_liftoff_utc_format.json errors=1
```

### Interpretations

Every place where the specification was ambiguous, or where it differs from the issue field list.
The specification is authoritative; where it differs from the issue, the specification wins and the
difference is recorded here.

1. **Site geometry field names, spec against issue.** Spec IV.5 names the geometry `phi_s_deg`,
   `lambda_s_deg`, `h_s_m`. The issue names them `name, lat, lon, alt_m`. The schema freezes the spec
   names, so `lat`, `lon` and `alt_m` are not in the contract. `name` is kept because neither source
   contradicts it and no spec name exists for a site identifier. ENGINE must emit `phi_s_deg`,
   `lambda_s_deg`, `h_s_m`.
2. **Skill response is larger in the spec than in the issue.** Spec IV.4 carries `roc_points`,
   `skill_horizon_measured_days` and `constants_block`; the issue field list omits all three. All
   three are frozen and required. WEATHER's `hindcast` output must therefore include them.
3. **`verification_source` and `reference_forecast`.** Spec IV.4 writes them as single quoted values
   (`"era5"`, `"climatology_base_rate"`) rather than as unions, so they are frozen as single value
   enums. Widening either is a schema change announced through Seam 2, not a silent edit.
4. **`site` on the weather response.** Spec IV.3 writes `"site": "canso"`, but IV.1 takes a site id
   from configuration and IV.7 rule 2 reserves 404 for an unknown site id. A single value enum would
   make that 404 unreachable, so the field is a string with `"default": "canso"` and its value is not
   frozen.
5. **`constants_block.source`.** The spec block lists six fields and no `source`; the issue adds
   `source: { each constant: source document }`. The issue reading is kept, because requirement 1 and
   spec II.10 need a per constant source, and the block is written `{...}` in the issue so the map
   itself stays open (`additionalProperties: true`). `source` is required, the keys inside it are not
   frozen.
6. **Required set of `windows_request`.** The spec gives defaults for `site`, `criteria_version`,
   `raan_tolerance_deg` and `include_weather`, so a client may omit them and they are not required.
   `corridor` is marked optional in the spec and stays optional. `target`, `date_range` and
   `vehicle_profile_id` are required.
7. **CUSTOM target rule.** `type` is the only unconditional member of `target`. `h_t_km` and
   `i_t_deg` are required and non-null only when `type` is `CUSTOM`, encoded with `if` on
   `type == CUSTOM` and `then` requiring both as `number`. Two bad examples cover the absent case and
   the null case. `raan_deg` and `ltan_hours` stay nullable for every target type.
8. **`ltan_hours` carries no pattern.** The spec gives `"10:30"` as an example only. A pattern would
   be an invented constraint, so the field is `string | null`.
9. **No conditional on `reachable`.** Spec IV.1 says `plane_change_dv_ms` is non-null when
   `reachable` is false and the penalty is computable, so it may be null on an unreachable result. No
   if/then links the two fields, because one would contradict the spec.
10. **Empty `windows`.** The `windows` array has no `minItems`. Spec IV.1 semantics make an empty
    array with `reachable: true` an informative result, not an error, and it is frozen as valid and
    asserted in `test_empty_windows_with_reachable_true_is_a_valid_result`.
11. **`p_success_components.range` and `.conjunction`.** Spec IV.1 types them as `number` with the
    comment "0 or 1 (pre-screen, II.8)". They are frozen as numbers in [0, 1] with
    `minimum`/`maximum` rather than as the two value enum 0 or 1, per the contract task, so a
    pre-screen probability that is not exactly binary is still expressible.
12. **Numeric ranges the spec does not state.** Frozen as definitional, not as physics:
    `lat_deg` in [-90, 90] and `lon_deg` in [-180, 180] on ephemeris points, `base_rate`, `bs`,
    `bs_ref`, `p_center`, `observed_freq`, `pod` and `far` in [0, 1], `n_cases`, `n`, `roc_points`
    counts and the site `car_references` items as strings, `n_cases` and `n` as non-negative
    integers, and `lead_time_days` at or above 0. `bss` is left unbounded because Brier skill
    score is signed.
13. **The constants themselves are not frozen as values.** `J2`, `GM`, `R_e` and `omega_sid_rad_s`
    are typed as `number` with the spec values shown in `description`. Freezing them with `const`
    would turn a corrected constant into a contract break, and the spec requires constants to come
    from configuration rather than from source.
14. **`site_response` is left open.** Spec IV.5 enumerates the body in prose (coordinate variants
    with sources, EA reference URLs, launch rate cap, corridor polygon vertices) without giving field
    names. The root object therefore stays open (`additionalProperties: true`) instead of inventing
    names. `corridor` inside it is closed, because the issue gives its four fields.
15. **`operating_hours` is untyped in both sources.** Spec IV.5 says "nominal operating hours
    (07:00-12:00 local)" and the issue gives only the name. The schema admits `string | object` and
    the ambiguity is recorded rather than resolved by invention. Both good site examples show one
    shape each.
16. **`car_references` values are not frozen.** The spec names 602.43 and 602.44 and both good
    examples carry them, but the array holds plain strings so that citing a further regulation does
    not break the contract.
17. **Objects the spec writes as bare `object` or `{...}`.** Left open with
    `additionalProperties: true`: `windows_response.sso_consistency_warning`,
    `constants_block.source`, and `provenance_block.site`, `provenance_block.corridor` and
    `provenance_block.row_flags`. Their contents are owned by ENGINE and WEATHER.
18. **`additionalProperties: false` scope.** Applied to `windows_request` and its `target`,
    `date_range` and `corridor`; to `windows_response` and each window, `p_success_components` and
    `screens`; to `ephemeris_response` and each point; to every array item of
    `weather_probability_response`; to `skill_response` and its `period`, `skill_series` items,
    `reliability_bins` items and `roc_points` items; to `constants_block` and `provenance_block`;
    and to `site_response.corridor`. Left open only where item 14 and item 17 say so.
19. **`engine_version` is a free string.** The issue rule that stub output carries
    `"engine_version": "stub"` is a convention, not an enumeration, so no value set is frozen. The
    stub is asserted by `test_stub_responses_are_distinguishable` and shown by the good example
    `windows_response_good_stub.json`.
20. **`date-time` enforcement had to be supplied.** The pinned jsonschema 4.26.0 in `.venv` ships a
    `date` checker but no `date-time` checker, because that one needs the optional
    rfc3339-validator package, which is absent and may not be installed. `test_schemas.py`
    therefore registers an equivalent strict check on a `FormatChecker` instance
    (`FormatChecker.checks`), requiring ISO-8601 with a `Z` or numeric offset suffix as spec IV.1
    demands, and only when the built-in checker is missing. If rfc3339-validator is ever installed,
    the built-in checker wins. Verified load bearing: without the format checker
    `windows_response_bad_t_liftoff_utc_format.json` validates, so the suite would be vacuous
    without it.
21. **Reference resolution.** Each schema carries `"$id"` equal to its file name, and
    `test_schemas.py` builds a `referencing.Registry` from every schema file, so
    `"$ref": "constants_block.json"` and `"$ref": "provenance_block.json"` resolve without any
    network retrieval. `test_shared_objects_are_referenced_and_never_copied` asserts that the shared
    fields are never declared inline anywhere else.
22. **Package name.** The issue and `docs/03_WORKFLOW_API.md` ask for the project name `launchwin`,
    while spec IV.9 names the client package `c2window`. `pyproject.toml` uses `launchwin` as
    instructed. The client import name for task A8 remains open and needs a decision before A8.
23. **Schema count.** The issue says "six endpoints" and "six schemas" and then lists eight schema
    files. The eight listed files are delivered. Spec IV.6 `/v1/citation` is deliberately not
    frozen here, because it is not in this issue's file list; see item 27.
24. **`skill_response` has no `lead_max` echo.** The spec takes `lead_max=10` as a query parameter
    and does not echo it in the body, so no field was added for it.
25. **Example values are illustrative.** All numeric values in the examples are placeholders that
    demonstrate the shape. Corridor azimuth bounds, the citation id and the skill series numbers
    carry no claim. No citation was invented: `constants_block.source` in the examples points at the
    spec II.10 constants table rather than at a literature reference, because citation resolution is
    by title through Crossref and is not this task's work.
26. **`pip install -e .` was not verified.** `setuptools` is not installed in `.venv` and installing
    it is not permitted here, so the build backend was exercised only by writing a conventional
    `pyproject.toml` with `backend*` package discovery. Definition-of-done item 3 of the issue is
    therefore unverified by execution and must be checked in a clean venv before the gate is called
    done. `pytest tests/contract/` is proved green.
27. **Left undone, deliberately.** Tag `g0-contract-frozen`, the push, and the issue comment quoting
    the tag SHA with this interpretation list. Committing and tagging were outside the instructions
    given for this session. Also not delivered: a schema for `GET /v1/citation` (spec IV.6), which
    this issue does not list, and the consumer tests `tests/contract/test_engine_schema.py` and
    `tests/contract/test_weather_schema.py`, which are the obligation of ENGINE and WEATHER under
    Seam 2 and not of this issue.
### Update to interpretation 26
`pip install -e .` verified by the lead: `uv venv` in a fresh temp dir, `uv pip install -e .`, then `python -c "import backend.api, fastapi, httpx, pydantic, uvicorn"` run from `/tmp` printed `install ok`.

## A1-A3 provenance, app skeleton and the stubbed window route

Issue: `docs/issues/issue-04-API.md`, tasks A1, A2 and A3 only. A4 to A11 are untouched and
nothing was committed by this session. The test suite is written before the code it tests; the
red observations are quoted below in the order they happened.

### What shipped

| Path | Purpose |
|---|---|
| `backend/api/provenance.py` | `constants_block`, `provenance_block`, the deterministic `citation_id`, the config hash, `assert_complete` |
| `backend/api/config.py` | the only reader of `backend/api/data`, and the `Settings` seam every other module takes |
| `backend/api/schemas.py` | loader for the frozen schemas under `tests/contract/schemas`, with a registry and an enforcing `date-time` format checker |
| `backend/api/errors.py` | the exception vocabulary and the spec IV.7 status mapping, each carrying the body fields its handler needs |
| `backend/api/app.py` | the FastAPI app, the `/v1` prefix, `openapi_url=/v1/openapi.json`, and `register_exception_handlers` |
| `backend/api/request_model.py` | application of the spec IV.1 request defaults |
| `backend/api/stubs.py` | the offline seam: fixture readers, target resolution, the reachability predicate of spec II.4, the plane-change penalty of spec II.5, the SSO consistency check of spec II.6, and the weather composition |
| `backend/api/routes/__init__.py`, `backend/api/routes/windows.py` | the `/v1` routers and `POST /v1/windows` |
| `backend/api/data/constants.json` | the five constants and their sources, the only place those values exist |
| `backend/api/data/service.json` | defaults, target classes, the spec II.6 inclination table, fixture paths, Retry-After durations |
| `backend/api/data/sites/canso.json` | site geometry, corridor, CAR references and row flags, until ENGINE lands its own file |
| `backend/api/tests/test_provenance.py` | A1, 36 tests |
| `backend/api/tests/test_error_model.py` | A2, 39 tests |
| `backend/api/tests/test_windows.py` | A3 and the requested additions, 24 tests |
| `backend/api/tests/test_fixtures.py` | every fixture against its frozen schema, 15 tests |
| `backend/fixtures/windows.json` | shape-complete stub response, three SSO windows from Canso, `engine_version` stub |
| `backend/fixtures/weather.json`, `skill.json`, `site.json`, `ephemeris.json` | copies of the most complete good examples |

`backend/fixtures/__init__.py` was not created: the fixtures are read by path, not imported, so a
package marker would be unused.

### Commands run and their output

The first run of the A1 tests, before any of the modules existed:

```
$ .venv/bin/python -m pytest backend/api/tests/test_provenance.py -q
ImportError while loading conftest '.../backend/api/tests/conftest.py'.
backend/api/tests/conftest.py:11: in <module>
    from backend.api.app import create_app
E   ModuleNotFoundError: No module named 'backend.api.app'
1 error in 0.35s
```

The A2 and A3 tests in place, after the modules existed but before two defects were fixed (the
reachable inclination band was built with its endpoints the wrong way round, and one test referred
to a renamed attribute):

```
$ .venv/bin/python -m pytest backend/api/tests -q
3 failed, 72 passed, 1 warning in 0.14s
```

The A3 tests, before the route reported the offline documents it had read:

```
$ .venv/bin/python -m pytest backend/api/tests/test_windows.py -q
1 failed, 22 passed, 1 skipped, 1 warning in 0.09s
```

The fixture tests, before the fixture set was complete:

```
$ .venv/bin/python -m pytest backend/api/tests/test_fixtures.py -q
2 failed, 13 passed, 1 warning in 0.03s
```

The API suite, the acceptance command for this issue:

```
$ .venv/bin/python -m pytest backend/api -q
113 passed, 1 skipped, 1 warning in 0.20s
```

The contract suite, unchanged by this session and still green:

```
$ .venv/bin/python -m pytest tests/contract -q
70 passed in 0.08s
```

The whole repository with the configured testpaths, which is the done condition:

```
$ .venv/bin/python -m pytest -q
183 passed, 1 skipped, 1 warning in 0.52s
```

The one skip is `test_the_live_engine_path_produces_schema_valid_output`, gated on
`backend.engine.compute_windows` existing, per the A3 instruction to skip gracefully until ENGINE
lands. Its mirror image, `test_the_stub_is_the_served_path_until_the_engine_lands`, is the one that
runs today and asserts `engine_version == "stub"`.

The application object imports the way uvicorn will import it:

```
$ .venv/bin/python -c "from backend.api.app import app; print(app.title)"
Launch window decision engine
```

### Interpretations

Numbering continues from the G0 list above.

28. **The service validates against `tests/contract/schemas` at run time.** Seam 2 makes those files
    the contract for everyone, so `backend/api/schemas.py` loads them rather than keeping a second
    copy that could drift. The directory is `LAUNCHWIN_CONTRACT_DIR` if set, otherwise the
    repository path. The consequence, stated plainly: the deployed service reads that directory, so
    a deployment must ship it. A copy under `backend/api/data/contract` was deliberately not made,
    because two copies of a frozen contract is the drift risk the freeze exists to prevent.
29. **`citation_id` is hashed over the effective request.** The hash input is the request after the
    spec IV.1 defaults have been applied, the constants including their recorded sources, and the
    whole service configuration. The consequence is deliberate: a request that omits `site` and the
    same request that states `site: "canso"` produce the same identifier, because they are the same
    run. `test_the_same_request_with_and_without_a_default_gives_the_same_citation_id` asserts it.
30. **The date part of `citation_id` is the request start, never the clock.** `run_YYYYMMDD_` where
    the date is `date_range.start` with the hyphens removed, followed by the first twelve hexadecimal
    characters of the SHA-256 of the canonical JSON (sorted keys, no insignificant whitespace) of
    request, constants and configuration. Spec IV shows the shape `run_20261003_...`, which is a
    different date from any request in the frozen examples; the specification is a shape, not a
    promise to stamp today's date, and a clock-derived identifier could not be reproduced.
31. **A corridor bound supplied in the request is recorded as unsourced.** Spec II.10 wants a source
    for every value. A bound that arrived in the request has no citation, so the bound takes the
    value from the request, the corridor `source` string says so, and its `row_flags` entry becomes
    `UNSOURCED_REQUEST_OVERRIDE` instead of the `ASSUMPTION` that was read from the site file. The
    frozen schema leaves `row_flags` open, which is what makes the extra value expressible.
32. **Three of the four weather fields cannot be null, so they take neutral values.** Spec IV.1 and
    the frozen schema type `p_success`, `p_success_components.weather` and `horizon_label` as
    non-nullable. With `include_weather` false the composition therefore sets `weather` to 1.0
    (weather imposes no penalty because it was excluded), `p_success` to the product of the two
    deterministic pre-screens `range` and `conjunction`, and `horizon_label` to `CLIMATOLOGY`, which
    is the honest label for a probability no forecast produced. `forecast_issue_time` is nullable and
    is null. This is the schema-valid neutral value the task brief asks for; the alternative,
    dropping the fields, would break the frozen response schema.
33. **The stub composes weather from the shipped snapshot.** With `include_weather` true and no
    WEATHER module, the four weather fields come from `backend/fixtures/weather.json`, whose
    `source` is `snapshot_cache`, the value spec IV.3 reserves for a recorded forecast echoed rather
    than refetched. `backend/fixtures/windows.json` is authored so that its own `p_success` is
    already that product, which makes the recomposition idempotent and is asserted by
    `test_fixture_windows_and_the_weather_snapshot_agree`.
34. **The stub returns rows only for the orbit class they describe.** The offline floor ships three
    SSO rows. Echoing an SSO row for a POLAR request would be a wrong answer dressed as a right one,
    so a resolved target whose inclination is outside `fixture_inclination_tolerance_deg` of a row's
    `reached_inclination_deg` gets the empty window list, which spec IV.1 calls an informative valid
    result. The tolerance is 0.8 deg, half the 1.6 deg span of the published inclination table across
    its 500 to 900 km range. Known limitation for FRONTEND: the POLAR preset renders "no window in
    range" until ENGINE supplies per-class rows at G1.
35. **The reachability interval is ordered by value, not as spec II.4 writes it.** Spec II.4 states
    the reachable set as `[i(A_max), i(A_min)]`. With the shipped corridor of 90 to 200 deg the map
    `i(beta) = arccos(cos(phi_s) sin(beta))` is ascending rather than descending, so the two
    endpoints are ordered by value and the set is unchanged. The result reproduces the
    specification's own check that a bound of 200 deg caps the reachable inclination at about
    104 deg: the computed upper end is 103.92 deg.
36. **The plane-change penalty is computed by the stub.** Spec IV.1 makes `plane_change_dv_ms`
    non-null when an unreachable target's penalty is computable, and spec III.5 pass criteria name
    26.8 m/s within 1 m/s. The stub computes spec II.5 exactly, `2 v_c sin(Delta_i / 2)` with
    `v_c = sqrt(GM / (R_e + h_t))` from the constants block, which gives 26.36 m/s for the advertised
    LEO 45.1 deg class at 600 km, inside the specification's tolerance. The formula is the
    specification's; the reachability verdict it accompanies is PROVED as algebraic in
    `docs/00_INTEGRATION_CONTRACT.md` section 5, while the magnitude belongs to ENGINE and will
    replace this value when ENGINE lands. The test asserts the specification's own criterion rather
    than the stub's number. The class altitudes that make the computation possible are transcribed
    from the spec III drift table into `service.json`, with their sources.
37. **The SSO consistency check reads a published table, and interpolation is refused.** Spec II.6
    tabulates the altitude-inclination coupling, so the table is transcribed into
    `service.json` and the stub reads the nearest row at or below the requested altitude. Nothing is
    interpolated, because an interpolated inclination would be a number the specification does not
    publish. The warning threshold is half the coarsest precision the table is quoted at, which is
    why an explicit `i_t_deg` of 98.1 at 600 km warns (the table says 97.8 at that altitude) while a
    consistent pair does not.
38. **Vehicle rows are reported as absent rather than invented.** ENGINE owns
    `backend/engine/data/vehicles/*.json`. Until it lands the API reads no vehicle rows, so
    `provenance_block.row_flags` carries only the site rows it actually read and the vehicle file is
    absent from `source_files`. The path is resolved so that the file appears by itself once
    ENGINE ships it. No row flag was fabricated to fill the block, which is the point of spec II.10.
39. **The criteria version is read from WEATHER when its file exists.** `service.json` names
    `backend/weather/data/criteria_v1.json` and the configured fallback version. While that file is
    absent the configured version is used and no criteria path is claimed in `source_files`; once
    WEATHER ships it, the version declared inside it wins and the file is listed. The criteria rows
    themselves are WEATHER's to compose at A4.
40. **The site document lives under `backend/api` until ENGINE lands its own.** The API owns
    `backend/api/data/sites/canso.json` and `Settings.site_path` prefers
    `backend/engine/data/site_canso.json` when that file exists, so the provenance block reports the
    file the engine actually reads. The corridor bounds are the spec II.3 defaults of 90 and
    200 deg with the specification's own ASSUMPTION flag, not the illustrative 100 and 140 of the
    frozen examples; the site altitude is the 0 m default of the spec II.10 row.
41. **429 and the orbit and run 404s are driven through the production handlers, not through
    endpoints that do not exist.** A2 requires those branches, but the endpoints that would raise
    them belong to A5, A6 and A7. `register_exception_handlers` is therefore a public function and
    the test builds a scratch application that calls it and then raises each exception, so the
    shipped handler code is what is asserted. The site 404 and the 503 are additionally exercised
    through the real route: an unknown site id is a 404, and an unreadable offline document is a
    503 whose body names the configured fixture path.
42. **`computation_ms` is measured and is the one field excluded from a byte comparison.** Every
    other numeric field is a pure function of the request and the configuration, which is what spec
    III.6 test 6 compares. A wall-clock duration cannot be, so the A9 determinism gate must exclude
    it rather than pretend otherwise. Recorded now so that A9 does not have to rediscover it.
43. **The stub fixture's own `citation_id` is an illustrative placeholder.** The route overwrites it
    on every response, as it overwrites both shared blocks. This is the same status as the numeric
    values of the frozen examples, recorded as interpretation 25 of the G0 list: the fixture
    demonstrates the shape and makes no claim about the value.
44. **`site_response` stays open, so `backend/fixtures/site.json` is a verbatim copy.** Spec IV.5
    enumerates the body in prose without field names, which is why the frozen schema leaves it open
    (G0 interpretation 14). The fixture therefore cannot add the EA reference URLs, the launch rate
    cap or the corridor polygon that spec IV.5 describes; A5 has to settle the names with ENGINE and
    announce any schema change through Seam 2 before this fixture gains fields.
45. **Not delivered, deliberately.** `backend/api/README.md` and `backend/api/DONE.md` are A11 and are
    not written, so the stub-versus-real statement required by the acceptance criteria of the issue
    is outstanding. There is no `GET /v1/site`, `GET /v1/weather/probability`,
    `GET /v1/validation/skill`, `GET /v1/orbits/{id}/ephemeris` or `GET /v1/citation` route; those are
    A4 to A6. There is no rate limiter, no cache and no run store; those are A6 and A7. The
    `weather.json`, `skill.json`, `site.json` and `ephemeris.json` fixtures exist because the task
    asked for the demo floor to be complete, and no endpoint reads three of them yet.
    `backend/api/data/service.json` carries `retry_after_s` values that nothing enforces until A7,
    so no test asserts a particular duration; the tests assert that the header is present and
    positive.
46. **`git status` was not clean before this session.** The working tree already carried
    `.oc-brief-contract.md` and `.oc-brief-api1.md` from the lead. Neither was edited here, and
    nothing was committed.

## A4-A7 weather, ephemeris, citation, cache and rate limits

Issue: `docs/issues/issue-04-API.md`, tasks A4, A5, A6 and A7 only. A8 to A11 are untouched and
nothing was committed by this session. Each test file was written before the module it tests, and
the red observations are quoted below in the order they happened.

### What shipped

| Path | Purpose |
|---|---|
| `backend/api/cache.py` | the three in-memory TTL caches of spec IV.8, the cache keys, the registry; a lifetime of zero switches a cache off |
| `backend/api/limits.py` | the sliding-window per-client budget of spec IV.8, with `enabled` to switch it off |
| `backend/api/middleware.py` | the read cache wrapper and the rate-limit route dependency |
| `backend/api/weather.py` | the WEATHER seam: cache, then the live module, then the recorded document, then a 503; and the window-weather composition with its outage policy |
| `backend/api/ephemeris.py` | the propagation seam probe and its contract check, the resampler, the documented closed form, and the query contract of spec IV.2 |
| `backend/api/orbits.py` | orbit identifiers, the preset matching, the in-process registry and the resolution order |
| `backend/api/citation.py` | the stored run records, the spec II.10 table serialised, and the citation read |
| `backend/api/site.py` | the spec IV.5 body assembled from the site document that was read |
| `backend/api/publish.py` | publishing the frozen schemas in the OpenAPI document for every route |
| `backend/api/routes/weather.py`, `ephemeris.py`, `site.py`, `citation.py` | the four new routers |
| `backend/api/data/provenance_table.json` | the spec II.10 table, in configuration, because the rule of construction says a result must be traceable to a row of it |
| `backend/api/data/ephemeris/polar879.json`, `sso981.json` | recorded offline ground-track segments for the polar and sun-synchronous classes |
| `backend/api/data/service.json` | the `cache`, `rate_limit`, `skill`, `orbits`, `ephemeris`, `site` and `runs_dir` sections, each value with its source |
| `backend/api/data/runs/.gitkeep` | the marker that keeps the ignored store directory in the repository |
| `backend/api/data/ephemeris/leo45.json` | the full-revolution leo45 record, alongside `polar879.json` and `sso981.json`; see interpretation 52 |
| `backend/api/README.md` | how to run it, the endpoint table, the error model, how to get a citation id, the fixture path, and the stub-versus-real statement |
| `backend/api/tests/test_weather.py` | A4, 26 tests |
| `backend/api/tests/test_ephemeris.py` | A5, 57 tests |
| `backend/api/tests/test_site.py` | A5, 20 tests |
| `backend/api/tests/test_citation.py` | A6, 25 tests |
| `backend/api/tests/test_cache_and_limits.py` | A7, 38 tests |
| `.gitignore` | the store directory, except its marker |

`tests/contract/` was not touched. Its suite is unchanged and still green.

### Commands run and their output

The A4 tests, before the module they import existed:

```
$ .venv/bin/python -m pytest backend/api/tests/test_weather.py -q
==================================== ERRORS ====================================
______________ ERROR collecting backend/api/tests/test_weather.py ______________
ImportError while importing test module '/Users/rafathossain/MDA_Mission_Accepted_Hackathon/backend/api/tests/test_weather.py'.
Traceback:
../.local/share/uv/python/cpython-3.12.13-macos-aarch64-none/lib/python3.12/importlib/__init__.py:90: in import_module
    return _bootstrap._gcd_import(name[level:], package, level)
backend/api/tests/test_weather.py:29: in <module>
    from backend.api import weather as weather_layer
E   ImportError: cannot import name 'weather' from 'backend.api' (/Users/rafathossain/MDA_Mission_Accepted_Hackathon/backend/api/__init__.py)
1 error in 0.05s
```

The A4 tests, after the modules existed but before the window route passed the cache registry and
before the neutral weather values were separated from the excluded ones:

```
$ .venv/bin/python -m pytest backend/api/tests/test_weather.py -q
7 failed, 18 passed, 1 skipped, 1 warning in 0.10s
```

The A5 tests, before the ephemeris module existed:

```
$ .venv/bin/python -m pytest backend/api/tests/test_ephemeris.py backend/api/tests/test_site.py -q
ERROR backend/api/tests/test_ephemeris.py
!!!!!!!!!!!!!!!!!!!!!!!! Interrupted: 1 error during collection !!!!!!!!!!!!!!!!!!!!
E   ImportError: cannot import name 'ephemeris' from 'backend.api'
1 warning, 1 error in 0.06s
```

The A6 tests, before the run store was written on every POST:

```
$ .venv/bin/python -m pytest backend/api/tests/test_citation.py -q
2 failed, 22 passed, 1 warning in 0.16s
```

The A7 tests, before the caches and the limiter were wired into the routes:

```
$ .venv/bin/python -m pytest backend/api/tests/test_cache_and_limits.py -q
21 failed, 17 passed, 1 warning in 0.19s
```

The whole repository after the A4 wiring, which caught a real determinism defect: the weather origin
was resolved once per row, so the first response listed the weather record in `source_files` and the
second, served from the cache, did not. A3's
`test_same_request_twice_gives_the_same_citation_id` caught it.

```
$ .venv/bin/python -m pytest -q
1 failed, 207 passed, 2 skipped, 1 warning in 0.79s
FAILED backend/api/tests/test_windows.py::test_same_request_twice_gives_the_same_citation_id
```

The whole repository after the A5 and A6 modules existed, before the ephemeris units were fixed. The
defects were a degrees-per-second multiplied by an argument in radians when anchoring a segment on
the site, and a modulo that mapped the last recorded sample onto the first.

```
$ .venv/bin/python -m pytest -q
3 failed, 231 passed, 2 skipped, 1 warning in 0.78s
```

The A5 ownership tests, written after the lead corrected the fixture edit and before the record was
moved. The two failures are the two halves of the correction: the leo45 base track resolved into
`backend/fixtures`, and that two-point record is not a full revolution.

```
$ .venv/bin/python -m pytest backend/api/tests/test_ephemeris.py -q
E       AssertionError: ('leo45', 'backend/fixtures/ephemeris.json')
E       assert False
E        +  where False = <built-in method startswith of str object at 0x7f...>('backend/api/')
E        +    where 'backend/api/'.startswith = <built-in method startswith of str object at 0x7f...>
E       AssertionError: assert PosixPath('.../backend/fixtures/ephemeris.json') not in {PosixPath('.../backend/api/data/ephemeris/polar879.json'), PosixPath('.../backend/api/data/ephemeris/sso981.json'), PosixPath('.../backend/fixtures/ephemeris.json')}
E       AssertionError: assert 45.28 < 0.0
E        +  where 45.28 = min([45.28, 48.11])
E       AssertionError: assert 48.11 == 45.1 +- 0.2
4 failed, 54 passed, 1 skipped, 1 warning in 0.33s
```

Per-module summaries of the final state:

```
$ .venv/bin/python -m pytest backend/api/tests/test_provenance.py -q
36 passed, 1 warning in 0.03s
$ .venv/bin/python -m pytest backend/api/tests/test_error_model.py -q
45 passed, 1 warning in 0.15s
$ .venv/bin/python -m pytest backend/api/tests/test_windows.py -q
23 passed, 1 skipped, 1 warning in 0.09s
$ .venv/bin/python -m pytest backend/api/tests/test_fixtures.py -q
15 passed, 1 warning in 0.01s
$ .venv/bin/python -m pytest backend/api/tests/test_weather.py -q
25 passed, 1 skipped, 1 warning in 0.10s
$ .venv/bin/python -m pytest backend/api/tests/test_ephemeris.py -q
56 passed, 1 skipped, 1 warning in 0.35s
$ .venv/bin/python -m pytest backend/api/tests/test_site.py -q
20 passed, 1 warning in 0.08s
$ .venv/bin/python -m pytest backend/api/tests/test_citation.py -q
25 passed, 1 warning in 0.11s
$ .venv/bin/python -m pytest backend/api/tests/test_cache_and_limits.py -q
38 passed, 1 warning in 1.18s
```

The API suite, the acceptance command for this issue:

```
$ .venv/bin/python -m pytest backend/api -q
283 passed, 3 skipped, 1 warning in 2.17s
```

The contract suite, unchanged by this session and still green:

```
$ .venv/bin/python -m pytest tests/contract -q
70 passed in 0.08s
```

The whole repository with the configured testpaths, which is the done condition:

```
$ .venv/bin/python -m pytest -q
353 passed, 3 skipped, 1 warning in 2.44s
```

The three skips, each the assertion that checks a live path the day its workflow lands:

```
$ .venv/bin/python -m pytest -q -rs
SKIPPED [1] backend/api/tests/test_ephemeris.py:543: backend.engine.ephemeris has not landed yet
SKIPPED [1] backend/api/tests/test_weather.py:348: backend.weather.probability has not landed yet
SKIPPED [1] backend/api/tests/test_windows.py:338: backend.engine.compute_windows has not landed yet
```

The application object imports the way uvicorn will import it:

```
$ .venv/bin/python -c "from backend.api.app import app; print(app.title)"
Launch window decision engine
```

The whole surface, exercised once end to end on the offline floor, which is what the A10 harness will
do: SSO 200 with three rows, POLAR 200 with the informative empty result, LEO 200 with
`reachable: false` and 26.38 m/s, site, weather, skill and all three ephemeris classes 200, a citation
with 24 items of the II.10 table, an unknown orbit 404 and a malformed body 422.

### Interpretations

Numbering continues from the G0 list and the A1-A3 list above.

46a. **Which offline documents the service reads changed in this session, and interpretation 45 is
    superseded on that point.** A4 to A7 add four readers of `backend/fixtures/`: `weather.json` on
    both the weather endpoint and the window route, `skill.json` on the validation endpoint,
    `windows.json` on the window route, as before. Two are still unread: `site.json`, because
    `GET /v1/site` is assembled from the site configuration document rather than from the demo-floor
    copy, and `ephemeris.json`, because the base tracks are API-owned records under
    `backend/api/data/ephemeris` and the demo-floor document is not a record this workflow resamples.
    Interpretation 44 of the A1-A3 list still stands for `site.json`: the frozen `site_response.json`
    leaves its root open, so the schema needs no change, but the names to settle with ENGINE are the
    ones named in interpretation 56.
47. **The chosen weather failure behaviour is that windows still return, and null is available for
    one of the four weather fields only.** The task offers "windows still return with null weather
    fields" and asks for the schema to be checked. Checked: `windows_response.json` types `p_success`,
    `p_success_components.weather` and `horizon_label` as non-nullable and leaves only
    `forecast_issue_time` nullable. So case three of the behaviour, a dead layer with nothing cached,
    sets `forecast_issue_time` to null and the other three to the neutral set already used when
    `include_weather` is false: `weather` 1.0, `p_success` the product of the two deterministic
    pre-screens, `horizon_label` CLIMATOLOGY. This is the same reading interpretation 32 reached for
    the excluded case, applied to the outage case. The choice, the reasoning and the three tests that
    hold it are in `backend/api/README.md`.
48. **A weather GET does not get the neutral fallback.** The window route cannot answer without the
    weather fields, so it degrades. The weather endpoints exist only to report weather, and a body of
    neutral values would answer a question nobody asked, so they degrade to the recorded document and
    then to a 503. A day or a verification period the record does not cover is a 503 naming the record
    rather than a 200 with the requested date printed on a forecast issued for another one. Both are
    tested; the reasoning is in the README.
49. **The weather cache key is the request, and the issue time is stored in the entry.** Spec IV.8
    keys the weather cache by date, site and source and stores `forecast_issue_time` with the entry;
    the A4 task says "cached on forecast_issue_time". Both are honoured by keying on what identifies
    the request, the date, the site and the criteria version, and carrying `forecast_issue_time` in
    the entry so that a served answer is echoed with the issue time it was produced under and is never
    presented as a fresh fetch. The criteria version joins the key because a different criteria table
    is a different answer for the same day, which
    `test_the_weather_cache_is_not_shared_across_criteria_versions` asserts.
50. **`source_files` lists the weather record only when the weather fields came from it.** A run whose
    weather fields were excluded or degraded did not read the document, and listing it anyway would be
    the provenance gap requirement 1 exists to prevent. The origin is resolved once per response, not
    once per row: resolving it per row made the first response and the second, cache-served, response
    disagree, which A3's determinism test caught. Fixed, and the fix is what makes two identical
    requests byte-identical.
51. **Spec IV.2 asks for a custom orbit id in the window response, and the frozen schema has no field
    for it.** `windows_response.json` closes `additionalProperties`, so there is nowhere in the spec
    IV.1 body for an `orbit_id`, and that schema is frozen at G0 and is not edited from here. The
    identifier is therefore recorded where the API owns it, in two places: the in-process orbit
    registry that every POST adds to, and the stored run record of A6. The ephemeris route reads both,
    so an id created by a POST resolves before and after a restart, which
    `test_a_custom_id_is_found_in_the_stored_run_record_after_a_restart` asserts. A schema change to
    add the field is a Seam 2 announcement and is not made here.
52. **`backend/fixtures/ephemeris.json` is FRONTEND content and was not edited.** An earlier pass of
    this session regenerated that file as a full-revolution leo45 record. The lead corrected it:
    contract section 0 gives this workflow the `backend/fixtures/` directory and FRONTEND its content,
    and Seam 3 makes the files hand-frozen. The edit was reverted and the record now lives at
    `backend/api/data/ephemeris/leo45.json`, generated by the same closed form as `polar879.json` and
    `sso981.json`, with `ephemeris.base_tracks.leo45` in `service.json` pointing at it. All three
    records are therefore documents this workflow owns, and
    `test_every_base_track_is_a_document_this_workflow_owns` holds that every configured base track
    resolves under `backend/api/`. `backend/fixtures/ephemeris.json` stays on disk, stays
    schema-valid, and is read as the demo floor of spec V.5 and nothing else;
    `test_the_offline_fallback_document_is_still_served_as_the_demo_floor` asserts both that it is
    valid and that no base track resolves to it. `git status backend/fixtures/` is empty. The A3
    assertions over the file, schema validity and no trailing content, are untouched and green.
    What the earlier pass got right is kept: the two-point, five-minute record could not answer a
    one-day request without repeating itself, which is why a full-revolution record was needed.
53. **The ground tracks are a closed form, not propagation, and the record is where the specification
    allows one.** Spec IV.2 says propagation for the named classes uses the secular-J2 model of Part
    II and that full force models are not offered. Neither ENGINE nor that model exists, so the three
    named classes are served from recorded segments and a custom id from the same closed form at
    request time. The closed form is the ground track of a circular orbit and nothing more: latitude
    from the inclination and the argument of latitude, longitude advancing at the orbital rate less
    the Earth's, altitude constant. No J2 precession, no perturbation. It is written out in
    `backend/api/ephemeris.py` and in `backend/api/README.md`, marked as a stand-in rather than a
    claim, and it is replaced the day `backend.engine.ephemeris` lands. Every number in it comes from
    `constants.json` or from configuration.

    The delegation to `backend.engine.ephemeris` is written now and is checked before its answer is
    served: delegation alone would put an unvalidated live answer in front of a client, and a live
    answer that breaks the contract is a worse outcome than the offline floor. The seam is asked first
    and its points are validated against the frozen `ephemeris_response.json`; a seam that raises,
    answers with something that is not a track, or answers with points the contract does not describe,
    falls through to the record. Three tests hold that, and the seam's call is asserted to carry the
    orbit id, the requested instants and the requested step.
54. **A recorded segment is repeated beyond its span, and `ground_track_valid` is the flag that says
    so.** Spec IV.2 gives no instruction for a request longer than the record. Repeating the segment is
    what a ground track does; truncating it would leave the frontend map with a five-minute stub for a
    one-day request. The repetition is a property of the offline floor, the flag is false beyond the
    three-day horizon on every id, and the README says so. Two further details: the recorded interval
    is a whole number of seconds so that the resampler can land on a recorded sample exactly, and the
    instant one span after the start is the last recorded sample rather than the first, which is what
    makes `test_the_resampler_reproduces_a_recorded_segment_exactly` hold at second resolution.
55. **`leo45` cannot overfly the site, and that is reachability rather than a defect.** The extreme
    latitude of the advertised low-Earth class is south of the site latitude, so no recorded track of
    that class crosses Canso. Spec II.4 makes the same statement algebraically, and spec III.5 makes
    that class the flagship honesty case. `test_the_leo45_track_cannot_reach_the_site_latitude` asserts
    it, and the polar and sun-synchronous classes are asserted to cross the site within 0.2 deg on the
    descending branch.
56. **`/v1/site` states two gaps instead of filling them.** Spec IV.5 asks for the environmental
    assessment reference URLs and the corridor polygon vertices used by the hazard test. No value for
    either appears in the specification, in the integration contract, or in any document this workflow
    owns. An invented URL is the phantom citation requirement 1 exists to prevent, so neither is
    returned, a `spec_gaps` field says which two are absent and why, and
    `test_the_two_items_the_repository_does_not_supply_are_absent_not_invented` holds that. The names
    to settle with ENGINE are `environmental_assessment_urls` and `corridor_polygon`. The launch rate
    cap of 8 per year and the coordinate-variant source string are returned, because spec IV.5 and
    spec II.10 give their values. The frozen `site_response.json` leaves its root open, so this needs
    no schema change; the names are still a proposal for the Seam 2 conversation.
57. **The weather response cannot carry a constants block, and that is a contract gap.** Spec IV says
    the block is "always present on result-bearing responses", and requirement 1 needs it. The frozen
    `weather_probability_response.json` closes `additionalProperties` and does not list it, so
    `GET /v1/weather/probability` cannot return one without breaking the contract. The frozen schema
    wins and no block is added. A schema change to add `constants_block` to
    `weather_probability_response.json` should be proposed through Seam 2; it is raised here and
    nowhere else, because `tests/contract/` is not edited from here. The other four result-bearing
    responses all carry one: the window response and the ephemeris response have it required by their
    schemas, the skill response has it required by its schema, and the site response carries it
    because that schema is open.
58. **A citation response schema should be proposed.** Spec IV.6 has no file in the G0 issue's list
    and none exists, and `tests/contract/` is frozen, so `GET /v1/citation` is validated by
    `backend/api/tests/test_citation.py` field by field instead: the five fields spec IV.6 names, the
    seven the A6 task requires, and the five fields of every spec II.10 item. A
    `tests/contract/schemas/citation_response.json` should be proposed through Seam 2 at the next gate,
    with `record_schema`, `request`, `request_body`, `constants_sources` and `provenance_block` among
    the fields to decide. Until then this response is the one body of the service that no frozen
    schema describes.
59. **A citation identifier for a read with no date in the request carries a zero date.** The window,
    weather, skill and ephemeris reads all have a date in the request and use it, which keeps the
    identifier of a run reproducible from the run. `GET /v1/site` has none, and a clock-derived date
    could not be reproduced, so its identifier is content addressed with the date part `00000000`,
    which is not a calendar date. A reader can therefore tell a configuration read from a dated run
    without a second field, and neither kind of value is invented from the clock.
60. **A citation identifier is validated before the store is touched.** The store is looked up by path,
    so an identifier carrying a separator or a parent reference could address a document outside the
    runs directory. Such an identifier is a malformed request, 422, not a miss, which is the reading
    of spec IV.7 rule 2 that does not treat a traversal attempt as a resource question. A containment
    check on the resolved path is kept as well, so the guarantee does not rest on the pattern alone.
61. **A cache replay returns the stored body byte for byte, including `computation_ms`.** The
    alternative, rewriting the timing field on replay, would make a cached answer differ from the
    fresh one it replaces. The consequence is the one interpretation 42 recorded: the determinism
    comparison of spec III.6 test 6 excludes `computation_ms`, because a wall-clock duration is not a
    function of the request. Every other field is compared, and
    `test_a_cached_replay_is_byte_identical_including_the_timing_field` states the stronger property
    that the replay is identical, timing included.
62. **The cache hit is asserted by a counter, not by a clock.** The A7 task says identical requests
    within the lifetime "hit cache and are faster". A timing assertion is flaky on a loaded machine and
    fails for reasons that have nothing to do with this code, so the tests assert the hit and miss
    counters, which state the same fact deterministically. This is recorded because it is a deliberate
    departure from the workflow wording, not an oversight.
63. **`/v1/openapi.json` and `/v1/health` are not charged against the read budget.** A client reading
    the contract or polling for liveness is not using the research budget, and charging it would let a
    monitoring system deny service to a researcher. Both are served by the application object rather
    than by a router, so they carry neither the cache nor the limiter.
64. **The window is sliding rather than fixed.** Spec IV.8 gives a per-minute budget and does not say
    how the minute is measured. A fixed window lets a client spend a whole budget at the end of one
    minute and another at the start of the next, so the counter forgets stamps older than the window
    and the `Retry-After` names the time until the oldest stamp falls out. `retry_after_s` in the
    configuration is the value reported when the whole window is still to run.
65. **A forwarded address is a separate budget.** The service is expected to run behind a reverse proxy,
    where every request would otherwise arrive from the proxy and share one budget of 60 a minute. The
    socket address is the primary key and `X-Forwarded-For` is honoured when present. A deployment that
    does not want this can set `enabled: false` and put a limiter in front.
66. **Not delivered, deliberately.** No Python client (A8), no `scripts/integration_test.py` (A10), no
    `DONE.md` (A11). No `tests/contract/schemas/citation_response.json`, for the reason in
    interpretation 58. No vehicle row is reported, because ENGINE owns
    `backend/engine/data/vehicles/*.json` and the file does not exist; the citation reads the path so
    that the rows appear the day it does, and nothing is invented in the meantime, which is
    interpretation 38 applied to the new endpoint. No TLE is fetched and no NOTAM screen reads a live
    feed, because ENGINE owns both; the citation records that state rather than leaving a reader to
    assume a live source.
67. **`git status` was not clean before this session, and the store was verified to be ignored.** The
    working tree already carried `.oc-brief-contract.md` and `.oc-brief-api1.md` from the lead; neither
    was edited here. The root `.gitignore` gained five lines, which is outside the paths this workflow
    owns and was required by the A6 task; nothing else outside `backend/api/`,
    `backend/fixtures/` and this log was touched. `git check-ignore -v
    backend/api/data/runs/somefile.json` reports `.gitignore:8`, and
    `git status --untracked-files=all backend/api/data/runs` lists only `.gitkeep`.
