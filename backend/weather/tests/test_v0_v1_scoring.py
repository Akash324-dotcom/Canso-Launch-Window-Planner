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


# Calibration gap and its sampling uncertainty (spec III.4 criterion 2) ---------------------------------------

def test_the_calibration_gap_is_given_under_both_readings_of_predicted():
    """Two forecasts of 0 (one verified) and two of 1 (both verified), ten bins.

    Bin 0.05: mean forecast 0.0, observed 0.5. Gap 0.5 against the mean forecast, 0.45 against the centre.
    Bin 0.95: mean forecast 1.0, observed 1.0. Gap 0.0 against the mean forecast, 0.05 against the centre.
    Mean over the two populated bins: 0.25 and 0.25.
    """
    gaps = hindcast.calibration_gaps([(0.0, 0), (0.0, 1), (1.0, 1), (1.0, 1)], n_bins=10)

    assert gaps == {"mean_forecast": pytest.approx(0.25), "bin_centre": pytest.approx(0.25),
                    "larger": pytest.approx(0.25), "populated_bins": 2}


def test_the_two_readings_differ_when_forecasts_sit_off_the_bin_centres():
    """Four forecasts of 0.5, of which one verified: bin centre 0.55, mean forecast 0.5, observed 0.25."""
    gaps = hindcast.calibration_gaps([(0.5, 1), (0.5, 0), (0.5, 0), (0.5, 0)], n_bins=10)

    assert gaps["mean_forecast"] == pytest.approx(0.25)
    assert gaps["bin_centre"] == pytest.approx(0.30)
    assert gaps["larger"] == pytest.approx(0.30)


def test_the_gap_of_no_pairs_is_undefined():
    with pytest.raises(ValueError):
        hindcast.calibration_gaps([], n_bins=10)


def rows_for(day: str, pairs):
    return [{"valid_date": day, "p": p, "o": o} for p, o in pairs]


def test_blocks_are_runs_of_consecutive_valid_dates_counted_from_the_first():
    """Days 1, 3 and 7 fall in the first seven-day block, day 8 opens the second, day 22 the fourth."""
    rows = (rows_for("2026-05-01", [(0.5, 1)]) + rows_for("2026-05-03", [(0.5, 0), (0.25, 0)])
            + rows_for("2026-05-07", [(1.0, 1)]) + rows_for("2026-05-08", [(0.0, 0)])
            + rows_for("2026-05-22", [(0.75, 1)]))

    blocks = hindcast.valid_date_blocks(rows, block_days=7)

    assert [len(block) for block in blocks] == [4, 1, 1], "an empty block is not a block"
    assert blocks[1] == [(0.0, 0)] and blocks[2] == [(0.75, 1)]


def test_resampling_identical_blocks_gives_the_point_estimate_every_time():
    """Three blocks that hold the same pairs: every resample is the same sample, so the interval has no width."""
    week = [(0.0, 0), (0.0, 1), (1.0, 1), (1.0, 1)]
    rows = rows_for("2026-05-01", week) + rows_for("2026-05-08", week) + rows_for("2026-05-15", week)

    summary = hindcast.bootstrap_calibration_gap(rows, n_bins=10, block_days=7, replicates=50, seed=1,
                                                 bound=0.15, interval=(0.05, 0.95))

    assert summary["blocks"] == 3 and summary["replicates"] == 50
    assert summary["interval"] == [pytest.approx(0.25), pytest.approx(0.25)]
    assert summary["share_at_or_below_bound"] == 0.0


def test_the_share_counts_the_resamples_whose_larger_gap_meets_the_bound():
    """Block A is perfectly calibrated, block B is exactly wrong.

    A resample of two blocks is AA, AB, BA or BB. The larger of the two gap readings is 0.05 for AA (the
    distance of 0 and 1 from the bin centres 0.05 and 0.95), 0.5 for AB and BA, and 1.0 for BB. Only AA meets a
    bound of 0.15, so the share is the fraction of resamples that drew A twice, and the 5th and 95th
    percentiles are the gaps of AA and BB.
    """
    block_a = [(0.0, 0), (0.0, 0), (1.0, 1), (1.0, 1)]
    block_b = [(0.0, 1), (0.0, 1), (1.0, 0), (1.0, 0)]
    rows = rows_for("2026-05-01", block_a) + rows_for("2026-05-08", block_b)

    summary = hindcast.bootstrap_calibration_gap(rows, n_bins=10, block_days=7, replicates=400, seed=7,
                                                 bound=0.15, interval=(0.05, 0.95))

    assert 0.15 < summary["share_at_or_below_bound"] < 0.35, "about one resample in four draws block A twice"
    assert summary["interval"][0] == pytest.approx(0.05) and summary["interval"][1] == pytest.approx(1.0)


def test_the_same_seed_gives_the_same_summary_and_the_seed_decides_the_draw():
    """With one replicate of two blocks the share is 1.0 when block A was drawn twice and 0.0 otherwise.

    The same seed must repeat its answer, and over twenty seeds both answers must occur: the draw comes from
    the seeded generator and from nothing else.
    """
    block_a = [(0.0, 0), (0.0, 0), (1.0, 1), (1.0, 1)]
    block_b = [(0.0, 1), (0.0, 1), (1.0, 0), (1.0, 0)]
    rows = rows_for("2026-05-01", block_a) + rows_for("2026-05-08", block_b)
    settings = dict(n_bins=10, block_days=7, replicates=1, bound=0.15, interval=(0.05, 0.95))

    shares = [hindcast.bootstrap_calibration_gap(rows, seed=seed, **settings)["share_at_or_below_bound"]
              for seed in range(20)]

    assert shares == [hindcast.bootstrap_calibration_gap(rows, seed=seed, **settings)["share_at_or_below_bound"]
                      for seed in range(20)]
    assert set(shares) == {0.0, 1.0}
