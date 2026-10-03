# Challenge 2 Build Specification: Launch Window Decision Engine for Spaceport Nova Scotia

Mission Accepted Space Hackathon, Challenge 2 (Mission Control / "Ben's special challenge").
MDA Space / Canadian Space Agency / ShiftKey Labs, Halifax. Submission: Sunday 4 Oct, 13:30 ADT.
Evidence base: `C2_launch_window_science.md` (referred to as SCIENCE Sec x) and `C2_prior_art_and_track.md` (referred to as PRIOR Sec x). No new research in this document.

Track declaration: **Track 1 (The Orbital Architect)**, delivered through an interface implementing the Track 2 feature list as renderings of engine outputs (PRIOR Sec B: rubric sum 41 vs 36; the slide's "choose one" governs the claimed core problem, the goals line mandates the interface for all participants).

---

## Sec 0. Executive summary (one page)

**The gap.** (a) No published orbital-mechanics or window analysis exists for Spaceport Nova Scotia (Canso, 45.3 N, 61.0 W); only EA and economic documents (PRIOR Sec A.9, bounded negative). (b) No open, forecast-based, orbit-coupled, hindcast-validated probability of a launchable day exists at a Canadian site; NASA MSFC APRA/PACER (NTRS 20080013555) provides climatological go-probabilities by month/hour only and explicitly names conditional day-after probabilities as unmet (PRIOR Sec A.6). (c) Ascent-aware (injection-consistent) windows are pre-empted at NASA (SLS Launch Window Algorithm, NTRS 20205004470) so we ship the vehicle-duration correction as a site-specific quantified number, not a novelty (PRIOR Sec A.8, C.2). We are not building a GMAT clone: propagation is commoditized (Orekit), the scarce artifact is the window search plus injection-consistent solve plus skill-validated probabilistic weather layer plus site-specific corridor, served over HTTP.

**The contribution.** An open, versioned REST engine that computes LEO/Polar/SSO launch windows from Canso geometry with an explicit injection-consistent (vehicle-duration) correction and an honest reachability verdict (the advertised 45.1 deg LEO target is unreachable by direct ascent from a 45.3 N pad, priced at a computed ~27 m/s plane change), and converts each deterministic window into a date-resolved probability of successful launch coupled to an ensemble weather forecast, labeled FORECAST (days 0-10) or CLIMATOLOGY (beyond), with skill assessed against a climatological reference by Brier skill score over an ERA5/Open-Meteo hindcast. Full contribution statement and non-claims: Part I.

**Architecture.** Deterministic ODE/analytic core (reachability predicate, J2 secular nodal rate computed from physical constants never hard-coded, window equation, fixed-point injection-consistent solve) + probabilistic weather layer (ensemble member violation fraction inside the skill horizon, climatological conditional P(L|month, hour) beyond) + range and conjunction screens as data-driven constraints. Nothing site-, vehicle-, or criteria-dependent is baked into code: site geometry and corridor from the EA, launch commit criteria as a versioned cited table, vehicle profiles as VERIFIED/ASSUMPTION data files, weather and space objects fetched at request time with forecast_issue_time recorded. Every result prints the constants block (J2, GM, R_e, source) and the data provenance (Part II Sec 10). Backend: FastAPI, /v1, no auth for read; Python client for researchers (Part IV). Frontend: React or static HTML+Leaflet with a precomputed offline fallback so the demo survives API failure at judging (Part V).

**Validation.** (1) Unit tests reproduce the SSO inclination table within 0.01 deg, Canso azimuths (177.0 deg for 87.9, 191.6 deg for 98.1), J2 drift (-5.14 deg/day at 600 km, i=45.1) within 1 percent, and a hand window-width case. (2) Credibility test: the engine reproduces 3-5 published launch windows (Cape Canaveral, Boca Chica, Mahia) to within stated tolerance. (3) The injection-consistent solve converges (contracting-map condition, Part II Sec 5) and shifts windows by the predicted minutes. (4) Weather layer passes hindcast: Brier skill score vs climatology positive, reliability diagram reported. (5) Positive honesty test: the engine flags 45.1 deg unreachable and prices the plane change. (6) Determinism: identical inputs give identical windows; constants and provenance echoed on every response. Full protocol: Part III.

**Three biggest build risks.** (1) Weather plumbing: live ensemble or ERA5 account unavailable at demo time; mitigation: precomputed climatology plus recorded forecast snapshots shipped in-repo, static demo path (Part V.5), and honest CLIMATOLOGY labeling instead of fabricated live skill. (2) Window credibility: engine fails the known-launch reproduction test; mitigation: that test gates the frontend work (hour 12 gate, Part VIII); failure means fix the geometry before anything else ships. (3) Scope creep toward a mission-design suite (general maneuvers, 6-DOF); mitigation: the explicit do-not-build list (Part I.4); any request to add propagation fidelity beyond the secular J2 window core is cut.

---

## Part I. The Gap and the Scientific Contribution

### I.1 The gap, stated precisely

**(a) No published orbital analysis for Spaceport Nova Scotia.** Bounded-negative searches for "Spaceport Nova Scotia launch window analysis" and "Canso orbital mechanics study" returned only the 2016/2019 environmental assessment documents (approved with conditions, June 2019), economic reports (Conference Board of Canada 2023), and promotional material. No window calendar, azimuth-climatology, or reachability study of the site exists in the searched literature (PRIOR Sec A.9). The EA itself states only qualitative facts: all trajectories south over the Atlantic, 3-sigma corridor over ocean, nominal operations 07:00-12:00 local, up to 8 launches per year, Transport Canada authorization under CARs 602.43/602.44 (PRIOR Sec A.4).

**(b) No open, forecast-based, orbit-coupled, hindcast-validated probability of a launchable day at a Canadian site.** The pre-emption frontier is NASA MSFC APRA/PACER (Burns and Altino, AMS 2008 Paper 133849; NTRS 20080013555): climatological probability of violating launch constraints per month and hour bin at a single site, converted to go-probabilities, used internally for SLS launch-availability TPM. What APRA/PACER leaves open, by the 2008 requirements document's own words, is "conditional probabilities for launch/landing opportunities following a criteria no-go attempt" (PRIOR Sec A.6). Neither APRA nor PACER is forecast-based, neither couples to an orbital window, neither is public or has an API. The 45th Weather Squadron and AMU probability-of-violation tools (NTRS 20100021378, 20130010089, 20120015454) are per-constraint, range-internal, and US-only (PRIOR Sec A.6). The bounded-negative conclusion: no published source computes, for a general site and target orbit, P(successful launch on date d) by coupling the orbital window with an ensemble NWP forecast AND validating the skill horizon by hindcast, openly (PRIOR Sec C.1).

**(c) The vehicle-duration correction is pre-empted at NASA, so it ships as a site-specific quantification.** The SLS Launch Window Algorithm (AAS 20-591, NTRS 20205004470) computes RAAN, inclination, and yaw biases as 5th-order polynomials of liftoff time over +/-2 h slips; LDCM provides RAAN steering across a 50-min window; Astos ALWA computes ascent-aware windows commercially (PRIOR Sec A.8). Therefore we do not claim ascent-aware windows as novel. We claim the open, reproducible, side-by-side quantification of the liftoff-instant approximation error for the Canso site and three orbit classes, as a number in minutes.

### I.2 The contribution, in one paragraph a referee would accept

We present an open launch-window decision engine for Spaceport Nova Scotia (Canso, 45.3 N, 61.0 W) delivered as a versioned REST API with a public Python client. The engine (1) computes LEO, Polar, and Sun-synchronous launch windows from site geometry with an explicit injection-consistent (vehicle-duration) correction, quantifying the error of the liftoff-instant approximation; (2) reports an honest reachability verdict including the computed plane-change penalty for targets below the site latitude (the advertised 45.1 deg case); and (3) converts each deterministic window into a date-resolved probability of successful launch by coupling with an ensemble weather forecast, with the skill horizon of that probability assessed against a climatological reference by Brier skill score over a hindcast period. What is measured: window centers and widths, injection-time corrections, P(L|d) components, Brier skill and reliability against ERA5/ECCC-archived verification. What is new relative to prior art: Orekit, GMAT, STK, and Astos ALWA provide propagation and window analysis but no weather probability, no openness, or no web delivery (PRIOR Sec A.2); APRA/PACER provide climatological availability but no forecasts, no orbital coupling, and no public interface (PRIOR Sec A.6); schedule aggregators (Next Spaceflight, RocketLaunch.live) publish announced windows, not engines (PRIOR Sec A.10). To our knowledge no open tool and no published study performs this coupling for Canso or any Canadian site (checked September-October 2026, PRIOR Sec C.5).

### I.3 What is NOT claimed

We do not claim: (i) that ascent-aware window computation is new (SLS, LDCM, ALWA pre-empt: PRIOR Sec A.8); (ii) that probabilistic launch weather is new (APRA/PACER, 45 WS PoV tools pre-empt the climatological and per-constraint versions: PRIOR Sec A.6); (iii) any theorem beyond the marked propositions of Part II Sec 9; (iv) that our launch commit criteria are flight-safety grade: our criteria table is a documented proxy set, because field mills and cloud-top temperature rules are not publicly observable at Canso (SCIENCE Sec D.3); (v) that the conjunction screen is operational: it is a pre-screen only (Part II Sec 8); (vi) forecast skill beyond day 10: probabilities beyond the skill horizon are labeled CLIMATOLOGY (SCIENCE Sec D.2, citing Lorenz 1982; Tellus A 2013 doi 10.3402/tellusa.v65i0.19022; Buizza and Leutbecher 2015 QJRMS); (vii) the "3-30-30 rule": rejected as unverifiable (SCIENCE Sec F).

### I.4 Positioning: not a GMAT clone

GMAT (NASA GSC-17778-1) is a desktop mission-design suite: general maneuver design, full force-model propagation, trajectory optimization. It is commoditized functionality; Orekit implements propagation better maintained today (PRIOR Sec A.2). GMAT has no window scheduler output, no weather layer, no probabilistic output, no web access. Our product is a web-based launch-window decision engine with an API: the scarce components are the window search with the injection-consistent solve, the skill-validated probabilistic weather layer, and the site-specific corridor, delivered over HTTP so a planner, a researcher, or a student can call it.

Deliberately NOT built, and why in 32 hours these would be a trap:

- No general maneuver design or multi-burn optimization (that is GMAT/STK territory; our ascent model is a fixed-point time budget per vehicle profile).
- No full 6-DOF or attitude control simulation (no fidelity gain for window geometry; unbounded scope).
- No general perturbation force model beyond secular J2 for the window core (the window tolerance is minutes; SCIENCE Sec C.1 shows secular J2 suffices; full numerical propagation is only needed for tight RAAN tolerances we do not claim).
- No rideshare manifesting optimizer (published pre-emption: Colombi et al. 2017 doi 10.2514/1.a33796; poor scope for 32 h: PRIOR Sec C.4).
- No SDE trajectory layer (range practice is deterministic dynamics plus probabilistic environment; SCIENCE Sec C.3).

---

## Part II. The Scientific Framework (the back end model)

Formal specification of the engine. Every symbol is defined in Sec II.0; every equation carries its source (SCIENCE Sec A-D) or is derived here. Scope discipline: the model is a reachability predicate, a secular-J2 window search, a scalar fixed point, and a probabilistic weather layer. It contains no general maneuver design, no 6-DOF dynamics, and no force model beyond secular J2 in the window core (Part I.4), by construction, not by omission.

### II.0 Symbols and conventions

Angles are carried in degrees in all tables, API responses, and configuration files; internally the code uses radians (conversion at the interface boundary). All times are UTC unless a local Atlantic (ADT, UTC-3) label is explicitly shown.

| Symbol | Meaning | Units | Defined at |
|---|---|---|---|
| phi_s | launch site geodetic latitude | deg | II.1 |
| lambda_s | launch site longitude, east-positive | deg | II.1 |
| h_s | site (pad) altitude above mean sea level | m | II.1 |
| beta | launch azimuth, clockwise from true north at liftoff (0 = north, 90 = east, 180 = south) | deg | II.2 |
| beta_rot | rotating-frame (compass) azimuth shown at liftoff | deg | II.2 |
| A_min, A_max | corridor bounds on beta, from the EA config file | deg | II.2 |
| i | orbital inclination of the insertion orbit | deg | II.2 |
| i_t, h_t | target inclination, target circular altitude | deg, km | II.1 |
| beta_min(i) | minimum azimuth solution for inclination i | deg | II.2 |
| Omega | right ascension of the ascending node (RAAN), inertial | deg | II.1 |
| Omega_t(t) | target RAAN as a function of time (J2-drifting or SSO-slaved) | deg | II.4 |
| Omega_targ_dot | secular nodal regression rate of the target orbit, dOmega/dt | deg/day | II.3 |
| J2 | Earth dynamic flattening coefficient (second zonal harmonic) | dimensionless | II.3 |
| GM (mu) | Earth gravitational parameter | m^3/s^2 | II.3 |
| R_e | Earth equatorial radius | m | II.3 |
| a | semi-major axis of target orbit; a = R_e + h for circular | m | II.3 |
| p | semi-latus rectum, p = a(1 - e^2) | m | II.3 |
| e | eccentricity | dimensionless | II.3 |
| n | mean motion, n = sqrt(GM/a^3) | rad/s | II.3 |
| omega_sid | sidereal rotation rate of Earth; 360.9856 deg/day = 15.0411 deg/hr | deg/hr | II.4 |
| GMST(t) | Greenwich mean sidereal time at time t | deg | II.1 |
| delta(i, phi_s) | hour-angle offset of the site from the node line when the site lies in the plane of inclination i; delta = asin(tan(phi_s)/tan(i)) on the ascending branch | deg | II.4 |
| Delta_Omega | allowed RAAN (plane) tolerance, half-width | deg | II.4 |
| t_l, t_i | liftoff time, injection time | s or UTC | II.5 |
| T_to_inj | liftoff-to-injection duration from the vehicle profile file | s | II.5 |
| tau | alias for T_to_inj in SCIENCE Sec A.6 | s | II.5 |
| L | binary launch-success event (all criteria satisfied during the window) | {0,1} | II.7 |
| W | launch commit criteria vector (versioned cited JSON table) | vector | II.7 |
| N | ensemble size (number of forecast members) | count | II.7 |
| P(L given d) | probability of event L on date d | in [0,1] | II.7 |
| p_m, o_m | forecast probability and outcome for verification case m | in [0,1], {0,1} | II.7 |
| BS, BSS | Brier score, Brier skill score | dimensionless | II.7 |
| phi_s config | all site quantities live in config/site_canso.json, never in code | file | II.10 |

Conventions: the engine computes in an Earth-centred inertial frame (ECI) realized by the GMST rotation from the Earth-centred fixed frame (ECEF); polar motion, nutation, and precession beyond the GMST model are neglected (effect on the window: sub-second of Earth rotation, far below the minute-level window tolerance; choice recorded in the constants block, SCIENCE Sec G.11). Ground tracks and hazard areas are computed in ECEF.

### II.1 State and frames

Site state (from config, never hard-coded):

- (lambda_s, phi_s, h_s) with defaults lambda_s = -61.0 deg (61.0 W, east-positive), phi_s = 45.3 deg, h_s = 0 m, taken from the Cyclone-4M Abbreviated User's Guide section 2.2 (pad "45.3 N, 61.0 W"; VERIFIED, SCIENCE Sec F.2). Alternate published coordinates (45.3036 N, 60.9829 W; 45.3223 N, 61.7076 W) are recorded as provenance variants in the same config file (SCIENCE Sec G.3); the engine uses one configured value and echoes it on every response.

Frames:

- ECI: quasi-inertial, realized as ECEF rotated by GMST(t) about the polar axis. GMST computed with the IAU 1982 sidereal-time model (choice fixed at build time; precision note SCIENCE Sec G.11: adequate for window work at the 0.1 s class; nutation-in-RA omitted, bounded by about 1 s of Earth rotation, negligible against a window tolerance of tens of seconds).
- ECEF: used for ground track, hazard area, and corridor tests; related to ECI by the GMST rotation only.

Target state (from the request, never hard-coded): either a named orbit class or an explicit tuple:

- LEO/Polar: (h_t, i_t, Omega_t0) where Omega_t0 is the requested RAAN at the reference epoch, or "free RAAN" (any plane reachable in the corridor on some date), which widens the search to any day.
- SSO: (h_t, LTAN_t) with i_t derived, or (h_t, i_t) with LTAN_t derived (II.6). Omega_t(t) for SSO is slaved to the Sun's right ascension through the LTAN relation (II.6).

Site right ascension at time t (SCIENCE eq. A6):

    RA_site(t) = GMST(t) + lambda_s                                           (II.1)

### II.2 Reachability

Direct-ascent plane geometry: the ascent trajectory plane contains the site position vector and the liftoff velocity vector, hence is the orbital plane. The component algebra gives the classical relation (SCIENCE eq. A1):

    cos(i) = cos(phi_s) * sin(beta)                                           (II.2)

Numeric azimuths from Canso (phi_s = 45.3 deg, cos(phi_s) = 0.7034; computed from (II.2), reproducible in the unit tests):

| Target | i (deg) | sin(beta) = cos(i)/cos(phi_s) | beta (southbound, deg) | Status |
|---|---|---|---|---|
| Advertised LEO | 45.1 | 1.0035 | no real solution | UNREACHABLE (see below) |
| Site minimum (due east) | 45.3 | 1.0000 | 90.0 | boundary case |
| Polar (OneWeb-class) | 87.9 | 0.0521 | 177.0 | reachable, 3.0 deg east of due south (SCIENCE Sec A.1) |
| True polar | 90.0 | 0 | 180.0 | reachable, due south |
| SSO | 98.1 | -0.2003 | 191.6 | reachable, 11.6 deg west of due south (SCIENCE Sec A.1) |

Northbound partners are 180 deg - beta on the prograde branch (3.0 deg for 87.9); the EA corridor admits only the southbound branch ("all launch trajectories would be to the south over the Atlantic Ocean", 2016 project description; PRIOR Sec A.4), so the engine evaluates the southbound solution set only, configurable in the corridor file.

Corridor constraint (from config/corridor.json, derived from the EA, with CARs references; requirement 1):

    A_min <= beta <= A_max                                                    (II.3)

Default corridor file ships with A_min = 90 deg, A_max = 200 deg (the "east and south over open ocean" fan: due east through south to the SSO azimuth plus margin), each bound marked ASSUMPTION pending the EA Figure 2.9 three-sigma corridor check (open item SCIENCE Sec G.2). The bound A_max = 200 deg caps the maximum reachable inclination at about 104 deg (SCIENCE Sec A.4). The corridor file is data; changing it changes the reachable set with no code change.

Reachability predicate (the engine's first gate, evaluated before any window search):

    reachable(i_t) := exists beta in [A_min, A_max] such that
                      cos(i_t) = cos(phi_s) * sin(beta)                        (II.4)

Equivalently, since arccos(cos(phi_s) sin(beta)) is monotone on the southbound branch, reachable(i_t) holds iff i_t lies in the closed interval [i(A_max), i(A_min)] on that branch, with i(beta) = arccos(cos(phi_s) sin(beta)). This is the corridor-intersection test of SCIENCE Sec A.1.4.

The 45.1 deg impossibility and its price. For i = 45.1 deg, sin(beta) = 1.0035 > 1: no real azimuth exists. The direct-ascent minimum inclination from 45.3 N is 45.3 deg, so the advertised 45.1 deg LEO product is 0.2 deg below the pad latitude. The engine does not return a 4xx or an empty list for this input; it returns reachable: false together with the computed plane-change penalty (Part IV error model):

    Delta-v_plane = 2 * v_c * sin(Delta_i / 2),  Delta_i = phi_s - i_t = 0.2 deg   (II.5)

with v_c = sqrt(GM/(R_e + h_t)) the circular speed at insertion altitude (v_c = 7.67 km/s at the reference case used in SCIENCE Sec A.1), giving Delta-v_plane = 7.67e3 * 2 * sin(0.1 deg) = 26.8 m/s, reported as ~27 m/s. This is a computed number from (II.5) with the constants printed, not a literal (SCIENCE Sec A.1; the Cyclone-4M guide's own note on an equatorial lateral maneuver for i < 45.1 is cited in the response provenance).

Rotating-frame correction (reported, not required for the predicate): the compass azimuth beta_rot differs from the inertial beta used in (II.2) by the site's rotational velocity (SCIENCE eq. A2):

    tan(beta_rot) = [v_orb sin(beta) - v_e] / [v_orb cos(beta)],
    v_orb = sqrt(GM/(R_e + h)),  v_e = omega_sid R_e cos(phi_s)               (II.6)

worked example on record: Cape Canaveral to 51.6 deg, beta_inertial = 45.0 deg, beta_rot = 42.8 deg (OrbiterWiki, VERIFIED SCIENCE Sec F.6). The API returns azimuth_deg (inertial) and azimuth_compass_deg (rotating frame) both.

### II.3 J2 secular dynamics

The window core propagates the target plane only by secular J2 nodal regression; no other perturbation enters the window search (Part I.4). The standard result (NASA GSFC GDC Orbit Primer, Oct 2018; SCIENCE eq. A3):

    Omega_targ_dot = dOmega/dt = -(3/2) * J2 * n * (R_e/p)^2 * cos(i)         [rad/s]  (II.7)

    with n = sqrt(GM/a^3), p = a(1 - e^2); for circular orbits p = a, so
    (R_e/p)^2 = (R_e/a)^2 and (II.7) equals -(3/2) J2 n (R_e/a)^2 cos(i)/(1-e^2)^2.

Sign convention: prograde orbits (i < 90 deg, cos i > 0) regress (negative); retrograde SSO orbits (i > 90 deg) advance (positive). All quantities in (II.7) come from the constants file (II.10); the drift rate is computed at request time and echoed on every result. Hard-coding a drift constant is forbidden by requirement 1 and by the falsification record: the commonly quoted "~3.99 deg/day" does not correspond to a 45.1 deg orbit at 600 km; direct substitution into (II.7) gives -5.14 deg/day, while 3.99 deg/day would require i = 56.7 deg at 600 km or i = 45.1 deg at about 1150 km (SCIENCE Sec A.2, REJECTED item 2).

Drift values for the three advertised targets, all computed from (II.7) with the II.10 constants (reproduced by Test 1 within 1 percent):

| Target | i (deg) | h (km, reference) | Omega_targ_dot (deg/day) | Source |
|---|---|---|---|---|
| LEO 45.1 | 45.1 | 600 | -5.14 | computed (II.7); SCIENCE Sec A.2 numeric check |
| Polar 87.9 | 87.9 | 600 | -0.27 | computed (II.7); small because cos(87.9 deg) = 0.0366 |
| SSO 98.1 | 98.1 | 674 (SSO-consistent) | +0.9856 (by construction, sec II.6) | SCIENCE eq. A4 |

Context values on record: -5.69 deg/day at 400 km, -4.65 at 800 km, -3.85 at 1200 km (all for i = 45.1); about -5.0 deg/day for ISS-like 51.6 deg at 420 km (SCIENCE Sec A.2). The engine never stores any of these as literals; they exist only as test expectations.

### II.4 The window equation: opportunity vs period

Definitions (SCIENCE Sec A.5): a launch WINDOW (opportunity) is a connected interval of launch instants during which all mission constraints (plane match within tolerance, corridor, criteria, screens) hold simultaneously; the window PERIOD is the recurrence interval between successive opportunities.

Site-in-plane condition. The site position lies in the plane (Omega, i) iff its right ascension satisfies the spherical-triangle relation derived from r . n = 0 with plane normal n:

    sin(RA_site - Omega) = tan(phi_s) / tan(i)                               (II.8)

so, with (II.1), the ascending-crossing branch of the window equation is:

    GMST(t) + lambda_s = Omega_t(t) + delta(i, phi_s)   (mod 360 deg)         (II.9)

    delta(i, phi_s) := asin(tan(phi_s) / tan(i))                              (II.10)

and the descending branch replaces delta by 180 deg - delta. Existence of delta is exactly the reachability condition i >= phi_s (the argument of the arcsine exceeds 1 iff phi_s > i), so (II.8)-(II.10) unify predicate (II.4) with the window search. For i = 87.9 deg, delta = 2.37 deg; for 98.1 deg, delta = -8.16 deg (computed, test fixtures). SCIENCE eq. A7 writes the simplified form without the delta term (site assumed at the node); the engine uses (II.9) with the explicit offset, and the simplified form is recovered for a hypothetical equatorial site (delta = 0).

Window width. The site's right ascension relative to the drifting target plane sweeps at (SCIENCE eq. A9):

    d(RA_site - Omega_t)/dt = omega_sid - Omega_targ_dot,
    omega_sid = 360.9856 deg/day = 15.0411 deg/hr                            (II.11)

A plane tolerance +/- Delta_Omega therefore gives the half-width and full width (SCIENCE eq. A10):

    tau_half = Delta_Omega / |omega_sid - Omega_targ_dot|   [hours],
    W_window = 2 * tau_half                                                    (II.12)

Hand case carried into Test 1: Delta_Omega = +/- 0.1 deg (tight plane match) gives tau_half = 0.1/15.04 hr = 24 s (instantaneous-class window, cf. the 15-second instantaneous service in the Falcon User's Guide 2025, SCIENCE Sec A.5); Delta_Omega = +/- 5 deg gives +/- 20 min, a 40-min window. Windows are minutes wide for plane-constrained missions because Earth sweeps 1 deg in about 4 min; hours-wide windows require either large plane tolerance or the corridor-open "any inclination in range" mode, which the engine exposes as tolerance mode: corridor (unbounded Delta_Omega clipped by (II.3)).

Recurrence (window period), from substituting (II.7) into (II.9): successive opportunities repeat after

    P_window = 360 / (360.9856 - Omega_targ_dot)   [days]                     (II.13)

which is 0.9973 days for a non-precessing plane (one sidereal day; the opportunity drifts about 3 min 56 s earlier in local solar time each solar day, SCIENCE Sec A.4) and exactly 1 solar day for an SSO target, because its +0.9856 deg/day drift cancels the Sun's apparent motion. Two candidate centers per sidereal day exist (ascending and descending branches); the corridor (II.3) may admit only one.

### II.5 Injection-consistent solve (the fixed point)

Problem. The plane condition (II.9) must hold at INJECTION, but the achievable plane Omega_ach is fixed in inertial space at LIFTOFF by (II.2) and (II.8)-(II.9) evaluated at t_l. Between liftoff and injection the target plane drifts by Omega_targ_dot * T_to_inj. Define T_to_inj = T(t_l) from the vehicle profile data file (requirement 1: per-vehicle rows marked VERIFIED or ASSUMPTION; SCIENCE Sec A.6 gives the class-level range: 10-60 min direct LEO, 30-120+ min with a coast to node; the default profile ships T as an ASSUMPTION row and prints it in the provenance block).

    Omega_ach(t_l) = GMST(t_l) + lambda_s - delta(i_t, phi_s)                 (II.14)
    requirement:  Omega_ach(t_l) = Omega_t(t_l + T(t_l))    (mod 360 deg)      (II.15)

Define the scalar residual (working modulo 360 deg, wrapped to (-180, 180]):

    g(t) = wrap[ GMST(t) + lambda_s - delta - Omega_t(t + T(t)) ]             (II.16)

The injection-consistent liftoff is the root g(t) = 0; window edges are the roots g(t) = +/- Delta_Omega. Window centers per day follow from (II.9); the fixed point refines them.

Iteration. Two implementation modes, both specified:

1. Relaxation (default, robust): t_{k+1} = t_k - g(t_k) / omega_sid_eff, with omega_sid_eff = omega_sid - Omega_targ_dot. Starting from the liftoff-instant solution t^(0) (root of g with T = 0).
2. Newton: t_{k+1} = t_k - g(t_k)/g'(t_k), g'(t) = omega_sid - Omega_targ_dot * (1 + dT/dt), analytic derivative; Brent fallback on bracketed windows (SCIENCE Sec C.1 pattern).

Contraction condition (the provable statement, Claim (i) of II.9). For the relaxation map Phi(t) = t - g(t)/omega_sid_eff:

    |Phi'(t)| = |Omega_targ_dot * (1 + dT/dt)| / |omega_sid - Omega_targ_dot| < 1   (II.17)

which is the contracting-map condition in the brief's normalized form: |dRAAN/dt * dT/dt|-class feedback must not amplify the sweep-rate correction; with dT/dt dimensionless (change of ascent duration per unit change of liftoff time) and |Omega_targ_dot| <= about 5.7 deg/day = 0.24 deg/hr against 15.04 deg/hr, the ratio is at most about 0.017 for fixed T and stays far below 1 for any physically plausible dT/dt (wind-driven T variation is minutes over hours, |dT/dt| << 1). Banach's fixed-point theorem then gives a unique root locally and linear convergence; expected correction and iteration counts below.

Expected correction (the Advanced Bonus number, computed per orbit class, printed with provenance). The correction has two distinct components, and both are reported to avoid a misleading single figure:

1. Window-center shift relative to a correct liftoff-instant computation that omits target drift (the fixed-point refinement term):

       Delta_t_shift = Omega_targ_dot * T_to_inj / (omega_sid - Omega_targ_dot)    (II.18)

    SSO target, T = 30 min: +0.0411 deg/hr * 0.5 hr / 15.0 deg/hr = 4.9 s (SCIENCE Sec A.6 worked example). Precessing mid-inclination target (about -5 deg/day), T = 45 min: about 38 s. Seconds to tens of seconds; equals zero only if T = 0.

2. Liftoff-instant approximation error against a naive baseline that reports injection-time conditions as launch times (or omits T entirely): the error is the full T_to_inj minus (II.18), i.e. of order MINUTES: about 10-45 min for the vehicle class (T_to_inj from the profile), consistent with the prior-art quantification "Earth rotates 2.0-2.5 deg in an 8-10 min ascent, the correction is O(minutes)" (PRIOR Sec C.2), and with SCIENCE Sec A.6: "minutes to tens of minutes of geometry error if a coast-to-node is involved".

The engine reports, per window row: t_liftoff_utc, t_injection_utc = t_liftoff + T_to_inj, window_center_shift_s (term 1), and liftoff_instant_error_min (term 2), each with T_to_inj and its VERIFIED/ASSUMPTION flag echoed. Convergence criterion: |g(t_k)| < 1e-6 deg or |Delta t_k| < 0.01 s, maximum 50 iterations (expected: 2-3 from the analytic start; a non-converging case returns constraint_fired: fixed_point_no_convergence with diagnostics, never a silent wrong answer).

### II.6 SSO specifics: LTAN-RAAN coupling and why 98.1 deg is altitude-specific

LTAN requirement converts to a RAAN requirement tied to launch date (SCIENCE eq. A13):

    Omega_required = alpha_sun + 15 deg * (T_LT - 12 h)                       (II.19)

with alpha_sun the Sun's right ascension (0 deg at vernal equinox; advances 0.9856 deg/day, eq. A4) and T_LT the local time of the ascending node (canonical values: 10:30 imagery, 06:00/18:00 dawn-dusk, 12:00 noon). Because alpha_sun is date-dependent, a "SSO, 10:30 LTAN" target becomes a date-indexed Omega_t(t) in (II.9), which is exactly the input the window search needs; the engine accepts either LTAN_t or explicit RAAN_t and derives the other, echoing both.

Altitude-inclination coupling: the SSO inclination is the solution of (II.7) = +0.9856 deg/day at fixed altitude (SCIENCE eq. A5). The table the unit tests enforce (computed from (A5) with the II.10 constants; SCIENCE Sec A.2):

| h_t (km) | i_SSO (deg) |
|---|---|
| 500 | 97.40 |
| 600 | 97.8 (97.79) |
| 674 | 98.08 (98.12-98.13 with R = 6380 km convention) |
| 700 | 98.19 (NASA GDC Orbit Primer: "98.2 deg", agrees) |
| 800 | 98.60 |
| 900 | 99.0 (99.03) |

Average slope over 500-900 km: about +0.0041 deg/km (about +0.003 near 650 km). Consequences the engine enforces: (a) 98.1 deg is the SSO inclination at roughly 650-700 km, the canonical Earth-observation band, and is NOT portable across altitudes; a request for (i_t = 98.1 deg, h_t = 600 km) triggers a consistency warning (required i at 600 km is about 97.8 deg; the node would precess at the wrong rate, accumulating LTAN drift); (b) insertion-altitude or inclination error appears as LTAN drift (a 0.01 deg inclination error at 700 km gives about 0.0004 deg/day precession error, about 6 min/year of LTAN drift; SCIENCE Sec A.7); (c) the requirement is LTAN-at-date, not inclination per se. All SSO consistency checks are computed from (II.7)/(II.19), printed with the constants block.

### II.7 The probabilistic weather layer

Event definition. Let the launch commit criteria be the vector W = (w_1, ..., w_J) from the versioned, cited criteria JSON table (requirement 1; each row carries its citation and a VERIFIED/PROXY flag; proxy caveat: field mills and cloud-top-temperature rules are not publicly observable at Canso, so the table is a documented proxy set, SCIENCE Sec D.3). For a window interval I(d) on date d define the binary event:

    L(d) = 1 iff criterion w_j holds at every required time in I(d), for all j   (II.20)

Forecasts (lead d - d0 <= 10 days): with N ensemble members each evaluated against W over I(d),

    P_forecast(L | d) = (1/N) * sum_n 1{ member n satisfies W over I(d) }     (II.21)

where the indicator per member uses the member's worst-case excursion over the window (windows are minutes; weather autocorrelation across minutes is effectively 1, so treating W as constant over I(d) is an explicit assumption, listed under Claim (iii)).

Horizon labeling (scientific-integrity feature, SCIENCE Sec D.2): the response carries horizon_label: FORECAST for lead <= 10 days with P from (II.21), and horizon_label: CLIMATOLOGY beyond, with

    P_clim(L | month, hour) = empirical frequency from the ERA5/station hindcast (II.22)

The 10-day boundary is the stated prior position, sourced: deterministic predictability limit about 2 weeks (Lorenz 1982, Tellus); "from around the 10-d forecast time, the ensemble mean begins to converge towards climatology" (Tellus A 2013, doi 10.3402/tellusa.v65i0.19022); ensemble skill horizon 16-23 days for grid-point fields (Buizza and Leutbecher 2015, QJRMS). Our own Brier-skill-vs-lead curve (Test 4) may move the boundary; the boundary is a config value, not a constant.

Combined probability. With the conditional-independence assumption (Claim (iii)):

    p_success = P(L | d) * P_range_clear * P_conjunction_clear                (II.23)

    p_success_components = { weather, range, conjunction }                    (API echo)

Verification metrics (researcher-facing, Part IV /v1/validation/skill):

    Brier score:  BS = (1/M) * sum_{m=1..M} (p_m - o_m)^2,  o_m in {0,1}       (II.24)

    Brier skill score vs climatology:
    BSS = 1 - BS_model / BS_ref,   BS_ref computed with p_m = p_base_rate      (II.25)

    (p_base_rate = frequency of L in the hindcast sample; BSS > 0 means the
    forecast probability beats the climatological reference, the acceptance
    threshold of Test 4.)

Reliability diagram: bins of p_m versus empirical frequency of o_m = 1 in each bin, plotted per lead time; perfect reliability is the diagonal. ROC (probability of detection vs false-alarm rate for the p >= 0.5 decision) is reported alongside. Output objects: the skill series (lead_time_days, BS, BS_ref, BSS), the reliability bins, and the base rate, all downloadable (Part V researcher view).

### II.8 Range and conjunction screens

Hazard-area test (in scope). The vehicle profile file carries the footprint model class (ellipse axes vs downrange, from the vehicle guide or EA figures; rows marked VERIFIED or ASSUMPTION). The engine computes the ground track from Canso for the computed azimuth, buffers it by the footprint, and tests containment in the corridor polygon from config/corridor.json (EA-derived, 3-sigma over ocean, "no overflight of land or populated areas", 2016 project description; PRIOR Sec A.4). Pass/fail feeds P_range_clear as a deterministic 0/1 (not a probability; documented as such).

Conjunction pre-screen (in scope, honest about fidelity). At request time the engine fetches TLEs from CelesTrak (endpoint probed 200, PRIOR Sec D), propagates coarse SGP4 crossings of the target altitude band near the window, and flags objects with predicted miss distance below a configurable threshold (config key conjunction.miss_threshold_km, default an ASSUMPTION value pending range feedback; operational context: SpaceX reserves the ability to shift liftoff seconds within a 15-second instantaneous window for conjunction avoidance, Falcon User's Guide 2025 sec. 3.4). Output: conjunction flag and the worst-case miss distance, feeding P_conjunction_clear (0/1 screen, not an operational probability).

NOTAM check (in scope, display only). Query the Nav Canada path (plan.navcanada.ca, probed 200; PRIOR Sec D) for active NOTAMs covering the window; display-only, not machine-blessed for bulk use, never used to gate a window. Transport Canada authorization under CARs 602.43/602.44 and Coast Guard Notices to Mariners are referenced as static regulatory provenance in the site config.

Explicitly out of scope in 32 hours (future work, stated in the response and the paper): operational CSpOC conjunction screening (Space-Track account, full screening volume), automated NOTAM parsing, Ee (expected casualty) analysis (Transport Canada's review stays outside the tool), and abort-mode coverage. The screens are pre-screens; the response marks constraint source as screen_level: pre_screen.

### II.9 The mathematical claims, with status marks

Every claim in the document is listed here with an honest status. Nothing is marked PROVED without a proof sketch a referee can check; nothing is invented to fill a slot.

**(i) Injection-consistent fixed point. PROVED.**
Proposition. Let g(t) be defined by (II.16) on a window day, assume: (a) T(t) is continuously differentiable with |dT/dt| <= c_T; (b) Omega_t is continuously differentiable with |Omega_targ_dot| <= c_Omega; (c) c_Omega (1 + c_T) < |omega_sid - Omega_targ_dot| (sweep-rate dominance). Then on any interval where g is unwrapped, the relaxation map Phi(t) = t - g(t)/(omega_sid - Omega_targ_dot) satisfies |Phi'(t)| <= c_Omega(1+c_T)/|omega_sid - Omega_targ_dot| < 1 (this is condition (II.17), the brief's |dRAAN/dt * dT/dt| < 1 in normalized form), so by Banach's fixed-point theorem Phi has a unique fixed point t*, g(t*) = 0, and the iteration t_{k+1} = Phi(t_k) converges to it linearly with rate q <= 0.017 for LEO-class targets (fixed T), i.e. a residual reduction by a factor of about 60 per iteration.
Proof sketch: g is C1; g'(t) = omega_sid - Omega_targ_dot(1 + dT/dt) by the chain rule, so Phi' = 1 - g'/omega_sid_eff = Omega_targ_dot(1+dT/dt)/omega_sid_eff; bound by (c); completeness of R and Banach apply on the closed interval where |Phi(t) - t| maps the interval into itself (guaranteed locally around the analytic start t^(0), since |Phi(t^(0)) - t^(0)| = |g(t^(0))|/omega_sid_eff is small: the T = 0 solution shifted by at most T * Omega_targ_dot/omega_sid, under a second of Earth rotation for LEO-class drifts). Uniqueness of the root in the unwrapped interval follows from g' > 0 (g strictly increasing) under (c). Existence of the analytic start is (II.9), always solvable when reachable(i_t) holds and the date admits a crossing in range. This is elementary calculus plus Banach; it is not claimed as new mathematics, it is claimed as a proved property of our implementation.

**(ii) Reachability result. PROVED (algebraic).**
Proposition. Direct ascent from site latitude phi_s reaches inclination i iff i in [phi_s, 180 deg - phi_s]; with corridor [A_min, A_max] on the southbound branch, the reachable set is exactly {arccos(cos(phi_s) sin(beta)) : beta in [A_min, A_max] intersected with the branch}, monotone in beta; from phi_s = 45.3 deg the target 45.1 deg is unreachable and the minimum plane-change penalty to reach it is (II.5), 26.8 m/s at the reference circular speed.
Proof sketch: the ascent plane is spanned by r_site and v_liftoff; its normal n = r x v has polar component giving cos(i) = cos(phi_s) sin(beta) by direct component algebra (this is (II.2), the classical result, SCIENCE eq. A.1, also stated in the Robertson monograph lineage). Solving for beta requires |cos(i)/cos(phi_s)| <= 1 iff i in [phi_s, 180 deg - phi_s]. For 45.1 < 45.3 the arcsine argument is 1.0035 > 1, no real beta. The penalty (II.5) is the chord length in velocity space between speed vectors of equal magnitude differing by angle Delta_i: |v' - v| = 2 v sin(Delta_i/2), elementary. The corridor intersection is then a monotone image of a closed interval, preserving the interval-completeness argument.

**(iii) Chance-constrained window formulation. SKETCHED.**
Formulation: find all t in a date range such that
    |g(t)| <= Delta_Omega,  beta(t) in [A_min, A_max],  hazard(t) = 1,
    P(L | d, F) >= p*,                                                  (II.26)
where F is the forecast issued at forecast_issue_time and p* is a configured go-probability threshold (config, default documented as an ASSUMPTION). The engine computes (II.26) by enumeration of the one or two crossings per sidereal day and evaluation of (II.21)-(II.23); it does not optimize p*.
Assumptions listed, not proven: (a) ensemble members are exchangeable samples of the verifying distribution; (b) W is constant over the window interval (weather autocorrelation across minutes); (c) stationarity of the L frequency for the climatological reference (II.22) over the hindcast period; (d) conditional independence of weather, range, and conjunction for the product (II.23); (e) the proxy criteria table stands in for flight-safety-grade LCCs (SCIENCE Sec D.3 caveat). No existence, uniqueness, or optimality theorem is claimed for (II.26); feasibility is decided by computation. Status: SKETCHED.

**(iv) Opportunity-process decision layer. SKETCHED.**
Model: the engine emits a deterministic sequence of candidate opportunities {t_k} (one or two per day from (II.9)-(II.13), or none if unreachable); each is independently successful with probability p_k from (II.23). Thinning a deterministic opportunity sequence by independent success indicators yields a sequence of success times; per-day with one window and constant p, the time to next success is geometric with mean 1/p days; for an inhomogeneous daily sequence {p_d}, the expected time to next success is
    E[T_next] = sum_{j>=0} (1 - prod_{s=1..j} (1 - p_{d+s})) * Delta_day        (II.27)
(survival expansion; for the first opportunity after a failed day this reduces to the standard geometric tail), and the expected delay cost relative to a nominal plan is
    E[cost] = C_day * (E[T_next] - T_nominal),                                (II.28)
with C_day a daily cost-of-delay parameter. This is the formal bridge from the slide's "a missed window can cost millions" to a computable quantity, and it connects to the published delay-cost estimation of O'Neill and Davidheiser, "Estimating the Operational Cost of a Launch Delay", Journal of Spacecraft and Rockets, doi 10.2514/1.a36618 (Crossref-verified, PRIOR Sec F), which supplies the cost-model genre our C_day parameter plugs into. Assumptions: independence across days; known p_d; constant or externally supplied C_day. Status: SKETCHED (the decision layer ships as an optional analysis endpoint computing (II.27) from a requested p-series; it is not claimed as a queueing-theorem result).

**(v) CONJECTURE (explicitly not yet established).**
- C1: within lead times up to 10 days, the forecast-based P(L | d) has BSS > 0 against climatology at 45.3 N (II.25). This is the hypothesis Test 4 accepts or rejects; until the hindcast runs it is a conjecture, and the tool reports the measured value either way.
- C2: the skill horizon at this site and variable set is about 10 days. The prior literature supports the order of magnitude (Lorenz 1982; Tellus A 2013 doi 10.3402/tellusa.v65i0.19022; Buizza and Leutbecher 2015), but the site-specific boundary is ours to measure; it may land anywhere in the 5-14 day band, and the config value moves to the measured crossover if Test 4 says so.
- C3: the bounded negative "no open tool couples an orbital window with an ensemble-forecast probability validated by hindcast at a Canadian site" (Part I.2). This is a search-bounded claim (PRIOR Sec C.5, checked September-October 2026), not a provable statement; it is reported as bounded, with the pre-emption frontier named (APRA/PACER, 45 WS, SLS, ALWA).
- C4: the proxy criteria table ranks days consistently with a flight-safety-grade LCC set. Unverifiable at Canso without field mills and cloud-top data; declared an assumption (SCIENCE Sec D.3), never presented as validated.

Also recorded, to be scrupulous: the window-width scaling W = 2 Delta_Omega / |omega_sid - Omega_targ_dot| is ELEMENTARY (SCIENCE Sec C.5: derivable, implicitly in handbooks, not publishable as new math); it is used, not claimed.

Venue fit for claims (i)-(iv) plus the dataset: Acta Astronautica (applied mission analysis, validated algorithms, site studies) is the primary target; Space Policy fits if reframed around Canadian sovereign access and CARs regulatory data; the Journal of Guidance, Control, and Dynamics would demand a theorem or estimation-theory contribution of heavier class than (i)-(iv) and is therefore honestly out of reach for this work (PRIOR Sec E). Claim type for the paper: validated algorithm plus new dataset, not a theorem.

### II.10 Constants and data provenance table

Requirement 1 compliance record: item | value or source | hard-coded or dynamic | file or endpoint | citation. This table is served, machine-readable, by GET /v1/citation for any run (Part IV) and rendered in the frontend constants block (Part V).

| Item | Value or source | Hard-coded or dynamic | File or endpoint | Citation |
|---|---|---|---|---|
| J2 | 1.08262668e-3 | Hard-coded (universal constant, printed with source on every result) | backend/constants.json | EGM2008 value as recorded in SCIENCE Sec A.2 |
| GM (mu) | 3.986004418e14 m^3/s^2 | Hard-coded (same policy) | backend/constants.json | NASA GSFC GDC Orbit Primer, Oct 2018 (formula set VERIFIED, SCIENCE Sec F.7); value SCIENCE Sec A.2 |
| R_e | 6378137 m | Hard-coded (same policy) | backend/constants.json | EGM2008/WGS84 equatorial radius (SCIENCE Sec A.2) |
| omega_sid | 7.292115e-5 rad/s (sidereal) | Hard-coded (same policy) | backend/constants.json | SCIENCE Sec A.4 |
| GMST model | IAU 1982 sidereal time; nutation omitted | Hard-coded algorithm; choice recorded | backend/constants.json (model field) | SCIENCE Sec G.11 (model choice and precision note) |
| SSO target rate | 0.9856473 deg/day (mean Sun) | Computed from (II.19) mean-motion constant; not a magic literal in window code | backend/constants.json | SCIENCE eq. A4 |
| Site geometry (phi_s, lambda_s, h_s) | 45.3 N, 61.0 W, 0 m default; alternates recorded | Dynamic config, never in code | config/site_canso.json | Cyclone-4M Abbreviated User's Guide sec 2.2 (VERIFIED SCIENCE Sec F.2); coordinate variants SCIENCE Sec G.3 |
| Corridor bounds [A_min, A_max] | 90-200 deg default (east-through-south fan); bounds ASSUMPTION pending EA Fig 2.9 | Dynamic config | config/corridor.json | EA 2016 project description ("south over the Atlantic"); novascotia.ca EA page (VERIFIED PRIOR Sec A.4); open item SCIENCE Sec G.2 |
| CARs references | CARs 602.43 / 602.44 authorization path | Dynamic config text | config/site_canso.json | EA project description (VERIFIED PRIOR Sec A.4) |
| Launch commit criteria W | versioned table, each row cited, VERIFIED or PROXY flag | Dynamic, versioned JSON; editable via documented edit path | data/criteria_v1.json | NASA KSC Shuttle weather LCC 167476main; NASA Falcon 9 crew criteria fact sheet; 45 WS AMS 103803 (all VERIFIED SCIENCE Sec F.12-F.14); proxy caveat SCIENCE Sec D.3 |
| Vehicle profiles (T_to_inj, footprint, performance) | per-vehicle data file; every row VERIFIED or ASSUMPTION | Dynamic, per-vehicle files | data/vehicles/*.json | Cyclone-4M User's Guide (VERIFIED SCIENCE Sec F.2); class-level ascent durations SCIENCE Sec A.6 |
| Target orbit (h_t, i_t, RAAN_t or LTAN_t) | request body | Dynamic at request time | POST /v1/windows | Slide inclinations 45.1/87.9/98.1 from maritimelaunch.com (VERIFIED SCIENCE Sec F.1) |
| Weather forecast fields | live ensemble/forecast fetch | Dynamic at request time | Open-Meteo https://api.open-meteo.com/v1/forecast (no key); ECCC GDPS https://dd.weather.gc.ca/ | Endpoints probed 200 (SCIENCE Sec D.1; GDPS readme SCIENCE Sec F.21); Open-Meteo CC BY 4.0 |
| forecast_issue_time | issued time of the forecast run used | Dynamic; recorded on every response | response field (Part IV) | Our design (requirement 1) |
| Hindcast / climatology | ERA5 hourly fields for the Canso point | Dynamic pull; pre-staged copy shipped for offline demo | Copernicus CDS https://cds.climate.copernicus.eu (account required) | ERA5 CDS endpoint verified (SCIENCE Sec D.1, F.23); no DOI invented here |
| Verification skill series | Brier/BSS vs lead time from our hindcast | Dynamic computation; cached artifact | GET /v1/validation/skill | Formulas (II.24)-(II.25); verification data ERA5 + Open-Meteo historical forecast archive (SCIENCE Sec D.1) |
| Space objects (TLEs) | CelesTrak GP data | Dynamic at request time | https://celestrak.org/NORAD/elements/gp.php | Endpoint probed 200 (PRIOR Sec D) |
| NOTAMs | Nav Canada | Dynamic, display-only | https://plan.navcanada.ca/ | Endpoint probed 200; not machine-blessed for bulk use (PRIOR Sec D) |
| Delay-cost model parameter C_day | user-supplied or documented default | Dynamic config; genre citation only | config/decision.json | O'Neill and Davidheiser, J. Spacecraft and Rockets, doi 10.2514/1.a36618 (Crossref-verified PRIOR Sec F) |
| Skill-horizon prior | 10 days config boundary | Dynamic config (measured value may override) | config/weather.json | Lorenz 1982 Tellus; Tellus A 2013 doi 10.3402/tellusa.v65i0.19022; Buizza and Leutbecher 2015 QJRMS (SCIENCE Sec F.20) |
| Azimuth-inclination relation, rotating-frame correction | equations (II.2), (II.6) | Computed in code | backend engine | OrbiterWiki worked example + Robertson monograph lineage (VERIFIED SCIENCE Sec F.6) |

Rule of construction: any number that appears in a result and is not computed from this table is a bug; Test 6 (Part III) fails the build if a result cannot be traced to a row here.

---

## Part III. Validation and Testing

Six tests, each with a pass criterion, an owner hour-gate, and a stated meaning of failure. Tests 1 and 5 are unit-scale and run on every commit; Tests 2-4 are the credibility suite and gate the frontend (hour 12 gate, Part VIII); Test 6 runs on every API response in production.

### III.1 Test 1: orbital unit tests

Cases and pass criteria:

| Case | Expected | Tolerance |
|---|---|---|
| SSO inclination from (II.7)=(A4) at h = 600 km | 97.79 deg ("97.8") | within 0.01 deg |
| SSO at 674 km | 98.08 deg | within 0.01 deg |
| SSO at 700 km | 98.19 deg | within 0.01 deg |
| SSO at 900 km | 99.03 deg | within 0.01 deg |
| Azimuth for i = 87.9 from phi_s = 45.3 | 177.0 deg | within 0.1 deg |
| Azimuth for i = 98.1 | 191.6 deg | within 0.1 deg |
| Reachability of i = 45.1 | unreachable, plane penalty | reachable flag false; Delta-v 26.8 m/s within 1 m/s |
| J2 drift, i = 45.1, h = 600 km | -5.14 deg/day | within 1 percent (also asserts NOT 3.99) |
| J2 drift, i = 51.6, h = 420 km | about -5.0 deg/day | within 1 percent |
| Window width, Delta_Omega = 0.1 deg, fixed plane | tau_half = 24 s | within 1 s (hand computation 0.1/15.0411 hr) |
| delta(i, phi_s) offsets | 2.37 deg (87.9), -8.16 deg (98.1) | within 0.01 deg |
| GMST round trip: ECEF->ECI->ECEF over 1 sidereal day | identity | within 1e-9 rad |

Failure means: the geometry layer is wrong; nothing downstream is trustworthy. Fix before any other work; the frontend does not start (Part VIII).

### III.2 Test 2: THE CREDIBILITY TEST, reproduction of published launch windows

Purpose: prove the engine, running with only public site and orbit inputs, reproduces windows that real ranges published.

Protocol: for 3-5 historical, publicly documented launches, configure the engine with the documented site coordinates, target orbit, and date, then compare engine window centers against published window open/close or liftoff times:

| Case | Site | Target | Published reference |
|---|---|---|---|
| Cape Canaveral, ISS-class 51.6 deg | 28.5 N, 80.6 W | i = 51.6 deg, RAAN window | published launch windows / liftoff times (public manifests) |
| Boca Chica, Starlink-class | 26.0 N, 97.2 W | i = 53.0 deg class, SSO variants as documented | SpaceX announced windows (aggregators quote identical open/close, PRIOR Sec A.10) |
| Mahia, Electron, 50-83 deg class | 39.3 S, 177.9 E | documented mission inclinations | Rocket Lab published windows |
| (optional) Cape Canaveral SSO/SSO-class | 28.5 N | i = 97-98 deg band as documented | published windows |

Pass criterion: engine window center within +/- 2 min of the published nominal liftoff inside the published window (windows are minutes wide, eq. (II.12); a 2-min tolerance absorbs the unknown exact RAAN tolerance of the published case), and the engine window interval overlaps the published open/close interval. Each case records: inputs used, engine output, published value, delta. All deltas are tabulated in the submission.

Failure means: either the frame/GMST handling or the plane-condition branch is wrong (classic bugs: east-longitude sign, ascending vs descending branch, GMST vs UT1, degrees/radians). The test case whose delta is largest localizes the bug. No frontend work proceeds until the suite passes (this is the hour-12 gate).

Honesty note: exact reproduction is not expected to the second because published windows embed range-weather holds, vehicle constraints, and RAAN tolerances we do not know; the +/- 2 min tolerance and the tabulated deltas are the disclosed standard.

### III.3 Test 3: injection-consistent convergence and predicted shift

Protocol: (a) run the fixed point (II.16) for each of the three orbit classes from Canso with the default vehicle profile; assert convergence within 50 iterations and |g| < 1e-6 deg; (b) assert the measured window-center shift equals the prediction (II.18) within 5 percent (SSO: about 4.9 s for T = 30 min; precessing target about 38 s for T = 45 min at -5 deg/day); (c) assert t_injection_utc - t_liftoff_utc equals T_to_inj exactly; (d) assert the reported liftoff_instant_error_min equals T_to_inj - shift within 0.1 min.

Failure means: the vehicle-duration bonus (the slide's Track 1 Advanced Bonus) is not computed correctly; the quantified correction is the deliverable, so a wrong number is worse than none. Fix the iteration or the T plumbing before proceeding.

### III.4 Test 4: weather hindcast, Brier skill and reliability

Protocol: over the pre-staged hindcast period (minimum 12 recent months for the demo-grade run, longer if the ERA5 pull allows; period is a researcher input, Part VI), generate daily P(L | d) from archived forecasts for leads 1-10 days and from climatology beyond; verify against ERA5-based criteria evaluation.

Pass criteria:
1. BSS > 0 against the climatological reference (II.25) aggregated over leads 1-7 days (the measurable skill band). BSS reported per lead day even where negative.
2. Reliability diagram produced with at least 5 populated bins; mean |observed - predicted| across bins <= 0.15 (calibration sanity bound, stated as the acceptance number).
3. The skill-vs-lead curve is served by GET /v1/validation/skill and rendered in the researcher view.

Failure means: either the probability layer is unskilled or the verification is misaligned (date, threshold, or variable errors). Meaning per outcome: if BSS <= 0 at all leads, the tool stops calling the product forecast-based probability for those leads and labels them CLIMATOLOGY (honest degradation, not fabrication); if the reliability diagram is wildly non-diagonal while BSS > 0, recalibrate (simple histogram recalibration) and re-run. The hindcast table ships either way; a negative result reported honestly still demonstrates the validation apparatus.

### III.5 Test 5: positive honesty test, unreachable target priced

Protocol: request i_t = 45.1 deg from the default Canso site.

Pass criteria: HTTP 200 (never 4xx, Part IV error model); response contains reachable: false, plane_change_dv_ms: 26.8 (within 1 m/s of (II.5)), the constants block, and a pointer to the Cyclone-4M guide inconsistency note. Additionally: request i_t = 98.1 with h_t = 600 km and assert the SSO-consistency warning fires (required i about 97.8 deg).

Failure means: the engine silently dropped the advertised flagship case or hard-coded a success path; both are credibility defects a judge from MDA or Maritime Launch can find in one API call. Fix before demo.

### III.6 Test 6: determinism and provenance echo

Protocol: (a) run the same POST /v1/windows request twice (and once after a cache flush); byte-compare all numeric fields; assert identical window lists; (b) assert every response object carries the constants block (J2, GM, R_e, omega_sid, model choice), the site and corridor values used, the criteria version, the vehicle profile id with row flags, and, for weather-bearing responses, forecast_issue_time and horizon_label; (c) assert GET /v1/citation for a stored run id reproduces exactly the constants used.

Failure means: either nondeterminism (time-dependent code paths, uninitialized seeds, cached-vs-fresh divergence) or a provenance gap violating requirement 1. Nondeterminism invalidates Test 2 and the published dataset; provenance gaps invalidate the citation story. Both block submission.

---

## Part IV. The Backend API (directly usable by others)

REST over HTTPS, JSON bodies, versioned under /v1, no authentication for read endpoints (researcher/student/planner reuse is the point; requirement 1 and Part VI). Framework: Python FastAPI (Part V stack note). OpenAPI schema served at /v1/openapi.json.

Shared building blocks (JSON objects reused below):

constants_block (type: object, always present on result-bearing responses):

    {
      "J2": 1.08262668e-3,
      "GM": 3.986004418e14,
      "R_e": 6378137.0,
      "omega_sid_rad_s": 7.292115e-5,
      "gmst_model": "IAU_1982",
      "citation_id": "run_20261003_..."
    }

provenance_block (type: object): {"site": object, "corridor": object, "criteria_version": string, "vehicle_profile_id": string, "row_flags": object, "source_files": [string]}.

### IV.1 POST /v1/windows

Request body (application/json):

    {
      "target": {
        "type": "LEO" | "POLAR" | "SSO" | "CUSTOM",
        "h_t_km": number | null,            // required if type=CUSTOM
        "i_t_deg": number | null,           // required if type=CUSTOM
        "raan_deg": number | null,          // null = any reachable plane
        "ltan_hours": string | null         // e.g. "10:30", SSO only
      },
      "site": string,                       // default "canso"; named site in config/
      "date_range": { "start": "YYYY-MM-DD", "end": "YYYY-MM-DD" },
      "vehicle_profile_id": string,         // e.g. "cyclone4m"
      "corridor": {                         // optional override; else EA config
        "A_min_deg": number | null,
        "A_max_deg": number | null
      },
      "criteria_version": string | null,    // default: current data/criteria_v*.json
      "raan_tolerance_deg": number | null,  // Delta_Omega; default per target class
      "include_weather": boolean            // default true
    }

Type mapping: LEO resolves to the configured default (i_t = 45.1 advertised class, see reachable handling), POLAR to i_t in [87.9, 90.0], SSO to i_t ~98.1 with i_t derived from h_t by (II.5-inclination table) unless i_t given, CUSTOM to explicit fields. All numeric fields are JSON numbers (float64); dates are ISO strings; times in responses are ISO-8601 UTC with Z suffix.

Response (HTTP 200 always for well-formed requests, including unreachable targets):

    {
      "reachable": boolean,
      "plane_change_dv_ms": number | null,   // non-null iff reachable=false and penalty computable
      "sso_consistency_warning": object | null,
      "windows": [
        {
          "t_liftoff_utc": "ISO-8601 string",
          "t_injection_utc": "ISO-8601 string",
          "raan_deg": number,
          "azimuth_deg": number,             // inertial (II.2)
          "azimuth_compass_deg": number,     // rotating frame (II.6)
          "reached_inclination_deg": number,
          "window_width_s": number,          // from (II.12)
          "window_center_shift_s": number,   // fixed-point term, (II.18)
          "liftoff_instant_error_min": number, // term 2, II.5
          "p_success": number,               // (II.23), in [0,1]
          "p_success_components": {
            "weather": number,
            "range": number,                 // 0 or 1 (pre-screen, II.8)
            "conjunction": number            // 0 or 1 (pre-screen, II.8)
          },
          "horizon_label": "FORECAST" | "CLIMATOLOGY",
          "forecast_issue_time": "ISO-8601 string" | null,
          "constraint_fired": string | null, // null unless a screen/FP stopped this row
          "screens": { "hazard": "pass"|"fail", "conjunction": "clear"|"flagged", "notam": "none"|"active" }
        }
      ],
      "constants_block": constants_block,
      "provenance_block": provenance_block,
      "engine_version": "string",
      "computation_ms": number
    }

Semantics: an empty windows array with reachable true means no crossing in the date range within tolerance (a valid, informative result). constraint_fired values are enumerated strings (fixed_point_no_convergence, hazard_area, conjunction_flagged, criteria_version_missing).

### IV.2 GET /v1/orbits/{id}/ephemeris

Path: id = "leo45" | "polar879" | "sso981" | custom orbit ids created implicitly by POST /v1/windows (response orbit_id).
Query: ?start=ISO&end=ISO&step_s=number (default 300).
Response:

    {
      "orbit_id": "string",
      "frame": "ECEF",
      "points": [
        { "t_utc": "ISO-8601", "lat_deg": number, "lon_deg": number, "alt_km": number }
      ],
      "ground_track_valid": boolean,   // false beyond 3-day TLE/propagation horizon for conjunction-derived tracks
      "constants_block": constants_block
    }

Propagation for named LEO/Polar/SSO targets uses the secular-J2 model of Part II (in-scope); full force models are not offered (Part I.4).

### IV.3 GET /v1/weather/probability?date=YYYY-MM-DD&site=canso

Response:

    {
      "date": "YYYY-MM-DD",
      "site": "canso",
      "p_launch": number,
      "horizon_label": "FORECAST" | "CLIMATOLOGY",
      "forecast_issue_time": "ISO-8601" | null,
      "ensemble_size": number | null,      // null in CLIMATOLOGY mode
      "criteria_version": "string",
      "components": [ { "criterion_id": "string", "p_violation": number, "flag": "VERIFIED"|"PROXY" } ],
      "source": "open_meteo" | "gdps" | "era5_climatology" | "snapshot_cache"
    }

### IV.4 GET /v1/validation/skill (researcher-facing hindcast skill series)

Query: ?period_start=YYYY-MM-DD&period_end=YYYY-MM-DD&lead_max=10.
Response:

    {
      "period": { "start": "YYYY-MM-DD", "end": "YYYY-MM-DD" },
      "verification_source": "era5",
      "reference_forecast": "climatology_base_rate",
      "base_rate": number,
      "skill_series": [
        { "lead_time_days": number, "bs": number, "bs_ref": number, "bss": number, "n_cases": number }
      ],
      "reliability_bins": [ { "p_center": number, "observed_freq": number, "n": number } ],
      "roc_points": [ { "threshold": number, "pod": number, "far": number } ],
      "skill_horizon_measured_days": number | null,
      "constants_block": constants_block
    }

### IV.5 GET /v1/site

Response: site geometry (phi_s_deg, lambda_s_deg, h_s_m, coordinate variants with sources), corridor bounds (A_min_deg, A_max_deg, assumption flags), CAR references (602.43, 602.44), EA reference URLs, nominal operating hours (07:00-12:00 local), launch-rate cap (8/yr), and the corridor polygon vertices used by the hazard test. All fields carry source strings (requirement 1 provenance table subset).

### IV.6 GET /v1/citation?id=<run_id> (or ?window=<window_row_id>)

Machine-readable constants-and-data provenance for one run, schema = the II.10 table serialized:

    {
      "run_id": "string",
      "engine_version": "string",
      "generated_at": "ISO-8601",
      "items": [
        {
          "item": "J2",
          "value_or_source": "1.08262668e-3",
          "hard_coded_or_dynamic": "hard-coded",
          "file_or_endpoint": "backend/constants.json",
          "citation": "EGM2008 (SCIENCE Sec A.2)"
        }
      ],
      "bibtex": "string"   // for our own report; external DOIs embedded in citation fields
    }

### IV.7 Error model

- Rule 1: any semantically valid request that the physics answers (including "unreachable", "no windows", "constraint fired") returns HTTP 200 with the body above; reachable:false carries plane_change_dv_ms (Part III Test 5).
- Rule 2: HTTP 4xx is reserved for malformed requests the engine cannot interpret: 422 for schema violations (missing target fields, bad dates), 404 for unknown orbit id or site id, 429 for rate limit, 503 for upstream weather/space-data outage with a Retry-After header (and the precomputed fallback path active, Part V.5).
- Rule 3: constraint outcomes live in the body as constraint_fired (string) plus per-row screens, never as HTTP errors.

### IV.8 Caching and rate limits

- Window computations keyed by hash(target, site, date_range, vehicle, corridor, criteria_version, raan_tolerance): cached 24 h (deterministic core is time-independent given inputs; Test 6 asserts cache equality).
- Weather responses cached 30 min keyed by (date, site, source); forecast_issue_time stored with the cache entry and echoed, so a cached answer is never presented as a fresh fetch.
- Rate limits (no auth): 60 requests/min per IP on POST /v1/windows, 120/min on GETs; 429 with Retry-After on breach. Limits in config, not code (requirement 1 spirit).

### IV.9 Public Python client (pip-installable)

Package: c2window (pyproject.toml in repo; `pip install c2window` from git URL or PyPI if time permits). Surface:

    from c2window import Client
    df = Client(base_url="https://<host>/v1").window(
        target="SSO", site="canso", dates=("2026-10-05", "2026-10-15"))
    # df: pandas.DataFrame with columns t_liftoff_utc, t_injection_utc, raan_deg,
    #     azimuth_deg, window_width_s, p_success, horizon_label, ...

Three lines as specified: import, window(...) call returning a DataFrame. Additional client methods mirror the endpoints: .site(), .weather(date), .skill(), .citation(run_id), .ephemeris(orbit_id, start, end). The client ships unit tests against a recorded fixture server.

---

## Part V. The Frontend

Delivery rule (Track declaration, PRIOR Sec B): every pixel is a rendering of a Track 1 engine output. No decorative 3D, no timer not driven by POST /v1/windows, no weather color without the underlying probability and its horizon label.

Tech stack for the 32-hour build: Python FastAPI backend (Part IV) serving a static frontend (HTML + Leaflet + vanilla JS) by default; React only if the team has prior React velocity and the hour-26 gate is intact (decision at hour 20, Part VIII). The static path is the recommended primary: fewer moving parts at judging, one repo, no build step failure at demo time.

### V.1 Screen 1: Window Engine (Track 1 core plus the slide countdown feature)

Checklist item 1, COUNTDOWN REQUIREMENT (slide Track 2 feature), specified exactly:

- Source of truth: the countdown ticks to t_liftoff_utc of the earliest row with reachable windows from POST /v1/windows (target selector + date range), fetched on load and re-fetched when inputs change. It is never a decorative interval: if the windows array changes, the countdown target changes. The displayed value is computed each second from Date.now() against t_liftoff_utc (UTC), so the timer survives a backend outage mid-countdown using the last fetched target.
- Timezone handling: dual display, always: primary "2d 04:16:33" style remaining time, plus absolute times in UTC (e.g. "T- 2026-10-07 11:42:00Z") and local Atlantic ("08:42 ADT, Oct 7"). Date objects parse ISO-8601 Z strings; conversion to Atlantic uses Intl with timeZone: "America/Halifax" (handles ADT automatically).
- When no window exists in range: the countdown region renders "No window in range" with the reason row from the engine (reachable:false with plane_change_dv_ms shown, or empty windows with constraint text). It never shows a zeroed or looping fake timer.
- Engine-driven guarantee: the countdown block and the window table read the same single response object in the page state; there is one fetch, one source (frontend state machine documented in V.7).

Screen contents: orbit selector (LEO / Polar / SSO presets with the slide's inclinations pre-filled, plus CUSTOM fields h_t, i_t, RAAN or LTAN), site selector (Canso default), date range picker, vehicle profile dropdown (each choice shows its VERIFIED/ASSUMPTION T_to_inj flag), corridor override fields (optional, default EA config). Output: window table with columns t_liftoff_utc (local + UTC), t_injection_utc, window_width_s, azimuth_deg, reached_inclination_deg, p_success (percentage), horizon_label badge (FORECAST/CLIMATOLOGY), constraint status. Countdown block above the table. Unreachable targets render the honesty panel (reachable:false, 26.8 m/s computed plane change, constants shown).

### V.2 Screen 2: Trajectory View (slide 2D/3D feature)

2D map (primary, Leaflet): southbound Atlantic corridor from Canso rendered as the corridor polygon from GET /v1/site; ground track of the selected orbit class per window row from GET /v1/orbits/{id}/ephemeris (lat/lon points); hazard-area buffer drawn around the nominal track for the selected vehicle footprint; site marker, and the four population-centre markers used by the viewing map (V.4). Each window row in Screen 1 highlights its own track on click (same response id, no second computation).

3D globe (optional, only if hour budget survives hour 26): a minimal WebGL globe drawing the same ephemeris points; cut before any 2D feature if time runs short; never a decorative Earth (PRIOR Sec G.4).

### V.3 Screen 3: Weather Panel (slide Green/Yellow/Red feature, made honest)

Rendered from GET /v1/weather/probability for the selected window date plus the p_success_components.weather of each window row:

- Green / Yellow / Red indicator derived by documented thresholds on p_launch (thresholds in config/weather.json: Green p >= 0.7, Yellow 0.4-0.7, Red < 0.4, defaults flagged ASSUMPTION and shown).
- Always displayed next to the color: the underlying probability as a number, the horizon_label badge (FORECAST for days 0-10, CLIMATOLOGY beyond, in a distinct style), and forecast_issue_time ("issued 00Z, 3 Oct 2026").
- Below the indicator: the visible hindcast skill curve fetched from GET /v1/validation/skill (Brier skill score vs lead time), so the public screen itself shows on what evidence the horizon label rests.
- Criterion breakdown on expand: per-criterion p_violation with VERIFIED/PROXY flags (from IV.3 components).

### V.4 Screen 4: Viewing Map (slide Advanced Bonus)

Illumination and elevation geometry for the ascent as seen from Canadian population centres (Halifax, Moncton, Charlottetown, St John's, plus the Canso area), computed from the same window rows:

- For each window row: at candidate observation times (T+0 to T+3 min along the track), compute the vehicle's ECEF position from the ground track and altitude (ephemeris), then the topocentric elevation and azimuth from each centre; mark centres with max elevation above a config elevation mask (default 10 deg, flagged ASSUMPTION) as "visible"; shade regions below mask or over the horizon as not visible.
- Rendering: Leaflet circles around visible centres plus elevation numbers per centre; a small chart of elevation vs time for the best centre.
- Honesty boundary: the map shows geometric visibility of the ascent track (line of sight, Earth curvature, elevation mask). It does not predict brightness, contrail lighting, or cloud cover (weather panel covers obscuration probability separately). Cut entirely if hour budget fails at hour 26; it is a bonus (slide wording: Advanced Bonus).

### V.5 The offline fallback (demo-survival requirement, CRITICAL)

Shipped in-repo, committed before hour 26, exercised in rehearsal (hour 30):

Precomputed and shipped: (1) a fixtures/windows_Canso_3orbitclasses_90days.json produced by the engine itself (Test 2/3 passing run), containing full window rows including constants and provenance blocks; (2) fixtures/weather_canso_180d.json with climatological P(L|month, hour) and a recorded FORECAST snapshot (with its forecast_issue_time) for the demo date; (3) fixtures/skill_series.json from the hindcast run (Test 4); (4) fixtures/site.json, corridor polygon, ephemeris samples for the three classes; (5) fixtures/citation.json. All fixtures are generated by a script (`make fixtures`) from a real engine run, never hand-edited (Test 6 discipline applies).

Fallback behavior: on any API 5xx/429/timeout, the frontend switches a banner to "OFFLINE PRECOMPUTED DATA (engine run <timestamp>)", loads fixtures, and serves the full four-screen experience from local JSON. Weather in fallback mode always displays forecast_issue_time of the snapshot and the horizon labels of the fixture; if the snapshot is older than the demo date, the label shows CLIMATOLOGY plus the snapshot age. No fabricated live values, ever.

What is deliberately NOT promised: live ensemble updates during judging; NOTAM automation; 3D globe if time is short. Cut rather than promise.

### V.6 What the RESEARCHER sees: the "Scientific analysis" view

A fifth route (/analysis in the static app) that exposes the full scientific output rather than a colored indicator:

- Brier skill series table and chart (GET /v1/validation/skill): lead_time_days, bs, bs_ref, bss, n_cases; the measured skill horizon annotated.
- Reliability diagram (reliability_bins rendered as a calibration plot) and the ROC points.
- The constants block and the full provenance table (GET /v1/citation) rendered as the II.10 table, with the hard-coded/dynamic column visible.
- Downloadable results: buttons exporting the current window table as CSV and JSON (client-side from the loaded response), and the skill series as CSV; links to the raw fixture files for the offline run.
- Input controls mirroring researcher inputs (Part VI): hindcast period, reference forecast (climatology base rate), ensemble size display, output format. These call the same public endpoints; the view is a client of /v1 like any other.

### V.7 Frontend dev handoff (checklist item 7): screen, endpoint, data contract per screen

| Screen | Route | Endpoints consumed | Renders (data contract) |
|---|---|---|---|
| 1 Window Engine + countdown | / | POST /v1/windows; GET /v1/site | orbit selector; window table (IV.1 windows[] fields); countdown from t_liftoff_utc; honesty panel from reachable/plane_change_dv_ms; constants_block footer |
| 2 Trajectory | /trajectory | GET /v1/site; GET /v1/orbits/{id}/ephemeris | corridor polygon; ground track polyline; hazard buffer; per-row highlight keyed by window row index |
| 3 Weather | /weather | GET /v1/weather/probability; GET /v1/validation/skill; IV.3 components | G/Y/R badge from p_launch thresholds; probability number; horizon_label badge; forecast_issue_time; skill curve; per-criterion list with VERIFIED/PROXY |
| 4 Viewing map | /viewing | GET /v1/orbits/{id}/ephemeris; window rows from cached IV.1 response | visibility marks per population centre; elevation-vs-time chart; mask value shown |
| 5 Scientific analysis | /analysis | GET /v1/validation/skill; GET /v1/citation; window response | skill table+chart; reliability diagram; ROC; provenance table; CSV/JSON downloads |
| Fallback layer | any (error boundary) | local fixtures/*.json (5 files, V.5) | identical renderers, banner state = offline_precomputed |

State machine (single source): `engineResponse` (from the one POST), `weatherResponse`, `skillResponse`, `siteResponse`; screens subscribe; the countdown and table both derive from engineResponse; fetch order and failure transitions (-> offline_precomputed) documented in the frontend README. Every numeric on screen is traceable to one of these objects (Track 1 coherence, PRIOR Sec B).

### V.8 Checklist item 2: all slide features mapped

| Slide requirement (Track 1 / Track 2 / bonus) | Where implemented (screen or endpoint) | Covered in |
|---|---|---|
| Track 1 core engine: Target Orbit Type LEO / Polar / SSO with inclinations ~45.1 / 87.9-90 / ~98.1 | Screen 1 selector; POST /v1/windows target.type presets | Part II (math), Part IV (API), V.1 |
| Track 1: list of compatible launch dates/times | Screen 1 window table; windows[] array | II.4-II.5, IV.1, V.1 |
| Track 1 Advanced Bonus: Vehicle Duration (time to injection point, not just liftoff) | t_injection_utc, window_center_shift_s, liftoff_instant_error_min rows; vehicle_profile_id selector | II.5, III.3, IV.1, V.1 |
| Track 2: countdown timer to the next available window | Screen 1 countdown, engine-driven | V.1 (this spec) |
| Track 2: 2D or 3D visual representation of trajectory / satellite path | Screen 2 (Leaflet 2D primary; 3D optional, cut-able) | V.2, IV.2 |
| Track 2: Weather Impact Green/Yellow/Red from mock or real API | Screen 3, real API (Open-Meteo/GDPS) with honest CLIMATOLOGY fallback; thresholds disclosed | V.3, II.7, IV.3 |
| Track 2 Advanced Bonus: Viewing Map of best-view regions | Screen 4 (cut-able) | V.4 |
| Goals line: user-friendly interface for planners and the public | Screens 1-4 (public) + /analysis (planners, researchers) | V.1-V.6, VI |
| Slide line "A missed window can cost millions" | quantified as expected delay cost in the decision layer | II.9 (iv), VI.3 |

---

## Part VI. What Researchers and Practitioners Do With It

### VI.1 Use cases (the three named audiences)

1. Mission planning (MLS planner or a prospective customer): exports a 90-day window CSV. Calls POST /v1/windows with target SSO, site canso, date_range = next 90 days, vehicle_profile_id = cyclone4m, corridor = EA default; receives the windows array with t_liftoff_utc, window_width_s, p_success, horizon_label per row; downloads it as CSV from Screen 1 or the Python client (df.to_csv). The planner sees, per date: when to show up, how long the window is open, the vehicle-duration shift already applied, and what probability the weather layer assigns, labeled by horizon.

2. Researcher: pulls GET /v1/validation/skill to cite a calibrated climatological and forecast probability of a launchable day at 45.3 N. The response supplies base_rate (the climatological P(L) at the site over the stated hindcast period), the Brier skill series per lead time, reliability bins, and verification provenance (ERA5, period, criteria version). This is the publishable dataset object: a hindcast-calibrated probability of a launchable day at 45.3 N with Brier skill, reliability diagram, and ROC, citable through GET /v1/citation and the Zenodo DOI (VI.4).

3. Student (or judge) recomputes a window: opens Screen 1 or runs the Python client, selects LEO, reads the constants block in the response, opens GET /v1/citation for the run, and re-derives the window center by hand from GMST(t) + lambda_s = RAAN + delta (II.9) using the printed constants. The citation endpoint exists precisely so a skeptic can check the arithmetic without trusting the UI.

### VI.2 Input parameters (checklist item 5): both audiences, explicitly

Planner inputs:

| Parameter | Type / example | What the backend computes from it | Objects returned |
|---|---|---|---|
| target.type or (h_t, i_t, LTAN_t / RAAN_t) | "SSO" or {600 km, 98.1, "10:30"} | reachability predicate (II.4); SSO consistency check (II.6); target plane evolution Omega_t(t) (II.7, II.19) | reachable flag, warnings |
| site | "canso" (config name) | RA_site(t) (II.1); corridor test (II.3) | site echo in provenance_block |
| date_range | start/end ISO dates | window search over crossings (II.9)-(II.13); period (II.13) | windows[] list |
| vehicle_profile_id | "cyclone4m" | T_to_inj lookup; fixed-point solve (II.16)-(II.18); footprint for hazard test | t_injection_utc, shift fields, screens |
| corridor (optional override) | {A_min_deg, A_max_deg} | reachable set intersection (II.4); beta clipping | corridor echo with flags |
| criteria_version | "criteria_v1" | weather evaluation against W (II.20)-(II.21) | p_success_components.weather, criterion list |
| raan_tolerance_deg | 0.1 or 5 | window width (II.12) | window_width_s |
| include_weather | boolean | whether to fetch forecast (cost control) | horizon_label, forecast_issue_time or null |

Researcher inputs:

| Parameter | Type / example | What the backend computes from it | Objects returned |
|---|---|---|---|
| hindcast period | period_start / period_end (e.g. 2024-10-01 to 2025-09-30) | verification sample M; Brier (II.24) per lead | skill_series[] with n_cases |
| reference forecast (Brier reference) | "climatology_base_rate" (default; only supported reference in v1) | BS_ref; BSS (II.25) | bs_ref, bss per lead |
| ensemble size N | display of N used per day (from forecast source) | P_forecast (II.21) | ensemble_size field in weather responses |
| output format | csv / json (client-side for windows; json from API for skill) | serialization of the same objects | CSV files, JSON bodies |
| lead_max | 10 (default) | skill curve extent; measured skill horizon | skill_horizon_measured_days |
| site / criteria_version | as planner | same chain with researcher-chosen verification definition | full provenance_block |

Backend chain run for either audience (the Part II pipeline): reachability gate -> target plane evolution -> crossing search (II.9) -> window width (II.12) -> injection-consistent fixed point (II.16) -> hazard/conjunction screens (II.8) -> weather probability (II.21)-(II.23) -> constants/provenance stamping (II.10). Analysis objects returned: windows (per-row with components), P(L|d) series (weather endpoint), skill series + reliability + ROC (validation endpoint), provenance block (citation endpoint).

### VI.3 The decision-theoretic payoff (why the probabilities matter)

For each candidate day the engine's p_d feeds the opportunity-process layer (II.9 iv): expected time-to-next-success (II.27) and expected delay cost (II.28) with C_day from config, in the genre of O'Neill and Davidheiser (doi 10.2514/1.a36618). A planner using the 90-day CSV can therefore compute not just when windows are, but the expected cost of waiting for a high-probability window versus launching on a marginal one, which is the quantitative form of the slide's "a missed window can cost millions". This layer ships as an optional analysis over any requested p-series; SKETCHED status (II.9 iv) is disclosed in its output.

### VI.4 Open data published

- Hindcast dataset: daily P(L|d) predictions with outcomes, period, criteria version, verification source (ERA5), as CSV + parquet, DOI via Zenodo if the account and time permit (fallback: GitHub release tag, stated as such in the report).
- Window tables: 90-day windows for the three orbit classes from Canso (the fixtures of V.5 double as the published tables).
- Corridor bounds and site config as consumed (with assumption flags).
- Skill series CSV (the III.4 output).
- Repository: GitHub, one repo with engine, fixtures, frontend, report inputs; Zenodo DOI minted from the release if time allows (cut item, hour 30 checklist).

### VI.5 How a researcher runs a simulation themselves (walkthrough)

1. Set parameters: target (type or h_t/i_t/LTAN), corridor (default EA or explicit bounds), criteria version, forecast issue date (or hindcast period for retrospective runs), vehicle profile, raan_tolerance, date range (the researcher-input table in VI.2 covers the retrospective controls).
2. Call POST /v1/windows (or the three-line client). The backend executes the Part II chain (VI.2 last paragraph) server-side in under a second for a 90-day range (computation_ms echoed).
3. Receive: windows[] with deterministic fields and the fixed-point corrections; p_success and components when include_weather; constants_block and provenance_block; constraint_fired where applicable.
4. For retrospective skill: GET /v1/validation/skill with the period; compare BSS across leads; read reliability bins; cite base_rate as the site climatology.
5. Audit: GET /v1/citation for the run; re-derive any window center by hand from the printed constants; download CSV/JSON from /analysis.
6. Extend: the researcher edits a copy of data/criteria_v1.json (documented edit path: bump criteria_version, keep old rows immutable, add citations per row) and re-runs; nothing in code changes (requirement 1).

---

## Part VII. Data and Rubric

### VII.1 Data availability and lead-time risk

| Data need | Source | Free? | Endpoint | Lead-time risk |
|---|---|---|---|---|
| Operational deterministic forecast, surface + upper air (wind, precip, cloud), 10-day class | ECCC MSC Datamart GDPS (240 h, 15 km, runs 00/12 UTC; GEPS ensemble to about 384 h TO VERIFY, SCIENCE Sec G.6) | Yes, anonymous, open licence with attribution | https://dd.weather.gc.ca/ ; OGC API https://api.weather.gc.ca/ | Low for demo (endpoint probed 200); medium for ensemble plumbing (raw GRIB2 parsing effort; fallback Open-Meteo) |
| Fast forecast for the live demo path (hourly, no key) | Open-Meteo (aggregates GFS, ECMWF IFS, ICON, MET Norway, GEM HRDPS) | Yes, non-commercial, CC BY 4.0, 10k calls/day | https://api.open-meteo.com/v1/forecast | Low; caveat: ensemble endpoint unreachable in one probe session (PRIOR Sec D); fallback GEFS via NOMADS or climatology |
| Hindcast / climatology backbone (P(L|month,hour), verification) | ERA5 via Copernicus CDS | Yes, free account + licence acceptance | https://cds.climate.copernicus.eu | HIGHEST: account creation and slow bulk download are same-day tasks; mitigate by starting the pull first (PRIOR Sec G.3) and by Open-Meteo historical archive as the fast path |
| Historical forecast runs for skill (leads 1-10 d) | Open-Meteo historical forecast archive (since 2021) | Yes | https://archive-api.open-meteo.com/v1/archive | Low-medium: archive coverage quirks; fallback = GEFS archived reforecasts if needed (cut scope first) |
| Space objects for conjunction pre-screen | CelesTrak GP/TLE | Yes | https://celestrak.org/NORAD/elements/gp.php | Low (probed 200); Space-Track (account) NOT required for pre-screen |
| NOTAM display | Nav Canada | Yes (display) | https://plan.navcanada.ca/ | Low (probed 200); not machine-blessed for bulk, display-only |
| Site geometry, corridor, CARs references | Canso EA (2016 project description, 2019 approval with conditions) | Yes, public PDFs | https://novascotia.ca/nse/ea/canso-spaceport-facility/ | Low; residual risk: corridor numeric bounds not published as data (config defaults flagged ASSUMPTION, SCIENCE Sec G.2) |
| Vehicle duration, performance, footprint | Vehicle user guides (Cyclone-4M guide primary; Isar/Electron guides as available) | Yes, public PDFs | maritimelaunch.com UG_C4M abbreviated (VERIFIED) | Low; every unverified row ships as ASSUMPTION |

Rule: nothing in the engine requires a paid endpoint at demo time; ERA5 account is the single item to complete on day one (PRIOR Sec G.3).

### VII.2 Rubric scoring against the slide wording (all eight rows, 1-5)

Scoring the delivered design as specified in this document; one-line justification each, grounded in the slide's own words.

| Rubric row (slide wording) | Score | One-line justification |
|---|---|---|
| Problem/Solution Definition | 5 | Slide defines Track 1 crisply (target orbit type in, launch dates/times out); our engine returns exactly that list plus the Vehicle Duration bonus, with the input/output contract in Part IV. |
| Problem Relevancy (scope and feasibility suitable given the context) | 5 | 32-hour-scoped: secular-J2 window core plus free weather APIs, nothing requiring GMAT-class infrastructure; Canadian site with an actual EA and actual operator (MLS). |
| Problem Significance (impactful given the context) | 4 | A missed window costing millions is the slide's own stakes; no published Canso analysis exists, but impact is bounded by MLS's current launch cadence (up to 8/yr). |
| Solution Feasibility | 5 | Closed-form geometry plus a scalar fixed point plus fetchable free data; feasibility is demonstrated by the hour-12 engine gate before any UI work. |
| Solution Viability (harmonizes with the goal; scope aligned with what can be accomplished) | 5 | Ships complete: engine, validated weather layer, four screens, offline fixtures; cut list (3D globe, NOTAM automation) explicitly enumerated rather than half-built. |
| Solution Originality (leverages something unexpected) | 4 | The unexpected move is coupling an open window engine to a hindcast-calibrated forecast probability with published skill metrics and an honest unreachable-target verdict; not claimable as 5 without the hindcast finished, per PRIOR Sec B. |
| Problem-Solution Coherency | 5 | Every screen renders Part II outputs through Part IV endpoints (V.7 state machine); the slide's Advanced Bonus appears as computed numbers, not a disclaimer. |
| Team Presentation | 4 | Four screens with countdown, map, weather-with-skill-curve, plus the scientific analysis view give a strong live demo path; score depends on delivery day, held at 4 not 5. |
| TOTAL | 37 | Sum of the eight rows above. |

Weakest row: Problem Significance (4), together with Solution Originality (4); the single weakest on argument risk is **Solution Originality**: a 5 requires the hindcast BSS result and the delay-cost layer to land live, both scheduled but not yet executed (Tests 4, II.9 iv). Significance is capped by site cadence and is fixed by context, not by us; Originality is where rehearsal must focus.

---

## Part VIII. Build Plan for ~32 Hours

Ordered tasks with hour budgets. Clock starts Friday evening; submission Sunday 13:30 ADT. Tasks are sequential unless marked parallel-safe.

| Hours | Task | Exit criterion |
|---|---|---|
| 0-2 | Repo skeleton, config files (site, corridor, constants with sources), criteria_v1.json scaffold, vehicle profile scaffold (rows flagged), ERA5 CDS account created and bounded download started (PRIOR Sec G.3) | config loads; constants printed by a hello-world endpoint |
| 2-6 | Window core: (II.2) reachability, (II.7) J2 drift, (II.9)-(II.13) window search and width, SSO table (II.5-table), GMST module | Test 1 (III.1) passing |
| 6-9 | Injection-consistent fixed point (II.16)-(II.18), vehicle profile T plumbing, honesty path reachable:false + plane_change_dv_ms | Tests 3 and 5 (III.3, III.5) passing |
| 9-12 | CREDIBILITY TEST (III.2) plus determinism/provenance echo (III.6) on the window endpoints | Test 2 suite green (3-5 known windows within +/- 2 min) and Test 6 green |
| **12** | **GATE: engine plus all tests above. The frontend does NOT start until this gate passes.** | all of Tests 1, 2, 3, 5, 6 green |
| 12-16 | Weather layer: criteria evaluation, Open-Meteo/GDPS fetch with forecast_issue_time, P(L|d) FORECAST mode, climatology mode, p_success product | weather responses labeled and echoing components |
| 16-20 | Hindcast: pre-staged ERA5/Open-Meteo archive run, Brier/BSS/reliability/ROC (II.24-II.25), GET /v1/validation/skill | Test 4 (III.4) executed; BSS table recorded (positive or honestly reported) |
| **20** | **GATE: weather layer plus hindcast artifact exist. Frontend stack decision (static vs React) locked here.** | skill endpoint serving; fixtures/skill_series.json written |
| 20-24 | Frontend Screens 1-2: window table, countdown (V.1), Leaflet corridor + ground track (V.2), single-state fetch machine (V.7) | countdown driven by t_liftoff_utc; table from IV.1; offline banner wired |
| 24-26 | Screen 3 weather panel with horizon labels + skill curve; fixtures for offline fallback committed (V.5) | full offline rehearsal passes with API killed |
| **26** | **GATE: frontend plus (time-permitting) viewing map. Viewing map (V.4) and 3D globe start only if the gate is early; otherwise cut here, declared cut.** | four screens rendering engine outputs only |
| 26-28 | /analysis researcher view (V.6), CSV/JSON downloads, GET /v1/citation rendering, Python client three-line demo | researcher walkthrough (VI.5) executed end to end |
| 28-30 | Report/Description sync: contribution statement (PRIOR Sec C.5) verbatim, rubric rows, provenance table in submission materials, Zenodo/GitHub release attempt | documents match engine behavior |
| **30** | **GATE: rehearsal. Full judged run on a clean machine: offline fallback exercised, timing, one failure injection (kill API mid-demo).** | demo survives API failure; talk track timed |
| 30-32 | Buffer: bug fixes, screenshot/fixture refresh, submission upload (confirm destination, SCIENCE Sec G.12) | submitted before 13:30 ADT Sunday |

Single biggest failure risk and mitigation: **weather plumbing collapsing at demo time** (ERA5 account/download slipping, Open-Meteo ensemble unreachable as already observed in probes, or GDPS parsing overrun). This is the only subsystem that depends on third-party state fetched under time pressure, and it is the subsystem the rubric Originality score leans on. Mitigation, layered: (1) start the ERA5 pull in hour 0-2, before any code; (2) ship the climatology path first (ERA5 month-hour table needs one archive file), so the tool is honest and complete with CLIMATOLOGY labels even if no live forecast ever connects; (3) commit the five-file offline fixture set (V.5) by hour 26 and rehearse the failure path at hour 30; (4) the frontend reads forecast_issue_time and horizon_label, so a stale or fallback source is visibly labeled rather than silently wrong; (5) Test 4's failure branch (III.4) degrades gracefully to CLIMATOLOGY labeling instead of fabricating skill. Secondary risk (engine credibility) is already gated at hour 12 with a defined fix-first protocol.

Explicit cut list, agreed now rather than promised later: 3D globe; NOTAM automation beyond display; conjunction fidelity above the TLE pre-screen; rideshare panel (PRIOR Sec G.4); live ensemble updates during judging; Zenodo DOI if account setup slips (GitHub release tag instead); React if static velocity is higher at hour 20.

---

## Appendix A. Challenge 2 slide text (verbatim)

Transcribed from the official photograph, for line-by-line checking of this specification against the challenge statement:

> CHALLENGE 2 - Mission Control aka "Ben's special challenge"
>
> "Space agencies and private launch providers face a complex puzzle: matching a satellite's required orbital parameters with the Earth's rotation, weather patterns, and launch vehicle capabilities. A missed window can cost millions.
>
> Your goal: Build a tool that calculates optimal launch windows based on orbital requirements and provides a user-friendly interface for both mission planners and the general public.
>
> Participants must choose one of the following tracks:
>
> Track 1: The Orbital Architect (Data & Math Focused): Focus: Solving the 'Hard' logic of orbital mechanics. Core Requirement: Create an engine that takes a 'Target Orbit Type' (LEO, Polar, or SSO) and outputs a list of compatible launch dates/times. The Logic: LEO: Calculate windows for inclinations ~45.1 deg. Polar: calculate windows for inclinations 87.9-90 deg. SSO: calculate windows for inclinations ~98.1 deg. Advanced Bonus: Incorporate 'Vehicle Duration.' Does the window account for the time it takes the rocket to reach the injection point, or does it only look at the liftoff moment?
>
> Track 2: The Launch Watcher (UX & Visualization Focused): Focus: Solving the 'Public Interface' and 'Engagement' aspect. Core Requirement: Build a web-based 'Launch Dashboard' for the public. The Features: A countdown timer to the next available window. A visual representation (2D or 3D) of the launch trajectory or the satellite's path around Earth. A 'Weather Impact' indicator (Green/Yellow/Red) based on mock or real-time weather API data. Advanced Bonus: A 'Viewing Map' that shows which geographic regions will have the best view of the ascent."

Rubric (8 rows, 1-5): Problem/Solution Definition; Problem Relevancy (Is the scope and feasibility of the problem apparent and is it suitable given the challenges context); Problem Significance (How impactful is the problem, is it important given the context of challenges); Solution Feasibility; Solution Viability (Does the final solution harmonize with the goal of the challenge, is the scope aligned with what could be accomplished); Solution Originality (Consider the uniqueness and creativity of the solution. Does it leverage something unexpected or solve it differently); Problem-Solution Coherency (Does the problem the team set out to solve get accomplished with the final solution); Team Presentation.

Mapping of slide lines to this document: slide Track 1 core -> Part II, Part IV, V.1; Vehicle Duration bonus -> II.5, III.3, IV.1; Track 2 countdown -> V.1 (checklist item 1); 2D/3D trajectory -> V.2, IV.2; Weather G/Y/R -> V.3, II.7, IV.3; Viewing Map -> V.4; rubric rows -> VII.2; "missed window can cost millions" -> II.9 (iv), VI.3.

END OF SPECIFICATION (Sec 0, Parts I-VIII, Appendix A).
