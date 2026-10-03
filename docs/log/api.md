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