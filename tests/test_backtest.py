"""Tests for backtesting the throughput forecast against what happened next."""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, date, datetime, timedelta
from statistics import fmean

import numpy as np
import pytest

from metrics.services.backtest import (
    Backtest,
    BacktestSummary,
    backtest_forecast,
    backtest_paces,
    bootstrap_totals,
    choose_pace,
    crps,
    judged_summary,
    kolmogorov_distance,
    probability_integral,
    recalibrate,
    recalibration_helps,
    steady_bias,
    summarize_backtests,
    trend_values,
)
from metrics.services.calculator import Pace

MONDAY = date(2024, 1, 1)


def _week_key(monday: date) -> str:
    return monday.strftime("%GW%V")


def _throughput_known_at(weekly: list[int]):
    """Weekly counts that never change once a week is over, from MONDAY on."""

    def known_at(at: datetime) -> dict[str, int]:
        return {
            _week_key(MONDAY + timedelta(weeks=i)): count
            for i, count in enumerate(weekly)
            if MONDAY + timedelta(weeks=i + 1) <= at.date()
        }

    return known_at


def test_bootstrap_totals_sum_horizon_draws_from_recent_weeks():
    rng = np.random.default_rng(0)
    totals = bootstrap_totals([100, 100, 3, 3, 3], 4, rng, pace=Pace(window=3))
    assert set(totals) == {12}


def test_probability_integral_counts_ties_as_half():
    predicted = np.array([1, 2, 2, 3])
    assert probability_integral(predicted, 2) == pytest.approx(0.5)
    assert probability_integral(predicted, 0) == 0.0
    assert probability_integral(predicted, 9) == 1.0


def test_crps_of_a_certain_forecast_is_the_absolute_error():
    assert crps(np.array([5, 5, 5]), 8) == pytest.approx(3.0)


def test_crps_rewards_spread_that_covers_the_outcome():
    # E|X - y| - E|X - X'| / 2 for X uniform on {0, 10}: 5 - 2.5
    assert crps(np.array([0, 10]), 5) == pytest.approx(2.5)


def test_kolmogorov_distance_is_the_largest_gap_from_uniform():
    assert kolmogorov_distance([0.5]) == pytest.approx(0.5)
    assert kolmogorov_distance([0.9, 0.95, 0.99]) == pytest.approx(0.9)


def test_backtest_starts_once_enough_history_and_ends_when_outcomes_run_out():
    weekly = [2] * 12
    weeks = [_week_key(MONDAY + timedelta(weeks=i)) for i in range(12)]
    results = backtest_forecast(
        _throughput_known_at(weekly),
        weeks,
        horizon=4,
        min_history=6,
        seed=1,
    )
    # the first week is skipped as possibly partial: origins at weeks 7 and 8
    assert [r.origin for r in results] == [
        MONDAY + timedelta(weeks=7),
        MONDAY + timedelta(weeks=8),
    ]
    assert all(r.actual == 8 for r in results)  # noqa: PLR2004
    assert all(r.at_least_85 == 8 for r in results)  # noqa: PLR2004


def test_backtest_forecasts_only_from_what_was_known_at_the_origin():
    weekly = [9, 1, 1, 1, 1, 1, 1, 1, 5, 5, 5]
    weeks = [_week_key(MONDAY + timedelta(weeks=i)) for i in range(len(weekly))]
    [result] = backtest_forecast(
        _throughput_known_at(weekly),
        weeks,
        horizon=3,
        min_history=7,
        seed=1,
    )
    assert result.origin == MONDAY + timedelta(weeks=8)
    assert result.p50 == 3  # noqa: PLR2004
    assert result.actual == 15  # noqa: PLR2004
    assert result.u == 1.0


def test_backtest_counts_outcomes_as_known_at_the_end_of_the_horizon():
    weeks = [_week_key(MONDAY + timedelta(weeks=i)) for i in range(9)]
    horizon_end = MONDAY + timedelta(weeks=9)

    def known_at(at: datetime) -> dict[str, int]:
        # week 8 had 4 finishes, but one was reopened by the end of the horizon
        counts = dict.fromkeys(weeks[:8], 1)
        if at.date() >= horizon_end:
            counts[weeks[8]] = 3
        return counts

    [result] = backtest_forecast(known_at, weeks, horizon=1, min_history=7, seed=1)
    assert result.actual == 3  # noqa: PLR2004


def _backtest(u: float, actual: int, at_least_85: int, score: float) -> Backtest:
    return Backtest(
        origin=MONDAY,
        horizon=4,
        actual=actual,
        p50=actual,
        at_least_85=at_least_85,
        u=u,
        crps=score,
    )


def test_summary_reports_how_often_the_85_percent_claim_held():
    summary = summarize_backtests(
        [
            _backtest(0.5, actual=10, at_least_85=8, score=1.0),
            _backtest(0.1, actual=5, at_least_85=8, score=3.0),
            _backtest(0.7, actual=8, at_least_85=8, score=2.0),
            _backtest(0.9, actual=12, at_least_85=8, score=2.0),
        ],
    )
    assert summary.horizon == 4  # noqa: PLR2004
    assert summary.count == 4  # noqa: PLR2004
    assert summary.held_85 == pytest.approx(0.75)
    assert summary.mean_crps == pytest.approx(2.0)
    us = [0.5, 0.1, 0.7, 0.9]
    assert summary.kolmogorov == pytest.approx(kolmogorov_distance(us))


def test_summary_counts_forecasts_whose_outcomes_do_not_overlap():
    weeks = [0, 1, 2, 3, 4, 5, 6, 7, 8, 12]
    results = [
        replace(_backtest(0.5, 1, 1, 1.0), origin=MONDAY + timedelta(weeks=w))
        for w in weeks
    ]
    summary = summarize_backtests(results)
    assert summary is not None
    # 4-week outcomes from weeks 0, 4, 8 and 12 share no week
    assert summary.independent == 4  # noqa: PLR2004


def test_summary_of_no_backtests_is_none():
    assert summarize_backtests([]) is None


def test_backtest_asks_for_each_moment_once():
    weekly = [2] * 20
    weeks = [_week_key(MONDAY + timedelta(weeks=i)) for i in range(20)]
    known_at = _throughput_known_at(weekly)
    asked = []

    def counting(at: datetime) -> dict[str, int]:
        asked.append(at)
        return known_at(at)

    backtest_forecast(counting, weeks, horizon=4, min_history=6, seed=1)
    assert len(asked) == len(set(asked))


def test_backtest_origins_are_utc_mondays():
    seen = []

    def known_at(at: datetime) -> dict[str, int]:
        seen.append(at)
        return {}

    weeks = [_week_key(MONDAY + timedelta(weeks=i)) for i in range(9)]
    backtest_forecast(known_at, weeks, horizon=1, min_history=7, seed=1)
    assert seen[0] == datetime(2024, 2, 26, tzinfo=UTC)


def _scored(horizon: int, independent: int, crps_mean: float) -> BacktestSummary:
    return BacktestSummary(
        horizon=horizon,
        count=50,
        independent=independent,
        held_85=0.85,
        kolmogorov=0.1,
        mean_crps=crps_mean,
    )


W12, W26, W52 = Pace(window=12), Pace(window=26), Pace(window=52)
HALF_LIFE_4 = Pace(half_life=4)


def test_choose_pace_by_crps_at_the_longest_horizon_with_enough_evidence():
    by_pace = {
        W12: [_scored(4, 24, 50.0), _scored(8, 12, 95.0)],
        W52: [_scored(4, 24, 55.0), _scored(8, 12, 63.0)],
    }
    assert choose_pace(by_pace, default=W12, min_independent=10) == W52


def test_choose_pace_falls_back_to_a_shorter_horizon():
    by_pace = {
        W12: [_scored(4, 24, 50.0), _scored(8, 9, 95.0)],
        W52: [_scored(4, 24, 55.0), _scored(8, 9, 63.0)],
    }
    assert choose_pace(by_pace, default=W26, min_independent=10) == W12


def test_choose_pace_keeps_the_default_without_enough_evidence():
    by_pace = {W12: [_scored(4, 3, 50.0)], W52: [_scored(4, 3, 40.0)]}
    assert choose_pace(by_pace, default=W12, min_independent=10) == W12


def test_choose_pace_needs_every_pace_scored_at_the_horizon():
    by_pace = {W12: [_scored(8, 12, 95.0)], W52: []}
    assert choose_pace(by_pace, default=W26, min_independent=10) == W26


def test_backtest_paces_replays_each_pace_over_each_horizon():
    weekly = [2] * 30
    weeks = [_week_key(MONDAY + timedelta(weeks=i)) for i in range(30)]
    runs = backtest_paces(
        _throughput_known_at(weekly),
        weeks,
        paces=(W12, HALF_LIFE_4),
        horizons=(4, 8),
        seed=1,
    )
    assert list(runs) == [W12, HALF_LIFE_4]
    assert sorted(runs[W12]) == [4, 8]
    assert all(r.actual == 8 for r in runs[HALF_LIFE_4][4])  # noqa: PLR2004


def test_choose_pace_breaks_a_tie_toward_the_earlier_candidate():
    by_pace = {
        W12: [_scored(8, 12, 116.8)],
        W26: [_scored(8, 12, 103.3)],
        W52: [_scored(8, 12, 102.1)],
        HALF_LIFE_4: [_scored(8, 12, 101.2)],
    }
    assert choose_pace(by_pace, default=W12, min_independent=10) == W26


def test_choose_pace_takes_a_weighted_pace_with_a_real_edge():
    by_pace = {W12: [_scored(8, 12, 48.6)], HALF_LIFE_4: [_scored(8, 12, 44.8)]}
    assert choose_pace(by_pace, default=W12, min_independent=10) == HALF_LIFE_4


def test_judged_summary_is_the_longest_horizon_with_enough_evidence():
    summaries = [_scored(4, 24, 22.9), _scored(8, 12, 48.6), _scored(41, 2, 398.6)]
    judged = judged_summary(summaries, min_independent=10)
    assert judged is not None
    assert judged.horizon == 8  # noqa: PLR2004


def test_judged_summary_falls_back_to_the_longest_horizon():
    summaries = [_scored(4, 6, 22.9), _scored(30, 1, 398.6)]
    judged = judged_summary(summaries, min_independent=10)
    assert judged is not None
    assert judged.horizon == 30  # noqa: PLR2004


def test_judged_summary_of_nothing_is_none():
    assert judged_summary([]) is None


def test_trend_values_match_the_y_plot_of_the_handbook():
    # Lyu, Handbook of Software Reliability Engineering, tables 4.3 and 4.4
    us = [0.650, 0.652, 0.451, 0.518, 0.395, 0.358, 0.394, 0.289, 0.249]
    expected = [0.191, 0.382, 0.491, 0.624, 0.714, 0.795, 0.886, 0.948]
    assert trend_values(us) == pytest.approx(expected, abs=0.002)


def test_trend_values_survive_an_outcome_above_every_simulation():
    values = trend_values([0.5, 1.0, 0.5])
    assert np.all(np.isfinite(values))


def _in_time(us: list[float], horizon: int = 1) -> list[Backtest]:
    return [
        replace(
            _backtest(u, actual=1, at_least_85=1, score=1.0),
            origin=MONDAY + timedelta(weeks=i),
            horizon=horizon,
        )
        for i, u in enumerate(us)
    ]


def test_summary_finds_drift_the_u_plot_averages_away():
    rising = [i / 21 for i in range(1, 21)]
    summary = summarize_backtests(_in_time(rising))
    assert summary is not None
    assert summary.bias_p is not None
    assert summary.bias_p > 0.5  # noqa: PLR2004
    assert summary.trend_p is not None
    assert summary.trend_p < 0.05  # noqa: PLR2004


def test_summary_tests_only_forecasts_whose_outcomes_do_not_overlap():
    # every other forecast overlaps the one before: only the 0.9s are independent
    us = [0.9, 0.1] * 10
    summary = summarize_backtests(_in_time(us, horizon=2))
    assert summary is not None
    assert summary.independent == 10  # noqa: PLR2004
    assert summary.bias_p is not None
    assert summary.bias_p < 0.01  # noqa: PLR2004


def test_summary_of_one_outcome_has_no_trend_test():
    summary = summarize_backtests(_in_time([0.5]))
    assert summary is not None
    assert summary.trend_p is None


def test_recalibrate_to_honest_past_errors_keeps_the_forecast():
    raw = np.arange(1, 101)
    past = [(k + 0.5) / 50 for k in range(50)]
    assert np.percentile(recalibrate(raw, past), [15, 50, 85]) == pytest.approx(
        np.percentile(raw, [15, 50, 85]),
        abs=1.5,
    )


def test_recalibrate_after_optimistic_forecasts_lowers_the_forecast():
    raw = np.arange(1, 101)
    optimistic = [0.1, 0.2, 0.15, 0.3, 0.05]
    assert np.median(recalibrate(raw, optimistic)) < np.median(raw)


def test_recalibrate_cannot_reach_past_the_raw_simulations():
    raw = np.arange(10, 21)
    assert set(recalibrate(raw, [0.0, 0.0, 0.0])) == {10}


def _always_too_high(_history, horizon, rng):
    return rng.integers(3, 7, size=10_000) * horizon


def test_backtest_recalibrates_from_forecasts_whose_outcomes_were_known():
    weekly = [2] * 20
    weeks = [_week_key(MONDAY + timedelta(weeks=i)) for i in range(20)]
    known_at = _throughput_known_at(weekly)
    raw = backtest_forecast(
        known_at,
        weeks,
        horizon=2,
        min_history=6,
        predictor=_always_too_high,
        seed=1,
    )
    corrected = backtest_forecast(
        known_at,
        weeks,
        horizon=2,
        min_history=6,
        predictor=_always_too_high,
        seed=1,
        recalibrate_after=3,
    )
    # a 2-week forecast is known two Mondays later: the fifth has three behind it
    assert [r.p50 for r in corrected[:4]] == [r.p50 for r in raw[:4]]
    assert all(r.p50 >= 8 for r in raw)  # noqa: PLR2004
    assert all(r.p50 == 6 for r in corrected[4:])  # noqa: PLR2004
    assert fmean(r.crps for r in corrected[4:]) < fmean(r.crps for r in raw[4:])


def test_steady_bias_needs_bias_without_drift_at_every_tested_horizon():
    def tested(bias_p: float, trend_p: float, independent: int = 12) -> BacktestSummary:
        return replace(_scored(8, independent, 50.0), bias_p=bias_p, trend_p=trend_p)

    assert steady_bias([tested(0.01, 0.3), tested(0.2, 0.4)])
    assert not steady_bias([tested(0.01, 0.3), tested(0.2, 0.01)])
    assert not steady_bias([tested(0.4, 0.3)])
    assert not steady_bias([tested(0.01, 0.3, independent=3)])


def test_recalibration_helps_only_with_a_lower_crps():
    raw = _scored(8, 10, 37.6)
    assert not recalibration_helps(raw, _scored(8, 10, 40.2))
    assert recalibration_helps(raw, _scored(8, 10, 35.0))
