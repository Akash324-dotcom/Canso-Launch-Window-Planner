# WEATHER validation: how to run the hindcast

Issue #7. The result and its honest reading are in `HINDCAST.md`. This file says how the result is produced and
where every input and output lives.

## Run it

```bash
.venv/bin/python -m backend.weather.scripts.run_hindcast canso     # hindcast, pairs, result, HINDCAST.md
.venv/bin/python scripts/build_skill_fixture.py                    # backend/fixtures/skill.json
.venv/bin/python -m pytest backend/weather tests/contract -q
```

Neither command needs the network or a key: the forecast archive and the hourly archive are committed.

From Python:

```python
from backend.weather import hindcast
body = hindcast("2026-04-02", "2026-09-27", lead_max=10)    # the GET /v1/validation/skill body, spec IV.4
```

`period_start` and `period_end` are the first and last forecast issue dates. `hindcast.longest_period("canso")`
returns the longest period the committed data supports. If a lead has no usable case for the period asked for,
`hindcast()` raises and asks for a smaller `lead_max`; a lead is never padded.

## Inputs

| File | What it is | Rebuilt by |
|---|---|---|
| `data/hindcast/runs_canso.csv.gz` | archived GFS runs, four per day, the fields every criterion needs, for the evaluation window of each valid date at leads 1 to 10 | `python -m backend.weather.scripts.fetch_hindcast_runs canso` (network) |
| `data/hindcast/source.json` | source, access date, coverage, units, every missing run | same |
| `data/era5_canso_hourly.csv.gz` | observed side: ERA5 and the station visibility | `python -m backend.weather.scripts.fetch_era5_archive canso` (network) |
| `data/criteria_v1.json` | the criteria both sides are judged by | edited by hand, versioned |

## Method

1. For each issue date, the four runs initialised on that UTC date are the members of a time-lagged ensemble.
   An issue date without all four runs is excluded and counted.
2. For each lead from 1 to `lead_max`, the forecast probability is the fraction of the four runs that satisfy every
   criterion at every hour of the evaluation window of the valid date. It is computed by
   `ensemble.ensemble_probability`, the function the operational layer uses. A forecast with a missing value in the
   window is excluded and counted; it is not evaluated on fewer runs.
3. The outcome is `observed_launchable(valid_date)`: the same rows, the same window and the same evaluator applied
   to the hourly archive. A day without a complete observation is excluded and counted.
4. Per lead: BS = mean((p - o)^2), BS_ref with p equal to the base rate of that lead's sample, BSS = 1 - BS / BS_ref.
5. Reliability bins and ROC points pool every lead. Empty bins are dropped. The ROC thresholds are the possible
   member fractions.
6. `skill_horizon_measured_days` is the last lead of the unbroken run of leads, starting at lead 1, with BSS above
   zero, or null.

## The lead range and the operational boundary

The hindcast scores leads 1 to `hindcast.lead_max_days` of `data/sources.json`, which is 10, the range spec III.4
names. That number is separate from the FORECAST boundary `max_forecast_lead_days` in `data/skill_horizon.json`,
which is what the hindcast measures. Issue #7 V6 says to set the boundary to the measured crossover. A test
compares the boundary and the `measured` block of that file with the committed result, so after a new run with a
different crossover the test fails until `data/skill_horizon.json` is updated, with the new numbers and sample
sizes. Then regenerate `backend/fixtures/weather.json` with `build_weather_fixture`.

## Extending the period

The period ends where the hourly archive ends. To move it forward: download newer GFS runs with
`fetch_hindcast_runs`, extend the hourly archive with `fetch_era5_archive canso --source open_data` (this needs
the Copernicus key, see `README.md`, because the keyless ERA5 copy is published months late), then run the three
commands above. The start cannot move back: the forecast archive keeps no run before 2 April 2026.

## The cache

`compute()` stores its result in `backend/weather/cache/hindcast/<key>.json` (ignored by git). The key is the
period, `lead_max`, the site, the criteria version, the forecast source, the verification source and the checksums
of the two data files. An unchanged key is answered from disk without recomputation; changing any part, including
the criteria version, forces a recompute. Tests cover both.

## Outputs

| File | Content |
|---|---|
| `data/hindcast/pairs_canso.csv` | one row per (issue date, lead): `issue_date, lead_time_days, valid_date, p, o` |
| `data/hindcast/result_canso.json` | skill by lead, base rate, reliability, ROC, coverage, exclusions, the pooled lead 1 to 7 score, per-criterion observed violation frequency |
| `HINDCAST.md` | the report, rendered from the result by `hindcast_report.render` |
| `backend/fixtures/skill.json` | the spec IV.4 response, written by `scripts/build_skill_fixture.py` |

Tests regenerate all four and compare them byte for byte with the committed files, so none can be edited by hand
without a test failing.

## What the hindcast does and does not show

It verifies the criteria, the evaluation chain and the predictability of the event with archived GFS runs. It does
not verify the operational probability, which comes from the ECMWF and GEFS ensembles: no open archive keeps
their past runs. `HINDCAST.md` states this and the other caveats with the numbers.
