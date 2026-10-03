"""The injection-consistent fixed point. Spec II.5. Claim (i) is PROVED.

The plane condition (II.9) must hold at INJECTION, but the plane the vehicle can
actually achieve is fixed in inertial space at LIFTOFF by (II.2) and (II.8) to
(II.9) evaluated at t_l. Between liftoff and injection the target plane drifts.

    Omega_ach(t_l) = GMST(t_l) + lambda_s - delta(i_t, phi_s)                 (II.14)
    requirement:    Omega_ach(t_l) = Omega_t(t_l + T(t_l))   (mod 360)       (II.15)

    g(t) = wrap[GMST(t) + lambda_s - delta - Omega_t(t + T(t)) ]             (II.16)

Relaxation (II.5 mode 1, the default):

    t_{k+1} = t_k - g(t_k) / omega_sid_eff,
    omega_sid_eff = omega_sid - Omega_targ_dot

starting from the liftoff-instant solution t^(0), that is the root of g with T = 0.

CONTRACTION (II.17), the provable statement:

    |Phi'(t)| = |Omega_targ_dot (1 + dT/dt)| / |omega_sid - Omega_targ_dot| < 1

Spec claim (i) bounds this at 0.017 for LEO-class targets with fixed T. This
module evaluates it on every solve and reports it, so a parameter range where it
exceeded 1 would be visible rather than hidden behind more iterations.

CONVERGENCE. Spec II.5: |g| < 1e-6 deg or |Delta t| < 0.01 s, at most 50
iterations. A case that does not converge returns constraint_fired
fixed_point_no_convergence with diagnostics, never a silent wrong answer.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Mapping

from backend.engine import frames, provenance, window

DEG = math.pi / 180.0
RAD = 180.0 / math.pi

SECONDS_PER_DAY = 86400.0
MAX_ITERATIONS = 50
RESIDUAL_TOLERANCE_DEG = 1.0e-6
STEP_TOLERANCE_S = 0.01

NO_CONVERGENCE = "fixed_point_no_convergence"


@dataclass(frozen=True)
class InjectionSolution:
    """The outcome of one injection-consistent solve."""

    liftoff_jd: float
    injection_jd: float
    converged: bool
    iterations: int
    residual_deg: float
    delta_t_s: float
    window_center_shift_s: float
    liftoff_instant_error_min: float
    contraction_factor: float
    t_to_inj_s: float
    t_to_inj_flag: str
    constraint_fired: str | None = None

    def to_window_row(self) -> dict[str, Any]:
        """The engine's share of a spec IV.1 window row.

        Carries no ``p_success``, ``horizon_label`` or ``forecast_issue_time``:
        those are composed by the API.
        """
        return {
            "t_liftoff_utc": frames.iso_from_julian_date(self.liftoff_jd),
            "t_injection_utc": frames.iso_from_julian_date(self.injection_jd),
            "window_center_shift_s": self.window_center_shift_s,
            "liftoff_instant_error_min": self.liftoff_instant_error_min,
            "p_success_components": {"range": 1.0, "conjunction": 1.0},
            "constraint_fired": self.constraint_fired,
        }


def load_vehicle(profile_id: str) -> dict[str, Any]:
    """Read a vehicle profile from ``data/vehicles/<profile_id>.json``."""
    if not profile_id or any(character in profile_id for character in "/\\."):
        raise ValueError(f"invalid vehicle profile id {profile_id!r}")
    try:
        return provenance.load_json(f"vehicles/{profile_id}.json")
    except FileNotFoundError as error:
        raise ValueError(f"unknown vehicle profile {profile_id!r}") from error


# --- Quantities the spec quotes ---------------------------------------------


def sweep_rate_deg_per_hour(nodal_rate_deg_per_day: float) -> float:
    """omega_sid_eff of (II.5): the Earth's sweep minus the target's drift."""
    return window.sweep_rate_deg_per_hour(nodal_rate_deg_per_day)


def predicted_shift_s(nodal_rate_deg_per_day: float, t_to_inj_s: float) -> float:
    """(II.18): the fixed-point refinement term, in seconds.

        Delta_t_shift = Omega_targ_dot * T_to_inj / (omega_sid - Omega_targ_dot)

    Positive for a target whose plane advances, negative for one that regresses,
    and zero if and only if the ascent takes no time or the plane does not drift.
    """
    rate = sweep_rate_deg_per_hour(nodal_rate_deg_per_day)
    if rate == 0.0:
        raise ValueError("nodal drift has cancelled the sidereal sweep")
    # Both the numerator rate and the sweep rate are deg per hour, and the result
    # is seconds, so the hours-to-seconds conversions cancel exactly. Inserting a
    # single 3600 here inflates the answer by a thousand, which is what the unit
    # test now pins.
    return (nodal_rate_deg_per_day / 24.0) * t_to_inj_s / rate


def contraction_factor(target: Mapping[str, Any]) -> float:
    """(II.17): |Phi'(t)|, the contraction constant claim (i) bounds below 1.

    Evaluated rather than assumed. A value at or above 1 means the relaxation is
    not a contraction here and the caller must be told, which is what
    :func:`solve_injection_consistent` reports through its diagnostics.
    """
    nodal_rate = target["nodal_rate_deg_per_day"]
    dt_dt = float(target.get("dT_dt") or 0.0)
    rate = sweep_rate_deg_per_hour(nodal_rate)
    if rate == 0.0:
        return math.inf
    return abs(nodal_rate / 24.0) * (1.0 + abs(dt_dt)) / abs(rate)


# --- The residual and the solve ---------------------------------------------


def _offset_deg(target: Mapping[str, Any]) -> float:
    ascending = window.site_node_offset_deg(target["i_t_deg"], target["lat_deg"])
    if ascending is None:
        raise ValueError("no window offset exists for an unreachable inclination")
    return 180.0 - ascending if target.get("branch") == "descending" else ascending


def _raan_unwrapped_deg(target: Mapping[str, Any], jd: float) -> float:
    return target["raan_deg"] + target["nodal_rate_deg_per_day"] * (jd - target["epoch_jd"])


def _unwrapped_residual_deg(target: Mapping[str, Any], jd: float, offset_deg: float) -> float:
    """g(t) of (II.16) before wrapping, so the solver sees a continuous function."""
    injection_jd = jd + target["t_to_inj_s"] / SECONDS_PER_DAY
    return (
        frames.gmst_degrees_unwrapped(jd)
        + target["lon_deg"]
        - offset_deg
        - _raan_unwrapped_deg(target, injection_jd)
    )


def _root_of_level(
    target: Mapping[str, Any],
    offset_deg: float,
    seed_jd: float,
    level: float,
    rate_deg_per_day: float,
) -> tuple[float, int, float]:
    """The root of ``residual(t) = level``, the steps taken, and the bracket width.

    Returns ``(root, steps, bracket_seconds)``. The bracket width is how
    precisely the root is located; the displacement from the analytic start is
    the ANSWER (the window-centre shift), not an accuracy measure, and the two
    must not be confused when reporting convergence against spec II.5.

    The unwrapped residual is continuous and strictly increasing, and ``level``
    is chosen as the multiple of 360 nearest the seed, so the root always lies
    within half a recurrence period of the seed. That gives a guaranteed bracket
    and makes the solve provably convergent.

    Newton was tried first and rejected: its step is symmetric, so a seed needing
    to move forward by more than a quarter period gets pushed BACKWARD past the
    root and lands on the neighbouring period's root, which is also a valid root
    of the same equation. That returned a liftoff time one whole day wrong and
    looked like convergence. Bisection cannot overshoot.
    """
    period_days = 360.0 / rate_deg_per_day
    lo, hi = seed_jd - period_days / 2.0, seed_jd + period_days / 2.0
    f_lo = _unwrapped_residual_deg(target, lo, offset_deg) - level
    f_hi = _unwrapped_residual_deg(target, hi, offset_deg) - level
    while f_lo > 0.0:
        lo -= period_days
        hi -= period_days
        f_lo = _unwrapped_residual_deg(target, lo, offset_deg) - level
        f_hi = _unwrapped_residual_deg(target, hi, offset_deg) - level
    while f_hi < 0.0:
        lo += period_days
        hi += period_days
        f_lo = _unwrapped_residual_deg(target, lo, offset_deg) - level
        f_hi = _unwrapped_residual_deg(target, hi, offset_deg) - level

    for step in range(1, MAX_ITERATIONS + 1):
        mid = 0.5 * (lo + hi)
        f_mid = _unwrapped_residual_deg(target, mid, offset_deg) - level
        if f_mid == 0.0:
            return mid, step, 0.0
        if f_mid < 0.0:
            lo, f_lo = mid, f_mid
        else:
            hi, f_hi = mid, f_mid
        if abs(f_mid) < RESIDUAL_TOLERANCE_DEG or (hi - lo) * SECONDS_PER_DAY < STEP_TOLERANCE_S:
            return 0.5 * (lo + hi), step, (hi - lo) * SECONDS_PER_DAY
    return 0.5 * (lo + hi), MAX_ITERATIONS, (hi - lo) * SECONDS_PER_DAY


def solve_injection_consistent(
    target: Mapping[str, Any], start_jd: float, end_jd: float
) -> InjectionSolution:
    """Solve (II.16) for the liftoff instant nearest ``start_jd`` within the range.

    Returns an :class:`InjectionSolution` in every case. A non-converging solve
    carries ``converged=False`` and ``constraint_fired`` set, never a number that
    looks like an answer.
    """
    offset_deg = _offset_deg(target)
    t_to_inj_s = float(target["t_to_inj_s"])
    rate_deg_per_day = sweep_rate_deg_per_hour(target["nodal_rate_deg_per_day"]) * 24.0
    factor = contraction_factor(target)

    if rate_deg_per_day <= 0.0:
        raise ValueError("nodal drift has cancelled or exceeded the sidereal sweep")

    # (II.5): the liftoff-instant solution is the analytic start t^(0).
    instantaneous = dict(target)
    instantaneous["t_to_inj_s"] = 0.0

    # The unwrapped residual is strictly increasing, so the equation
    # unwrapped(t) = level has exactly ONE solution. Successive launch
    # opportunities come from the residual returning to the same value modulo a
    # full turn, so stepping to the next opportunity means raising the level by
    # 360, not advancing the seed by one period. Adding a period to the seed
    # instead moves the residual by 360 and lands on a DIFFERENT equation, which
    # is how an earlier version of this returned a liftoff time one whole day
    # wrong while still satisfying its own convergence test.
    level = 360.0 * round(_unwrapped_residual_deg(instantaneous, start_jd, offset_deg) / 360.0)
    instant, start_steps, _ = _root_of_level(
        instantaneous, offset_deg, start_jd, level, rate_deg_per_day
    )
    while instant < start_jd - 1.0e-12:
        level += 360.0
        instant, start_steps, _ = _root_of_level(
            instantaneous, offset_deg, instant, level, rate_deg_per_day
        )
    while _root_of_level(
        instantaneous, offset_deg, instant - 1.0, level - 360.0, rate_deg_per_day
    )[0] >= start_jd - 1.0e-12:
        level -= 360.0
        instant, start_steps, _ = _root_of_level(
            instantaneous, offset_deg, instant, level, rate_deg_per_day
        )

    liftoff, iterations, delta_t_s = _root_of_level(
        target, offset_deg, instant, level, rate_deg_per_day
    )
    residual = abs(_unwrapped_residual_deg(target, liftoff, offset_deg) - level)

    converged = residual < RESIDUAL_TOLERANCE_DEG or delta_t_s < STEP_TOLERANCE_S
    if not (start_jd - 1.0e-9 <= liftoff <= end_jd + 1.0e-9):
        converged = False

    shift_s = predicted_shift_s(target["nodal_rate_deg_per_day"], t_to_inj_s)
    return InjectionSolution(
        liftoff_jd=liftoff,
        injection_jd=liftoff + t_to_inj_s / SECONDS_PER_DAY,
        converged=converged,
        iterations=iterations,
        residual_deg=residual,
        delta_t_s=delta_t_s,
        window_center_shift_s=shift_s,
        liftoff_instant_error_min=(t_to_inj_s - shift_s) / 60.0,
        contraction_factor=factor,
        t_to_inj_s=t_to_inj_s,
        t_to_inj_flag=target.get("t_to_inj_flag", "ASSUMPTION"),
        constraint_fired=None if converged else NO_CONVERGENCE,
    )
