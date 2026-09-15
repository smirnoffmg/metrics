"""Backtest the throughput forecast: forecast from the past, compare with what followed.

Following Fenton and Pfleeger's check of prediction systems: each past forecast
yields u, the probability it gave to an outcome at most what happened. Honest
forecasts spread u evenly over 0..1; the Kolmogorov distance of the u values
from uniform measures how far they are from that.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from functools import cache
from statistics import fmean
from typing import TYPE_CHECKING, Final

import numpy as np

from .calculator import FORECAST_WINDOW_WEEKS, MIN_FORECAST_HISTORY_WEEKS

if TYPE_CHECKING:
    from collections.abc import Callable, Sequence

BACKTEST_HORIZON_WEEKS: Final[int] = 4
BACKTEST_SIMULATIONS: Final[int] = 10_000


@dataclass(frozen=True)
class Backtest:
    """One forecast made at a past Monday and the outcome that followed it."""

    origin: date
    horizon: int
    actual: int
    p50: float
    # the most issues the forecast gave an 85% chance of finishing
    at_least_85: float
    u: float
    crps: float


@dataclass(frozen=True)
class BacktestSummary:
    """How past forecasts held up, taken together."""

    count: int
    held_85: float
    kolmogorov: float
    mean_crps: float


def bootstrap_totals(
    history: Sequence[int],
    horizon: int,
    rng: np.random.Generator,
    window: int = FORECAST_WINDOW_WEEKS,
    simulations: int = BACKTEST_SIMULATIONS,
) -> np.ndarray:
    """Issues finished over the horizon, drawing weeks as the forecast does."""
    samples = np.asarray(history[-window:])
    return rng.choice(samples, size=(simulations, horizon)).sum(axis=1)


def probability_integral(predicted: np.ndarray, actual: int) -> float:
    """Share of predicted outcomes below the actual one, ties counting half."""
    below = np.count_nonzero(predicted < actual)
    ties = np.count_nonzero(predicted == actual)
    return float((below + ties / 2) / len(predicted))


def crps(predicted: np.ndarray, actual: int) -> float:
    """Continuous ranked probability score of simulated outcomes; lower is better.

    E|X - y| - E|X - X'| / 2 (Gneiting and Raftery, 2007): the absolute error
    of a certain forecast, and it rewards spread only where spread was due.
    """
    x = np.sort(predicted.astype(float))
    n = len(x)
    ranks = np.arange(1, n + 1)
    mean_pair_gap = 2 * np.sum((2 * ranks - n - 1) * x) / n**2
    return float(np.mean(np.abs(x - actual)) - mean_pair_gap / 2)


def kolmogorov_distance(us: Sequence[float]) -> float:
    """Largest gap between the u values' distribution and the uniform one."""
    u = np.sort(np.asarray(us, dtype=float))
    n = len(u)
    ranks = np.arange(1, n + 1)
    return float(max(np.max(ranks / n - u), np.max(u - (ranks - 1) / n)))


def backtest_forecast(  # noqa: PLR0913
    throughput_at: Callable[[datetime], dict[str, int]],
    weeks: Sequence[str],
    *,
    horizon: int = BACKTEST_HORIZON_WEEKS,
    min_history: int = MIN_FORECAST_HISTORY_WEEKS,
    predictor: Callable[..., np.ndarray] = bootstrap_totals,
    seed: int | None = None,
) -> list[Backtest]:
    """Forecast from each past Monday with what was known then, and score it.

    throughput_at gives weekly finishes as the report would have shown them at
    a moment; weeks are the complete ISO weeks of the latest data, oldest first.
    The outcome is counted as known at the end of the horizon, so a finish
    reopened before then does not count.
    """
    rng = np.random.default_rng(seed)
    # one origin's horizon end is a later origin: rebuilding a moment is the slow part
    throughput_at = cache(throughput_at)
    mondays = [date.fromisocalendar(int(w[:4]), int(w[5:]), 1) for w in weeks]
    results = []
    # the first week can have started before the query's window, so it is left out
    for i in range(1 + min_history, len(mondays) - horizon + 1):
        origin = mondays[i]
        known = throughput_at(_midnight(origin))
        history = [count for week, count in known.items() if week != weeks[0]]
        if len(history) < min_history:
            continue
        later = throughput_at(_midnight(origin + timedelta(weeks=horizon)))
        actual = sum(later.get(week, 0) for week in weeks[i : i + horizon])
        totals = predictor(history, horizon, rng)
        results.append(
            Backtest(
                origin=origin,
                horizon=horizon,
                actual=actual,
                p50=float(np.percentile(totals, 50)),
                at_least_85=float(np.percentile(totals, 15, method="lower")),
                u=probability_integral(totals, actual),
                crps=crps(totals, actual),
            ),
        )
    return results


def summarize_backtests(results: Sequence[Backtest]) -> BacktestSummary | None:
    """Share of 85% claims that held, distance from honest u values, mean CRPS."""
    if not results:
        return None
    return BacktestSummary(
        count=len(results),
        held_85=fmean(r.actual >= r.at_least_85 for r in results),
        kolmogorov=kolmogorov_distance([r.u for r in results]),
        mean_crps=fmean(r.crps for r in results),
    )


def _midnight(day: date) -> datetime:
    return datetime(day.year, day.month, day.day, tzinfo=UTC)
