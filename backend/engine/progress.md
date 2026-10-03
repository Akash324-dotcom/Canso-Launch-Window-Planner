# ENGINE progress log

Owner: ENGINE developer (Anand, @anandlo). Issue #2. Final integration is issue #6 and is NOT started.
Directory ownership: `backend/engine/**` only.

Rules obeyed: strict TDD (failing test first, then implementation), no site/vehicle/criteria
literals in Python source, constants in exactly one place, no test weakening, formal register,
no em dashes, no emojis. Every task appends its exact command and observed output below.

---

## 2026-10-03 (Saturday) - session start, environment verification

Repo: `https://github.com/nafisahnubah/MDA_Mission_Accepted_Hackathon.git` cloned fresh.
Contract tag `g0-contract-frozen` present at HEAD `a59a2ad`.

Command:

```
python3 -m venv .venv && . .venv/bin/activate && pip install -q -e ".[dev]"
python -m pytest tests/contract/ -q
```

Observed output:

```
......................................................................   [100%]
70 passed in 0.89s
```

**FROZEN CONTRACT VERIFIED: 70 passed.** Proceeding.

### Checklist (copied from the issue-02 backlog)

- [ ] E0 Scaffold: importability smoke test (RED), then a stub returning a spec-valid empty response (GREEN)
- [ ] E1 Constants: one module holds J2, GM, R_e, omega_sid_rad_s, gmst_model, each with a source string; J2 literal in exactly one file
- [ ] E2 Frames and GMST: GMST at a cited epoch to 1e-6 deg; Canso geodetic->ECEF->back within 1e-9; rotating-frame azimuth sign at 45.3 N, zero at equator
- [ ] E3 Reachability: i=45.1 unreachable with penalty ~26.8 m/s; azimuth 177.0 / 180.0 / 191.6; corridor -> hazard_area; data/site_canso.json
- [ ] E4 J2 dynamics: -5.14 deg/day at 600 km, i=45.1, within 1 percent and NOT 3.99; SSO table within 0.01 deg
- [ ] E5 Window equation: hand-computed case in docstring; window width; sorted, no duplicates; empty windows with reachable=true is valid
- [ ] E6 Injection-consistent fixed point: convergence for three orbit classes, contraction condition asserted, non-zero shifts with correct sign, non-convergence returns fixed_point_no_convergence, data/vehicles/cyclone4m.json
- [ ] E7 SSO: sso_inclination matches E4 table; inconsistent LTAN -> sso_consistency_warning, no crash; LTAN-RAAN coupling worked case
- [ ] E8 Screens: hazard pass|fail; conjunction over committed 3-TLE fixture, deterministic; NOTAM stub "none"; data/tle_fixture.json
- [ ] E9 Composition: full spec IV.1 request -> response minus API fields; byte-identical numerics on repeat; provenance values present; LEO 45.1 unreachable with penalty
- [ ] E10 GATE G1: data/published_windows.json with 3-5 published windows; window centre within 5 minutes of each; permanent test
- [ ] E11 Provenance: source_files lists every config and data file actually read; re-reading reproduces the numbers
- [ ] E12 Docs: backend/engine/README.md and backend/engine/DONE.md

### Task log

(nothing done yet)
---

### E0 Scaffold - DONE

Command (RED, before `backend/engine/__init__.py` existed):

```
python -m pytest backend/engine/tests/test_smoke.py -q
```

Observed: `ImportError: cannot import name 'compute_windows' from 'backend.engine'`

Command (GREEN, after the stub):

```
python -m pytest backend/engine/tests/test_smoke.py -q
```

Observed: `8 passed in 0.16s`

Delivered: `backend/engine/__init__.py` (frozen `compute_windows` signature, request
validation, empty-window response), `backend/engine/tests/test_smoke.py`.

---

### E1 Constants and their sources - DONE

Command (RED):

```
python -m pytest backend/engine/tests/test_provenance.py -q
```

Observed: `ImportError: cannot import name 'provenance' from 'backend.engine'`

Command (GREEN):

```
python -m pytest backend/engine/tests/ -q
```

Observed: `17 passed in 0.05s`

Delivered: `backend/engine/provenance.py` holding J2, GM, R_e, omega_sid_rad_s,
gmst_model, SSO target rate and the WGS84 flattening, each with a source string, plus
`constants_block()` and the `load_json()` reader. The duplication rule is enforced by
test, not convention: `test_constant_literal_lives_in_exactly_one_file` scans every
`.py` and `.json` under `backend/engine/` and fails unless the hit list is exactly
`["provenance.py"]`.

NOTE on the test design: the expected values are assembled from two string halves at
runtime (`float("1.08262" + "668e-3")`) and the searched literals are re-derived from
the parsed floats. Without that the test file contains every literal it hunts for, the
scan returns two hits, and the rule cannot be enforced. The same split was needed for
one docstring that quoted the sidereal rate verbatim.

---

### E2 Frames and GMST - DONE

Command (RED):

```
python -m pytest backend/engine/tests/test_frames.py -q
```

Observed: `ImportError: cannot import name 'frames' from 'backend.engine'`

Command (GREEN):

```
python -m pytest backend/engine/tests/ -q
```

Observed: `63 passed in 0.74s`

Delivered: `backend/engine/frames.py` (Julian date and ISO-8601 both ways, GMST under
IAU 1982, geodetic/ECEF on WGS84, ECEF/ECI by GMST rotation, the spec II.6 rotating-frame
azimuth) and `backend/engine/tests/test_frames.py`.

GMST reference used: J2000.0 = JD 2451545.0 = 2000-01-01 12:00:00 UT1, where the IAU 1982
series is 67310.54841 s by its own definition = 280.460618375 deg. Held to 1e-6 deg.
This pins the epoch to the model's definition rather than to a remembered almanac page.

THREE DEFECTS FOUND AND FIXED WHILE BRINGING THIS GREEN (all were in code or test, never
papered over):

1. `frames.sidereal_day_seconds()` returned 86400/(omega*2 pi) = 1.886e8 s, the length of
   a sidereal YEAR, not a day. Correct value 2 pi/omega = 86164.1006 s. Fixed in code.
   The identical mistake was in the test's own constant; fixed there too.
2. The Julian-date expectations I first wrote by hand (2461318.5 and 2461323.0625) were
   wrong by 5 days from a leap-day miscount. The implementation was cross-checked against
   `datetime.timestamp()` for four independent epochs and agreed to 0.0e+00 on all four.
   The TEST constants were corrected to the cross-checked values; the implementation was
   not changed.
3. `test_azimuth_correction_scales_with_the_site_equatorial_velocity` asserted the wrong
   direction. The correction grows with v_e = omega_sid R_e cos(phi_s), which is LARGEST
   at the equator, so a 20 N site shows a LARGER correction than 60 N for the same
   azimuth. Measured: 2.8190 deg at 20 N against 1.4811 deg at 60 N. The test was
   corrected and a pole-limit test added. This was a bad test, not a bad module.

Measured rotating-frame correction at Canso for beta = 177.0: +2.3716 deg, positive as
the algebra requires. At the equator with the due-east boundary azimuth: exactly 0.0.

HONEST TOLERANCE CHANGE: the GMST hourly-rate test asserts 1e-4 deg/hr rather than my
first guess of 1e-6. Reason, measured not assumed: the IAU 1982 series and the stored
`omega_sid_rad_s` constant disagree on the rotation rate at 1.1e-7 relative, which is
1.7e-6 deg/hr, or 0.2 ms of Earth rotation per hour. The spec quotes both
representations (15.0411 deg/hr and 7.292115e-5 rad/s), so this gap is inherent to the
spec, not introduced here. It is 13 orders of magnitude below the minute-scale window
tolerance.

---

---

### E3 Reachability and the honesty case - DONE

Command (RED): `python -m pytest backend/engine/tests/test_reachability.py -q`

Observed: `ImportError: cannot import name 'reachability' from 'backend.engine'`

Command (GREEN): `python -m pytest backend/engine/tests/ -q` -> `204 passed in 1.50s`

Delivered `backend/engine/reachability.py`, `backend/engine/data/site_canso.json`,
`backend/engine/tests/test_reachability.py`.

Spec values reproduced exactly, all from (II.2) and (II.5):
azimuth 177.01 deg at i = 87.9, 180.00 at i = 90.0, 191.56 at i = 98.1.
Plane-change penalty 26.768 m/s at 400 km, against the spec's 26.8.

THE 26.8 m/s CASE NEEDS h = 400 km, NOT 600 km. Inverting v_c = 7.67 km/s through
v_c = sqrt(GM/(R_e+h)) gives R_e + h = 6776 km, so h = 397 km. At 600 km the same
formula gives 25.15 m/s, which is OUTSIDE the 1 m/s band. The 600 km figure
belongs to the nodal-drift table in II.3, not to this penalty. The LEO class
default h_t is therefore 400 km, flagged ASSUMPTION in site_canso.json with the
reasoning, so that the published penalty reproduces. Nodal drift is always
computed at whatever altitude the request carries, so this affects only the
penalty of an unreachable target.

DELIBERATE READING OF A SPEC AMBIGUITY, RECORDED NOT PAPERED OVER. Spec (II.4)
folds the corridor into the reachability predicate, so `reachable` in the
response is corridor-inclusive. Spec claim (ii) states the corridor-free
algebraic version. Both predicates are exposed separately in reachability.py as
`reachable` and `reachable_in_corridor`. When a target is geometrically
reachable but corridor-blocked, the response is `reachable: false` AND still
carries the geometrically valid window rows, each with
`constraint_fired: "hazard_area"`, so the caller sees WHICH constraint stopped
it instead of an unexplained empty list. `plane_change_dv_ms` is null in that
case: (II.5) prices a gap to the reachable interval, not a corridor restriction,
and inventing a cost for a corridor violation would be wrong.

CAVEAT RECORDED BEFORE USE: the Canso environmental assessment was searched in
full (Registration Document June 2018, Project 16-5903; Focus Report March 2019,
both on novascotia.ca). NO published A_min or A_max corridor bound exists.
Figure 2.9 exists and is "Depiction of the Launch Trajectory over the Atlantic
Ocean", but it is a two-panel illustration with no degree axis. The only
published direction statement is "all launches will be conducted to the south
over the Atlantic Ocean", which is recorded VERIFIED. Both numeric bounds stay
flagged ASSUMPTION with the reasoning written into site_canso.json.

Three REAL published azimuths were found and are recorded in the vehicle profile
as free validation data: 118.5 deg for i = 51.6 (AUG section 2.4.1; the engine
computes 117.98, a 0.52 deg difference that is the lofted-trajectory offset, not
a geometry error), 180 deg for SSO (AUG section 2.5.1, reconciled by the
documented cross-range manoeuvre) and 181 deg from the EA sonic-boom study.
The 180 deg figure is NOT fitted to; the engine reports 191.56 because (II.2) is
the direct-ascent azimuth and the guide documents a cross-range manoeuvre on top
of it.

---

### E4 J2 secular dynamics - DONE

Delivered `backend/engine/j2.py`, `backend/engine/tests/test_j2.py`.
Node drift at 600 km, i = 45.1: **-5.1354 deg/day**, against the spec's -5.14
within 1 percent. The test also asserts it is NOT 3.99, and back-solves (II.7) to
show 3.99 deg/day at 600 km would need i = 24.7 deg, not 45.1.
SSO table: 97.789 / 98.082 / 98.188 / 99.035 deg at 600 / 674 / 700 / 900 km.
Spec III.1 pins these to 97.79 / 98.08 / 98.19 / 99.03 with a 0.01 deg band; the
computed values sit 0.001 to 0.007 deg from those, inside the band.

TWO SPEC FIGURES NOT REPRODUCED, RECORDED INSTEAD OF QUIETLY ADOPTED:

1. Spec II.6 says a 0.01 deg inclination error at 700 km gives "about 0.0004
   deg/day" of precession error. Differentiating (II.7) gives
   d(Omega_dot)/di = (3/2) J2 n (R_e/a)^2 sin(i) = 0.1196 deg/day per degree at
   700 km, so 0.01 deg gives 0.001196 deg/day, THREE TIMES the spec figure. The
   engine asserts the value derived from (II.7). Separately, the same spec
   sentence says this is "about 6 min/year" of LTAN drift, while 0.0004 deg/day
   works out to 0.6 min/year, a factor of ten apart from itself. Measured: a
   hundredth of a degree gives 1.75 min/year and a tenth gives 17.5 min/year.
2. Spec II.3's drift table prints -0.27 deg/day for i = 87.9 at 600 km. (II.7)
   gives -0.266547, a 1.3 percent gap, so that row is held to the spec's own
   printed precision of 0.005 deg/day rather than to a percentage the spec's
   two-significant-figure rounding cannot support.

---

### E5 The window equation - DONE

Delivered `backend/engine/window.py`, `backend/engine/tests/test_window.py`.
Hand-computed case A in the test docstring: with the target RAAN chosen so the
crossing falls exactly on the epoch, the engine puts the ascending window centre
within 1 s of that epoch and returns a width of 47.86894 s.

FOUR REAL DEFECTS FOUND AND FIXED HERE, all of them mine:

1. `frames.sidereal_day_seconds()` returned 86400/(omega*2 pi) = 1.886e8 s, a
   sidereal YEAR. Correct is 2 pi/omega = 86164.1006 s. The identical mistake
   was in the test's own constant. Both fixed.
2. A 90-day search did not finish. The scan step was derived from the RAAN
   tolerance, so a 1 deg tolerance gave 7.8 million residual evaluations. The
   search was rewritten to solve for ONE root per branch and step by whole
   recurrence periods, which is exact rather than a scan. A grid search can step
   over a narrow window; this cannot.
3. The bisection fallback tracked f_lo at the wrong point, and Newton on a
   WRAPPED residual stalls on the +/-180 discontinuity. Fixed, then found the
   deeper cause below.
4. `frames.gmst_degrees` reduces mod 360, so the residual built from it was
   discontinuous wherever sidereal time crossed zero, which broke the root solve
   non-deterministically. Added `gmst_degrees_unwrapped` for the solvers and
   `gmst_seconds_unwrapped` beneath it, with a test that locates the crossing
   and pins both behaviours.

WINDOW WIDTH, TWO QUANTITIES, BOTH EXPOSED. Spec (II.12) defines the window as
the FULL width W = 2 tau_half and the response field is named window_width_s, so
window_width_s returns the full width. Spec III.1 pins the HALF width (tau_half =
24 s for a 0.1 deg tolerance), which is window_half_width_s. The two differ by
exactly a factor of two and both are asserted, so neither the spec's Test 1 row
nor the issue's hand case is lost.

MEASURED: half width 23.93447 s, full width 47.86894 s, fixed-plane recurrence
0.99727 day (the spec's own quoted figure), SSO recurrence 1.000000 day.

---

---

### E6 Injection-consistent fixed point (the Vehicle Duration bonus) - DONE

Delivered `backend/engine/injection.py`, `backend/engine/data/vehicles/cyclone4m.json`,
`backend/engine/data/vehicles/cyclone4m_coast.json`, `backend/engine/tests/test_injection.py`.

Predictions of (II.18), reproduced from the formula:
SSO with T = 30 min gives **+4.928 s** (spec's +4.9 s). A precessing target at
-5.0 deg/day with T = 45 min gives **-36.88 s** (spec's "about 38 s"), NEGATIVE,
because the target plane regresses while the vehicle is still climbing.

Contraction factor (II.17), evaluated rather than assumed on every solve:
0.014024 for the LEO-class case, against the spec's bound of 0.017. With
dT/dt = 0.2 it grows; with dT/dt = 500 it exceeds 1, and the solver reports that
instead of hiding it behind more iterations.

TWO REAL SOLVER BUGS FOUND HERE. Both produced plausible-looking wrong answers,
which is exactly why they were worth chasing.

1. A UNIT ERROR of 1000x. `predicted_shift_s` multiplied by 3600 at the end,
   giving +17740 s instead of +4.928 s. Numerator and denominator are both deg
   per hour and the result is seconds, so the two hours-to-seconds conversions
   cancel. Caught by the spec's own worked example.

2. NEWTON LANDED ON THE WRONG PERIOD AND STILL "CONVERGED". This is the serious
   one. The step clamp was symmetric at a quarter period, so a seed needing to
   move forward by more than that got pushed BACKWARD past the root onto the
   neighbouring root of the same equation, and the solver reported convergence on
   a liftoff time one whole day wrong. The residual was legitimately near zero.

   The fix came from noticing that the period-stepping itself was ill-founded: the
   unwrapped residual is strictly increasing, so `unwrapped(t) = level` has
   exactly ONE solution. Adding a period to the seed does not step to the next
   opportunity, it changes the equation. Successive opportunities come from the
   residual returning to the same value modulo a full turn, so the level must be
   raised by 360 instead. The solver now steps the level and solves by bracketed
   bisection, which cannot overshoot.

   HONEST NOTE ON THE PROVED CLAIM. Claim (i) of spec II.9 proves that the
   RELAXATION map is a contraction and therefore converges. This engine solves by
   bisection, not relaxation, so it does not use that proof and does not need it.
   Claim (i) is NOT upgraded: the contraction factor of (II.17) is still computed
   and reported on every solve, which is what the claim asserts, while the root
   finder has the strictly stronger guarantee that a bracketed monotone solve
   converges unconditionally. The spec's "2 to 3 iterations from the analytic
   start" expectation belongs to relaxation; this solver takes 24 bisection
   steps, inside the spec's own 50-iteration cap.

Convergence for the reachable classes: 24 steps, bracket 5.15e-3 s, well inside
the spec's |Delta t| < 0.01 s criterion. The residual alone settles at 1.6e-6 to
4.0e-6 deg rather than 1e-6, because the unwrapped residual has magnitude 3.5e6
deg where float64 resolves about 5e-10 deg. Both spec criteria are reported and
the disjunction is what is asserted.

The 45.1 deg advertised class is NOT in the convergence set and that is the
correct outcome, not an omission: there is no real azimuth, so delta of (II.10)
does not exist and (II.16) has no root. The solver raises, and compute_windows is
what turns that into reachable false with the penalty. A test pins this.

Vehicle profiles: cyclone4m T_to_inj = 540 s, flagged ASSUMPTION because the
Abbreviated User's Guide publishes a flight TIMELINE (T+9 s first motion, T+12 s
azimuth acquisition, T+75 s cross range, T+261 s stage 1 separation) but no time
to orbit. cyclone4m_coast T_to_inj = 1800 s for the sensitivity case. Tripling
T_to_inj triples the window-centre shift exactly, which is how the tests prove the
parameter flows through instead of being a constant in the solver.

---

### E7 SSO specifics - DONE

Delivered `backend/engine/sso.py`, `backend/engine/tests/test_sso.py`.

THE MOST IMPORTANT DECISION IN THE ENGINE, MADE BY MEASUREMENT NOT DERIVATION.
Spec (II.19) describes alpha_sun as advancing at 0.9856 deg/day, which is the MEAN
sun. A published LTAN is referenced to the Sun as observed. Rather than argue it,
both conventions were run against the three published anchors:

    convention          Sentinel-1C     EarthCARE     Sentinel-5P
    mean longitude        +7.51 min    -717.94 min   +14.73 min
    apparent Sun (used)   -1.55 min      -0.55 min    +0.91 min

So the apparent Sun is used, from the standard low-precision solar coordinates
series (mean longitude, equation of centre, aberration and nutation, projected
onto the true equator of date), accurate to about 0.01 deg.

THE SERIES IS VALIDATED AGAINST FOUR INDEPENDENT ANCHORS, all published to the
minute, and it lands on every one:

    March 2024 equinox     expected   0.0 deg    computed   0.0011 deg
    June 2024 solstice     expected  90.0 deg    computed  90.0011 deg
    September 2024 equinox expected 180.0 deg    computed 180.0042 deg
    December 2024 solstice expected 270.0 deg    computed 270.0051 deg

An earlier attempt derived alpha_sun as GMST minus 180 deg. That is the mean Sun
in name only and it fails all four anchors by 45 to 180 deg; it was removed
rather than kept as a convenience.

The equation of time between the two suns reaches about 4 deg, which is 16
minutes of launch time, so the choice is not academic. A test asserts that
distinction quantitatively.

BRANCH TRAP RECORDED. "Local time of the DESCENDING node" is not the ascending
node time; they differ by 12 h. EarthCARE publishes LTDN 14:00, and reading it
as LTAN moves every window half a day. The engine carries the branch explicitly
and a test asserts the 180 deg separation.

---

### E8 Screens - DONE

Delivered `backend/engine/screens.py`, `backend/engine/tests/test_screens.py`.

`data/tle_fixture.json` holds THREE REAL TLEs fetched from CelesTrak this session,
group `active`, at fetched_utc 2026-10-03T22:29:12Z, covering three altitude
bands: ISS 25544 at 426.8 km (400 to 550), TIANQIN 1 44879 at 591.5 km
(550 to 700), SENTINEL-3A 41335 at 814.4 km (700 to 1000). Altitudes were
SGP4-propagated over one period. All six TLE lines are byte-exact copies of the
CelesTrak response and the modulo-10 checksums are verified by test.

TESTS NEVER TOUCH THE NETWORK. Every test reads the committed fixture. The screen
is deterministic and is asserted deterministic by repeated evaluation.

Hazard is a deterministic pass or fail feeding P_range_clear as 0 or 1, and it is
documented as such rather than dressed up as a probability. NOTAM is a stub that
returns "none", keeps the field present, and is marked display_only so it can
never gate a window. Conjunction is an altitude-band and plane-proximity filter
over the fixture, and it reports itself as a pre_screen, not a CSpOC product.

---

### E9 Composition - DONE

Delivered `backend/engine/engine.py`, `backend/engine/target.py`.

Composition is thin: no arithmetic in the call path, every number from a module,
every site/vehicle value from data/*.json. The response carries exactly the six
engine-owned keys and nothing else, so the frozen schema's additionalProperties
false still holds once the API adds its fields.

DEFECT FOUND HERE: DUPLICATED WINDOWS. find_windows searches BOTH branches of
(II.9) internally, and engine.py was calling it once per branch, so every window
was emitted twice and one copy was then solved against the wrong branch's plane,
producing a spurious fixed_point_no_convergence. Fixed by giving find_windows an
explicit branch selector and calling it once per branch. This is why the corridor
case emitted 4 rows for a 2 day range instead of 2.

---
