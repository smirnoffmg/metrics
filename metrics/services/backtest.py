"""Backtest the throughput forecast: forecast from the past, compare with what followed.

Following Fenton and Pfleeger's check of prediction systems: each past forecast
yields u, the probability it gave to an outcome at most what happened. Honest
forecasts spread u evenly over 0..1; the Kolmogorov distance of the u values
from uniform measures how far they are from that.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from functools import cache, partial
from statistics import fmean
from typing import TYPE_CHECKING, Final

import numpy as np

from .calculator import FORECAST_WINDOW_WEEKS, MIN_FORECAST_HISTORY_WEEKS

if TYPE_CHECKING:
    from collections.abc import Callable, Mapping, Sequence

BACKTEST_HORIZON_WEEKS: Final[int] = 4
# short horizons alongside the forecast's own: far more outcomes that do not overlap
SHORT_HORIZONS_WEEKS: Final[tuple[int, ...]] = (4, 8)
# windows of recent weeks the forecast may draw from, chosen per team by backtest
CANDIDATE_WINDOWS_WEEKS: Final[tuple[int, ...]] = (12, 26, 52)
# below this, even a far-off share of held promises can be chance
MIN_INDEPENDENT_OUTCOMES: Final[int] = 10
CRPS_TIE_TOLERANCE: Final[float] = 0.05
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

    horizon: int
    count: int
    # forecasts that can be picked with no outcome week in common
    independent: int
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


def backtest_windows(
    throughput_at: Callable[[datetime], dict[str, int]],
    weeks: Sequence[str],
    *,
    windows: Sequence[int] = CANDIDATE_WINDOWS_WEEKS,
    horizons: Sequence[int] = SHORT_HORIZONS_WEEKS,
    seed: int | None = None,
) -> dict[int, dict[int, list[Backtest]]]:
    """Backtest the forecast drawing from each window, over each horizon."""
    throughput_at = cache(throughput_at)
    return {
        window: {
            horizon: backtest_forecast(
                throughput_at,
                weeks,
                horizon=horizon,
                predictor=partial(bootstrap_totals, window=window),
                seed=seed,
            )
            for horizon in horizons
        }
        for window in windows
    }


def choose_window(
    by_window: Mapping[int, Sequence[BacktestSummary]],
    default: int = FORECAST_WINDOW_WEEKS,
    min_independent: int = MIN_INDEPENDENT_OUTCOMES,
) -> int:
    """Shortest window scoring about the best CRPS at the longest judgeable horizon.

    Long horizons are where the forecast's promise lives, but a week apart
    they share most outcomes; without enough independent ones anywhere, the
    default stays. Windows within CRPS_TIE_TOLERANCE of the best count as a
    tie, broken toward recent pace: a sliver of CRPS is noise, not a reason
    to forecast from a year-old pace.
    """
    horizons = {s.horizon for summaries in by_window.values() for s in summaries}
    for horizon in sorted(horizons, reverse=True):
        scores = {
            window: s.mean_crps
            for window, summaries in by_window.items()
            for s in summaries
            if s.horizon == horizon and s.independent >= min_independent
        }
        if len(scores) == len(by_window):
            best = min(scores.values())
            return min(
                window
                for window, score in scores.items()
                if score <= best * (1 + CRPS_TIE_TOLERANCE)
            )
    return default


def judged_summary(
    summaries: Sequence[BacktestSummary],
    min_independent: int = MIN_INDEPENDENT_OUTCOMES,
) -> BacktestSummary | None:
    """Pick the longest horizon enough independent outcomes judge, else the longest.

    The forecast's own horizon is usually too long for a verdict, while a
    shorter one can already show that its promises fail.
    """
    judged = [s for s in summaries if s.independent >= min_independent]
    return max(judged or summaries, key=lambda s: s.horizon, default=None)


def summarize_backtests(results: Sequence[Backtest]) -> BacktestSummary | None:
    """Share of 85% claims that held, distance from honest u values, mean CRPS."""
    if not results:
        return None
    return BacktestSummary(
        horizon=results[0].horizon,
        count=len(results),
        independent=_independent(results),
        held_85=fmean(r.actual >= r.at_least_85 for r in results),
        kolmogorov=kolmogorov_distance([r.u for r in results]),
        mean_crps=fmean(r.crps for r in results),
    )


def _independent(results: Sequence[Backtest]) -> int:
    """Most forecasts whose horizons do not overlap: overlapping ones share outcomes."""
    count = 0
    free_from = date.min
    for result in sorted(results, key=lambda r: r.origin):
        if result.origin >= free_from:
            count += 1
            free_from = result.origin + timedelta(weeks=result.horizon)
    return count


def _midnight(day: date) -> datetime:
    return datetime(day.year, day.month, day.day, tzinfo=UTC)
