# WEATHER: probabilistic launch-weather layer

Workflow WEATHER of the launch-window decision engine for Spaceport Nova Scotia (Canso). Issue #3, the
operational probability layer, and issue #7, its hindcast validation. The hindcast result is in `HINDCAST.md` and
how to run it is in `validation_README.md`.

## What it computes

`probability(date_iso, site, criteria_version=None)` returns the body of `GET /v1/weather/probability`
(spec IV.3): the probability `p_launch` that a launch on that date passes the weather criteria, with the label
that says how far the number can be trusted.

The event (spec II.20). L(d) = 1 if and only if every criterion of the criteria table holds at every hour of the
evaluation window on date d. The frozen signature takes a date and no time, so the window is the site's nominal
operating hours, 07:00 to 12:00 local time (spec IV.5), read from `data/sites.json`. Hourly values labelled 07:00
to 12:00 local, both included, are evaluated. A criterion is violated for the window if it is violated at any of
those hours (worst-case excursion, spec II.21).

Three properties hold everywhere and are enforced by tests:

- **No null.** Every criterion has data on the forecast side and on the observed side. The hourly archive has no
  missing value, the stored forecasts have no missing value, and a response never carries a missing number. If a
  forecast cannot evaluate every criterion for a date, the date is answered from climatology, where every
  criterion has data.
- **No assumed limit.** Every limit is quoted from a public document, taken from a published definition, or
  computed from published coordinates. A quantity for which no numeric rule is published is not a criterion.
- **One event.** The same rows, window and evaluator (`criteria.window_violations`) are used for ensemble
  members, for the hourly history and for the verification outcome.

## The two modes, and why they exist

| | FORECAST | CLIMATOLOGY |
|---|---|---|
| When | the date is 0 to 5 days after the forecast issue time and both ensembles cover its window | every other case |
| `p_launch` | member fraction of the ECMWF ensemble for every row it carries, reduced by the share of GEFS members that fail on visibility alone (see "Two ensembles") | fraction of days of that month in the hourly archive that satisfied every criterion over the window (spec II.22) |
| `ensemble_size` | members used: 51 ECMWF plus 31 GEFS | null |
| `forecast_issue_time` | the older of the two model run times | null |
| `source` | `open_meteo`, or `snapshot_cache` when a forecast was read from disk | `era5_climatology` |
| `components` | one row per criterion: fraction of members that violate it | one row per criterion: fraction of days that violated it |

A forecast loses skill with lead time, and beyond some lead it is no better than a climatological guess. The
response therefore says which of the two it is. The boundary is the value `max_forecast_lead_days` in
`data/skill_horizon.json`, not a literal in code. It is 5: the hindcast found skill against climatology at leads
1 to 5 and none at lead 6 (see "The hindcast and the BSS result"), and issue #7 prescribes that the boundary
follows the measurement. The spec's prior value of 10 is kept in the file as a record. Lead is counted in calendar
days from the UTC date of the forecast issue time.

Cases that are answered as CLIMATOLOGY on purpose:

- Only a deterministic forecast is available. One run is not a probability, and no 0 or 1 is made from it. This
  is the behaviour chosen from the two the issue allows; it is encoded in
  `test_a_deterministic_forecast_does_not_yield_a_probability` and
  `test_when_only_a_deterministic_forecast_exists_no_probability_is_fabricated`.
- A forecast in which any member lacks a value for an evaluated field at an hour of the window. Such a forecast
  is not used and no member is dropped to make it fit (`ensemble.require_complete_members`). The same holds for
  a forecast with fewer than 2 members (`ensemble.min_members`).
- Either ensemble is unavailable and no stored copy covers the date. A forecast that cannot evaluate visibility
  is not issued with a gap; the date goes to climatology.
- The date is inside the horizon but an ensemble does not reach it, or the date is before the issue date.

The contract schema types `p_launch` as a number, so the "no probability" case cannot be sent as null. The
climatological value under the CLIMATOLOGY label is what "let CLIMATOLOGY carry those days" means here.

### Two ensembles

No single open ensemble carries every field. Eleven models on Open-Meteo were probed on 3 October 2026: only the
ECMWF ensembles carry low and mid-level cloud cover, and only NCEP GEFS and the UKMO global ensemble carry
visibility. NOAA's own decoder-free GEFS feed has been retired. So two ensembles are used:

- ECMWF IFS ensemble, 51 members: every row except visibility.
- NCEP GEFS, 31 members: visibility, together with the rows both ensembles carry.

They are separate samples, so the joint behaviour of a cloud row and visibility inside one member is not
available. The combination uses no dependence assumption:

    p_launch = max(0, P - Q)

P is the fraction of ECMWF members that satisfy every row ECMWF carries. Q is the fraction of GEFS members that
satisfy every common row and violate visibility. Since P(A and B) = P(A) - P(A and not B) and "A and not B" is
contained in "common rows hold and not B", the value is a lower bound on the probability that every row holds.
It equals the exact member fraction whenever no GEFS member fails on visibility alone, and otherwise it can only
understate the launch probability, never overstate it. In the 2022 to 2025 archive visibility was the only
violated row on 1.6 percent of days, so the bound is rarely different from the exact value.

## API keys: where they live

The project documents name no key file. They say "No credentials in code; the app reads paths and keys from
environment" (`docs/03_WORKFLOW_API.md`) and "No credentials in code or commits" (`docs/issues/issue-04-API.md`).
So the key is an environment variable, and nothing real is committed.

| Variable | Meaning | Needed for |
|---|---|---|
| `CDSAPI_URL` | Copernicus Climate Data Store API address | the Copernicus route of the archive download |
| `CDSAPI_KEY` | Copernicus Climate Data Store personal access token | the Copernicus route of the archive download |

These are the names the official `cdsapi` client reads. Two ways to set them:

1. Export them in the shell, or
2. write them in `backend/weather/.env`. That file is ignored by git (`backend/weather/.gitignore`).
   `backend/weather/.env.example` is the committed template; it holds the placeholder
   `REPLACE_WITH_YOUR_CDS_PERSONAL_ACCESS_TOKEN` and must keep it.

A variable set in the shell wins over the file. A placeholder is never sent to the service. The key is never
printed or written to any file by this code, and a failed download is recorded by its error type only.

`probability()` and `hindcast()` need no key: they read committed data and keyless forecast services. The key is
used in one place, the archive download, where it does two things. It supplies ERA5 CAPE, and because Copernicus
publishes ERA5 within about five days while the keyless NCAR copy is months behind, it lets the archive reach
the latest published day. The committed archive was built that way, with the owner's key:

```bash
.venv/bin/pip install cdsapi xarray netCDF4                 # download-time packages, not in pyproject.toml
.venv/bin/python -m backend.weather.scripts.fetch_era5_archive canso --source open_data
.venv/bin/python -m backend.weather.scripts.build_climatology canso
.venv/bin/python -m backend.weather.scripts.build_weather_fixture canso
.venv/bin/python -m backend.weather.scripts.run_hindcast canso
.venv/bin/python scripts/build_skill_fixture.py
.venv/bin/python -m pytest backend/weather tests/contract -q
```

Without a key the same commands build an archive that ends in 2025, which is enough for the climatology and the
operational layer but leaves the hindcast without outcomes for 2026.

The Space-Track credential that issue #2 mentions is consumed by ENGINE, not by this layer, and the documents name
no variable for it. It is not stored here.

## How to run

```bash
python3.11 -m venv .venv && .venv/bin/pip install -e ".[dev]"

.venv/bin/python -m pytest backend/weather -q                        # no network; one test is skipped without xarray
.venv/bin/python -m pytest tests/contract/test_weather_schema.py -q  # output and fixture against spec IV.3

.venv/bin/python -c "from backend.weather import probability; print(probability('2026-10-05','canso'))"
.venv/bin/python -c "from backend.weather import climatology; print(climatology(10, 14))"
LAUNCHWIN_WEATHER_OFFLINE=1 .venv/bin/python -c "from backend.weather import probability; print(probability('2026-10-05','canso'))"
```

`LAUNCHWIN_WEATHER_OFFLINE=1` disables every live request. The layer then answers from the stored forecast and
the climatology, which is the demo floor of spec V.5.

Exports of `backend.weather`:

| Name | Purpose |
|---|---|
| `probability(date_iso, site, criteria_version=None)` | spec IV.3 body |
| `climatology(month, hour, site="canso", criteria_version=None)` | one bin of P(L \| month, UTC hour) with `n`, `p_launch`, `p_violation`, `low_confidence` |
| `hindcast(period_start, period_end, lead_max=10)` | spec IV.4 body: Brier skill by lead, reliability bins, ROC points |
| `criteria_version()` | the current default criteria version, resolved from `data/criteria_v*.json` |
| `observed_launchable(date_iso, criteria_version=None, site="canso")` | verification outcome 1, 0 or None from the hourly archive, for issue #7 |

A `criteria_version` argument is accepted in two exact forms: the file stem (`criteria_v1`) and its short form
(`v1`), which is what the API default and the contract examples use. Both name `data/criteria_v1.json`; the
response always carries the file stem. Any other spelling, and any version without a table, raises
`CriteriaVersionMissingError`. `None` means the current version.

Errors, for API to map (spec IV.7):

| Raised | Meaning | Mapping |
|---|---|---|
| `CriteriaVersionMissingError` | no table for the requested criteria version | body value `constraint_fired: "criteria_version_missing"` (attribute `constraint_fired` carries the string) |
| `UnknownSiteError` | site id not in `data/sites.json` | HTTP 404 |
| `ValueError` | date is not `YYYY-MM-DD` | HTTP 422 |
| `WeatherDataError` | a data file is missing or inconsistent | HTTP 503 |

## Sources

Configured in `data/sources.json`, which also records every endpoint probed with its HTTP status and access date.

Forecast, in order:

1. `open_meteo`: the ECMWF IFS ensemble and the NCEP GEFS ensemble through the Open-Meteo ensemble API. The model
   run time is read from each model's metadata endpoint and becomes `forecast_issue_time`.
2. `snapshot_cache`: the most recent forecasts on disk, either the local cache or the committed snapshot in
   `data/snapshot/`. They keep their original issue time and are never presented as a fresh fetch. The committed
   snapshots hold no missing value; a test checks it.
3. `era5_climatology`: the table in `data/climatology_canso.json`.

`fetch_forecast(site, chain="deterministic")` also serves single-run forecasts, with the order GFS through
Open-Meteo (`open_meteo`), then the ECCC GDPS through Open-Meteo (`gdps`), then the snapshot. A single run is
never turned into a probability.

Raw fetches are cached under `cache/<site>/<issue time>/`. A request inside 30 minutes of the last one makes no
network call (spec IV.8). After an outage the live source is tried again after 5 minutes. Twelve forecast days
are requested, inside the range of both ensembles and enough for any boundary up to 10 days.

Hourly archive for climatology and verification. Every field has one named, real source, recorded per field in
the archive metadata:

| Field | Source |
|---|---|
| 10 m wind speed, gust and direction, 2 m temperature, precipitation, snowfall, low and mid-level cloud cover | ERA5 reanalysis, Open-Meteo archive API with `models=era5` |
| CAPE | ERA5 reanalysis, from the Copernicus Climate Data Store when a key is configured, otherwise from the NSF NCAR ERA5 archive (dataset d633000), anonymous. The two were compared over a month and are identical |
| visibility | hourly observation at the ECCC station PORT HAWKESBURY (climate id 8204495), 48.3 km from the site centre, the nearest station that reports visibility |

Reanalysis has no visibility field, so the observation is the real source for it. Hours the station did not
report are filled with the NCEP GFS visibility at the Canso grid point from the Open-Meteo historical forecast
archive, and every filled hour is listed in the archive metadata under `gap_filled`. The archive is written only
if no value is missing; otherwise the build stops with an error.

The climatology is built from the complete calendar years 2022 to 2025; 2022 is the first complete year of the
gap-fill source. With a Copernicus key the archive also runs past 2025 to the latest published day, so that
recent forecasts can be verified; those months do not enter the climatology. Without a key it ends in 2025,
because the NCAR copy of ERA5 is published months late.

Three ways lead to the same reanalysis, chosen with `--source`:

- `open_data`, the route of the committed archive: surface fields from the Open-Meteo ERA5 archive, CAPE as in the
  table above.
- `era5_cds`: every ERA5 field from Copernicus, month by month. It is the route issue W4 names as preferred. It was
  verified against the live service on 4 October 2026 with a one-month download that agreed with the open route.
  A full pull is 57 monthly requests of about 12 minutes each in the Copernicus queue, which is why the committed
  archive takes only CAPE from Copernicus. Copernicus `fg10` is the hourly maximum gust; the gust served by
  Open-Meteo differs from it by 0.4 m/s on average.
- `auto`: `era5_cds` when the key is usable, otherwise `open_data`.

## The criteria table

`data/criteria_v1.json`. A documented proxy set, not the launch commit criteria of any vehicle (spec I.3(iv)).
It has 11 criteria rows, each with `criterion_id`, `parameter`, `comparison`, a numeric `limit`, `unit`,
`source_citation` and `flag`, plus 17 `not_assessed` entries. Together they cover all 27 rows of the team's
variable inventory, which a test checks. All 11 rows are evaluated, on both sides, with data.

- `flag: VERIFIED` (7 rows): the limit is transcribed from a named public document that was opened and read on
  3 October 2026, with the sentence stored in `source_quote`. It verifies the citation, not that the rule applies
  at Canso. A test fails if a VERIFIED row lacks its document, URL, quote or access date.
- `flag: PROXY` (4 rows): the published rule cannot be observed from open data, so a substitute variable stands
  in for it (`_comment` says SUBSTITUTION). The limit of a PROXY row is never a number of our own: `limit_basis`
  records the published definition or the published coordinates it comes from, with the quote and the derivation.
  A test fails if any row contains an assumed limit.
- `comparison` states when the row is violated: `gt`, `lt`, or `between`.

Sources read: the Canso Spaceport Facility Environmental Assessment Registration Document (the only site-specific
source), the NASA Space Shuttle Launch Commit Criteria fact sheet (FS-2008-02-039-KSC), the SpaceX Falcon User's
Guide of 2025-05-09, the 45th Weather Squadron paper by Roeder and McNamara (AMS 103803), the NASA Falcon 9 Crew
Dragon and Atlas V weather fact sheets, the NOAA Storm Prediction Center instability classes, and the federal
definition of a ceiling. The Falcon User's Guide contains no numeric weather limit and sources no row.

The 11 rows, with how often each was violated over the daily window in the 1,461 days of the archive:

| Row | Field | Violated when | Flag | Where the limit comes from | Days violated |
|---|---|---|---|---|---|
| `surface_wind_speed` | 10 m wind | > 13.41 m/s (30 mph) | VERIFIED | NASA FS-2020-05-568-KSC, Falcon 9 Crew Dragon | 7.4 % |
| `surface_wind_gust` | 10 m gust | > 16.98 m/s (33 kt) | VERIFIED | NASA FS-2013-01-010-KSC, Atlas V | 9.9 % |
| `wind_direction` | 10 m wind direction | between 57.4 and 175.7 deg | PROXY | computed from the assessment's site centre and the gazetteer coordinates of the three communities it names | 23.9 % |
| `visibility` | visibility | < 7408 m (4 NM) | VERIFIED | NASA FS-2013-01-010-KSC, Atlas V; the Canso assessment states the rule without a number | 31.3 % |
| `precipitation_type_frozen` | hourly snowfall | > 0 cm/h | VERIFIED | Roeder and McNamara, disturbed weather rule | 7.3 % |
| `precipitation_rate` | hourly precipitation | > 0 mm/h | VERIFIED | Canso environmental assessment, Table 11.1 | 35.7 % |
| `ceiling_proxy_low_cloud` | low cloud cover | > 62.5 % (5 oktas) | PROXY | definition of a ceiling (14 CFR 1.1) and of broken cloud (NWS glossary) | 61.7 % |
| `temperature_hot` | 2 m temperature | > 37.2 degC (99 degF) | VERIFIED | NASA FS-2008-02-039-KSC, Space Shuttle | 0.0 % |
| `lightning_proxy_cape` | CAPE | > 1000 J/kg | PROXY | NOAA Storm Prediction Center: moderate instability begins at 1000 J/kg | 0.0 % |
| `cloud_cover_thick_layer_proxy` | mid-level cloud cover | > 87.5 % (above 7 oktas) | PROXY | NWS glossary: broken is 5/8 to 7/8, so more is overcast | 28.7 % |
| `ground_operations_wind` | 10 m gust | > 21.61 m/s (42 kt) | VERIFIED | NASA FS-2008-02-039-KSC, tanking | 3.4 % |

What the Canso assessment says, quoted in the rows: "Any precipitation at the launch site or within the flight
path will prohibit a launch."; "Fog: Reduced visibility will prohibit launch."; clouds matter for "hazardous
electric fields, temperatures ranging into freezing zone, low ceiling, or low visibility"; and the wind go-no go
criteria are "to ensure any cloud is well away and/or aloft from any populated areas up range".

The PROXY rows, stated plainly:

- **Wind direction.** The assessment gives the rule and no numbers; the real criteria will come from plume
  modelling that is not published. The sector is computed, not chosen: the bearing from the site centre printed
  in the assessment to each community it names (coordinates from the Canadian Geographical Names Database),
  turned by 180 degrees. Little Dover gives 57.4, Hazel Hill 118.2, Canso 175.7 degrees.
  `scripts/derive_direction_sector.py` reproduces it and a test compares the row with the computed sector. The
  row ignores wind speed, so a light wind in the sector violates it, and on some days it decides the result.
- **Lightning.** Field mills, lightning detection, radar and cloud-top temperature are not publicly observable at
  Canso. Modelled CAPE stands in for them, which is one of the two proxies the issue names. The limit is the
  start of the "moderate instability" class of the NOAA Storm Prediction Center. At this cold maritime site that
  class is rare: the row was violated on no window in the archive. The other named proxy, convective
  precipitation rate, cannot be used: Open-Meteo serves that field as the constant 0.0.
- **Ceiling and cloud cover.** No cloud base height or layer thickness is available on the forecast side, so low
  cloud cover stands in for a ceiling below 6,000 ft and overcast mid-level cloud for a thick cloud layer. The
  limits follow from the published definitions of a ceiling and of broken cloud. The altitude ranges of the two
  fields are UNVERIFIED. The ceiling proxy is the most violated row in every month.

Inventory rows that are not criteria, each with its reason in `not_assessed`. Two matter for the issue's list:

- **Upper-level wind at 850, 700, 500, 300 and 200 hPa.** No numeric limit is published by any operator: the
  public rule is "wind shear that could lead to control problems", and the real criterion is a vehicle load
  analysis, not a wind speed. Any threshold would be a number of our own. It becomes a row when a launch provider
  supplies a limit.
- **Cold temperature.** The only published cold limit is the Space Shuttle's, and it is not a threshold but a
  table: a function of temperature, wind and humidity for a cryogenic external tank. The Falcon 9 and Atlas V
  fact sheets state no temperature limit. Taking one value from the table would be a choice of our own.

To change a limit: copy the file to `criteria_v2.json`, set `criteria_version`, edit the copy, cite each row.
No source code changes. A published version is not edited. The climatology for a version without a committed
table is built on request from the hourly archive.

## The climatology

`data/climatology_canso.json`, built by `scripts/build_climatology.py` from the committed hourly archive
`data/era5_canso_hourly.csv.gz`.

- Grid cell 45.25 N, 61.0 W, 2022-01-01 to 2025-12-31, 35,064 hours, none missing, 1,461 days, none excluded.
- `bins`: 288 bins by (month, UTC hour), 113 to 124 samples each. `p_launch` is the fraction of hours at which no
  criterion was violated. Range 0.177 to 0.658.
- `daily_window`: 12 bins by month, 113 to 124 days each. `p_launch` is the frequency of the event L(d) and is
  the value `probability()` returns in CLIMATOLOGY mode.
- A bin with fewer than 30 samples, or with a frequency of exactly 0 or 1, is flagged `low_confidence` with the
  reason. A bin with no sample has `p_launch: null`, not zero. No bin of the committed file is flagged.
- A test rebuilds the table from the archive and compares it with the committed file. Other tests check that the
  archive has no missing value, that every field names its source, that every gap-filled hour is listed, and that
  no evaluated field is constant over the archive.

P(L | month), daily window, 2022 to 2025:

| Jan | Feb | Mar | Apr | May | Jun | Jul | Aug | Sep | Oct | Nov | Dec |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 0.089 | 0.150 | 0.210 | 0.292 | 0.290 | 0.283 | 0.355 | 0.395 | 0.392 | 0.363 | 0.175 | 0.105 |

Over all 1,461 days the launchable fraction is 0.259. These numbers are a measurement over the stated period
under the stated proxy criteria. They are not a statement about any vehicle's real launch availability.

## Reproducing the data

| File | Produced by | Network |
|---|---|---|
| `data/sources.json`, `probes` list | `python -m backend.weather.scripts.probe_sources` | yes |
| `data/era5_canso_hourly.csv.gz` and `.meta.json` | `python -m backend.weather.scripts.fetch_era5_archive canso --source open_data` | yes |
| `data/climatology_canso.json` | `python -m backend.weather.scripts.build_climatology canso` | no |
| wind direction sector in `criteria_v1.json` | shown by `python -m backend.weather.scripts.derive_direction_sector canso` | no |
| `data/snapshot/canso/*.json` | `python -m backend.weather.scripts.refresh_snapshot canso` | yes |
| `tests/fixtures/*.json` | `python -m backend.weather.scripts.capture_test_fixtures canso` | yes |
| `backend/fixtures/weather.json` | `python -m backend.weather.scripts.build_weather_fixture canso` | no |
| `data/hindcast/runs_canso.csv.gz`, `source.json` | `python -m backend.weather.scripts.fetch_hindcast_runs canso` | yes |
| `data/hindcast/pairs_canso.csv`, `result_canso.json`, `HINDCAST.md` | `python -m backend.weather.scripts.run_hindcast canso` | no |
| `backend/fixtures/skill.json` | `python scripts/build_skill_fixture.py` | no |

`fetch_era5_archive` takes `--source auto|era5_cds|open_data`, `--first-year`, `--last-year` and
`--no-extension`. With `auto` a failed Copernicus download switches to the open ERA5 route and records the failure
by error type only. With `era5_cds` a failure is an error. The archive is refused if any value is missing.

The fixture is generated from the committed snapshots and climatology, and a test regenerates it and compares the
bytes. `weather.json` is the spec IV.3 response for 6 October 2026, the date the API's offline record and the
frozen window rows use (`fixture.date` in `data/sources.json`), three days after the snapshots were issued.

## The hindcast and the BSS result

Issue #7. The full report with every table and caveat is `HINDCAST.md`; how to run it is `validation_README.md`.
The numbers below are copied from the generated result `data/hindcast/result_canso.json`.

- Period, by forecast issue date: 2026-04-02 to 2026-09-27, 179 verified days, base rate
  0.296. It is the longest period the open forecast archive supports; it is not the 12 months the spec
  asks for, because the archive keeps no run before 2 April 2026.
- Forecast: four archived runs of the GFS deterministic model per issue date, used as a four-member time-lagged
  ensemble and evaluated by the same function as the operational layer. No open archive keeps past runs of the
  ECMWF or GEFS ensembles, so **the operational 82-member probability itself is not what was verified.**
- Outcome: `observed_launchable()` on the hourly archive. Reference: the base rate of the same sample.

| Lead (days) | 1 | 2 | 3 | 4 | 5 | 6 | 7 | 8 | 9 | 10 |
|---|---|---|---|---|---|---|---|---|---|---|
| n_cases | 173 | 172 | 171 | 170 | 169 | 168 | 167 | 166 | 165 | 164 |
| BSS | 0.456 | 0.373 | 0.223 | 0.223 | 0.152 | -0.118 | -0.263 | -0.003 | -0.313 | -0.348 |

Reading, in the words of the report:

- BSS is above zero from lead 1 to lead 5 and at or below zero from lead 6. Skill against climatology
  disappears after lead 5. The FORECAST boundary is set to that lead.
- Spec III.4 criterion 1, BSS above zero pooled over leads 1 to 7: met, BSS 0.151 on 1190 cases.
- Spec III.4 criterion 2, at least 5 populated reliability bins with a mean calibration gap of at most 0.15:
  **not met**. Five bins are populated; the gap is 0.157 against the mean forecast in each bin and 0.147 against
  the bin centres, and the larger figure decides. The forecasts are overconfident, as a four-member ensemble is
  expected to be. No recalibration was applied; the report says why.
- Criterion 3, the series in the spec IV.4 shape: met. `backend/fixtures/skill.json` is the output of
  `scripts/build_skill_fixture.py`, and a test regenerates it and compares the bytes.
- No threshold was changed after the first hindcast run. The report carries the checksum of the criteria file,
  and a test compares it with the file in use.

## Claims and their status (spec II.9)

- The chance-constrained formulation that this layer evaluates is SKETCHED (claim iii). Its assumptions are not
  proven: members are exchangeable samples, the weather is constant over the window, the frequency of L is
  stationary over the climatology period, and the proxy table stands in for flight-safety-grade criteria.
- Positive Brier skill against climatology (conjecture C1 of the spec) is SKETCHED for leads 1 to 5: measured
  on 2026-04-02 to 2026-09-27, 173 to 169 cases per lead, for a four-run GFS ensemble. For leads 6 to 10 the
  same measurement found no skill. For the operational 82-member product it remains a CONJECTURE: it has not
  been verified, because no open archive of its past runs exists.
- The skill horizon (conjecture C2) is SKETCHED at 5 days, with the same period, sample and forecast system
  behind it. It is one period of about six months without a winter. The prior value of 10 days came from Lorenz
  1982 (doi 10.1111/j.2153-3490.1982.tb01839.x), Froude, Bengtsson and Hodges 2013
  (doi 10.3402/tellusa.v65i0.19022) and Buizza and Leutbecher 2015 (doi 10.1002/qj.2619), resolved through
  Crossref on 3 October 2026.
- That the proxy table ranks days as a real criteria set would is a CONJECTURE (C4) and cannot be verified at Canso.

## What this layer does not claim

- It does not claim that probabilistic launch weather is new. Prior art named in spec I.1 and I.3: the NASA MSFC
  APRA and PACER tools (Burns and Altino, AMS 2008) and the 45th Weather Squadron probability-of-violation
  products. Those references are quoted from the spec and were not re-resolved in this workflow: UNVERIFIED here.
- It does not claim flight-safety-grade criteria. The numeric limits come from public documents for other
  vehicles; the Canso assessment supplies the site-specific rules without numbers.
- It does not claim forecast skill for the operational ensemble product, and none beyond 5 days for any
  forecast. See the hindcast section.
- It does not evaluate weather along the flight path, upper-level winds, thin-layer shear, electric fields, cold
  temperature limits, sea state or space weather. Each is listed with its reason in the criteria table.

## Known limitations

- The gust field of the archive is the ERA5 gust as served by Open-Meteo. Compared over April 2024 with the
  Copernicus hourly maximum gust it is lower by 0.4 m/s on average (44 against 49 hours above the 33 kt limit).
- Visibility is observed at Port Hawkesbury, 48.3 km from the site, because no closer station reports it. Fog at
  the coast near Canso can differ from fog at that station.
- The forecast probability is a lower bound when the two ensembles disagree on which members fail on visibility
  alone; it can understate the launch probability on foggy days.
- The wind direction row stands in for plume criteria that are not published. It ignores wind speed.
- The ECMWF ensemble is served at 3-hourly steps after 90 hours and 6-hourly steps after 144 hours, interpolated
  to hourly by Open-Meteo. Hourly maxima such as gusts are smoother at long lead than at short lead.
- One grid cell of 0.25 degrees stands for the pad. Coastal effects such as sea breeze are not resolved.
- Open-Meteo's free tier is for non-commercial use.
- The probability is for the fixed morning window, not for the hour of a particular launch window. The hourly
  climatology is available through `climatology(month, hour)`; an hour-resolved forecast is not exposed because
  the frozen signature has no time argument.
