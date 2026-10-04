# backend/api

The `/v1` REST surface of the Canso launch window decision engine. Tasks A1 to A7 of
`docs/issues/issue-04-API.md` are complete. A8 to A11 are not.

## How to run it

```bash
.venv/bin/python -m uvicorn backend.api.app:app --host 127.0.0.1 --port 8000
```

The OpenAPI document is served from inside the versioned prefix at
`/v1/openapi.json`, and the interactive page at `/v1/docs`. `/v1/health` reports the
contract schema directory in force, which a deployment must ship: the service
validates against `tests/contract/schemas` at run time rather than keeping a second
copy of the frozen contract.

Tests:

```bash
.venv/bin/python -m pytest -q              # the whole repository
.venv/bin/python -m pytest backend/api -q  # this workflow's suite
.venv/bin/python -m pytest tests/contract -q
```

## Endpoints

| Method and path | Spec | What it answers |
|---|---|---|
| `POST /v1/windows` | IV.1 | Launch windows for one target, site, date range and vehicle |
| `GET /v1/orbits/{id}/ephemeris` | IV.2 | An ECEF ground track, query `start`, `end`, `step_s` (default 300) |
| `GET /v1/weather/probability` | IV.3 | Launch probability for `date` and `site` |
| `GET /v1/validation/skill` | IV.4 | Hindcast skill series, query `period_start`, `period_end`, `lead_max` |
| `GET /v1/site` | IV.5 | Site geometry, corridor with source and flag, CAR references |
| `GET /v1/citation?id=` | IV.6 | The spec II.10 provenance table of one stored run |
| `GET /v1/health` | none | Liveness and the configuration in force |
| `GET /v1/openapi.json` | IV | The contract, with the frozen schemas published in place |

## The error model, in one paragraph

A semantically valid request is HTTP 200 whatever the physics answers: an
unreachable target, an empty window list and a fired constraint are answers, and
they are in the body as `reachable: false`, `windows: []` and `constraint_fired`
(spec IV.7 rules 1 and 3). HTTP 4xx and 5xx are reserved for four conditions only:
422 for a request the service cannot interpret, 404 for an orbit, site or run
identifier it does not know, 429 for a spent per-client budget, and 503 for an
upstream layer that is unreachable, which always carries `Retry-After` and a body
naming the offline document that is answering instead. A malformed body never
reaches 500, and neither does a breach of the rate limit.

## The weather failure behaviour

**A dead weather layer never fails the window route. This is the choice the A4 task
requires to be picked, tested and documented, and it is this.**

Spec IV.7 rule 1 makes HTTP 200 the answer for every well formed request, so
`POST /v1/windows` returns 200 with the window rows in all three of these cases:

1. the weather layer answers: the four weather fields come from its answer, and
   `forecast_issue_time` is that answer's issue time;
2. the weather layer raises but a cached answer exists: the cached answer is served
   with the `forecast_issue_time` stored beside it, so a cached answer is never
   presented as a fresh fetch (spec IV.8);
3. the weather layer raises and nothing is cached: the rows carry
   `forecast_issue_time: null`, `horizon_label: "CLIMATOLOGY"`,
   `p_success_components.weather: 1.0` and `p_success` equal to the product of the
   two deterministic pre-screens. `backend/fixtures/weather.json` is then absent from
   `source_files`, because that run did not read it.

Case 3 is worth stating precisely, because it is not literally "null weather
fields". The frozen `windows_response.json` types `p_success`,
`p_success_components.weather` and `horizon_label` as non-nullable, so null is
available for one of the four weather fields only, namely `forecast_issue_time`. The
other three take the neutral set above, which is the schema-valid analogue of the
values used when `include_weather` is false, and CLIMATOLOGY is the honest label for
a probability no forecast produced.

The two weather GET endpoints have no such fallback, because a body of neutral values
would answer a question nobody asked. They degrade to the recorded document in
`backend/fixtures`, and only when that cannot be read or does not cover the requested
day do they return 503 with `Retry-After` and the path named. A date or a
verification period the record does not cover is a 503 rather than an answer with the
requested date printed on a forecast that was issued for another one.

The branch is tested in `backend/api/tests/test_weather.py`:
`test_windows_still_return_when_the_weather_layer_raises`,
`test_windows_carry_a_null_forecast_issue_time_and_the_neutral_weather_values` and
`test_a_cached_weather_answer_survives_the_outage`.

## How to get a citation identifier

The `constants_block` of every window response carries a `citation_id`, and every
`POST /v1/windows` writes the run to `backend/api/data/runs/<citation_id>.json`. So:

```bash
curl -s -X POST localhost:8000/v1/windows \
  -H 'content-type: application/json' \
  -d '{"target":{"type":"SSO","h_t_km":674.0},"date_range":{"start":"2026-10-05","end":"2026-10-15"},"vehicle_profile_id":"cyclone4m"}' \
  | .venv/bin/python -c "import json,sys; print(json.load(sys.stdin)['constants_block']['citation_id'])"

curl -s "localhost:8000/v1/citation?id=run_20261005_0123456789ab"
```

The identifier is a deterministic hash of the effective request, the constants and
the whole service configuration, so the same request always yields the same
identifier, and an identifier no run stored is a 404 whose detail says the run was
not found.

## The offline fixture path

`backend/fixtures/*.json` is the demo floor of spec V.5: it is what the service reads
when a live layer is unavailable, and it is what keeps the demo alive at judging with
the network unplugged. Each document is schema-valid, and
`backend/api/tests/test_fixtures.py` asserts that it is.

**The content of that directory is not this workflow's to edit.** Contract section 0
gives API the directory and FRONTEND the content, and Seam 3 makes the files
hand-frozen and valid against the schemas. This service therefore never writes there:
it reads `backend/fixtures/*.json` as the offline fallback, and every record it
resamples or generates for itself lives under `backend/api/data`. The one place the
distinction is visible in the configuration is `ephemeris.base_tracks`, which points
at `backend/api/data/ephemeris/*.json` for all three named classes rather than at the
demo-floor ephemeris document; `test_every_base_track_is_a_document_this_workflow_owns`
holds it.

The fixtures are generated records today rather than captures of a real engine run,
because ENGINE has not landed; `backend/fixtures/windows.json` already carries
`engine_version: "stub"`.

Configuration lives in `backend/api/data/service.json`: cache lifetimes, request
budgets, target classes, the site geometry file, the recorded ground tracks and the
references each configuration value has. No lifetime, budget, inclination, altitude,
corridor bound or constant is a literal in the service source; two tests scan the
source to keep it that way.

## What is stubbed and what is real at this commit

| Area | Status | Source served today |
|---|---|---|
| `POST /v1/windows` reachability, penalty, SSO consistency check | **stub**, marked `engine_version: "stub"` | `backend/fixtures/windows.json` plus spec II.4, II.5 and II.6 arithmetic in `stubs.py` |
| Window rows for POLAR and LEO classes | **not modelled** | The informative empty result of spec IV.1, or `reachable: false` for LEO |
| `GET /v1/weather/probability` | **stub** | `backend/fixtures/weather.json`, one recorded snapshot for one date |
| `GET /v1/validation/skill` | **stub** | `backend/fixtures/skill.json`, one recorded verification period |
| `GET /v1/orbits/.../ephemeris` | **stub, no propagation** | Recorded circular ground-track segments, resampled to `step_s` |
| `GET /v1/site` | **real, from configuration** | `backend/api/data/sites/canso.json`, or ENGINE's file once it exists |
| `GET /v1/citation` | **real** | The stored run record, and the spec II.10 table from configuration |
| Cache and rate limits | **real** | `backend/api/data/service.json` |
| Constants and provenance blocks | **real** | `backend/api/data/constants.json` |

What replaces each stub: `backend.engine.compute_windows`, `backend.engine.ephemeris`,
`backend.weather.probability` and `backend.weather.hindcast`. Each is already probed
at request time, so the day one lands it becomes the served path without a change
here, and the assertions that would check the live path are already written and
skipped.

### The offline ground tracks, precisely

The three named classes of spec IV.2 are served from recorded segments listed under
`ephemeris.base_tracks`, one per class, at `backend/api/data/ephemeris/leo45.json`,
`polar879.json` and `sso981.json`. Each segment was produced by the documented closed
form

```
latitude  = asin(sin(i) sin(u))        over the argument of latitude u
longitude advances at (n - omega_sid)   n = sqrt(GM / (R_e + h)^3)
altitude  = h, constant, the orbit being circular
```

with every quantity read from `backend/api/data/constants.json` or from the target
class in `service.json`. There is **no J2 precession and no perturbation**: those are
ENGINE's terms and arrive with `backend.engine.ephemeris` at gate G1. The segments
span one revolution in whole-second intervals and are laid out so that the southbound
pass crosses the site longitude at the site latitude; a request longer than the
recorded span repeats it, which is what a ground track does and what
`ground_track_valid: false` beyond three days warns a client about. `leo45` is the
reachable case that is not: its extreme latitude of 45.1 deg is south of the site at
45.3 deg, which is spec II.4 reachability made visible in a track, and the reason the
specification's flagship LEO class is the unreachable one.

A custom orbit identifier, created by a `POST /v1/windows` whose target names no
published class, has no recorded segment, so the same closed form produces one at
request time from the target the run recorded.

## Known gaps

* No `tests/contract/schemas/citation_response.json`. Gate G0 froze the contract
  without one, that directory is not edited from here, and the citation body is
  asserted field by field in `backend/api/tests/test_citation.py` instead. The
  proposal is recorded in `docs/log/api.md`.
* Spec IV.5 names environmental assessment reference URLs and the corridor polygon
  vertices used by the hazard test. No value for either exists in the specification,
  the integration contract or any document this workflow owns, so neither is
  returned. `GET /v1/site` states the absence in its `spec_gaps` field rather than
  inventing a URL, and the names to settle with ENGINE are in `docs/log/api.md`.
* `weather_probability_response.json` closes `additionalProperties`, so the weather
  endpoint cannot carry a `constants_block` even though spec IV asks for one on every
  result-bearing response. This is a contract gap, raised in `docs/log/api.md`.
* The ground track repeats beyond its recorded span and carries no precession, as
  described above.
* No Python client (A8), no integration harness (A10) and no `DONE.md` (A11).

## Configuration read from the environment

| Variable | Effect |
|---|---|
| `LAUNCHWIN_DATA_DIR` | Directory holding `service.json`, `constants.json` and `sites/` |
| `LAUNCHWIN_REPO_ROOT` | Root the recorded relative paths in the configuration resolve from |
| `LAUNCHWIN_CONTRACT_DIR` | Directory holding the frozen schemas |

No credentials are read and none are needed: spec IV allows unauthenticated reads.