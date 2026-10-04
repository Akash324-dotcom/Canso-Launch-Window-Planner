# ENGINE: launch window decision engine, Spaceport Nova Scotia (Canso)

Owner: ENGINE developer, issue #2. This directory is self-contained: it reads
`backend/engine/data/*.json` and nothing else, touches no network, and depends
on nothing outside the standard library.

## What it computes

`compute_windows(request: dict) -> dict` is the frozen seam. It turns a spec IV.1
request into launch windows, or into an honest refusal when the target cannot be
reached from this pad.

The response it returns is the engine's share of the spec IV.1 body. It
deliberately does **not** contain `p_success`, `p_success_components.weather`,
`horizon_label`, `forecast_issue_time`, `constants_block` or
`provenance_block`: the API composes those. The API gets them from two
importable helpers:

```python
from backend.engine import provenance
provenance.constants_block(run_id)            # the constants block
provenance.build_provenance_block(request)    # the provenance block
```

### The chain

1. `target.py` resolves the request against `data/site_canso.json`: orbit class,
   altitude, inclination, plane, tolerance, node branch.
2. `reachability.py` applies the reachability predicate (spec II.4). If the
   target is below the pad latitude there is no real azimuth, and the response
   says so with the plane-change penalty of (II.5).
3. `j2.py` computes secular nodal drift (II.7) and, for an SSO request, the
   inclination the altitude demands.
4. `sso.py` converts an LTAN requirement into a date-indexed RAAN (II.19).
5. `window.py` finds the opportunities: the site lies in the target plane when
   (II.9) holds, solved per branch and stepped by whole recurrence periods.
6. `injection.py` refines each opportunity so the plane condition holds at
   INJECTION rather than at liftoff, which is the Vehicle Duration bonus.
7. `screens.py` runs the hazard, conjunction and NOTAM pre-screens.

### Running the tests

```bash
git clone https://github.com/nafisahnubah/MDA_Mission_Accepted_Hackathon.git
cd MDA_Mission_Accepted_Hackathon
python3 -m venv .venv && . .venv/bin/activate
pip install -e ".[dev]"
python -m pytest backend/engine/ -q          # 283 passing
python -m pytest backend/engine/tests/test_reproduce_published_windows.py -q -s
```

The second command prints the G1 residual table. No test touches the network.

## The two PROVED claims

Claim status is exactly as spec II.9 marks it. Nothing here is upgraded.

**Claim (ii), reachability, PROVED and algebraic.** Direct ascent from site
latitude `phi_s` reaches inclination `i` if and only if `i` lies in
`[phi_s, 180 deg - phi_s]`, because the ascent plane is spanned by the site
position and the liftoff velocity, whose component algebra gives
`cos(i) = cos(phi_s) sin(beta)`, and solving for `beta` needs
`|cos(i)/cos(phi_s)| <= 1`. At 45.3 N the advertised 45.1 deg LEO product is 0.2
deg below the pad, so no azimuth exists. `reachability.py` is the implementation;
`tests/test_reachability.py` is the check.

**Claim (i), the injection-consistent fixed point, PROVED for the relaxation
map.** The specification proves that the relaxation map `Phi` is a contraction
whenever `|dOmega/dt (1 + dT/dt)| < |omega_sid - dOmega/dt|`, and that the
iteration therefore converges to a unique root.

This engine does **not** rely on that proof, and the distinction is deliberate.
The contraction factor of (II.17) is computed and reported on every solve, which
is what the claim asserts, and the tests assert it holds at 0.014024 against the
spec's bound of 0.017. But the root finder is a bracketed bisection, not
relaxation, because a clamped relaxation step was caught landing on the
neighbouring period's root and reporting convergence on a liftoff time one whole
day wrong. Bisection on the monotone unwrapped residual has the strictly stronger
guarantee of unconditional convergence. Claim (i) is therefore neither proved nor
disproved for this code; it is reported, not relied upon.

What is SKETCHED and what is CONJECTURE per spec II.9: the chance-constrained
window and the opportunity-process decision layer are SKETCHED. Positive forecast
Brier skill at this site, the skill-horizon value, and proxy-criteria consistency
are CONJECTURE. The weather layer is not in this directory at all, so the engine
makes no forecast-skill claim of any kind.

## Gate G1: what reproduced and what did not

The gate lives in `tests/test_reproduce_published_windows.py` and stays in the
suite permanently. It runs at two levels.

**Level 1, the physics.** For each anchor the engine is given only the site
coordinates, the PUBLISHED inclination, the PUBLISHED local time of the ascending
or descending node, and the date. The published RAAN is never supplied and never
back-solved, because back-solving would make the test circular.

**Level 2, the seam, and this is the level that matters for the team.** A second
test drives the shipped `compute_windows` for every anchor over a real date range
and asserts the returned window centre matches the published instant. Level 1 was
insufficient on its own: an earlier version of it re-derived the residual and the
root solve inside the test file, and an adversarial mutation audit showed the
gate still passed with `find_windows` returning an empty list, with
`solve_injection_consistent` raising, with `nodal_rate_deg_per_day` forced to zero
and with `gmst_degrees_unwrapped` forced to zero. A gate that re-implements the
algorithm it is gating cannot detect the algorithm being broken. Level 2 catches
all four. Both levels are re-verified by mutation audit; the residual table below
is measured by Level 1 and reproduced independently through Level 2 to within
0.03 min.

**Residual is the engine's window centre minus the published launch instant:**

| Case | Site | i (deg) | Published node | Engine residual |
|---|---|---|---|---|
| Sentinel-1C, 2024-12-05 | Kourou ELA-1 | 98.18 | LTAN 18:00 | **-1.545 min** |
| EarthCARE, 2024-05-28 | Vandenberg SLC-4E | 97.05 | LTDN 14:00 | **-0.547 min** |
| Sentinel-5P, 2017-10-13 | Plesetsk 133/3 | 98.74 | LTAN 13:35 | **+0.914 min** |
| Sentinel-3C, 2026-09-15 | Kourou ELA-1 | 98.60 | LTDN 10:00 | **+2.257 min** |

Tolerance is 5 minutes and is asserted at that value by
`test_the_gate_does_not_widen_its_tolerance_to_absorb_a_miss`. Three of the four
are also inside spec III.2's tighter 2 minute standard; Sentinel-3C is 0.257 min
outside it and is recorded rather than dropped.

**Case not reproduced, and why.** Sentinel-3A (+24.947 min) and Sentinel-3B
(+7.514 min), both Rockot from Plesetsk with unambiguous published inclination
and node time, miss the gate. The same engine reproduces Sentinel-5P from the same
pad and vehicle to +0.914 min, so this is not a site or vehicle error, and no
physical explanation was found within scope. They are excluded and their measured
residuals are published in `data/published_windows.json`. A 30 minute tolerance
would admit them. It was not adopted. Landsat 9 misses by +16.011 min because
Atlas V lofts for roughly half an hour downrange before inserting, which a
pad-plane model cannot represent. Sentinel-1D misses at +9.641 min against a
published time whose sources differ by a minute.

### The branch trap, stated once

A descending node at 10:00 and an ascending node at 22:00 are the **same
orbital plane**. The published branch therefore fixes the plane, not which launch
instant is used. Into any one plane the site crosses twice per period, and both
are legitimate opportunities. Pairing the published branch with a single site
crossing double-counts the branch and shifts EarthCARE by twelve hours, which is
exactly the error the test caught. The gate asks whether the published instant is
*any* of the engine's opportunities into the published plane, and reports which
branch matched.

## Every ASSUMPTION row in the data files

No corridor bound, no ascent duration and no footprint is published. Each is
flagged and the flag is carried on the response.

**`data/site_canso.json`**

| Row | Flag | Why |
|---|---|---|
| `corridor.A_min_deg` = 90 | ASSUMPTION | Not published. Set to due east, the azimuth giving exactly the pad latitude, which the reachability algebra makes the minimum reachable inclination. A consequence of geometry, not a range constraint. |
| `corridor.A_max_deg` = 200 | ASSUMPTION | Not published. Extends past due south to cover the 98.1 deg SSO azimuth plus margin. Caps the reachable inclination at about 104 deg, as spec II.2 states. |
| `corridor` as a whole | ASSUMPTION | The Canso environmental assessment (Registration Document June 2018, Project 16-5903; Focus Report March 2019) was searched in full and publishes **no** numeric corridor. Figure 2.9 exists but is a two-panel illustration with no degree axis. |
| `operating_hours` | ASSUMPTION | No published operating-hours restriction located. Treated as continuously available so operating hours never silently removes a window. |
| `target_classes.CUSTOM` | VERIFIED | Carries no defaults, because spec IV.1 requires explicit fields for CUSTOM. |
| `target_classes.LEO.h_t_km` = 400 | ASSUMPTION | The advertised inclination is published, the class altitude is not. 400 km is chosen because it is the altitude at which the spec's own 26.8 m/s penalty reproduces; at 600 km the same formula gives 25.15 m/s. Affects only the penalty of an unreachable target. |
| `coordinate_variants` | VERIFIED | Alternate published coordinates recorded by spec II.1. |
| `car_references` 602.43, 602.44 | VERIFIED | Confirmed at laws-lois.justice.gc.ca under SOR/96-433. |
| `conjunction.miss_threshold_km` = 50 | ASSUMPTION | Spec II.8 names the key and states the default is an assumption pending range feedback. |

**`data/vehicles/cyclone4m.json`**

| Row | Flag | Why |
|---|---|---|
| `t_to_inj_s` = 540 | ASSUMPTION | **Not published.** The Abbreviated User's Guide gives a flight timeline (T+9 s first motion, T+12 s azimuth acquisition, T+75 s cross range, T+261 s stage 1 separation) but no time to orbit. 540 s is the class floor for a direct insertion, consistent with the 10 to 60 min range in spec II.5. |
| `hazard_footprint.downrange_km` = 2000 | ASSUMPTION | Registration Document gives "just over 2,000 km south of the launch site"; read as the debris downrange extent. |
| `hazard_footprint.cross_range_km` = 200 | ASSUMPTION | **Not published in any located document.** Assumed from the small-launch-vehicle class. |
| `hazard_footprint.pad_hazard_area_radius_m` = 500 | VERIFIED | Registration Document: "a radius of less than 500 metres". |
| `ascent_profile.*` | VERIFIED | Abbreviated User's Guide section 2.5.2 Table 2.2. |
| `published_azimuths` 118.5, 180, 181 | VERIFIED | AUG sections 2.4.1 and 2.5.1; Registration Document section 5. |
| `lateral_manoeuvre.applies_below_inclination_deg` = 45.1 | VERIFIED | AUG section 2.3. This is the vehicle guide's own note on the impossibility the engine reports. |

**`data/vehicles/cyclone4m_coast.json`** is a sensitivity case, every row
ASSUMPTION except the two inherited from the same guide. It exists so the tests
can prove `T_to_inj` flows through the solver rather than being a constant in it.

**`data/tle_fixture.json`** records `fetched_utc`, the exact CelesTrak URL, and
the group. Three real TLEs at 426.8, 591.5 and 814.4 km. Mean altitudes were
SGP4-propagated over one period and are ASSUMPTION-free computations, but the
fixture is a snapshot and goes stale.

**`data/published_windows.json`** records the altitude used for two anchors as
ASSUMPTION, because those sources publish inclination and node time but not
altitude. The test passes the published inclination directly, so the assumed
altitude does not enter the comparison.

## Known-unread and unresolved items

1. **The environmental assessment Figure 2.9 three-sigma corridor check** (spec
   SCIENCE Sec G.2). Both corridor bounds remain ASSUMPTION until this is read.
   This is the single largest open item and it is why the reachable set could
   change without any code change.
2. **Sentinel-3A and Sentinel-3B do not reproduce.** Measured residuals are
   published. Unexplained.
3. **Citations could not be Crossref-verified.** The project's rule is to resolve
   every citation by title through Crossref. Queries were run for the NASA GSFC
   Orbit Primer, Vallado, Bate/Mueller/White, Aoki's GMST conversion and
   Monteith, and **none has a Crossref record**: they are books and technical
   reports, which do not carry DOIs. No DOI has been invented for any of them.
   The source strings in `provenance.py` therefore name the document and the spec
   table row rather than an identifier. One Crossref lookup did succeed and is
   real: `10.2514/1.A36618`, O'Neill and Davidheiser, "Estimating the Operational
   Cost of a Launch Delay", Journal of Spacecraft and Rockets. Its Crossref record
   has no volume or issue and its `issued` field is the record-creation date, so
   no year is quoted from it.
4. **The solar series is a modelling choice.** (II.19) describes the mean Sun,
   but a published LTAN refers to the Sun as observed. The apparent Sun was
   selected on measured residuals, not by preference: the mean longitude gives
   +7.5, +14.7 and -718 min against the anchors where the apparent Sun gives
   -1.5, +0.9 and -0.5 min. The series is validated against four equinox and
   solstice anchors to within 0.005 deg.
5. **`T_to_inj` is assumed, not known.** Every window-centre shift depends on it.
   The shift is linear in it, so a wrong duration scales the Vehicle Duration
   bonus directly.
6. **The conjunction screen is coarse by construction.** An altitude-band and
   plane-proximity filter over three TLEs, not SGP4 screening and not a CSpOC
   product. Spec II.8 places operational screening out of scope.
7. **Space-Track was not used.** Het holds the account. The screen runs against
   CelesTrak, which needs no key, exactly as the issue instructed. Switching it on
   is a one-line change once a key exists.
8. **Published windows are instants, not intervals.** None of the four anchors
   publishes an open and a close time. Landsat 9 and TDRS-M do publish intervals,
   and both were dropped for the reasons above, so the gate compares against a
   published liftoff instant and cannot check interval overlap.
9. **Spec figures not reproduced.** The 0.0004 deg/day inclination sensitivity in
   II.6 is three times the value implied by differentiating (II.7), and its own
   "about 6 min/year" disagrees with its 0.0004 deg/day by a factor of ten. The
   drift table's -0.27 deg/day for i = 87.9 is a 1.3 percent gap from (II.7) at the
   precision the spec prints. All three are asserted at the value derived from
   the governing equation, with the discrepancy recorded in `progress.md`.

## What this engine does NOT do

No weather, no probability, no forecast. `p_success` is never invented here. No
NOTAM querying. No SGP4. No general manoeuvre design, no 6-DOF, no force model
beyond secular J2 in the window core, no rideshare manifesting, per spec I.4. No
phasing model, so launches whose time is set by rendezvous are out of scope by
construction. One site and two vehicle profiles.