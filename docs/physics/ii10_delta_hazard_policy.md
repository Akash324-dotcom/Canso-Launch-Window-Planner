# The site-to-node offset of (II.10): which form is correct, and why

> Companion to `docs/physics/ii10_delta.md` (the merged derivation of #33). Both reach the same verdict on the closed form. This note adds the replayed hazard-screen evidence (section 9) and the per-site policy that `backend/engine/tests/test_hazard_direction_policy.py` pins.

Issue W5b. Status of the conclusion: PROVED for the geometry (it is algebra, sections 2 to 4),
measured for the published launches (section 6). No engine behaviour is changed by this note.

## 1. The question

The window equation of spec II.4 is

    GMST(t) + lambda_s = Omega_t(t) + delta(i, phi_s)   (mod 360 deg)         (II.9)

and two forms of `delta` were in dispute:

    form A   delta = asin( tan(phi) / tan(i) )      spec (II.10), backend/engine/window.py
    form B   delta = asin( sin(phi) / sin(i) )      the "spherical triangle" form

At i = 98.1 deg and phi = 45.3 deg form A gives -8.27 deg and form B gives +45.89 deg. They cannot
both be the offset of (II.9), and gate G1 reproduces the published launches with form A.

**Answer.** Both formulas are correct, for two different sides of the same spherical triangle.
Form A is the difference in right ascension between the site meridian and the ascending node.
Form B is the argument of latitude, the arc along the orbit from the node to the site. Equation
(II.9) is an equation in right ascension, so it needs form A. The engine is right and stays as it is.

## 2. Form A from first principles

Notation. Omega is the right ascension of the ascending node and i the inclination of the target
plane. alpha is the right ascension of the site, alpha = GMST(t) + lambda_s by (II.1). phi is the
latitude of the site position vector.

The unit vector along the orbital angular momentum, the normal of the plane, is

    n = ( sin i sin Omega,  -sin i cos Omega,  cos i ).

The unit vector from the centre of the Earth to the site is

    r = ( cos phi cos alpha,  cos phi sin alpha,  sin phi ).

The site is in the plane exactly when r is perpendicular to n:

    r . n = cos phi sin i ( cos alpha sin Omega - sin alpha cos Omega ) + sin phi cos i
          = -cos phi sin i sin(alpha - Omega) + sin phi cos i
          = 0.

Dividing by cos phi sin i, which is not zero away from the poles and for i not 0 or 180 deg,

    sin(alpha - Omega) = tan(phi) / tan(i).                                   (II.8)

This is (II.8) of the spec, with no step skipped. The two solutions for alpha - Omega in one turn are

    alpha - Omega = delta            with  delta = asin( tan(phi) / tan(i) ),   (II.10)
    alpha - Omega = 180 deg - delta,

and substituting alpha = GMST + lambda_s gives (II.9) with the first solution and its second branch
with the second. A solution exists exactly when |tan phi| <= |tan i|, which is the reachability
condition of spec II.4.

So `delta` in (II.9) is by construction the quantity alpha - Omega: **the right ascension of the
site meridian measured from the ascending node.** That is form A.

## 3. The triangle, and what form B is

Take the right spherical triangle on the unit sphere with vertices

- N, the ascending node on the equator,
- S, the site,
- F, the foot of the site meridian on the equator.

Its sides are the equatorial arc NF = alpha - Omega, the meridian arc FS = phi, and the arc along
the orbit NS = u, the argument of latitude. The angle at F is 90 deg. The angle at N is the
inclination i. Napier's rules for this triangle give three relations:

    sin(phi)           = sin(i) sin(u)            (a)   opposite side from hypotenuse and angle
    sin(alpha - Omega) = tan(phi) / tan(i)        (b)   adjacent side from opposite side and angle
    tan(alpha - Omega) = cos(i) tan(u)            (c)   adjacent side from hypotenuse and angle

Relation (b) is (II.8) again, form A. Relation (a) solved for u is

    u = asin( sin(phi) / sin(i) ),

which is form B. **Form B is the hypotenuse of the triangle: the arc the vehicle travels along the
orbit from the ascending node to the latitude of the site.** It is a correct formula. It is the
right angle for a question about position along the orbit, for example the time since the node
crossing. It is not a right ascension and it cannot be added to Omega.

Relation (c) ties the two together and is a check on any pair of numbers:
cos(98.1 deg) tan(45.8865 deg) = -0.140901 * 1.031434 = -0.145330 = tan(-8.2689 deg).

The same statement in coordinates. In the frame whose x axis points at the node, the point of the
orbit at argument of latitude u is

    ( cos u,  cos i sin u,  sin i sin u ).

Its height above the equator is sin i sin u, which gives (a). Its right ascension from the node is
atan2( cos i sin u, cos u ), which gives (c). For a retrograde plane cos i is negative, so the right
ascension falls while the vehicle climbs north: the site meridian lies **west** of the ascending
node and `delta` is negative. That is the sign of -8.27 deg, and it is not a convention.

## 4. What (II.9) requires

(II.9) equates two right ascensions: the left side is the right ascension of the site meridian, the
right side is the right ascension of the node plus an offset. The offset must therefore be a
difference of right ascensions, and section 2 shows it is exactly alpha - Omega of (II.8). Form A.

Using form B there states that the site meridian is u degrees of right ascension east of the node.
For i = 98.1 deg and phi = 45.3 deg that places the site at

    r . n = -cos(phi) sin(i) sin(45.8865 deg) + sin(phi) cos(i)
          = -0.703395 * 0.990024 * 0.717962 + 0.710799 * (-0.140901)
          = -0.6001,

that is 36.88 deg out of the plane it is supposed to be in.

The two forms coincide only for a site on the equator, where both are zero.

## 5. Numerical check that uses neither formula

`backend/engine/tests/test_ii10_delta.py` checks the above without the closed forms:

- it builds n and r from their definitions and evaluates r . n for each form, on both branches, for
  seven inclinations from 51.6 to 120 deg, five latitudes from 5.24 to 62.89 deg and four nodes;
- it walks the orbit from the node by bisection on the height sin i sin u until the latitude of the
  site is reached, then reads the right ascension and the arc of that point.

| i (deg) | phi (deg) | walked right ascension from the node | form A | walked arc | form B |
|---|---|---|---|---|---|
| 98.1 | 45.3 | -8.2689 | -8.2689 | 45.8865 | 45.8865 |
| 87.9 | 45.3 | +2.1235 | +2.1235 | 45.3389 | 45.3389 |
| 98.0 | 45.3 | -8.1648 | -8.1648 | 45.8719 | 45.8719 |
| 51.6 | 28.5 | +25.4892 | +25.4892 | 37.5070 | 37.5070 |

With form A, |r . n| is below 1e-12 on both branches in every case. With form B it is above 1e-3 in
every case.

## 6. The decisive empirical check: the published launches under each form

Data: `backend/engine/data/published_windows.json`, the six anchors of gate G1. Method: the gate's
own residual function (`_residuals_minutes` in `test_reproduce_published_windows.py`), run once with
the engine's offset and once with form B in its place. Residuals are minutes from the published
liftoff instant; "gate" is the residual the gate judges, the nearer branch with the common ascent
profile bias of 10.015 min subtracted for the two Rockot anchors. The tolerance of the gate is 5 min.

| Anchor | Site latitude | i | delta A | delta B | A ascending | A descending | **A gate** | B ascending | B descending | **B gate** |
|---|---|---|---|---|---|---|---|---|---|---|
| Sentinel-1C, Kourou | 5.239 | 98.180 | -0.755 | 5.293 | -1.545 | -715.712 | **-1.545** | 22.656 | 700.510 | **22.656** |
| EarthCARE, Vandenberg | 34.633 | 97.050 | -4.900 | 34.935 | 680.316 | -0.547 | **-0.547** | -600.464 | -159.901 | **-159.901** |
| Sentinel-5P, Plesetsk | 62.887 | 98.740 | -17.473 | 64.233 | 0.914 | -579.203 | **0.914** | 327.684 | 533.789 | **327.684** |
| Sentinel-3A, Plesetsk | 62.887 | 98.620 | -17.222 | 64.195 | 10.148 | -572.054 | **0.133** | 335.801 | 542.234 | **325.786** |
| Sentinel-3B, Plesetsk | 62.887 | 98.628 | -17.238 | 64.197 | 9.882 | -572.147 | **-0.133** | 335.584 | 541.983 | **325.569** |
| Sentinel-3C, Kourou | 5.239 | 98.600 | -0.795 | 5.299 | 2.257 | -711.209 | **2.257** | 26.625 | 704.066 | **26.625** |
| Root mean square | | | | | | | **1.20** | | | **240.2** |

Under form A every anchor is inside the 5 minute gate. Under form B none is: the nearest miss is
22.7 min and the Plesetsk anchors miss by more than five hours.

The size of the miss is the size the geometry predicts. The site sweeps the plane at
360.9856 - 0.9856 = 360 deg per day, 0.25 deg per minute, so replacing the offset moves the crossing
by (delta B - delta A) / 0.25 minutes: 24.2 min at Kourou (measured 24.2), 326.8 min at Plesetsk
(measured 326.8), 159.3 min at Vandenberg (measured 159.4, with the opposite sign because that
anchor is on the descending branch, whose offset is 180 deg - delta).

Six launches from three sites at latitudes from 5 to 63 deg agree with form A to 2.3 minutes and
disagree with form B by 23 to 328 minutes. The gate is not passing by coincidence.

## 7. Determination

- **Form A is correct for (II.9).** It is what r . n = 0 gives, and it is the only one of the two that
  is a right ascension.
- **Form B is a correct formula for the argument of latitude,** the third side of the same triangle.
  The dispute came from using the name "spherical triangle form" for one relation of a triangle that
  has three.
- **There is no contradiction between geometry and gate.** The form the geometry requires is the form
  the engine has, and it is the form that reproduces the launches.
- **No behaviour change.** `site_node_offset_deg` in `backend/engine/window.py` is left as it is.
  Nothing was changed to make a gate pass, and nothing needed to be.

A perturbation check was made and reverted: with form B in `window.py` the engine suite has 65
failures, 28 of them in the G1 gate. With the committed form it has none.

## 8. Two observations that are not acted on here

**8.1 The two example values in the spec text do not match (II.10) at phi_s = 45.3 deg.** Spec II.4
quotes delta = 2.37 deg for i = 87.9 deg and -8.16 deg for i = 98.1 deg. Direct evaluation gives
2.1235 deg and -8.2689 deg. The quoted -8.16 deg is the value at i = 98.0 deg (-8.1648 deg). The
engine computes from the formula and stores neither number, so the windows are not affected. The
spec text is outside the scope of this issue and was not edited.

**8.2 Geodetic and geocentric latitude.** In section 2, phi is the latitude of the position vector r,
which is the geocentric latitude. The engine passes the geodetic latitude of the site file, as spec
II.1 states its convention. At sea level the two are related by tan(phi_geocentric) =
(1 - f)^2 tan(phi_geodetic) with the WGS84 flattening f.

| Site | Geodetic | Geocentric | delta with geodetic | delta with geocentric | Difference | In time |
|---|---|---|---|---|---|---|
| Kourou, i 98.18 | 5.2392 | 5.2043 | -0.7552 | -0.7502 | 0.0051 deg | 1.2 s |
| Vandenberg, i 97.05 | 34.6327 | 34.4530 | -4.9001 | -4.8672 | 0.0329 deg | 7.9 s |
| Canso, i 98.1 | 45.3 | 45.1076 | -8.2689 | -8.2132 | 0.0557 deg | 13.4 s |
| Plesetsk, i 98.74 | 62.887 | 62.7306 | -17.4731 | -17.3524 | 0.1207 deg | 29.0 s |

The gate residuals with the geocentric latitude are -1.525, -0.679, 1.397, 0.609, 0.343 and 2.278
min, root mean square 1.32 against 1.20. All are inside the gate either way, so **the published
launches cannot tell the two conventions apart**: the difference is at most half a minute and the
anchors are known to about a minute. The Rockot profile bias was also fitted with the geodetic value,
so those two anchors are not an independent test of it. The effect at Canso is 13 seconds, against a
window of 480 seconds. It is recorded for the engine owner as a refinement with a known size, not as
an error that the evidence establishes. No change is proposed here.

## 9. The hazard screen's southbound rule

Until the change of section 9.1, `backend/engine/screens.py` refused every azimuth outside 90 to 270 deg before it looked at the
corridor of the site, with the reason "The Canso environmental assessment states that all launches
are conducted to the south over the Atlantic Ocean".

**Verdict: the rule is correct for Canso and wrong as a rule for all sites. It needs a per-site
policy.** The policy is now in place (section 9.1); the evidence below is the state that led to it.

Evidence, from `compute_windows` on the gate request of each anchor. The row nearest the published
instant is the launch that was flown.

| Anchor | Site | Azimuth of the row that reproduces the launch | Hazard screen | Residual of that row |
|---|---|---|---|---|
| Sentinel-1C | Kourou | 351.79 deg, northbound | **fail**, `hazard_area` | -1.533 min |
| EarthCARE | Vandenberg | 188.58 deg, southbound | pass | -0.533 min |
| Sentinel-5P | Plesetsk | 340.52 deg, northbound | **fail**, `hazard_area` | +0.933 min |
| Sentinel-3A | Plesetsk | 340.80 deg, northbound | **fail**, `hazard_area` | +10.283 min, +0.268 after the profile bias |
| Sentinel-3B | Plesetsk | 340.78 deg, northbound | **fail**, `hazard_area` | +9.733 min, -0.282 after the profile bias |
| Sentinel-3C | Kourou | 351.36 deg, northbound | **fail**, `hazard_area` | +2.267 min |

Five of the six published launches flew north, from Kourou and from Plesetsk. The engine finds their
instants to 2.3 minutes and then marks the crossing that was flown as refused on range grounds,
citing an assessment that concerns another site. Only the Vandenberg launch, which does go south,
passes.

What is right and what is not:

- For Canso the statement is a fact of the site: its environmental assessment admits southbound
  flight over the Atlantic only.
- At Canso the constant adds nothing. The corridor of `site_canso.json` is 115 to 195 deg (flag
  DERIVED), which already lies inside the southbound half, so the corridor test alone refuses a
  northbound azimuth there.
- For any other site the constant is a property of Canso applied where it does not hold, and its
  reason text names the wrong site.
- The corridors of the three gate sites are 90 to 260 deg, each flagged ASSUMPTION and described in
  its file as "not a published corridor", so with the constant removed those northbound launches
  would still be refused, by a placeholder. The per-site policy therefore needs real data for those
  sites, not only the removal of the constant.

### 9.1 The change made

The admissible direction is now site data, and `screens.py` names no site.

- `site_canso.json` carries `corridor.direction_policy`: `admitted_branch` southbound, the statement
  and its source (Registration Document sections 2.2.5 and 2.2.5.4), flag VERIFIED.
  `reachability.direction_policy` reads it; `_is_southbound` as a rule of the screen is deleted.
- A site whose file states no policy has none applied. Its corridor bounds alone decide, over a
  sector that may cross north (`A_min_deg` greater than `A_max_deg` runs from `A_min_deg` through
  360 deg to `A_max_deg`). `corridor_inclination_bounds` includes the turning points of the
  inclination at 90 and 270 deg, which the sector may now contain.
- `reachable_in_corridor` asks whether the site admits either crossing of the plane, the southbound
  azimuth of (II.2) or its northbound partner, by the same two tests the screen applies to a row.
- A request that overrides the corridor bounds at Canso keeps the policy of the site: the override
  moves bounds, not the statement of the environmental assessment.
- Every reason names the corridor that decided and the flag of its bounds, for example
  "leaves the corridor [90, 260] deg (bounds flagged ASSUMPTION)".

At Canso nothing changes in any verdict. The tests are in
`backend/engine/tests/test_hazard_direction_policy.py`.

### 9.2 What is still open

The five northbound launches are still marked refused, now by the placeholder corridors of the gate
sites and with a reason that says the bounds are an ASSUMPTION. The table above is unchanged. To
close it each gate site needs a published corridor in its file, and none is written here because
none was confirmed from a primary document:

| Site | Lead found | Standing |
|---|---|---|
| Kourou | launch azimuths from -10.5 to 93.5 deg are attributed to the Guiana Space Centre in secondary references; the Vega C User's Manual is the document to quote | not read at the page; not entered |
| Vandenberg | secondary references disagree: 147 to 201 deg, 158 to 201 deg, 170 to 240 deg | no primary document found; not entered |
| Plesetsk | the Eurockot Plesetsk User's Manual (EHB0006) is distributed on request | not obtained; not entered |

With the Kourou figures entered as the sector 349.5 to 93.5 deg, the two Kourou launches (351.79 and
351.36 deg) would pass and their southbound partners would be refused, which the sector logic above
already supports. This does not touch gate G1, which is a gate on time.

## 10. Reproducing this note

    .venv/bin/python -m pytest backend/engine/tests/test_ii10_delta.py -q          # 206 tests
    .venv/bin/python -m pytest backend/engine/tests/test_reproduce_published_windows.py -q

The first file holds the geometry of sections 2 to 5, the engine pin, the residuals of section 6
under both forms, and the hazard-screen evidence of section 9. The per-site policy of section 9.1 is
in `backend/engine/tests/test_hazard_direction_policy.py`.
