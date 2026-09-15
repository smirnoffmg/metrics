"""Tests for backtesting the throughput forecast against what happened next."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

import numpy as np
import pytest

from metrics.services.backtest import (
    Backtest,
    backtest_forecast,
    bootstrap_totals,
    crps,
    kolmogorov_distance,
    probability_integral,
    summarize_backtests,
)

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
    totals = bootstrap_totals([100, 100, 3, 3, 3], horizon=4, rng=rng, window=3)
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
    assert summary.count == 4  # noqa: PLR2004
    assert summary.held_85 == pytest.approx(0.75)
    assert summary.mean_crps == pytest.approx(2.0)
    us = [0.5, 0.1, 0.7, 0.9]
    assert summary.kolmogorov == pytest.approx(kolmogorov_distance(us))


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
