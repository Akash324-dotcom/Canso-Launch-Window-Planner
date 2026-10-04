"""Issue #7, V0 and V1: the scoring functions. Pure, no I/O, hand-checked values."""

from __future__ import annotations

import pytest

from backend.weather import hindcast

# V0 Brier score ----------------------------------------------------------------------------------------------


def test_a_perfect_forecast_has_brier_score_zero():
    """p = 1 when it happened, p = 0 when it did not: every (p - o)^2 is 0."""
    assert hindcast.brier_score([(1.0, 1), (0.0, 0), (1.0, 1)]) == 0.0


def test_a_confidently_wrong_forecast_has_brier_score_one():
    """p = 0 when it happened, p = 1 when it did not: every (p - o)^2 is 1."""
    assert hindcast.brier_score([(0.0, 1), (1.0, 0)]) == 1.0


def test_a_mixed_case_matches_the_hand_computation():
    """(0.75 - 1)^2 = 0.0625, (0.25 - 0)^2 = 0.0625, (0.5 - 1)^2 = 0.25, (1.0 - 0)^2 = 1.0. Mean = 1.375 / 4."""
    pairs = [(0.75, 1), (0.25, 0), (0.5, 1), (1.0, 0)]

    assert hindcast.brier_score(pairs) == pytest.approx(0.34375)


def test_the_brier_score_of_no_pairs_is_undefined_not_zero():
    with pytest.raises(ValueError):
        hindcast.brier_score([])


# V0 Brier skill score ----------------------------------------------------------------------------------------

def test_skill_is_one_minus_the_ratio_of_scores():
    assert hindcast.brier_skill_score(0.0, 0.25) == 1.0          # perfect forecast
    assert hindcast.brier_skill_score(0.25, 0.25) == 0.0         # identical to the reference
    assert hindcast.brier_skill_score(0.1, 0.25) == pytest.approx(0.6)


def test_a_forecast_worse_than_the_reference_has_negative_skill_and_it_is_not_clipped():
    assert hindcast.brier_skill_score(0.5, 0.25) == pytest.approx(-1.0)
    assert hindcast.brier_skill_score(1.0, 0.1) == pytest.approx(-9.0)


def test_skill_is_undefined_when_the_reference_score_is_zero():
    """A sample in which the event always or never happened has a perfect base-rate forecast; no skill number."""
    assert hindcast.brier_skill_score(0.2, 0.0) is None


def test_the_reference_score_comes_from_the_base_rate_of_the_sample_not_from_a_constant():
    """Outcomes 1, 0, 0, 0: base rate 0.25. Reference BS = mean((0.25 - o)^2) = (0.5625 + 3 * 0.0625) / 4 = 0.1875.

    A second sample with a different base rate must give a different reference.
    """
    first = [(0.9, 1), (0.1, 0), (0.2, 0), (0.3, 0)]
    second = [(0.9, 1), (0.1, 1), (0.2, 0), (0.3, 0)]

    assert hindcast.base_rate(first) == 0.25
    assert hindcast.reference_brier_score(first) == pytest.approx(0.1875)
    assert hindcast.base_rate(second) == 0.5
    assert hindcast.reference_brier_score(second) == pytest.approx(0.25)


# V1 reliability bins -------------------------------------------------------------------------------------------

def test_bins_are_equal_width_over_zero_to_one_with_centre_frequency_and_count():
    pairs = [(0.05, 0), (0.05, 0), (0.45, 1), (0.45, 0), (0.95, 1), (1.0, 1)]

    bins = hindcast.reliability_bins(pairs, n_bins=10)

    assert bins == [
        {"p_center": pytest.approx(0.05), "observed_freq": 0.0, "n": 2},
        {"p_center": pytest.approx(0.45), "observed_freq": 0.5, "n": 2},
        {"p_center": pytest.approx(0.95), "observed_freq": 1.0, "n": 2},
    ]


def test_empty_bins_are_dropped_not_zero_filled():
    """A bin with no forecast in it has no observed frequency. Showing it as 0 would be a false statement."""
    bins = hindcast.reliability_bins([(0.05, 0), (0.95, 1)], n_bins=10)

    assert len(bins) == 2
    assert all(entry["n"] > 0 for entry in bins)


def test_the_counts_add_up_to_the_number_of_pairs():
    pairs = [(index / 20, index % 2) for index in range(21)]

    assert sum(entry["n"] for entry in hindcast.reliability_bins(pairs, n_bins=10)) == len(pairs)


def test_ten_pairs_in_one_bin_give_one_populated_bin_with_the_right_frequency():
    """Ten forecasts of 0.72, of which 7 verified: one bin, centre 0.75, observed frequency 0.7."""
    pairs = [(0.72, 1)] * 7 + [(0.72, 0)] * 3

    bins = hindcast.reliability_bins(pairs, n_bins=10)

    assert bins == [{"p_center": pytest.approx(0.75), "observed_freq": pytest.approx(0.7), "n": 10}]


def test_a_probability_on_a_bin_edge_goes_to_the_upper_bin_and_one_goes_to_the_last():
    bins = hindcast.reliability_bins([(0.5, 1), (1.0, 1), (0.0, 0)], n_bins=4)

    assert [(entry["p_center"], entry["n"]) for entry in bins] == [(0.125, 1), (0.625, 1), (0.875, 1)]


# ROC points ----------------------------------------------------------------------------------------------------

def test_roc_points_match_the_hand_contingency_table():
    """Threshold 0.5. Forecast yes when p >= 0.5.

    Pairs: (0.75, 1) hit, (0.5, 0) false alarm, (0.25, 1) miss, (0.0, 0) correct negative, (1.0, 1) hit.
    POD = hits / (hits + misses) = 2 / 3. FAR = false alarms / (false alarms + correct negatives) = 1 / 2.
    """
    pairs = [(0.75, 1), (0.5, 0), (0.25, 1), (0.0, 0), (1.0, 1)]

    points = hindcast.roc_points(pairs, thresholds=[0.5])

    assert points == [{"threshold": 0.5, "pod": pytest.approx(2 / 3), "far": pytest.approx(0.5)}]


def test_roc_points_are_omitted_when_a_rate_is_undefined():
    """With no observed event there is no probability of detection; the point is left out, not set to zero."""
    assert hindcast.roc_points([(0.75, 0), (0.25, 0)], thresholds=[0.5]) == []
