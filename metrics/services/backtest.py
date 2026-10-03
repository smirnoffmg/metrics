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
from typing import TYPE_CHECKING, Any, Final, Literal

import numpy as np
from scipy import stats

from .calculator import (
    DEFAULT_PACE,
    MAX_FORECAST_WEEKS,
    MIN_FORECAST_HISTORY_WEEKS,
    Pace,
    burndown,
    pace_draws,
    weekly_throughput,
    weeks_to_clear,
)

if TYPE_CHECKING:
    from collections.abc import Callable, Mapping, Sequence

    from metrics.entity import Issue

BACKTEST_HORIZON_WEEKS: Final[int] = 4
# short horizons alongside the forecast's own: far more outcomes that do not overlap
SHORT_HORIZONS_WEEKS: Final[tuple[int, ...]] = (4, 8)
# paces the forecast may draw from, chosen per team by backtest; on a tie the
# earlier wins, so plain windows go first and recency weights need a real edge
CANDIDATE_PACES: Final[tuple[Pace, ...]] = (
    Pace(window=12),
    Pace(window=26),
    Pace(window=52),
    Pace(half_life=4),
    Pace(half_life=8),
)
# below this, even a far-off share of held promises can be chance
MIN_INDEPENDENT_OUTCOMES: Final[int] = 10
SIGNIFICANCE: Final[float] = 0.05
# past forecasts with known outcomes a recalibration needs before it corrects one
MIN_RECALIBRATION_HISTORY: Final[int] = 10
CRPS_TIE_TOLERANCE: Final[float] = 0.05
BACKTEST_SIMULATIONS: Final[int] = 10_000
# past windows a share of finishes going to already open issues needs before it
# stands in for the next one
MIN_SHARE_WINDOWS: Final[int] = 6
DATE_CHECK_SIMULATIONS: Final[int] = 2_000


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
    # Kolmogorov-Smirnov p-values over independent forecasts: u-plot for a
    # consistent bias, y-plot for errors drifting over time; None if untestable
    bias_p: float | None = None
    trend_p: float | None = None
    held_independent: int = 0


@dataclass(frozen=True)
class DateCheck:
    """A clear date promised at a past Monday and when the list it covered cleared.

    The list cleared once none of its issues was open, done or dropped; None
    for either date when the promise was beyond the cap or the data.
    """

    origin: date
    promised: date | None
    cleared_on: date | None


@dataclass(frozen=True)
class DateSummary:
    """How many past clear dates held, among those due and independent."""

    held: int
    judged: int
    not_due: int


@dataclass(frozen=True)
class ScopeResult:
    """A forecast query's forecast and, when paced by its own finishes, its replay.

    basis is "assumed" when the scope is paced by a share of the team's
    throughput, which nothing replays: runs and open_work are empty then.
    """

    forecast: dict[str, Any]
    open_work: dict[str, Any]
    runs: dict[int, list[Backtest]]
    dates: DateSummary | None
    basis: Literal["measured", "assumed"]


@dataclass(frozen=True)
class Moment:
    """What Jira showed at one moment: weekly finishes, open and done issues."""

    throughput: dict[str, int]
    open_keys: frozenset[str]
    done_keys: frozenset[str]


def moment_of(issues: Sequence[Issue], at: datetime) -> Moment:
    """Keep what the open-work backtest needs of issues as they were at a moment."""
    return Moment(
        throughput=weekly_throughput(issues, now=at),
        open_keys=frozenset(issue.key for issue in issues if issue.is_open),
        done_keys=frozenset(issue.key for issue in issues if issue.was_done),
    )


def window_share(start: Moment, end: Moment, weeks: Sequence[str]) -> float | None:
    """Share of the window's finishes that went to issues open at its start.

    Both counts are as known at the window's end, so an issue reopened by then
    counts in neither. None when nothing was finished.
    """
    finished = sum(end.throughput.get(week, 0) for week in weeks)
    if finished == 0:
        return None
    return min(1.0, len(start.open_keys & end.done_keys) / finished)


def past_shares(
    moment_at: Callable[[datetime], Moment],
    weeks: Sequence[str],
    *,
    until: int,
    horizon: int,
) -> list[float]:
    """Shares of finishes going to open issues in windows ending by weeks[until]."""
    return [
        share
        for share in _window_shares(moment_at, weeks, until=until, horizon=horizon)
        if share is not None
    ]


def _window_shares(
    moment_at: Callable[[datetime], Moment],
    weeks: Sequence[str],
    *,
    until: int,
    horizon: int,
) -> list[float | None]:
    if not weeks:
        return []
    first = _monday(weeks[0])
    # the first week can have started before the query's window, so it is left out
    return [
        window_share(
            moment_at(_midnight(first + timedelta(weeks=j))),
            moment_at(_midnight(first + timedelta(weeks=j + horizon))),
            weeks[j : j + horizon],
        )
        for j in range(1, until - horizon + 1)
    ]


def bootstrap_totals(
    history: Sequence[int],
    horizon: int,
    rng: np.random.Generator,
    pace: Pace = DEFAULT_PACE,
    simulations: int = BACKTEST_SIMULATIONS,
) -> np.ndarray:
    """Issues finished over the horizon, drawing weeks as the forecast does."""
    samples, chances = pace_draws(history, pace)
    return rng.choice(samples, size=(simulations, horizon), p=chances).sum(axis=1)


def open_work_totals(  # noqa: PLR0913
    n_open: int,
    history: Sequence[int],
    shares: Sequence[float],
    horizon: int,
    rng: np.random.Generator,
    *,
    pace: Pace,
    simulations: int = BACKTEST_SIMULATIONS,
) -> np.ndarray:
    """Issues of an open list done over the horizon, as the forecast simulates them."""
    done = burndown(
        n_open,
        history,
        rng,
        weeks=horizon,
        pace=pace,
        shares=shares,
        simulations=simulations,
    )
    return done[:, horizon - 1]


def forecast_open_work(  # noqa: PLR0913
    n_open: int,
    history: Sequence[int],
    shares: Sequence[float],
    *,
    horizon: int,
    pace: Pace,
    past_us: Sequence[float] | None,
    now: datetime,
    seed: int | None = None,
) -> dict[str, Any]:
    """How many of the open issues get done over the horizon, as the backtest replays.

    past_us, raw u values of past open-work forecasts over the same horizon,
    recalibrate it when given.
    """
    totals = open_work_totals(
        n_open,
        history,
        shares,
        horizon,
        np.random.default_rng(seed),
        pace=pace,
    )
    if past_us is not None:
        totals = recalibrate(totals, past_us)
    return {
        "horizon": horizon,
        "n_open": n_open,
        "p50": float(np.percentile(totals, 50)),
        "at_least_85": float(np.percentile(totals, 15, method="lower")),
        "by_date": (now + timedelta(weeks=horizon)).date(),
        "share": float(np.median(shares)),
        "recalibrated": past_us is not None,
    }


def recalibrate(totals: np.ndarray, past_us: Sequence[float]) -> np.ndarray:
    """Correct simulated outcomes by the u-plot of past forecasts: F*(x) = G(F(x)).

    Fenton and Pfleeger's recalibration: each quantile level q of the corrected
    forecast is the raw forecast's quantile at G's inverse of q, G being the
    distribution of past u values, joined up between them. Unlike their PLR,
    CRPS needs no smoothing of it. A correction cannot reach past the raw
    simulations: outcomes beyond all of them only pile up at the extremes.
    """
    levels = (np.arange(len(totals)) + 0.5) / len(totals)
    return np.quantile(totals, np.quantile(np.asarray(past_us, dtype=float), levels))


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


def trend_values(
    us: Sequence[float],
    simulations: int = BACKTEST_SIMULATIONS,
) -> np.ndarray:
    """Y-plot points: u values in forecast order, turned into shares of a running sum.

    With honest forecasts -ln(1 - u) behaves like independent exponential gaps,
    whose normalised running sums spread evenly over 0..1 (Brocklehurst and
    Littlewood); a drift in u bunches them. An outcome above every simulation
    has u = 1, kept finite at half a simulation below it.
    """
    u = np.clip(np.asarray(us, dtype=float), 0, 1 - 0.5 / simulations)
    x = -np.log1p(-u)
    return np.cumsum(x)[:-1] / x.sum()


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
    recalibrate_after: int | None = None,
) -> list[Backtest]:
    """Forecast from each past Monday with what was known then, and score it.

    throughput_at gives weekly finishes as the report would have shown them at
    a moment; weeks are the complete ISO weeks of the latest data, oldest first.
    The outcome is counted as known at the end of the horizon, so a finish
    reopened before then does not count. With recalibrate_after, a forecast is
    recalibrated once that many raw forecasts had their outcomes known by its
    Monday, from their raw u values only.
    """
    rng = np.random.default_rng(seed)
    # one origin's horizon end is a later origin: rebuilding a moment is the slow part
    throughput_at = cache(throughput_at)
    mondays = [date.fromisocalendar(int(w[:4]), int(w[5:]), 1) for w in weeks]
    results = []
    raw_us: list[tuple[date, float]] = []
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
        known_on = origin + timedelta(weeks=horizon)
        raw_us.append((known_on, probability_integral(totals, actual)))
        past_us = [u for on, u in raw_us[:-1] if on <= origin]
        if recalibrate_after is not None and len(past_us) >= recalibrate_after:
            totals = recalibrate(totals, past_us)
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


def backtest_open_work(  # noqa: PLR0913
    moment_at: Callable[[datetime], Moment],
    weeks: Sequence[str],
    *,
    horizon: int,
    pace: Pace,
    min_history: int = MIN_FORECAST_HISTORY_WEEKS,
    min_shares: int = MIN_SHARE_WINDOWS,
    assume_share: float | None = None,
    seed: int | None = None,
    recalibrate_after: int | None = None,
) -> list[Backtest]:
    """Forecast from each past Monday how many of the issues open then get done.

    Throughput is scaled by past shares of finishes that went to issues
    already open, from windows that ended by the Monday; assume_share replaces
    them, 1.0 being the old belief that all throughput goes to the open list.
    Origins without min_shares such windows are skipped either way, so a
    baseline replays the same Mondays. Recalibration as in backtest_forecast.
    """
    rng = np.random.default_rng(seed)
    moment_at = cache(moment_at)
    mondays = [_monday(week) for week in weeks]
    shares_by_window = _window_shares(
        moment_at, weeks, until=len(weeks), horizon=horizon
    )
    results = []
    raw_us: list[tuple[date, float]] = []
    for i in range(1 + min_history, len(mondays) - horizon + 1):
        origin = mondays[i]
        known = moment_at(_midnight(origin))
        history = [
            count for week, count in known.throughput.items() if week != weeks[0]
        ]
        shares = [s for s in shares_by_window[: max(0, i - horizon)] if s is not None]
        if len(history) < min_history or len(shares) < min_shares:
            continue
        later = moment_at(_midnight(origin + timedelta(weeks=horizon)))
        actual = len(known.open_keys & later.done_keys)
        totals = open_work_totals(
            len(known.open_keys),
            history,
            shares if assume_share is None else (assume_share,),
            horizon,
            rng,
            pace=pace,
        )
        known_on = origin + timedelta(weeks=horizon)
        raw_us.append((known_on, probability_integral(totals, actual)))
        past_us = [u for on, u in raw_us[:-1] if on <= origin]
        if recalibrate_after is not None and len(past_us) >= recalibrate_after:
            totals = recalibrate(totals, past_us)
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


def date_checks(  # noqa: PLR0913
    moment_at: Callable[[datetime], Moment],
    weeks: Sequence[str],
    *,
    horizon: int,
    pace: Pace,
    min_history: int = MIN_FORECAST_HISTORY_WEEKS,
    min_shares: int = MIN_SHARE_WINDOWS,
    max_weeks: int = MAX_FORECAST_WEEKS,
    seed: int | None = None,
    simulations: int = DATE_CHECK_SIMULATIONS,
) -> list[DateCheck]:
    """Promise from each past Monday when all issues open then are cleared, and check.

    The promise is the forecast's 85% clear date with shares from horizon-week
    windows that ended by the Monday, as the forecast takes them today; the
    list is checked at each later Monday the data reaches.
    """
    rng = np.random.default_rng(seed)
    moment_at = cache(moment_at)
    mondays = [_monday(week) for week in weeks]
    shares_by_window = _window_shares(
        moment_at, weeks, until=len(weeks), horizon=horizon
    )
    checks = []
    for i in range(1 + min_history, len(mondays)):
        origin = mondays[i]
        known = moment_at(_midnight(origin))
        history = [
            count for week, count in known.throughput.items() if week != weeks[0]
        ]
        shares = [s for s in shares_by_window[: max(0, i - horizon)] if s is not None]
        n_open = len(known.open_keys)
        if len(history) < min_history or len(shares) < min_shares or n_open == 0:
            continue
        done = burndown(
            n_open,
            history,
            rng,
            weeks=max_weeks,
            pace=pace,
            shares=shares,
            simulations=simulations,
        )
        p85 = float(np.percentile(weeks_to_clear(done, n_open), 85))
        checks.append(
            DateCheck(
                origin=origin,
                promised=origin + timedelta(weeks=p85) if p85 <= max_weeks else None,
                cleared_on=_cleared_on(moment_at, known.open_keys, origin, mondays),
            ),
        )
    return checks


def _cleared_on(
    moment_at: Callable[[datetime], Moment],
    keys: frozenset[str],
    origin: date,
    mondays: Sequence[date],
) -> date | None:
    # the data reaches the Monday after its last complete week
    for k in range(1, (mondays[-1] - origin).days // 7 + 2):
        day = origin + timedelta(weeks=k)
        if keys.isdisjoint(moment_at(_midnight(day)).open_keys):
            return day
    return None


def summarize_date_checks(checks: Sequence[DateCheck], last: date) -> DateSummary:
    """Held clear dates among those due by last whose intervals do not overlap.

    A list fed by new work may never empty, so a promise counts only once its
    date has passed; a promise beyond the cap is never due.
    """
    due = [c for c in checks if c.promised is not None and c.promised <= last]
    picked: list[DateCheck] = []
    free_from = date.min
    for check in sorted(due, key=lambda c: c.origin):
        if check.origin >= free_from and check.promised is not None:
            picked.append(check)
            free_from = check.promised
    return DateSummary(
        held=sum(
            c.cleared_on is not None
            and c.promised is not None
            and c.cleared_on <= c.promised
            for c in picked
        ),
        judged=len(picked),
        not_due=len(checks) - len(due),
    )


def backtest_paces(
    throughput_at: Callable[[datetime], dict[str, int]],
    weeks: Sequence[str],
    *,
    paces: Sequence[Pace] = CANDIDATE_PACES,
    horizons: Sequence[int] = SHORT_HORIZONS_WEEKS,
    seed: int | None = None,
) -> dict[Pace, dict[int, list[Backtest]]]:
    """Backtest the forecast drawing at each pace, over each horizon."""
    throughput_at = cache(throughput_at)
    return {
        pace: {
            horizon: backtest_forecast(
                throughput_at,
                weeks,
                horizon=horizon,
                predictor=partial(bootstrap_totals, pace=pace),
                seed=seed,
            )
            for horizon in horizons
        }
        for pace in paces
    }


def choose_pace(
    by_pace: Mapping[Pace, Sequence[BacktestSummary]],
    default: Pace = DEFAULT_PACE,
    min_independent: int = MIN_INDEPENDENT_OUTCOMES,
) -> Pace:
    """First pace scoring about the best CRPS at the longest judgeable horizon.

    Long horizons are where the forecast's promise lives, but a week apart
    they share most outcomes; without enough independent ones anywhere, the
    default stays. Paces within CRPS_TIE_TOLERANCE of the best count as a tie,
    broken toward the earlier candidate: a sliver of CRPS is noise, not a
    reason for a year-old pace or a more elaborate one.
    """
    horizons = {s.horizon for summaries in by_pace.values() for s in summaries}
    for horizon in sorted(horizons, reverse=True):
        scores = {
            pace: s.mean_crps
            for pace, summaries in by_pace.items()
            for s in summaries
            if s.horizon == horizon and s.independent >= min_independent
        }
        if len(scores) == len(by_pace):
            best = min(scores.values())
            return next(
                pace
                for pace, score in scores.items()
                if score <= best * (1 + CRPS_TIE_TOLERANCE)
            )
    return default


def judgeable_summaries(
    summaries: Sequence[BacktestSummary],
    min_independent: int = MIN_INDEPENDENT_OUTCOMES,
) -> list[BacktestSummary]:
    """Horizons with enough independent outcomes to test for bias and drift."""
    return [
        s
        for s in summaries
        if s.independent >= min_independent
        and s.bias_p is not None
        and s.trend_p is not None
    ]


def steady_bias(summaries: Sequence[BacktestSummary]) -> bool:
    """Whether past errors are biased without drifting, the case recalibration fits.

    Fenton and Pfleeger's first step: errors must be about stationary, so any
    tested horizon drifting rules it out.
    """
    tested = judgeable_summaries(summaries)
    return (
        bool(tested)
        and all((s.trend_p or 0.0) >= SIGNIFICANCE for s in tested)
        and any((s.bias_p or 1.0) < SIGNIFICANCE for s in tested)
    )


def recalibration_helps(raw: BacktestSummary, recalibrated: BacktestSummary) -> bool:
    """Whether recalibrated forecasts scored better overall than raw ones.

    A better u-plot alone is not enough: Fenton and Pfleeger also want the
    recalibrated forecasts to win on a global score, their prequential
    likelihood, for which CRPS stands in here.
    """
    return recalibrated.mean_crps < raw.mean_crps


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
    picked = independent_forecasts(results)
    independent = [r.u for r in picked]
    return BacktestSummary(
        horizon=results[0].horizon,
        count=len(results),
        independent=len(independent),
        held_85=fmean(r.actual >= r.at_least_85 for r in results),
        kolmogorov=kolmogorov_distance([r.u for r in results]),
        mean_crps=fmean(r.crps for r in results),
        bias_p=float(stats.kstest(independent, "uniform").pvalue),
        # with every u at 0 the Y-plot divides by a zero sum: drift is untestable
        trend_p=float(stats.kstest(trend_values(independent), "uniform").pvalue)
        if len(independent) > 1 and any(independent)
        else None,
        held_independent=sum(r.actual >= r.at_least_85 for r in picked),
    )


def independent_forecasts(results: Sequence[Backtest]) -> list[Backtest]:
    """Most forecasts whose horizons do not overlap: overlapping ones share outcomes.

    The u- and y-plot tests assume independent u values, which forecasts a
    week apart over longer horizons are not.
    """
    picked: list[Backtest] = []
    free_from = date.min
    for result in sorted(results, key=lambda r: r.origin):
        if result.origin >= free_from:
            picked.append(result)
            free_from = result.origin + timedelta(weeks=result.horizon)
    return picked


def _monday(week: str) -> date:
    return date.fromisocalendar(int(week[:4]), int(week[5:]), 1)


def _midnight(day: date) -> datetime:
    return datetime(day.year, day.month, day.day, tzinfo=UTC)
