"""The delay-cost decision layer of spec II.9 (iv), checked against closed forms.

The expected extra days are the survival sum  sum_{j>=1} prod_{s<=j} (1 - p_s).
Every expectation here is derived by hand or by a different route (a direct
enumeration of the success-day distribution), so none of them repeats the code.
"""

from __future__ import annotations

import itertools
import math

import pytest

from backend.engine import decision


def _enumerated_extra_days(p_series: list[float]) -> tuple[float, float]:
    """Expected extra days by walking the whole outcome distribution, not the survival sum.

    P(first success on day k) = p_k * prod_{s<k} (1 - p_s). Days after the horizon are cut,
    so a run with no success contributes N (the truncation), like the survival sum does.
    """
    n = len(p_series)
    expected_t = 0.0
    q = 1.0
    for k, p in enumerate(p_series, start=1):
        expected_t += k * p * q
        q *= 1.0 - p
    expected_t += n * q  # truncated: T is cut at N
    return expected_t - 1.0, q


def test_a_constant_probability_gives_the_geometric_tail():
    p = 0.5
    result = decision.expected_extra_days([p] * 200)

    assert result["expected_extra_days"] == pytest.approx((1 - p) / p, abs=1e-12)
    assert result["p_no_success_in_horizon"] == pytest.approx((1 - p) ** 200)


def test_a_hand_computed_three_day_series():
    # p = 0.5 each day: P(T>1) = 0.5, P(T>2) = 0.25, so extra days = 0.5 + 0.25 = 0.75.
    result = decision.expected_extra_days([0.5, 0.5, 0.5])

    assert result["expected_extra_days"] == pytest.approx(0.75)
    assert result["p_no_success_in_horizon"] == pytest.approx(0.125)


def test_a_certain_first_day_costs_nothing():
    result = decision.expected_extra_days([1.0, 0.0, 0.0])

    assert result["expected_extra_days"] == 0.0
    assert result["p_no_success_in_horizon"] == 0.0


def test_a_week_of_no_chance_is_the_full_truncated_wait():
    result = decision.expected_extra_days([0.0] * 7)

    assert result["expected_extra_days"] == pytest.approx(6.0)  # T cut at N = 7, minus 1
    assert result["p_no_success_in_horizon"] == 1.0


def test_one_day_has_no_extra_days_and_keeps_the_miss_probability():
    result = decision.expected_extra_days([0.3])

    assert result["expected_extra_days"] == 0.0
    assert result["p_no_success_in_horizon"] == pytest.approx(0.7)


@pytest.mark.parametrize(
    "series",
    [
        [0.61, 0.0, 0.706, 0.98, 0.51],
        [0.2, 0.9, 0.1, 0.4],
        [0.05] * 6,
        [0.0, 0.0, 1.0, 0.3],
    ],
)
def test_the_survival_sum_equals_the_enumerated_distribution(series):
    expected, left_over = _enumerated_extra_days(series)
    result = decision.expected_extra_days(series)

    assert result["expected_extra_days"] == pytest.approx(expected, abs=1e-12)
    assert result["p_no_success_in_horizon"] == pytest.approx(left_over, abs=1e-12)


def test_the_printed_form_of_ii27_diverges_and_the_survival_form_does_not():
    """The spec prints sum (1 - prod(1 - p)), which is P(T <= j) and grows with the horizon."""
    p = 0.5

    def printed(horizon: int) -> float:
        return sum(1.0 - (1.0 - p) ** j for j in range(horizon))

    assert printed(1000) > 900.0
    assert decision.expected_extra_days([p] * 1000)["expected_extra_days"] == pytest.approx((1 - p) / p)


def test_a_higher_probability_never_lengthens_the_wait():
    base = [0.3, 0.4, 0.5, 0.2]
    for index in range(len(base)):
        better = list(base)
        better[index] = min(1.0, better[index] + 0.2)
        assert (
            decision.expected_extra_days(better)["expected_extra_days"]
            <= decision.expected_extra_days(base)["expected_extra_days"] + 1e-15
        )


def test_the_truncated_sum_is_a_lower_bound_of_a_longer_horizon():
    short = [0.2, 0.2, 0.2]
    longer = short + [0.2] * 10

    assert (
        decision.expected_extra_days(short)["expected_extra_days"]
        < decision.expected_extra_days(longer)["expected_extra_days"]
    )


def test_the_cost_is_c_day_times_the_extra_days_and_is_absent_without_it():
    series = [0.5, 0.5, 0.5]
    without = decision.expected_delay_cost(series)
    with_cost = decision.expected_delay_cost(series, c_day=2_000.0)

    assert without["expected_cost"] is None and without["c_day"] is None
    assert without["expected_extra_days"] == pytest.approx(0.75)
    assert with_cost["expected_cost"] == pytest.approx(1_500.0)
    assert with_cost["c_day_flag"] == "USER_SUPPLIED"


def test_the_bound_is_exact_only_when_no_mass_is_left_beyond_the_horizon():
    assert decision.expected_delay_cost([0.5, 1.0])["bound"] == "exact"
    assert decision.expected_delay_cost([0.5, 0.5])["bound"] == "lower"


def test_the_summary_states_its_status_assumptions_and_citation():
    body = decision.expected_delay_cost([0.4, 0.4])

    assert body["status"] == "SKETCHED"
    assert any("independent" in text for text in body["assumptions"])
    assert "10.2514/1.a36618" in body["citation"]


def test_the_module_writes_no_default_cost_number():
    import inspect

    source = inspect.getsource(decision)
    assert "c_day: float | None = None" in source


@pytest.mark.parametrize(
    "bad",
    [[], [0.5, -0.1], [0.5, 1.1], [0.5, float("nan")], [0.5, float("inf")], ["0.5"], [True], "0.5"],
)
def test_a_bad_series_is_refused(bad):
    with pytest.raises(ValueError):
        decision.expected_extra_days(bad)


@pytest.mark.parametrize("bad", [-1.0, float("nan"), float("inf"), "5", True])
def test_a_bad_cost_is_refused(bad):
    with pytest.raises(ValueError):
        decision.expected_delay_cost([0.5, 0.5], c_day=bad)


def test_all_outcomes_of_a_small_series_sum_to_one():
    series = [0.3, 0.6, 0.2]
    total = 0.0
    q = 1.0
    for p in series:
        total += p * q
        q *= 1.0 - p
    total += q

    assert math.isclose(total, 1.0)
    # and the enumeration over all 2^3 success patterns agrees with the closed form
    expectation = 0.0
    for pattern in itertools.product([0, 1], repeat=3):
        probability = 1.0
        for p, hit in zip(series, pattern):
            probability *= p if hit else 1.0 - p
        first = next((k for k, hit in enumerate(pattern, start=1) if hit), len(series))
        expectation += probability * first
    assert expectation - 1.0 == pytest.approx(decision.expected_extra_days(series)["expected_extra_days"])
