# [WEATHER] Probabilistic launch-weather layer: P(L|d), climatology, criteria table - GATE G2 (part 1 of 2)

**Assigned to:** Het (GitHub: @HetJivani04) - holds the data-API accounts.

**This workflow is split across two issues.** This issue (#3) covers the operational probability layer: the criteria table, forecast and ensemble acquisition, P(L|d) for days 0 to 10, climatology beyond, and the horizon configuration. **The hindcast validation, Brier skill and reliability work now lives in issue #7, which is also yours.** #3 must land first because #7 consumes its criteria version and its probability function.

**Owner role:** WEATHER developer. **Depends on:** G0 contract. **Blocks:** API composition; carries the Originality rubric row.

**Credentials (important):** Het holds the **ERA5 / Copernicus CDS** account and the **Space-Track** account. The ERA5 account is the day-one dependency of this workflow: request the API key in hour one and record in `progress.md` the moment it becomes usable. The Space-Track key is not needed here, but see issue #2: Het owns that credential too, and the ENGINE conjunction screen consumes it.
**You own:** `backend/weather/**` and nothing else.

**Read first:** `docs/00_INTEGRATION_CONTRACT.md`, then spec Parts **II.7, II.10**, **III.4**, **VII.1**. Do not read Parts II.1-II.6, III.1-III.3, IV, V.

**Maintain:** `backend/weather/progress.md`.

---

## Mission

Turn "weather" from a coloured light into a measured probability. Produce a date-resolved probability that a launch on a given day passes its weather criteria, labelled by how far the forecast can be trusted, and back that label with a hindcast that reports its own skill honestly.

Frozen signatures (contract Seam 1):
```python
# backend/weather/__init__.py
def probability(date_iso: str, site: str, criteria_version: str | None = None) -> dict
def hindcast(period_start: str, period_end: str, lead_max: int = 10) -> dict
```

**Day-one action, before any code: request the Copernicus CDS account** (free, for ERA5). It is the single highest lead-time risk in the project and it is a human process you cannot parallelize.

---

## Task backlog (TDD)

### W0 Scaffold (30 min)
- [ ] TEST: `probability("2026-10-07", "canso")` imports and returns the spec IV.3 key set - RED, then stub - GREEN
- [ ] Commit the first version of `backend/fixtures/weather.json` (FRONTEND consumes it)

### W1 Criteria table - do this early, everything depends on it (1.5 h)
- [ ] TEST: `criteria_v1.json` loads; every row has `criterion_id`, `parameter`, `limit`, `unit`, `source_citation`, `flag` (VERIFIED|PROXY), `comparison` (lt|gt|between)
- [ ] TEST: **every row flagged VERIFIED has a non-empty source.** A row without a verifiable source must be PROXY. Enforce it in a test, not a convention
- [ ] DATA: write `data/criteria_v1.json` from the spec's 27-row variable inventory: surface wind speed and gusts, direction, visibility, precipitation type and rate, ceiling, temperature, lightning, upper-level wind at 850/700/500/300/200 hPa, cloud cover, and the rest of the inventory
- [ ] Sources for VERIFIED rows: NASA Shuttle Launch Commit Criteria, the Falcon User Guide (2025), the 45th Weather Squadron papers. Name the document, not just the agency
- [ ] Lightning: field mills and cloud-top temperature are **not publicly observable at Canso** (spec I.3(iv)). Substitute a documented proxy (modelled convective precipitation rate, or a CAPE-based proxy), flag PROXY, and explain the substitution in the JSON `_comment`
- [ ] TEST: requesting an unknown `criteria_version` raises the error the API maps to `constraint_fired: "criteria_version_missing"`

### W2 Forecast acquisition and fallbacks (1.5 h)
- [ ] TEST: `fetch.py` parses Open-Meteo hourly fields (temperature, wind speed 10 m, gusts, precipitation, cloud cover, visibility, plus whatever the criteria need) from a **committed fixture**; tests never touch the network
- [ ] TEST: every fetch result carries `forecast_issue_time`; a missing issue time is a bug
- [ ] TEST: unit conversion is explicit and one worked value is asserted end to end (km/h to m/s and back)
- [ ] IMPLEMENT `fetch.py` with cache keyed `(site, forecast_issue_time)`
- [ ] DATA: probe and record in `data/sources.json` with HTTP status and access date: Open-Meteo forecast (HTTP 200 confirmed), Open-Meteo ensemble (HTTP 200 confirmed), ECCC GeoMet (HTTP 200), ECCC Datamart (root is date-partitioned, `model_gem_global` 404'd in our probes - record exactly what you find), GEFS via NOMADS, EC ADS. Define the fallback order
- [ ] TEST: primary unreachable falls back to the next source and the response `source` field says which answered

### W3 Ensemble P(L|d) for days 0-10 - FORECAST mode (2 h)
- [ ] TEST: with a mock ensemble of N members, `p_launch` equals the fraction satisfying all criteria - worked case N=10, 6 pass, expect 0.6
- [ ] TEST: `horizon_label == "FORECAST"` within 10 days of the issue time
- [ ] TEST: `components[]` has one row per criterion with `p_violation` and the row's flag
- [ ] TEST: `ensemble_size` is reported; **if only a deterministic forecast exists, do not fabricate a probability.** Either return `p_launch: null` with a `source` explaining why and let CLIMATOLOGY carry those days, or apply a documented single-member method and say so. Encode whichever you choose as a test
- [ ] IMPLEMENT `ensemble.py`

### W4 Climatology beyond day 10 - CLIMATOLOGY mode (2 h)
- [ ] TEST: `horizon_label == "CLIMATOLOGY"` beyond day 10; `ensemble_size` and `forecast_issue_time` are null
- [ ] DATA: build `data/climatology_canso.json` = P(L | month, hour of day). Preferred source ERA5 (the account you requested); fallback Open-Meteo historical archive (`archive-api.open-meteo.com`, HTTP 200, since 2021). Minimum 3 full years; state the period in the file metadata
- [ ] Method: for each (month, hour) bin, the fraction of historical hours satisfying all criteria for the chosen version. Document the binning. **Any bin with fewer than 30 samples is flagged `low_confidence: true`** - a thin bin is not a probability
- [ ] TEST: every bin carries `n` and either passes the 30-sample floor or is flagged
- [ ] TEST: no bin returns exactly 0 or exactly 1 without a flag
- [ ] The JSON carries `source`, `period_start`, `period_end`, `criteria_version_used`, `generated_at`

### W5 Skill horizon as configuration, not a literal (1 h)
- [ ] TEST: the 10-day boundary comes from `data/skill_horizon.json` (`{"max_forecast_lead_days": 10, "source": "...", "flag": "SKETCHED"}`)
- [ ] Cite the skill-decay literature in the JSON: Lorenz 1982; Tellus A 2013 (doi 10.3402/tellusa.v65i0.19022); Buizza and Leutbecher 2015. **The boundary is SKETCHED in spec II.9 until your own hindcast supports or kills it. Do not claim it as established for Canso before the hindcast runs.**

### W6 Hindcast and skill - MOVED TO ISSUE #7 (1 h here, for the seam only)
- [ ] **The hindcast, Brier score, Brier skill score, reliability diagram and the skill fixture are now issue #7.** Do not implement them here
- [ ] What stays in #3 is the **seam**: export `criteria_version` and the outcome evaluator (`observed_launchable`) so #7 can consume exactly the same thresholds. Add a test asserting #7 can import them
- [ ] TEST: the exported surface exists and is importable from `backend.weather`

### W7 Contract integration (1 h)
- [ ] TEST: your outputs validate against `tests/contract/` (schema from the API workflow). If the schema does not exist yet, validate against the spec text and note it for API
- [ ] TEST: `source` is one of `open_meteo | gdps | era5_climatology | snapshot_cache`. If you need another, open an issue - do not emit unlisted values silently

### W8 Offline fixtures (1 h)
- [ ] `backend/fixtures/weather.json` and `skill.json`, realistic and valid - the demo runs on these if the network fails at judging
- [ ] **The skill fixture is generated by your own hindcast via a committed script** (`scripts/build_skill_fixture.py`), never hand-typed, so the demo number has provenance
- [ ] TEST: both fixtures validate against the schemas

### W9 Documentation (45 min)
- [ ] `backend/weather/README.md`: what P(L|d) means, why the FORECAST/CLIMATOLOGY split exists, the criteria table with its PROXY rows, how to reproduce the hindcast, and what the BSS result actually was
- [ ] `backend/weather/DONE.md`

---

## Acceptance criteria

1. `pytest backend/weather/ -q` green on a clean clone.
2. `pytest tests/contract/test_weather_schema.py -q` green.
3. `cat backend/weather/HINDCAST.md` states the BSS result with sample sizes; it does not hide a negative result.
4. `criteria_v1.json` has every row sourced or explicitly flagged PROXY.
5. `data/sources.json` records every endpoint probed with status and date.
6. Fixtures exist and validate; the skill fixture was generated by the committed script.

## Time budget

| Hours | Work |
|---|---|
| 0-1 | W0, W1 - and **request the ERA5 account in this hour** |
| 1-3 | W2 |
| 3-5 | W3 |
| 5-7 | W4, W5 |
| 7-11 | **W6 - GATE G2** |
| 11-12 | W7, W8, W9 |

## What will go wrong

- **The ERA5 account does not arrive.** Fall back to the Open-Meteo historical archive; state the period everywhere; HINDCAST.md says the skill result is provisional. Say it, do not hide it.
- **The historical forecast archive is thin or gappy.** Report `n_cases` per lead. Skill computed on 20 cases is not a validation and must be labelled as such.
- **BSS is negative.** Report it, then check your criteria evaluation (a criterion almost never met makes every day look like a failure). Fix the evaluation, re-run, report again. Only then suspect the forecast.
- **Deterministic-only days inside day 10.** Follow W3: null with a reason, or a documented single-member method. Never a fabricated 0 or 1.

## Rules

- TDD: red, green, refactor.
- No thresholds or horizons hard-coded in source (contract section 4).
- Every probability carries `forecast_issue_time`, `horizon_label`, `ensemble_size`, `source`.
- Formal register. No em dashes. No emojis.
- The skill horizon stays SKETCHED until your hindcast speaks. Your BSS number is a measurement over a stated period, not a claim about the world beyond it.

## Subagent dispatch and anti-corner-cutting law (applies to every task above)

- Dispatch each task to a subagent with this issue's text plus that task's exact acceptance test. The subagent sees nothing else, so quote into its prompt the context it needs: the spec sections (II.7, III.4, IV.3, IV.4), the response shapes, and the discipline rules below.
- A subagent may not close a task on the strength of "it runs". The acceptance test is the closing criterion; paste its output into progress.md.
- No partial development. A module is done when its tests pass and its README states what it does and does not claim. Anything half-written is marked UNDONE in progress.md and must not be merged.
- No test weakening. If the hindcast returns a Brier skill score at or below zero, that is the result. You report it, investigate the criteria evaluation, re-run, and report again. You never tune the evaluation until the number turns positive.
- No fabricated probabilities. A deterministic forecast does not yield a probability; W3 states exactly what to return instead. A probability that cannot be traced to ensemble members or to a climatological bin does not ship.
- No hard-coded thresholds or horizons in source; they live in versioned, cited JSON.
- No TODO placeholders in merged code. Cut the feature and record it in DONE.md.
- Every claim is marked PROVED, SKETCHED or CONJECTURE per spec II.9. The skill horizon is SKETCHED until your hindcast supports a narrower statement, and that statement carries its period and sample size.
- Every task update appends to progress.md with the exact command run and its observed output.
