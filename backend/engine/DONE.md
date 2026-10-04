# DONE: what shipped and what is unfinished

ENGINE, issue #2. Branch `engine/issue-02`. Directory ownership `backend/engine/**`
only; no file outside it was created, edited or deleted.

Last verified: `python -m pytest backend/engine/ -q` -> **283 passed**;
`python -m pytest tests/contract/ -q` -> **70 passed**.
Both counts are from the command shown, scoped to what this workflow owns.
A whole-repo count includes the API workflow's contract tests and is not
this workflow's number to quote.
Frozen contract `python -m pytest tests/contract/ -q` -> **70 passed**.

## Shipped

| Task | Status | Evidence |
|---|---|---|
| E0 Scaffold | DONE | `compute_windows` with the frozen signature, request validation, response shape. |
| E1 Constants | DONE | One module, each value with a source. The duplication rule is enforced BY TEST: the scan fails unless the hit list is exactly `["provenance.py"]`. |
| E2 Frames and GMST | DONE | GMST to 1e-6 deg at a cited epoch; geodetic round trip to 1e-9; rotating-frame correction signed correctly at 45.3 N and exactly zero at the equator. |
| E3 Reachability | DONE | 177.01 / 180.00 / 191.56 deg azimuths; penalty 26.768 m/s; corridor block sets `hazard_area`. |
| E4 J2 dynamics | DONE | -5.1354 deg/day at 600 km, within 1 percent, and asserted NOT to be the rejected constant. SSO table within 0.01 deg. |
| E5 Window equation | DONE | Hand-computed case in the test docstring, width 47.86894 s, sorted, deduplicated, 90-day search, empty-is-valid. |
| E6 Injection-consistent fixed point | DONE | Converges for both reachable classes; contraction factor reported every solve; shifts +1.48 s and -0.40 s with correct signs; two profiles give different shifts; non-convergence yields `fixed_point_no_convergence`. |
| E7 SSO | DONE | Solar series validated against four equinox and solstice anchors to 0.005 deg; inconsistency warns without crashing; LTAN-RAAN coupling invertible. |
| E8 Screens | DONE | Hazard pass/fail, deterministic conjunction over a committed 3-TLE fixture, NOTAM stub. Tests never touch the network. |
| E9 Composition | DONE | Exactly six engine-owned keys; byte-identical numerics on repeat; the 45.1 honesty case returns `reachable: false` with the penalty. |
| E10 GATE G1 | **GREEN** | Four published launches within 2.257 min against a 5 min gate. |
| E11 Provenance | DONE | `source_files` names exactly the files a run read; re-reading reproduces the numbers; row flags travel with the values. |
| E12 Docs | DONE | `README.md` and this file. |

## The gate, stated plainly

`pytest backend/engine/tests/test_reproduce_published_windows.py -q -s`

| Anchor | Residual |
|---|---|
| Sentinel-1C, Kourou ELA-1, 2024-12-05 | -1.545 min |
| EarthCARE, Vandenberg SLC-4E, 2024-05-28 | -0.547 min |
| Sentinel-5P, Plesetsk 133/3, 2017-10-13 | +0.914 min |
| Sentinel-3C, Kourou ELA-1, 2026-09-15 | +2.257 min |

Tolerance 5 minutes, asserted at that value by a test. Three anchors are also
inside spec III.2's 2 minute standard.

## UNDONE, with reasons

Nothing in the task backlog is unfinished. The following are unfinished
*knowledge*, deliberately recorded rather than papered over.

1. **Sentinel-3A and Sentinel-3B do not reproduce** (+24.947 and +7.514 min).
   Published inclination and node time are unambiguous, and the same engine
   reproduces Sentinel-5P from the same pad and vehicle to +0.914 min, so it is
   not a site or vehicle error. **Unexplained.** Excluded and published in
   `data/published_windows.json`. A 30 minute tolerance would admit them and was
   not adopted.
2. **Corridor bounds are ASSUMPTION.** The Canso environmental assessment was
   searched in full and publishes no numeric azimuth corridor. Figure 2.9 exists
   and has no degree axis. The reachable set could therefore change with no code
   change.
3. **`T_to_inj` for Cyclone-4M is ASSUMPTION.** The vehicle guide publishes a
   flight timeline, not a time to orbit. Every window-centre shift scales
   linearly with it.
4. **Hazard footprint cross-range axis is ASSUMPTION.** Not published anywhere
   located.
5. **Operating hours are ASSUMPTION.** No published restriction located.
6. **Citations are not Crossref-verified.** The NASA GSFC Orbit Primer, Vallado,
   Bate/Mueller/White, Aoki and Monteith were each queried by title through
   Crossref and **none has a record**: they are books and technical reports. No
   DOI was invented. One DOI was verified real, `10.2514/1.A36618`. This is an
   open question for whoever owns the citation register.
7. **Conjunction screen is coarse by construction**, and Space-Track is unused
   pending Het's key. One-line switch when it exists.
8. **No published window INTERVALS.** All four anchors publish a launch instant,
   not an open and a close, so the gate cannot test interval overlap as spec
   III.2 asks. The two candidates that publish intervals were both dropped for
   stated reasons.
9. **Spec figures not reproduced**, asserted at the value derived from the
   governing equation and recorded: the II.6 inclination sensitivity (3x off),
   the II.6 minute-per-year figure (10x off from its own neighbour), and the
   II.3 -0.27 deg/day drift row (1.3 percent off at the precision printed).

## Not built, by design

Weather and probability (WEATHER owns it), NOTAM querying, SGP4 propagation,
ephemeris endpoint content beyond the kinematic ascent of `ascent.py` (flagged
ASSUMPTION, not an integrated trajectory) and the plane model, phasing, and everything spec
I.4 places out of scope: general manoeuvre design, 6-DOF, attitude control, force
models beyond secular J2 in the window core, rideshare manifesting, SDE
trajectory layer.

## Open issues to file against other owners

1. **API:** `tests/contract/test_engine_schema.py` does not exist. It is listed
   as this workflow's obligation but the directory is API-owned. The engine's own
   equivalent is enforced here: `tests/test_smoke.py` asserts the response carries
   exactly the six engine-owned keys, so once the API adds its five fields the
   frozen schema will hold without the engine changing.
2. **API:** the engine emits no `constants_block` or `provenance_block`, by
   contract. The API must call `provenance.constants_block(run_id)` and
   `provenance.build_provenance_block(request)`. Both are tested.
3. **Spec owner:** clarify whether `reachable` is corridor-inclusive. This engine
   follows (II.4) and says so in `engine.py`, and additionally reports the
   corridor-blocked window rows so no information is lost either way.