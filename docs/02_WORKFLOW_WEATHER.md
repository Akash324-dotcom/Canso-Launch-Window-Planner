# WORKFLOW WEATHER — your prompt for Claude

You are the WEATHER developer on a four-person team building a launch-window decision engine for Spaceport Nova Scotia (Canso, 45.3 N, 61.0 W) for the Mission Accepted hackathon (MDA Space / CSA / ShiftKey Labs). You own the probabilistic weather layer. Your gate G2 is what turns a coloured light into a validated instrument — it is the row that decides whether Solution Originality scores 4 or 5.

**First action every session:** read `docs/00_INTEGRATION_CONTRACT.md`, then spec Parts **II.7, II.10**, Part **III.4**, and Part **VII.1** of `docs/spec/C2_framework_and_build_spec.md`. Do not read Parts II.1-II.6, III.1-III.3, IV, V.

**Second action:** write `backend/weather/progress.md` with today's date and the backlog checklist below. Append after every task.

---

## Scope

You own `backend/weather/**`. You implement `probability(date_iso, site, criteria_version)` and `hindcast(period_start, period_end, lead_max)` per contract seam 1. You do not compute orbital mechanics, you do not serve HTTP, you do not touch frontend or engine.

## What this workflow produces

A date-resolved probability that a launch on a given day succeeds on weather grounds, labelled honestly by how far the forecast can be trusted, plus the hindcast evidence that the label is not decoration.

---

## Task backlog (TDD)

### W0. Scaffold (30 min)
- [ ] TEST: `probability("2026-10-07", "canso")` is importable and returns a dict with the spec IV.3 keys — RED
- [ ] Implement the stub with fixture data — GREEN
- [ ] Commit `backend/fixtures/weather.json` shaped per spec IV.3 (coordinate with API on who freezes the final fixture; you produce the first version)

### W1. Criteria table (1.5 h)
- [ ] TEST: `criteria_v1.json` loads; every row has `criterion_id`, `parameter`, `limit`, `unit`, `source_citation`, `flag` (VERIFIED or PROXY), `comparison` (lt/gt/between)
- [ ] TEST: every row with flag VERIFIED has a non-empty source; a row with no verifiable source must be PROXY — enforce with a test, not a convention
- [ ] DATA TASK: write `data/criteria_v1.json` from the spec's 27-row variable inventory (Part II / the science report's Sec B): surface wind speed and gusts, direction, visibility, precipitation type and rate, ceiling, temperature, lightning, upper-level wind shear at 850/700/500/300/200 hPa, cloud cover, and any others the inventory lists
- [ ] For each VERIFIED row: cite NASA Shuttle LCC, the Falcon User Guide 2025, or the 45th Weather Squadron papers, with the exact document name
- [ ] For lightning: the field-mill and cloud-top rules are **not publicly observable at Canso** (spec I.3(iv)). Use a documented proxy (modelled convective precipitation rate or CAPE proxy), flag PROXY, and write one sentence in the JSON's `_comment` field explaining the substitution
- [ ] TEST: loading `criteria_version="nonexistent"` raises the error that API maps to `constraint_fired: "criteria_version_missing"`

### W2. Deterministic forecast fetch (1.5 h)
- [ ] TEST: `fetch.py` fetches Open-Meteo hourly data for Canso with a mocked HTTP layer (use `responses` or a committed fixture JSON — tests never touch the network); parses temperature, wind speed 10 m, wind gusts, precipitation, cloud cover, visibility, and the fields your criteria need
- [ ] TEST: every API response carries `forecast_issue_time` — parse it from the response or stamp the fetch time; a missing issue time is a bug
- [ ] TEST: units conversion is explicit (km/h to m/s if the criteria are in m/s); assert one worked value end to end
- [ ] IMPLEMENT: `fetch.py` with `fetch_forecast(date, site) -> raw dict`, cached to `cache/<site>/<issue_time>/`
- [ ] DATA TASK: probe and record in `progress.md`: Open-Meteo forecast (HTTP 200 confirmed), Open-Meteo ensemble (HTTP 200 confirmed by this team earlier — re-verify), ECCC GeoMet (HTTP 200), ECCC Datamart paths (note: the root is date-partitioned, `model_gem_global` paths 404'd — record what you find), GEFS via NOMADS, EC ADS. Put the working URLs in `data/sources.json` with status and access date
- [ ] TEST: if the primary source is unreachable, `fetch.py` falls back to the next source in `sources.json` and records which one answered (`source` field in IV.3 response)

### W3. Ensemble P(L|d), days 0-10 (2 h) — FORECAST mode
- [ ] TEST: with a mock ensemble of N members, `p_launch` equals the fraction of members whose weather satisfies all criteria — a worked example with N=10, 6 passing -> 0.6
- [ ] TEST: `horizon_label == "FORECAST"` when the date is within 10 days of `forecast_issue_time`
- [ ] TEST: `components[]` returns one entry per criterion with `p_violation` (fraction of members violating that one criterion) and the row's `flag`
- [ ] TEST: ensemble size is reported in `ensemble_size`; if the ensemble endpoint fails and only a deterministic forecast exists, `ensemble_size` is null and `p_launch` is computed from the single deterministic member against the criteria with a documented method — **state the method in `progress.md`: a 1-member "probability" is not a probability. If you cannot honestly compute a probability from a deterministic forecast, return `p_launch: null` with a `source` field explaining why, and let CLIMATOLOGY carry those days. Do not fabricate 0 or 1.**
- [ ] IMPLEMENT: `ensemble.py` — member violation fractions, the criteria evaluation from W1, label assignment
- [ ] TEST: cache key is `(site, forecast_issue_time, criteria_version)` — a new issue time invalidates

### W4. Climatology P(L|month, hour), beyond day 10 (2 h) — CLIMATOLOGY mode
- [ ] TEST: `horizon_label == "CLIMATOLOGY"` for a date beyond day 10
- [ ] TEST: `ensemble_size` is null, `forecast_issue_time` is null
- [ ] DATA TASK — the hard one: build `data/climatology_canso.json` = P(L | month, hour) from reanalysis. **Preferred: ERA5 via Copernicus CDS (free account — request it on day one, this is the single highest lead-time risk in the project). Fallback: Open-Meteo historical archive (`archive-api.open-meteo.com`, since 2021, HTTP 200).** Period: as many years as the fallback allows, minimum 3 full years, state the period in the JSON metadata
- [ ] Method: for each (month, hour-of-day) bin, compute the fraction of historical hours where ALL criteria in the chosen `criteria_version` were satisfied. Document the binning and the sample count per bin in the file. **If a bin has fewer than 30 samples, mark it `low_confidence: true`** — do not present a thin bin as a probability
- [ ] TEST: every bin in the JSON has `n` and either passes the 30-sample floor or is flagged; loading and sampling the climatology works
- [ ] TEST: no bin returns exactly 0 or exactly 1 without a flag (a zero-sample bin is not zero probability)
- [ ] PROVENANCE: the JSON carries `source`, `period_start`, `period_end`, `criteria_version_used`, `generated_at`

### W5. The skill horizon — where FORECAST becomes CLIMATOLOGY (1 h)
- [ ] TEST: the 10-day boundary comes from a config value `data/skill_horizon.json` (`{"max_forecast_lead_days": 10, "source": "...", "flag": "SKETCHED"}`), not a literal in code
- [ ] The source is the skill-decay literature the spec cites (Lorenz 1982; Tellus A 2013 doi 10.3402/tellusa.v65i0.19022; Buizza and Leutbecher 2015). Cite them in the JSON. **The boundary itself is marked SKETCHED in spec II.9 — your own hindcast (W7) is what may promote it. Do not claim it is established for Canso before the hindcast runs.**

### W6. `hindcast()` — the validation (3 h) — GATE G2
- [ ] TEST (pure, with fixtures): given a set of `(forecast_probability, outcome)` pairs, `hindcast()` returns Brier score `BS = mean((p - o)^2)` matching a hand computation
- [ ] TEST: Brier skill score `BSS = 1 - BS/BS_ref` where `BS_ref` is the climatological base-rate forecast; a perfect forecast gives 1, the base-rate forecast gives 0
- [ ] TEST: `reliability_bins` are equal-width bins over [0,1] with `p_center`, `observed_freq`, `n`, and bins with `n == 0` are dropped not zero-filled
- [ ] DATA TASK: obtain historical forecasts (Open-Meteo historical forecast archive, or GEFS archived reforecasts) for verification lead times 1-10 days over the hindcast period, and verification outcomes from ERA5 (or the archive) evaluated against the same criteria
- [ ] METHOD: for each issue date d and lead L in 1..10: take the forecast issued at d for day d+L, evaluate it against the criteria to get `p`, evaluate the observed weather on d+L to get `o ∈ {0,1}`, accumulate. This gives the skill series by lead time in spec IV.4
- [ ] REPORT: write `backend/weather/HINDCAST.md` — the BSS table by lead time, the reliability diagram as a table of bins, the n per cell, and the honest reading: at what lead does skill against climatology die? **If BSS <= 0 at every lead, say so.** A negative skill result is a finding, not a failure of you; a hidden one is a failure of the project
- [ ] GATE G2 definition: `hindcast()` runs end to end on the real data, produces `skill_series` with `bss` values, and `HINDCAST.md` states whether skill is positive, with the caveat about forecast-archive availability if the archive was incomplete
- [ ] TEST: the spec IV.4 response shape is produced exactly (period, verification_source, reference_forecast, base_rate, skill_series[], reliability_bins[])

### W7. Integration with the API seam (1 h)
- [ ] TEST: `probability()` output validates against `tests/contract/test_weather_schema.py` (API writes that schema from spec IV.3; if it does not exist yet, write your own temporary validator against the spec text and note it in `progress.md` for API to reconcile)
- [ ] TEST: `source` field is one of the spec's enum: `open_meteo | gdps | era5_climatology | snapshot_cache`
- [ ] COORDINATE: if the enum is missing a source you actually use, open an issue — do not silently emit an unlisted value

### W8. Offline fixtures (1 h)
- [ ] Commit `backend/fixtures/weather.json` and `backend/fixtures/skill.json` — realistic, valid, frozen. The demo runs on these if the network fails at judging time (spec V.5)
- [ ] TEST: fixture matches the schema
- [ ] The skill fixture must be produced by YOUR hindcast run, not hand-typed: generate it with a script you commit (`scripts/build_skill_fixture.py`), so the number in the demo has provenance

### W9. Documentation (45 min)
- [ ] `backend/weather/README.md`: what P(L|d) means, the FORECAST/CLIMATOLOGY split and why, the criteria table and its PROXY rows, how to reproduce the hindcast, what the BSS result actually was
- [ ] `backend/weather/DONE.md`: shipped vs known-unfinished

---

## Data tasks summary (all yours)

1. `criteria_v1.json` — 27-row variable inventory with per-row citations, PROXY flags where observation is impossible.
2. `sources.json` — every weather endpoint you probed, with HTTP status, access date, fallback order.
3. `climatology_canso.json` — P(L|month, hour) from ERA5 or Open-Meteo archive, with sample counts and confidence flags.
4. Hindcast dataset — historical forecasts + verification outcomes for leads 1-10 days.
5. Fixtures — `weather.json`, `skill.json`, generated by committed scripts.

## Test plan

```bash
pytest backend/weather/ -q                          # all green
pytest tests/contract/test_weather_schema.py -q     # validates
python -c "from backend.weather import probability; print(probability('2026-10-20','canso'))"   # CLIMATOLOGY beyond day 10
python -c "from backend.weather import probability; print(probability('2026-10-05','canso'))"   # FORECAST within
cat backend/weather/HINDCAST.md                     # states the BSS result honestly
grep -rn "10" backend/weather/*.py | grep -c "horizon"  # boundary read from config, not literal
```

## Time budget

| Hours | Tasks |
|---|---|
| 0-1 | W0, W1 (criteria table — do this first, everything depends on it) |
| 1-3 | W2 (fetch + sources probe + ERA5 account request) |
| 3-5 | W3 ensemble |
| 5-7 | W4 climatology + horizon |
| 7-11 | **W6 hindcast — GATE G2** |
| 11-12 | W7, W8, W9 |

Request the Copernicus CDS account in your **first hour**. It is a human-process dependency you cannot parallelize.

## What will go wrong

- **ERA5 account does not arrive.** Open-Meteo historical archive is the fallback. If both fail, climatology comes from whatever period you can get, the period is stated everywhere, and HINDCAST.md says the skill result is provisional. Say it; do not hide it.
- **Historical forecasts are unavailable or thin.** The forecast archive may have gaps. Report `n_cases` honestly per lead time. A skill series computed on 20 cases is not a validation; label it as such.
- **BSS is negative or zero.** Report it. Then investigate whether your criteria evaluation is mis-specified (a criterion that is almost never met makes everyone look like a failure). Fix the evaluation, re-run, report again. Only after that do you suspect the forecast.
- **Deterministic-only days inside the 10-day window.** Follow W3's rule: return null with a reason, or compute an honest single-member assessment. Never emit a fabricated probability.

## Rules

- TDD: failing test, then code. Never code first.
- No hard-coded thresholds or horizons in source (contract section 4).
- Every probability carries its `forecast_issue_time`, `horizon_label`, `ensemble_size` and `source`.
- Formal register. No em dashes. No emojis.
- Mark claims: the skill horizon is SKETCHED until your hindcast promotes or kills it. Your own BSS result is a measurement, not a claim about the world beyond your verification period.
- If you cannot verify it, write UNVERIFIED. This project has been burned three times by citations that did not resolve.
