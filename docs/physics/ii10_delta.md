# (II.10): what `delta` is, and which closed form is correct

Status: the repo's `delta = asin(tan(phi_s)/tan(i))` is CORRECT. The proposed
replacement `asin(sin(phi_s)/sin(i))` is a different physical quantity that was
conflated with it. No engine change is required.

## 1. What (II.9) requires `delta` to be

    GMST(t) + lambda_s = Omega_t(t) + delta                    (II.9)

`GMST(t) + lambda_s` is by definition the right ascension of the site's meridian,
`RA_site(t)`. Rearranged:

    delta = RA_site(t) - Omega_t(t)

So (II.9) requires `delta` to be an angle **in the equatorial plane**: the
hour-angle offset of the sub-satellite point from the ascending node, that is a
right-ascension difference. This matches the spec's own wording at the
(II.4) provenance row: "hour-angle offset of the site from the node line".

It does **not** ask for an angle measured in the orbit plane.

## 2. Derivation of both forms

Set up the spherical triangle with the ascending node `A`, the north pole `N`,
and the sub-satellite point `P`. Two standard relations of the ground track are
available, and they are the whole story:

    (a)  sin(phi_s) = sin(i) sin(u)          u = argument of latitude
    (b)  tan(delta)  = cos(i) tan(u)         delta = RA offset from the node

Solve (a) for u, substitute into (b):

    sin u = sin(phi_s)/sin(i)
    cos u = sqrt(1 - sin^2(phi_s)/sin^2(i)) = sqrt(sin^2 i - sin^2 phi_s)/sin i
    tan u = sin(phi_s) / sqrt(sin^2 i - sin^2 phi_s)

    tan(delta) = cos(i) sin(phi_s) / sqrt(sin^2 i - sin^2 phi_s)

Taking the sine rather than the tangent:

    sin^2(delta) = c^2 a^2 / (c^2 a^2 + (b^2 - a^2))          with a = sin phi_s, b = sin i, c = cos i
                 = c^2 a^2 / (b^2 - a^2 b^2)
                 = c^2 a^2 / (b^2 cos^2 phi_s)

    sin(delta) = cos(i) sin(phi_s) / (sin(i) cos(phi_s)) = tan(phi_s) / tan(i)

Therefore

    delta = asin( tan(phi_s) / tan(i) )        EXACT

**The tan form is the hour-angle offset. The sin form is equation (a) inverted,
so `asin(sin(phi_s)/sin(i))` is `u`, the argument of latitude, an angle measured
along the orbit from the node, not a right-ascension difference.** They differ by
the factor `cos(i)` between `tan(delta)` and `tan(u)`, which for a near-polar
orbit is small but not the same quantity: at `i = 98.1, phi_s = 45.3` one gives
`delta = -8.2689 deg` and `u = 45.8865 deg`.

## 3. Independent vector verification

`scripts/ii10_check.py` part A builds an orbit from `(i, Omega)` with no closed
form involved, bisects the argument of latitude until the ECI/ECEF/geodetic
round trip puts the sub-satellite point at the geodetic site latitude, then reads
`atan2(y, x) - Omega`. The residual against the tan form (0.005 to 0.19 deg) is
the geodetic/geocentric flattening correction the spherical identity omits; the
residual against the sin form is 6 to 101 deg.

| i | phi_s | vector | tan form | sin form |
|---|---|---|---|---|
| 98.100 | 45.300 | -8.21940 | -8.26891 | 45.88648 |
| 98.740 | 62.887 | -17.36600 | -17.47314 | 64.23267 |
| 97.050 | 34.633 | -4.87088 | -4.90011 | 34.93473 |
| 87.900 | 45.300 | 2.11091 | 2.12354 | 45.33892 |
| 69.400 | 45.300 | 22.18346 | 22.32329 | 49.40718 |
| 100.000 | 70.000 | -28.78841 | -28.97673 | 72.59015 |

## 4. Window-equation residuals at the published anchors

Residual in minutes of `(II.9)` at the published liftoff instant, best over the
engine's two site crossings, `scripts/ii10_check.py` part B. Gate is 5.0 min.

| anchor | i | phi_s | tan delta | tan res | sin delta | sin res | branch | bias | tan gate |
|---|---|---|---|---|---|---|---|---|---|
| sentinel_1c_2024_12_05 | 98.180 | 5.239 | -0.7552 | -1.545 | 5.2932 | +22.656 | asc | 0 | PASS |
| earthcare_2024_05_28 | 97.050 | 34.633 | -4.9001 | -0.547 | 34.9347 | -159.901 | desc | 0 | PASS |
| sentinel_5p_2017_10_13 | 98.740 | 62.887 | -17.4731 | +0.914 | 64.2327 | +327.684 | asc | 0 | PASS |
| sentinel_3a_2016_02_16 | 98.620 | 62.887 | -17.2219 | +10.148 | 64.1947 | +335.801 | asc | 10.015 | PASS |
| sentinel_3b_2018_04_25 | 98.628 | 62.887 | -17.2378 | +9.882 | 64.1971 | +335.584 | asc | 10.015 | PASS |
| sentinel_3c_2026_09_15 | 98.600 | 5.239 | -0.7946 | +2.257 | 5.2989 | +26.625 | asc | 0 | PASS |

tan form: 6/6 inside the gate, max absolute residual 2.257 min.
sin form: 0/6, max absolute residual 327.7 min (5.5 h).

The sin-form miss is latitude-dependent, not a constant offset that could be
absorbed: `sin delta - tan delta` runs 6.05 deg at Kourou and 81.7 deg at
Plesetsk.

## 5. Why the conflation went unnoticed

Both forms share the same reachability predicate, `|argument| <= 1`, which is
`i >= phi_s` in either case (verified for `i < phi_s`: `|tan phi_s/tan i|` and
`|sin phi_s/sin i|` both exceed 1). So the `(II.8)` to `(II.10) unification the
spec claims still holds under the correct form, and a reachability test cannot
distinguish the two.

## 6. Branch assignment

`descending_offset_deg = 180 - delta` is right. The descending node sits at
`Omega + 180`, so the same sub-satellite point has offset `delta - 180` from it;
the engine's `180 - delta` places the site the same magnitude east of the
descending node, the mirror image of the ground track. The branch handling needs
no change.

## 7. Hazard screen

`screen._is_southbound` hard-codes Canso's `[90, 270]` Atlantic southbound rule
and applies it to every site, including the three G1 anchor sites whose corridor
files declare `branch: southbound` but carry no such published numeric rule
(their `source` field reads "NOT A PUBLISHED CORRIDOR").

**At every current site the rule is a no-op.** Each declared corridor is a subset
of `[90, 270]` (Canso `[115, 195]`, all three anchors `[90, 260]`), so corridor
membership already implies southbound and the hard-coded test never rejects
anything corridor membership would admit.

**It is still a latent bug in construction**, not correct behaviour: a
Canso-specific environmental-assessment fact is a global constant, and the
rejection string names the Canso EA even when screening Vandenberg. Probing a
site whose corridor is genuinely northbound, azimuth 341.5 in `[330, 350]`
declared `branch: northbound`, is rejected with the Canso Atlantic reason. That
matters here: the Rockot/Briz-KM SSO profile the data file documents flies a
341.5 deg corridor, i.e. northbound out of Plesetsk.

**Honest per-site policy.** Directional admissibility belongs in configuration,
not in Python. `corridor.branch` already carries it per site; the screen should
test the numeric corridor membership of (II.3) and consult `branch` as a site
fact, emitting a reason that names the site whose rule fired and its source.
Sites with no published directional rule should be gated on corridor membership
alone. `_is_southbound` as a module-level constant should go.

This is recorded, not changed: the current output is identical at all four sites,
and changing the screen is out of scope for a derivation finding.

## 8. Verdict

`asin(tan(phi_s)/tan(i))` is correct and load-bearing. It is exact algebra, it
matches independent vector geometry, and it reproduces all six published
anchors inside 2.26 min. The sin form computes the argument of latitude, breaks
the G1 gate on every anchor, and is rejected. No engine behaviour changes.