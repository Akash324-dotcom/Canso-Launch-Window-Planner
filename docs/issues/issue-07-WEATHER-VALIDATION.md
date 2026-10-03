# [WEATHER-VALIDATION] Hindcast, Brier skill, reliability diagram - GATE G2

**Assigned to:** Het (GitHub: @HetJivani04).

**Owner role:** WEATHER developer. **Depends on:** issue #3 (the criteria table and the probability layer, specifically W1 and W3). **Blocks:** the claim that the weather indicator is an instrument rather than a decoration; the Originality rubric row.

**You own:** `backend/weather/hindcast.py`, `backend/weather/HINDCAST.md`, `backend/weather/data/hindcast/`, and the skill entries in `backend/fixtures/`.

**Read first:** `docs/00_INTEGRATION_CONTRACT.md`, then spec Parts **II.7** (the probability layer), **III.4** (this gate), **IV.4** (the response shape), and **VII.1** (data sources). Do not read Parts II.1-II.6, III.1-III.3, V.

**Maintain:** append to `backend/weather/progress.md` after every task.

---

## Mission

The operational layer in #3 produces a probability. This issue establishes whether that probability has **skill** - whether it beats a climatological guess. The deliverable is a hindcast over a stated historical period with a Brier skill score by lead time, a reliability diagram, and an honest written reading of the result. **A negative result reported accurately is a successful completion of this issue. A tuned positive result is a failure of the project.**

Frozen signature (contract Seam 1):
```python
def hindcast(period_start: str, period_end: str, lead_max: int = 10) -> dict:
    """Returns the GET /v1/validation/skill body per spec IV.4. Heavy; cache to disk."""
```

---

## Task backlog (TDD: failing test first, always)

### V0. The scoring functions, pure (1 h)
- [ ] TEST: given a list of `(p, o)` pairs, `brier_score()` equals `mean((p - o)**2)` against a hand computation shown in the docstring. Use at least three cases: a perfect forecast (0.0), a confidently wrong forecast (1.0), and a mixed case
- [ ] TEST: `brier_skill_score(bs, bs_ref)` equals `1 - bs/bs_ref`; a perfect forecast gives 1.0; a forecast identical to the reference gives 0.0; a worse-than-reference forecast gives a negative value and it is not clipped
- [ ] TEST: `bs_ref` is computed from the **climatological base rate** of the verification sample, not from a constant
- [ ] Implement `hindcast.py` scoring functions. No I/O, no network, pure

### V1. Reliability bins (45 min)
- [ ] TEST: `reliability_bins(pairs, n_bins=10)` returns equal-width bins over [0,1] with `p_center`, `observed_freq`, `n`
- [ ] TEST: bins with `n == 0` are **dropped, not zero-filled** (a zero-frequency bin plotted as observed 0 is a lie)
- [ ] TEST: the sum of `n` over bins equals the number of input pairs
- [ ] TEST: a hand-checked case - 10 pairs concentrated in one bin produce exactly one populated bin with the right `observed_freq`

### V2. Historical forecast acquisition (2 h)
- [ ] DATA: obtain historical **forecasts** for the hindcast period, for leads 1 to `lead_max`. Preferred source: the Open-Meteo historical forecast archive (`archive-api.open-meteo.com`); alternate: GEFS archived reforecasts via NOMADS or the AWS Open Data mirror. Record which source in `data/hindcast/source.json` with URL, access date and coverage
- [ ] TEST: the loader parses the archive into `(issue_time, valid_time, fields)` records from a **committed sample fixture**; tests never touch the network
- [ ] TEST: issue times are complete enough to compute leads 1 to `lead_max`; gaps are reported as a count, not silently skipped
- [ ] Record in `progress.md`: the archive's actual date coverage, the number of issue times available, and any gap. **If the archive is too thin to support a 10-lead series, say so here and narrow `lead_max` explicitly** - do not pad

### V3. Verification outcomes (1.5 h)
- [ ] DATA: obtain the **observed** weather for the same days from ERA5 (spec III.4 names it as the verification source) or, if the account is still pending, the same Open-Meteo archive evaluated against the criteria
- [ ] TEST: `observed_launchable(date, criteria_version)` returns 0 or 1 by evaluating the observed fields against the **same criteria version** used by the forecast side. Assert that the same function and the same JSON drive both sides - a mismatch here invalidates the whole gate
- [ ] TEST: a day with missing observations returns `None` and is excluded from the sample, with the exclusion counted

### V4. The hindcast loop (2 h)
- [ ] TEST: with a small synthetic fixture, the loop produces one row per `(issue_date, lead)` with `p` from the forecast, `o` from the observation, and the pair passed to the scoring functions
- [ ] TEST: `skill_series` has exactly one entry per lead from 1 to `lead_max`, each with `lead_time_days`, `bs`, `bs_ref`, `bss`, `n_cases`
- [ ] TEST: `n_cases` is the true count of usable `(p, o)` pairs at that lead. **A lead with `n_cases` below 30 is still reported but the observation count is stated in HINDCAST.md** - a skill value from 20 cases is not a validation
- [ ] TEST: `base_rate` equals the observed launchable fraction over the verification sample and matches a hand computation on the fixture
- [ ] IMPLEMENT the loop with disk cache keyed on `(period, lead_max, criteria_version, forecast_source, verification_source)`. Re-running with an unchanged key must not refetch

### V5. Run it on the real data (2 h)
- [ ] Run the hindcast over the longest period the archive supports, minimum 12 months if available, and record the exact period
- [ ] Produce `skill_series` and `reliability_bins` on real data, and cache the raw outputs to `data/hindcast/`
- [ ] Compare against the **reference forecast**: the climatological base rate. This is what `bss` is measured against, and it is the standard the spec names (`reference_forecast: "climatology_base_rate"`)
- [ ] TEST: the spec IV.4 response validates field for field

### V6. The report - HINDCAST.md (1.5 h) - the honest deliverable
- [ ] Write `backend/weather/HINDCAST.md` containing, in this order:
  1. The period, the forecast source, the verification source, the criteria version, and `n_cases` per lead
  2. The BSS table by lead time
  3. The reliability table (the bins from V1)
  4. The verdict: at what lead, if any, does skill against climatology disappear? State it as a lead number or state that it never rose above zero
  5. The caveats: archive coverage, sample sizes per lead, the criteria table's PROXY rows, and whether ERA5 or the fallback was used
- [ ] **If BSS is at or below zero at every lead, this section says exactly that, in those words.** That is a finding about the current state of the operational layer, and it is more valuable than a fabricated positive
- [ ] If BSS is positive at short leads and dies later, state the crossover lead and set the skill horizon config (from #3, W5) accordingly, with the number and the sample size behind it
- [ ] **Anti-tuning check before you close this issue: read your own criteria evaluation and confirm you did not change a threshold to improve the score.** If you did change one, revert it, re-run, and record both results in HINDCAST.md

### V7. The skill fixture, generated (45 min)
- [ ] IMPLEMENT `scripts/build_skill_fixture.py`: runs the hindcast and writes `backend/fixtures/skill.json` in the spec IV.4 shape
- [ ] TEST: running the script twice produces byte-identical output for the same cache state
- [ ] The fixture is the demo's evidence. It is **generated, never hand-typed** - a hand-typed skill number in the demo has no provenance and fails review

### V8. Documentation (45 min)
- [ ] `backend/weather/validation_README.md`: how to run the hindcast, the cache key, how to regenerate the fixture, and where the raw outputs live
- [ ] Append to `backend/weather/DONE.md`: the BSS result in one line, and what remains unresolved (for example a pending ERA5 account, or a thin archive)

---

## Acceptance criteria (GATE G2 - the issue closes when all hold)

1. `pytest backend/weather/` green, including the pure scoring tests with hand-checked values.
2. `hindcast()` runs end to end on real data and emits a spec IV.4 valid response.
3. `backend/weather/HINDCAST.md` exists and states the BSS result **with `n_cases` per lead, the period, and the sources**. A negative result is stated plainly.
4. `backend/fixtures/skill.json` exists and was produced by the committed script, proven by re-running it.
5. The anti-tuning check is recorded: the criteria version used for the hindcast is the same one the operational layer uses, and no threshold was changed to improve the score.

## Time budget (5 to 6 hours; the rest of the WEATHER budget is in #3)

| Hours | Work |
|---|---|
| 0-1 | V0, V1 (pure scoring, hand-checked) |
| 1-3.5 | V2, V3 (the two archives plus the shared outcome function) |
| 3.5-5.5 | V4, V5 (the loop and the real run) |
| 5.5-7 | V6, V7, V8 (the report, the fixture, the docs) |

## What will go wrong

- **The historical forecast archive is thin or gappy.** Report the coverage, narrow `lead_max` explicitly, and state it in HINDCAST.md. Do not interpolate or pad to fill leads.
- **BSS comes back negative.** Report it. Then check one thing before accepting it: whether a single criterion is almost never satisfied, which makes every day look like a failure and depresses both the forecast and the reference. If that is the cause, the finding belongs in HINDCAST.md alongside the score. **Do not tune thresholds to fix it.**
- **The ERA5 account is still pending.** Use the Open-Meteo archive for verification, say so in HINDCAST.md, and mark the result provisional in the file.
- **The cache produces a stale result after the criteria version changes.** The cache key includes `criteria_version`; verify with a test that changing it forces a recompute.

## Subagent dispatch and anti-corner-cutting law (applies to every task above)

- Dispatch each task to a subagent with this issue's text plus that task's exact acceptance test. Quote into its prompt the spec sections it needs (II.24-II.25 for the formulas, IV.4 for the shape) and the hand-checked numbers from V0.
- A subagent may not close a task on the strength of "it runs". The acceptance test is the closing criterion; paste its output into progress.md.
- **No test weakening.** If a scoring test fails, the formula or the code is wrong. Never adjust the expected value.
- **No tuning to a positive score.** The criteria version is frozen for the hindcast. Any change is reverted, re-run, and both results are recorded.
- **No fabricated numbers.** Every value in HINDCAST.md traces to a computation over a stated sample; every value in the fixture traces to the script.
- No partial development. A module is done when its tests pass and its README states what it does and does not claim.
- Every claim is marked PROVED, SKETCHED or CONJECTURE per spec II.9. The skill horizon remains SKETCHED until this issue's result supports a narrower statement, and that statement carries its period and sample size.
- Every task update appends to progress.md with the exact command run and its observed output.

## Rules

- TDD: red, green, refactor.
- Formal register. No em dashes. No emojis.
- Tests never touch the network; committed fixtures only.
- If a citation is needed, resolve it by title via Crossref, never from memory.
