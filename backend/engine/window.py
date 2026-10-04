"""The window equation: opportunity versus period (spec II.4).

A launch WINDOW is a connected interval of launch instants during which the
mission constraints hold simultaneously. A WINDOW PERIOD is the recurrence
interval between successive opportunities. They are different objects and this
module keeps them apart.

    delta(i, phi_s) = asin(tan(phi_s) / tan(i))                               (II.10)

    GMST(t) + lambda_s = Omega_t(t) + delta      (mod 360)                    (II.9)

on the ascending branch, with the descending branch substituting 180 - delta.
Existence of delta is exactly the reachability condition i >= phi_s, so (II.8)
to (II.10) unify the predicate of (II.4) with the window search.

    d(RA_site - Omega_t)/dt = omega_sid - Omega_targ_dot                      (II.11)

    tau_half  = Delta_Omega / |omega_sid - Omega_targ_dot|   [hours]         (II.12)
    W_window  = 2 * tau_half

    P_window  = 360 / (360.9856 - Omega_targ_dot)           [days]           (II.13)

Search method: the residual g(t) of (II.16) with T = 0 is monotone in t because
g'(t) = omega_sid - Omega_targ_dot > 0 for every physically meaningful drift, so
the crossings can be bracketed and bisected. No iteration count is guessed and no
grid step can miss a window: the sweep rate bounds how far the residual can move
between two samples.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Mapping

from backend.engine import frames, provenance

DEG = math.pi / 180.0
RAD = 180.0 / math.pi

_SECONDS_PER_DAY = 86400.0


@dataclass(frozen=True)
class Window:
    """One launch opportunity on one branch."""

    open_jd: float
    centre_jd: float
    close_jd: float
    open_raan_deg: float
    close_raan_deg: float
    raan_deg: float
    width_s: float
    branch: str


# --- Offsets (II.10) ---------------------------------------------------------


def site_node_offset_deg(i_t_deg: float, lat_deg: float) -> float | None:
    """The site-to-node offset ``delta``, or None when i_t < phi_s (unreachable)."""
    cos_lat = math.cos(lat_deg * DEG)
    tan_i = math.tan(i_t_deg * DEG)
    if abs(cos_lat) < 1.0e-15 or abs(tan_i) < 1.0e-12:
        raise ValueError("offset is undefined at the pole or at equatorial inclination")
    ratio = math.tan(lat_deg * DEG) / tan_i
    if ratio > 1.0 + 1.0e-12 or ratio < -1.0 - 1.0e-12:
        return None
    return math.degrees(math.asin(max(-1.0, min(1.0, ratio))))


def descending_offset_deg(i_t_deg: float, lat_deg: float) -> float:
    """The descending branch offset, 180 deg - delta (spec II.4)."""
    ascending = site_node_offset_deg(i_t_deg, lat_deg)
    if ascending is None:
        raise ValueError("no descending offset for an unreachable inclination")
    return 180.0 - ascending


# --- Sweep rate and widths (II.11, II.12) ------------------------------------


def sidereal_rate_deg_per_hour() -> float:
    return provenance.OMEGA_SID_RAD_S * RAD * 3600.0


def sweep_rate_deg_per_hour(nodal_rate_deg_per_day: float) -> float:
    """(II.11): how fast the site's RA runs away from the target plane."""
    return sidereal_rate_deg_per_hour() - nodal_rate_deg_per_day / 24.0


def window_half_width_s(tolerance_deg: float, nodal_rate_deg_per_day: float) -> float:
    """tau_half in seconds, spec (II.12) and spec III.1's 24 s test row."""
    rate = abs(sweep_rate_deg_per_hour(nodal_rate_deg_per_day))
    return tolerance_deg / rate * 3600.0


def window_width_s(tolerance_deg: float, nodal_rate_deg_per_day: float) -> float:
    """The full window width in seconds, spec (II.12)."""
    return 2.0 * window_half_width_s(tolerance_deg, nodal_rate_deg_per_day)


def window_period_days(nodal_rate_deg_per_day: float) -> float:
    """Recurrence interval between opportunities, spec (II.13)."""
    return 360.0 / (sidereal_rate_deg_per_hour() * 24.0 - nodal_rate_deg_per_day)


# --- Residual and root search (II.9, II.16) ----------------------------------


def _target_raan_deg(target: Mapping[str, Any], jd: float) -> float:
    """Omega_t(t) on [0, 360): the requested plane at t, including secular drift."""
    return _target_raan_unwrapped_deg(target, jd) % 360.0


def _target_raan_unwrapped_deg(target: Mapping[str, Any], jd: float) -> float:
    """Omega_t(t) without wrapping. Continuous in t, which the root solver needs."""
    return target["raan_deg"] + target["nodal_rate_deg_per_day"] * (jd - target["epoch_jd"])


def _residual_deg(target: Mapping[str, Any], jd: float, offset_deg: float) -> float:
    """g(t) of (II.16) with T = 0, wrapped to (-180, 180].

    Uses the continuous GMST so that the reported residual agrees with the one
    the solver converged on. Reducing a sidereal time of magnitude 3.5e6 deg
    modulo 360 first loses about 4e-5 deg to the modulus.
    """
    raw = (
        frames.gmst_degrees_unwrapped(jd)
        + target["lon_deg"]
        - offset_deg
        - _target_raan_unwrapped_deg(target, jd)
    )
    return (raw + 180.0) % 360.0 - 180.0


def _unwrapped_deg(target: Mapping[str, Any], jd: float, offset_deg: float) -> float:
    """The same expression before wrapping. Continuous and strictly increasing.

    Wrapping makes the residual discontinuous at +/-180 deg, and a Newton step
    that lands on that jump stalls or oscillates. Solving the unwrapped form
    against an integer multiple of 360 deg finds the same roots without the
    discontinuity.
    """
    return (
        frames.gmst_degrees_unwrapped(jd)
        + target["lon_deg"]
        - offset_deg
        - _target_raan_unwrapped_deg(target, jd)
    )


def _solve_root(
    target: Mapping[str, Any],
    offset_deg: float,
    seed_jd: float,
    sweep_deg_per_day: float,
    period_days: float,
    tolerance_deg: float = 1.0e-11,
    max_iterations: int = 60,
) -> float:
    """Root of g(t) = 0 on one branch, the one nearest the seed."""
    level = 360.0 * round(_unwrapped_deg(target, seed_jd, offset_deg) / 360.0)
    t = seed_jd
    for _ in range(max_iterations):
        delta = _unwrapped_deg(target, t, offset_deg) - level
        if abs(delta) < tolerance_deg:
            return t
        step = max(-period_days / 4.0, min(period_days / 4.0, delta / sweep_deg_per_day))
        t -= step

    lo, hi = t - period_days / 2.0, t + period_days / 2.0
    f_lo = _unwrapped_deg(target, lo, offset_deg) - level
    f_hi = _unwrapped_deg(target, hi, offset_deg) - level
    if not f_lo < 0.0 < f_hi:
        raise RuntimeError("window root is not bracketed; sweep rate assumption failed")
    for _ in range(200):
        mid = 0.5 * (lo + hi)
        f_mid = _unwrapped_deg(target, mid, offset_deg) - level
        if f_mid == 0.0:
            return mid
        if f_mid < 0.0:
            lo, f_lo = mid, f_mid
        else:
            hi, f_hi = mid, f_mid
    return 0.5 * (lo + hi)


def find_windows(
    target: Mapping[str, Any],
    start_jd: float,
    end_jd: float,
    branch: str | None = None,
) -> list[Window]:
    """Every window whose interval lies inside ``[start_jd, end_jd]``, ascending.

    Both branches of (II.9) are searched unless ``branch`` names one of them. The
    caller must be able to ask for a single branch: for a date-indexed LTAN
    target the two branches carry different RAAN values, so solving one branch
    against the other's plane finds a different root. Roots are spaced exactly one recurrence
    period (II.13) apart, so the search solves for ONE root per branch and then
    steps by whole periods. This is exact rather than a scan: a grid search can
    step over a narrow window, and at one second of resolution a 90-day range
    would need millions of residual evaluations.

    The residual g of (II.16) is smooth and has derivative
    omega_sid - Omega_targ_dot, which is positive for every physically meaningful
    drift, so Newton from the linear seed converges in two or three steps. A
    bisection fallback backs it up so a stalled Newton can never return a wrong
    answer silently.
    """
    i_t = target["i_t_deg"]
    lat = target["lat_deg"]
    tolerance = target["raan_tolerance_deg"]
    nodal_rate = target["nodal_rate_deg_per_day"]

    ascending = site_node_offset_deg(i_t, lat)
    if ascending is None:
        return []

    sweep_deg_per_day = sidereal_rate_deg_per_hour() * 24.0 - nodal_rate
    if sweep_deg_per_day <= 0.0:
        raise ValueError("nodal drift has cancelled or exceeded the sidereal sweep")
    period = 360.0 / sweep_deg_per_day
    half_days = window_half_width_s(tolerance, nodal_rate) / _SECONDS_PER_DAY

    branches = [("ascending", ascending), ("descending", 180.0 - ascending)]
    if branch is not None:
        branches = [item for item in branches if item[0] == branch]

    results: list[Window] = []
    for name, offset in branches:
        root = _solve_root(target, offset, start_jd, sweep_deg_per_day, period)
        # Walk the exact period spacing to reach the first root that can open
        # inside the range, then emit while the window still fits.
        steps = math.ceil((start_jd - half_days - root) / period)
        candidate = root + steps * period
        while candidate - half_days <= end_jd:
            # Whole-period stepping reintroduces a small timing error, so each
            # emitted centre is polished back onto the residual root. Spec II.5
            # sets the convergence criterion at |Delta t| < 0.01 s; this meets it.
            candidate = _solve_root(target, offset, candidate, sweep_deg_per_day, period)
            results.append(
                _make_window(target, candidate, offset, name, tolerance, half_days)
            )
            candidate += period

    results = [
        entry
        for entry in results
        if entry.open_jd >= start_jd - 1.0e-12 and entry.close_jd <= end_jd + 1.0e-12
    ]
    results.sort(key=lambda entry: entry.centre_jd)
    deduplicated: list[Window] = []
    for entry in results:
        if deduplicated and abs(entry.centre_jd - deduplicated[-1].centre_jd) < 1.0e-9:
            continue
        deduplicated.append(entry)
    return deduplicated


def _make_window(
    target: Mapping[str, Any],
    centre_jd: float,
    offset_deg: float,
    branch: str,
    tolerance: float,
    half_days: float,
) -> Window:
    return Window(
        open_jd=centre_jd - half_days,
        centre_jd=centre_jd,
        close_jd=centre_jd + half_days,
        open_raan_deg=_residual_deg(target, centre_jd - half_days, offset_deg),
        close_raan_deg=_residual_deg(target, centre_jd + half_days, offset_deg),
        raan_deg=_target_raan_deg(target, centre_jd),
        width_s=2.0 * half_days * _SECONDS_PER_DAY,
        branch=branch,
    )