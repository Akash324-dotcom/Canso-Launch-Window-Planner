# Integration Contract — read this first, every workflow

Challenge 2 "Mission Control". Launch Window Decision Engine, Spaceport Nova Scotia (Canso, 45.3 N, 61.0 W). Four developers, four parallel workflows, one final `git pull`. This document is the binding interface between the four. Nothing in your workflow may contradict it.

Full scientific specification: `C2_framework_and_build_spec.md` (891 lines, Part I to VIII plus verbatim slide appendix). Read the parts named for your workflow; do not read the whole file unless you need to.

## 0. Repository layout and file ownership

Each path below has exactly ONE owner. Do not create, edit, or delete files outside your own paths. If you need a change in someone else's path, open an issue; do not edit.

```
hackathon_repo/
├── Canso Launch Prototype.html      [FRONTEND, inherited]  refactored, never deleted
├── docs/
│   ├── 00_INTEGRATION_CONTRACT.md   [SHARED, read-only]    this file
│   ├── 01_WORKFLOW_ENGINE.md        [ENGINE]               your prompt
│   ├── 02_WORKFLOW_WEATHER.md       [WEATHER]              your prompt
│   ├── 03_WORKFLOW_API.md           [API]                  your prompt
│   ├── 04_WORKFLOW_FRONTEND.md      [FRONTEND]             your prompt
│   └── spec/C2_framework_and_build_spec.md  [read-only]    copy of the build spec
├── backend/
│   ├── engine/                      [ENGINE owns]
│   │   ├── __init__.py              exports: compute_windows(), reachability(), j2_nodal_rate(), ephemeris()
│   │   ├── frames.py  reachability.py  j2.py  window.py  injection.py  sso.py  screens.py
│   │   ├── data/site_canso.json     [ENGINE]  corridor, CAR refs, EA provenance
│   │   ├── data/vehicles/*.json     [ENGINE]  one file per vehicle, each row VERIFIED|ASSUMPTION
│   │   └── tests/                   [ENGINE]  pytest
│   ├── weather/                     [WEATHER owns]
│   │   ├── __init__.py              exports: probability(), hindcast(), climatology()
│   │   ├── fetch.py  ensemble.py  climatology.py  criteria.py  hindcast.py  cache/
│   │   ├── data/criteria_v1.json    [WEATHER]  versioned, per-row source citation
│   │   ├── data/climatology_canso.json
│   │   └── tests/                   [WEATHER]  pytest
│   ├── api/                         [API owns]
│   │   ├── app.py                   FastAPI app, /v1 router
│   │   ├── schemas.py  routes/  provenance.py  citation.py
│   │   ├── client/launchwin.py      the public Python client
│   │   └── tests/                   [API] contract tests
│   └── fixtures/                    [API owns, written by FRONTEND pull requests]
│       ├── windows.json  weather.json  skill.json  site.json  ephemeris.json
├── frontend/                        [FRONTEND owns]
│   ├── src/  (screens, state, api client)
│   ├── index.html
│   └── tests/
├── scripts/
│   └── integration_test.py          [API owns]  the final pull gate
├── tests/contract/                  [API owns]  JSON Schema files
└── pyproject.toml                   [API owns]
```

## 1. Git conventions

- Branch per workflow: `engine/...`, `weather/...`, `api/...`, `frontend/...`
- Commit prefixes: `engine:`, `weather:`, `api:`, `frontend:`, `docs:`
- Never commit to `main` directly. One PR per task, not one PR per workflow.
- Never delete or reformat another workflow's files.
- Every PR must leave `pytest` green for the tests that exist at that moment.
- If a test in another workflow's directory fails because of their bug, open an issue, do not fix their file.

## 2. Inter-workflow interfaces (the only three seams)

### Seam 1: ENGINE and WEATHER both implement plain Python functions

API calls these directly. The signatures are frozen; bodies are yours.

```python
# backend/engine/__init__.py
def compute_windows(request: dict) -> dict:
    """Takes the POST /v1/windows request body (spec IV.1), returns the
    response body (spec IV.1) minus p_success, horizon_label,
    forecast_issue_time, p_success_components.weather, minus
    constants_block and provenance_block (API adds those).
    Pure function. No network. No I/O beyond its own data/*.json."""

# backend/weather/__init__.py
def probability(date_iso: str, site: str, criteria_version: str | None = None) -> dict:
    """Returns the GET /v1/weather/probability body (spec IV.3). May use cache/."""

def hindcast(period_start: str, period_end: str, lead_max: int = 10) -> dict:
    """Returns the GET /v1/validation/skill body (spec IV.4). Heavy; cache to disk."""
```

Until a workflow lands, API stubs these with the offline fixture in `backend/fixtures/`. **Stub first, real implementation second.** FRONTEND never waits on a backend workflow.

### Seam 2: JSON Schemas in `tests/contract/` are the source of truth

API writes them from spec Part IV. ENGINE and WEATHER run them against their own function output:

```bash
python -m pytest tests/contract/test_engine_schema.py   # ENGINE's obligation
python -m pytest tests/contract/test_weather_schema.py  # WEATHER's obligation
```

A schema file may only be changed by API, and a change is announced in the issue tracker before anyone else adapts.

### Seam 3: offline fixtures are the demo floor

`backend/fixtures/*.json` is hand-frozen, valid against the schemas, and committed. The demo runs on fixtures if any live call fails (spec V.5, V.6). API owns the directory; FRONTEND owns the content; ENGINE and WEATHER must be able to produce fixture-compatible output so the frozen files stay representative.

## 3. The gate schedule

| Gate | Owner | Test that defines it |
|---|---|---|
| **G0 — contract frozen** | API | `pytest tests/contract/` green with schemas only, no implementations |
| **G1 — engine credible** | ENGINE | spec III.2: reproduces 3-5 published launch windows within 5 minutes |
| **G2 — weather honest** | WEATHER | spec III.4: hindcast Brier skill > 0 against climatology, reliability diagram produced |
| **G3 — API live** | API | spec III.6: determinism and provenance echo on every response |
| **G4 — frontend complete** | FRONTEND | spec V.7 requirements mapping table, all slide features present, works on fixtures with network off |
| **G5 — final integration** | you (final touch) | `python scripts/integration_test.py` green on a clean clone |

**G1 blocks frontend work on real data.** FRONTEND proceeds on fixtures from hour zero and switches to live data when G1 and G3 pass.

## 4. Data and credentials

| Need | Source | Access | Owner |
|---|---|---|---|
| Weather forecast, 16 d hourly | Open-Meteo | free, no key, probed HTTP 200 | WEATHER |
| Ensemble members | Open-Meteo ensemble, GEFS/NOMADS fallback | free, no key | WEATHER |
| Official Canadian model | ECCC GeoMet (probed 200), Datamart `dd.weather.gc.ca` | free, anonymous | WEATHER |
| Hindcast / climatology | ERA5 via Copernicus CDS, fallback Open-Meteo historical archive | **free account required — request day one** | WEATHER |
| Space objects | CelesTrak (HTTP 200, no key); Space-Track account optional | free | ENGINE |
| Site geometry, corridor | Canso environmental assessment PDFs, CARs 602.43/602.44 | public | ENGINE |
| Vehicle ascent profiles | Cyclone-4M user guide; each row VERIFIED or ASSUMPTION | public | ENGINE |
| NOTAM display | Nav Canada | display only | ENGINE (screen stub) |

Hard rule from spec II.10: nothing site-, vehicle-, or criteria-dependent is hard-coded in source. Constants (J2, GM, R_e) are fixed but printed with their source in every response. If you are about to write a number into code that could have come from a config file, stop.

## 5. The claims, and what you may and may not assert

Spec Part II.9 is binding:

- **PROVED:** injection-consistent fixed point (Banach, contraction q <= 0.017); reachability (algebraic).
- **SKETCHED:** chance-constrained window; opportunity-process decision layer.
- **CONJECTURE:** positive Brier skill; ~10-day skill horizon; proxy-criteria consistency.

In code comments, README and commit messages, mark claims with their status. Do not write "theorem" where the spec says conjecture. Do not claim ascent-aware windows are novel (SLS pre-empts: spec I.3).

## 6. Definition of done for your workflow

You are done when ALL of the following hold:

1. Your task backlog in your workflow doc is fully checked.
2. `pytest <your tests>` is green on a clean clone after `git clone && pip install -e .`.
3. Your fixtures validate against `tests/contract/`.
4. Your README section exists: what it computes, how to run it, what it does not claim.
5. You have opened no PR against another workflow's paths.
6. You have written a `DONE.md` in your directory listing what shipped and what is known-unfinished.

## 7. What is explicitly out of scope for everyone

From spec I.4: no general maneuver design, no 6-DOF, no attitude control, no force model beyond secular J2 in the window core, no rideshare manifesting optimizer, no SDE trajectory layer. If you think you need one, open an issue first.

## 8. Working with Claude

Each of you drives your own Claude instance with your workflow doc as the persistent prompt. Claude must:

- Read `00_INTEGRATION_CONTRACT.md` at the start of every session.
- Read the spec parts your workflow names, never the whole spec unless asked.
- Write failing tests before implementation (TDD: red, green, refactor).
- Append its progress to `docs/log/<workflow>.md` after each task, so a session restart loses nothing.
- Never edit files outside its owner paths.
- Flag anything it cannot verify rather than inventing it. Three phantom citations have already been caught in this project; identifiers are resolved by title via Crossref, never from memory.
