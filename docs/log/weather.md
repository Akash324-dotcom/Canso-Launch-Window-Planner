# WEATHER workflow log

Kept as required by `docs/00_INTEGRATION_CONTRACT.md` section 8. The full task-by-task log, with every command
run and its observed output, is `backend/weather/progress.md`, which the issue brief names as the file to
maintain. This file is the summary and the pointer.

## Issue #3, operational probability layer, and issue #7, hindcast validation

Date of this entry: 4 October 2026 (UTC), revision 3 (no null parameter, no assumed limit, no stand-in data),
with the hindcast run on real data. Branch `feature-weather`. Status: W0 to W9 and V0 to V8 done, tests green,
committed locally, not pushed.

### What shipped

| Path | Purpose |
|---|---|
| `backend/weather/__init__.py` | exports `probability`, `hindcast`, `climatology`, `criteria_version`, `observed_launchable` |
| `backend/weather/criteria.py`, `data/criteria_v1.json` | versioned criteria table and evaluator |
| `backend/weather/fetch.py`, `units.py`, `data/sources.json` | forecast acquisition, issue time, units, cache, fallback, probes |
| `backend/weather/ensemble.py` | member fraction of spec II.21, the two-ensemble rule and the horizon label |
| `backend/weather/credentials.py`, `.env.example` | API key slot, read from the environment |
| `backend/weather/era5.py` | hourly archive: ERA5 fields and observed visibility, refused if any value is missing |
| `backend/weather/climatology.py`, `data/climatology_canso.json`, `data/era5_canso_hourly.csv.gz` | climatology |
| `backend/weather/service.py`, `data/skill_horizon.json`, `data/sites.json` | FORECAST and CLIMATOLOGY wiring, configuration |
| `backend/weather/observations.py` | verification outcome, used by the hindcast |
| `backend/weather/hindcast.py`, `hindcast_report.py`, `data/hindcast/` | scoring, the hindcast loop, the report generator, archived GFS runs, pairs and result |
| `backend/weather/HINDCAST.md`, `validation_README.md` | the hindcast report (generated) and how to run it |
| `scripts/build_skill_fixture.py`, `backend/fixtures/skill.json` | the skill fixture and the script that generates it |
| `backend/weather/scripts/` | probe, archive download, climatology build, direction sector, snapshots, fixtures, hindcast runs download, hindcast run |
| `backend/fixtures/weather.json` | generated offline fixture |
| `tests/contract/test_weather_schema.py` | WEATHER's Seam 2 obligation |
| `backend/weather/README.md`, `DONE.md`, `progress.md` | documentation and log |

### Results that other workflows may rely on

- `probability()` returns FORECAST for dates 0 to 5 days after the issue time, from the ECMWF ensemble (51
  members) and the NCEP GEFS ensemble (31 members, for visibility), and CLIMATOLOGY otherwise. Every emitted
  `source` is in the spec enumeration. `components` has 11 rows and never a null. `ensemble_size` is 82.
- Climatological launchable fraction at Canso for the 07:00 to 12:00 local window under `criteria_v1`, 2022 to
  2025: 0.089 in January, 0.395 in August, 0.259 over all 1,461 days.
- The boundary of 5 days is the hindcast's measured crossover (issue #7 V6). It replaces the 10 days of spec II.7
  in `data/skill_horizon.json`; the flag stays SKETCHED.
- `hindcast(period_start, period_end, lead_max=10)` returns the spec IV.4 body without network or key. Period
  supported by the committed data: 2026-04-02 to 2026-09-27. `backend/fixtures/skill.json` is that body.
- Hindcast result: Brier skill score against the climatological base rate 0.456, 0.373, 0.223, 0.223, 0.152 at
  leads 1 to 5 (169 to 173 cases each), negative at leads 6 to 10; 0.151 pooled over leads 1 to 7 (1,190 cases).
  Verified forecasts are four GFS deterministic runs per issue date, not the operational ensembles.
- `pytest backend/weather -q`: 227 passed, 1 skipped. `pytest tests/contract -q`: 77 passed. Whole repository:
  304 passed, 1 skipped.

### What is not done

- Gate G2: the contract's wording (Brier skill above zero against climatology, reliability diagram produced) is
  met. Of the three pass criteria of spec III.4, criterion 2 is not: the mean calibration gap is 0.157 against a
  bound of 0.15. It is reported as a miss in `HINDCAST.md`. Whether the gate is passed is INTEGRATION's call.
- The operational 82-member probability is not verified: no open archive keeps past ensemble runs.
- The hindcast covers six months, not the twelve the spec asks for: the forecast archive starts on 2 April 2026.
- Upper-level wind rows: no numeric limit is published anywhere, and an assumed one was ruled out.
- The full list is `backend/weather/DONE.md`.

### Interpretations and findings to reconcile

1. `p_launch` is a non-null number in the frozen schema. The issue's "return `p_launch: null`" option for a
   deterministic-only forecast is therefore realised as a CLIMATOLOGY response.
2. Open-Meteo serves the convective precipitation field as constant zero, its ERA5 archive has no CAPE, and its
   GDPS run metadata is stale (last run reported 2026-05-26). All three are recorded in `data/sources.json` and
   guarded by tests. NOAA retired the OPeNDAP feed of GEFS (Service Change Notice 25-81).
3. The frozen `probability(date_iso, site, criteria_version)` has no time argument, so the event is defined on
   the 07:00 to 12:00 local window that the Canso environmental assessment states.
4. The documents name no key file. Keys are read from the environment, per `docs/03_WORKFLOW_API.md`.
5. The response says `source: "era5_climatology"` for a climatology whose visibility row comes from a station
   observation, because reanalysis has no visibility and the contract allows no other climatology value. The
   archive metadata names the source of every field. If API wants the label to say so, the enumeration needs a
   new value; none was emitted.
6. No single open ensemble carries every field, so two are combined by a rule that gives a lower bound.
6. The hindcast measured a skill horizon of 5 days, and issue #7 V6 says to set the configuration to the measured
   crossover. Spec II.7 and the frontend copy may still say 10 days; the response label is what is authoritative.
7. With a Copernicus key the archive reaches the latest published ERA5 day, which the hindcast needs for its 2026
   outcomes. The key is read from the environment and is in no committed file.
