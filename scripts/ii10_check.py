"""Derivation check for (II.10) delta = asin(tan(phi_s)/tan(i)) vs asin(sin(phi_s)/sin(i)).

Two independent checks:

A. GEOMETRY. Build an orbit from (i, Omega) with no delta formula involved,
   propagate to the argument of latitude whose sub-satellite latitude equals
   phi_s, convert the ECI position through frames.eci_to_ecef and
   frames.ecef_to_geodetic, and read the resulting geographic longitude. The
   hour-angle offset from the node is that longitude minus Omega. Whichever
   closed form reproduces the vector-derived number is the hour-angle offset.

B. RESIDUALS. Run the (II.9) window equation at the published launch instants
   from data/published_windows.json with each candidate delta.
"""

from __future__ import annotations

import json
import math
import pathlib

from backend.engine import frames, j2, sso, window

D = math.pi / 180.0


# --- A. Independent vector geometry ------------------------------------------


def hour_angle_from_orbit(i_deg: float, phi_s_deg: float, raan_deg: float) -> float:
    """Delta (deg) from an ECI/ECEF round-trip. No closed form is used here."""
    i = i_deg * D
    r = 6371.0e3 + 800.0e3

    def eci_at(u: float) -> tuple[float, float, float]:
        return (
            r * (math.cos(u) * math.cos(raan_deg * D)
                 - math.sin(u) * math.sin(raan_deg * D) * math.cos(i)),
            r * (math.cos(u) * math.sin(raan_deg * D)
                 + math.sin(u) * math.cos(raan_deg * D) * math.cos(i)),
            r * math.sin(u) * math.sin(i),
        )

    # Solve for the argument of latitude u that puts the sub-satellite point at the
    # GEODETIC site latitude, by bisection on the geodetic round-trip. No
    # sin(u) = sin(phi_s)/sin(i) shortcut is used, so this stays independent.
    def geodetic_lat(u: float) -> float:
        lat, _, _ = frames.ecef_to_geodetic(*frames.eci_to_ecef(eci_at(u), 2451545.0))
        return lat

    lo, hi = -math.pi / 2.0, math.pi / 2.0
    for _ in range(200):
        mid = 0.5 * (lo + hi)
        if geodetic_lat(mid) < phi_s_deg:
            lo = mid
        else:
            hi = mid
    u = 0.5 * (lo + hi)
    assert abs(geodetic_lat(u) - phi_s_deg) < 1.0e-9, "point is not over the site"

    eci = eci_at(u)
    ra_point = math.degrees(math.atan2(eci[1], eci[0])) % 360.0
    return (ra_point - raan_deg + 180.0) % 360.0 - 180.0


def tan_form(i_deg: float, phi_s_deg: float) -> float | None:
    r = math.tan(phi_s_deg * D) / math.tan(i_deg * D)
    return None if abs(r) > 1 else math.degrees(math.asin(r))


def sin_form(i_deg: float, phi_s_deg: float) -> float | None:
    r = math.sin(phi_s_deg * D) / math.sin(i_deg * D)
    return None if abs(r) > 1 else math.degrees(math.asin(r))


def wrap360(x: float) -> float:
    return (x + 180.0) % 360.0 - 180.0


print("=" * 78)
print("A. VECTOR GEOMETRY: which closed form is the hour-angle offset?")
print("=" * 78)
print(f"{'i':>7} {'phi_s':>7} {'vector':>10} {'tan form':>10} {'sin form':>10} "
      f"{'|v-tan|':>9} {'|v-sin|':>9}")
for i_deg, phi_s in [(98.1, 45.3), (98.18, 5.2392), (98.74, 62.887), (97.05, 34.6327),
                     (98.62, 62.887), (98.6276, 62.887), (98.6, 5.2392), (87.9, 45.3),
                     (45.1, 45.3), (69.4, 45.3), (70.0, 20.0), (100.0, 70.0)]:
    v = hour_angle_from_orbit(i_deg, phi_s, 213.7) if i_deg >= phi_s else float("nan")
    t = tan_form(i_deg, phi_s)
    s = sin_form(i_deg, phi_s)
    dt = abs(wrap360(v - t)) if (t is not None and v == v) else float("nan")
    ds = abs(wrap360(v - s)) if (s is not None and v == v) else float("nan")
    print(f"{i_deg:7.3f} {phi_s:7.3f} {v:10.5f} {str(round(t, 5) if t is not None else 'unreachable'):>10} "
          f"{str(round(s, 5) if s is not None else 'unreachable'):>10} {dt:9.2e} {ds:9.2e}")

# --- B. Window-equation residuals at the published instants -------------------


def residuals_minutes(case: dict, form: str) -> dict[str, float]:
    """Best |residual| in minutes over the engine's two site crossings."""
    jd_pub = frames.julian_date_from_iso(case["published_liftoff_utc"])
    i, lat = case["inclination_deg"], case["latitude_deg"]
    nodal = j2.nodal_rate_deg_per_day(case["altitude_km"], i)
    sweep = window.sweep_rate_deg_per_hour(nodal) * 24.0
    ascending = (tan_form if form == "tan" else sin_form)(i, lat)
    out = {}
    for branch, off in (("ascending", ascending), ("descending", 180.0 - ascending)):

        def resid(jd: float, off: float = off) -> float:
            raan = sso.raan_for_ltan_deg(jd, case["ltan_hours"], case["ltan_branch"])
            return frames.gmst_degrees_unwrapped(jd) + case["longitude_deg"] - off - raan

        half = 180.0 / sweep
        lo, hi = jd_pub - half, jd_pub + half
        level = 360.0 * round(resid(jd_pub) / 360.0)
        assert resid(lo) - level < 0.0 < resid(hi) - level
        for _ in range(200):
            mid = 0.5 * (lo + hi)
            if resid(mid) - level < 0.0:
                lo = mid
            else:
                hi = mid
        out[branch] = (0.5 * (lo + hi) - jd_pub) * 1440.0
    return out


root = pathlib.Path(__file__).resolve().parents[1]
data = json.loads((root / "backend/engine/data/published_windows.json").read_text())
tol = data["tolerance_minutes"]
print()
print("=" * 78)
print(f"B. (II.9) RESIDUALS AT PUBLISHED LIFTOFF (min, engine minus published), gate = {tol}")
print("=" * 78)
print(f"{'anchor':28} {'i':>7} {'phi_s':>6} {'tan delta':>10} {'tan res':>9} "
      f"{'sin delta':>10} {'sin res':>9} {'br':>4} {'bias':>7} {'tan-gate':>9}")
print(f"{'':28} {'':>7} {'':>6} {'':>10} {'min':>9} {'':>10} {'min':>9} "
      f"{'':>4} {'min':>7} {'PASS/FAIL':>9}")
tbest_list, sbest_list = [], []
for case in data["cases"]:
    ta, sa = tan_form(case["inclination_deg"], case["latitude_deg"]), sin_form(case["inclination_deg"], case["latitude_deg"])
    rt, rs = residuals_minutes(case, "tan"), residuals_minutes(case, "sin")
    bt = min(rt, key=lambda b: abs(rt[b]))
    bs = min(rs, key=lambda b: abs(rs[b]))
    bias = case.get("profile_bias_min", 0.0)
    tc, sc = rt[bt] - bias, rs[bs] - bias
    tbest_list.append(tc)
    sbest_list.append(sc)
    verdict = "PASS" if abs(tc) <= tol else "FAIL"
    print(f"{case['id']:28} {case['inclination_deg']:7.3f} {case['latitude_deg']:6.3f} "
          f"{ta:10.4f} {rt[bt]:+9.3f} {sa:10.4f} {rs[bs]:+9.3f} {bt[:4]:>4} "
          f"{bias:+7.3f} {tc:+9.3f} {verdict:>9}")
print()
print(f"tan form: {sum(1 for v in tbest_list if abs(v) <= tol)}/{len(tbest_list)} within the "
      f"{tol} min gate, max |residual| = {max(abs(v) for v in tbest_list):.3f} min")
print(f"sin form: {sum(1 for v in sbest_list if abs(v) <= tol)}/{len(sbest_list)} within the "
      f"{tol} min gate, max |residual| = {max(abs(v) for v in sbest_list):.3f} min")