"""Headline stat tiles and stuck-ticket rows for the report."""

from __future__ import annotations

from dataclasses import dataclass
from statistics import fmean, median
from typing import TYPE_CHECKING, Any, Literal

from scipy import stats

from .backtest import (
    MIN_INDEPENDENT_OUTCOMES,
    SIGNIFICANCE,
    judgeable_summaries,
    recalibration_helps,
)
from .calculator import MIN_FORECAST_HISTORY_WEEKS

if TYPE_CHECKING:
    from collections.abc import Sequence

    import pandas as pd

    from .backtest import BacktestSummary, DateSummary, ScopeResult
    from .calculator import BacklogFlow

CLAIMED_CHANCE = 0.85
# A week's arrivals and finishes vary by several issues, so a smaller gap
# between their averages is not evidence that either side is ahead.
FLOW_NOISE = 0.1


@dataclass(frozen=True)
class Tile:
    """One headline number for the report hero row."""

    label: str
    value: str
    delta_text: str | None = None
    delta_good: bool | None = None


@dataclass(frozen=True)
class Trust:
    """How far past promises like the forecast's came true, in plain words."""

    word: Literal["holds", "optimistic", "unchecked"]
    held: int
    of: int


@dataclass(frozen=True)
class StuckRow:
    """One open issue for the stuck-tickets action table."""

    key: str
    status: str
    age_days: float
    url: str


def _cycle_tile(scatter: pd.DataFrame) -> Tile:
    label = "Cycle time p50"
    if scatter.empty:
        return Tile(label, "n/a")
    current, previous = _split_halves(scatter)
    value = float(current["cycle_time_days"].quantile(0.5))
    if previous.empty or current.empty:
        return Tile(label, f"{value:.1f}d")
    delta = value - float(previous["cycle_time_days"].quantile(0.5))
    if delta == 0:
        return Tile(label, f"{value:.1f}d")
    arrow = "↓" if delta < 0 else "↑"
    # lower cycle time is the good direction
    return Tile(label, f"{value:.1f}d", f"{arrow} {abs(delta):.1f}d", delta < 0)


def _split_halves(scatter: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    start = scatter["finished_at"].min()
    end = scatter["finished_at"].max()
    midpoint = start + (end - start) / 2
    current = scatter[scatter["finished_at"] >= midpoint]
    previous = scatter[scatter["finished_at"] < midpoint]
    return current, previous


def _forecast_tile(forecast: dict[str, Any], label: str) -> Tile:
    if not forecast:
        return Tile(label, "n/a")
    if forecast["p85_date"] is None:
        return Tile(label, "not within 2 years")
    return Tile(label, f"by {forecast['p85_date']:%d %b %Y}")


def _throughput_tile(throughput: dict[str, int]) -> Tile:
    label = "Throughput"
    if not throughput:
        return Tile(label, "n/a")
    values = list(throughput.values())
    half = len(values) // 2
    current = values[half:]
    value = fmean(current)
    if half < 2:  # noqa: PLR2004
        return Tile(label, f"{value:.1f}/wk")
    delta = value - fmean(values[:half])
    if delta == 0:
        return Tile(label, f"{value:.1f}/wk")
    arrow = "↑" if delta > 0 else "↓"
    # higher throughput is the good direction
    return Tile(label, f"{value:.1f}/wk", f"{arrow} {abs(delta):.1f}", delta > 0)


def build_headline_tiles(  # noqa: PLR0913
    scatter: pd.DataFrame,
    aging: pd.DataFrame,
    open_work: dict[str, Any],
    forecast: dict[str, Any],
    throughput: dict[str, int],
    flow_efficiency: float,
    *,
    backtest: Tile | None = None,
    scope_tile: Tile | None = None,
    flow: BacklogFlow | None = None,
) -> list[Tile]:
    """Build the report hero row; scope_tile is None without a forecast query."""
    n_open = open_work.get("n_open", forecast.get("backlog", 0))
    return [
        open_work_tile(open_work),
        backtest if backtest is not None else backtest_tile(None),
        clear_date_tile(forecast, n_open),
        *([scope_tile] if scope_tile is not None else []),
        flow_tile(flow),
        _cycle_tile(scatter),
        Tile("Work in progress", str(len(aging))),
        _throughput_tile(throughput),
        Tile("Flow efficiency", f"{flow_efficiency:.0%}"),
    ]


def open_work_tile(open_work: dict[str, Any]) -> Tile:
    """How many of the open issues get done over the backtested horizon."""
    if not open_work:
        return Tile("open issues done (85% chance)", "n/a")
    label = (
        f"of {open_work['n_open']} open issues done"
        f" in {open_work['horizon']} weeks (85% chance)"
    )
    if open_work["recalibrated"]:
        label = f"{label}, recalibrated"
    return Tile(label, f"≥ {open_work['at_least_85']:.0f}")


def clear_date_tile(forecast: dict[str, Any], n_open: int) -> Tile:
    """When every issue open now is done, which may be beyond the simulated years."""
    label = (
        f"all {n_open} open issues done (85% chance)"
        if n_open
        else "all open issues done (85% chance)"
    )
    return _forecast_tile(forecast, label)


def flow_tile(flow: BacklogFlow | None) -> Tile:
    """Issues arriving against issues finished a week.

    It says nothing of the open list's direction: discarded issues leave it too,
    and they are not among the finishes.
    """
    label = "Arrivals and finishes"
    if flow is None:
        return Tile(label, "n/a")
    value = f"{flow.arrived:.1f} in / {flow.finished:.1f} done per week"
    if abs(flow.net) < FLOW_NOISE * flow.finished:
        return Tile(label, value)
    behind = flow.net > 0
    return Tile(
        label,
        value,
        "more arrive than get done" if behind else "more get done than arrive",
        not behind,
    )


def scope_forecast_tile(
    forecast: dict[str, Any],
    open_count: int,
    total: int,
    *,
    note: str | None = None,
) -> Tile:
    """Headline tile for the forecast query's issues; note says what it rests on."""
    label = f"all {total} issues of the scope done (85% chance)"
    if open_count == 0:
        return Tile(label, "all done")
    tile = _forecast_tile(forecast, label)
    return Tile(tile.label, tile.value, note)


def backtest_tile(summary: BacktestSummary | None) -> Tile:
    """How many past promises over the horizon came true, of those not overlapping."""
    if summary is None:
        return Tile("past promises held", "n/a")
    label = f"past {summary.horizon}-week promises held"
    value = f"{summary.held_independent} of {summary.independent}"
    if summary.independent < MIN_INDEPENDENT_OUTCOMES:
        return Tile(label, value, f"only {summary.independent} independent outcomes")
    held = _held_as_promised(summary.held_independent, summary.independent)
    return Tile(
        label,
        value,
        "as promised" if held else "fewer than promised",
        held,
    )


def trust(summary: BacktestSummary | None) -> Trust:
    """Judge past promises held among those not overlapping, as backtest_tile does."""
    if summary is None:
        return Trust("unchecked", 0, 0)
    held, of = summary.held_independent, summary.independent
    if of < MIN_INDEPENDENT_OUTCOMES:
        return Trust("unchecked", held, of)
    return Trust("holds" if _held_as_promised(held, of) else "optimistic", held, of)


def _held_as_promised(held: int, of: int) -> bool:
    # an honest 85% promise scores 9 or fewer of 11 about half the time, so only
    # a share too low to be chance shows the forecast is optimistic
    return bool(stats.binom.cdf(held, of, CLAIMED_CHANCE) >= SIGNIFICANCE)


def forecast_verdict(  # noqa: PLR0913
    open_work: dict[str, Any],
    forecast: dict[str, Any],
    trust: Trust,
    flow: BacklogFlow | None,
    dates: DateSummary | None,
    release: Sequence[str] = (),
) -> list[str]:
    """Say what to expect of the open issues, how far to trust it and what to do.

    Natural frequencies ("held 17 of 20 times") rather than percentages, and
    an action last, so the page answers whether to act before any chart.
    The release's lines go just before the action.
    """
    if not open_work or not forecast:
        # the first week may start before the query's window and is left out
        return [
            "No forecast: no open issues, or fewer than"
            f" {MIN_FORECAST_HISTORY_WEEKS + 1} weeks of finished work.",
            *release,
        ]
    verdict = [
        f"At least {open_work['at_least_85']:.0f} of the {open_work['n_open']}"
        f" open issues will be done in {open_work['horizon']} weeks,"
        f" by {open_work['by_date']:%d %b %Y} (85% chance).",
        _trust_sentence(trust, open_work["horizon"]),
    ]
    behind = (
        flow is not None and flow.net > 0 and flow.net >= FLOW_NOISE * flow.finished
    )
    if flow is not None:
        verdict.append(
            f"About {flow.arrived:.1f} issues arrive and {flow.finished:.1f}"
            " get done a week" + ("; more arrive than get done." if behind else "."),
        )
    verdict.append(_clear_date_sentence(forecast, dates))
    verdict += release
    action = _ACTIONS[trust.word]
    if behind or forecast["p85_date"] is None:
        action = f"{action[:-1]}, but don't promise a date for all of it" + (
            "." if release else "; scope a release with --forecast-jql."
        )
    verdict.append(action)
    return verdict


_ACTIONS: dict[str, str] = {
    "holds": "Commit to the number.",
    "optimistic": "Treat the number as optimistic and commit to fewer.",
    "unchecked": "Treat the number as a guess until more history builds up.",
}


def _trust_sentence(trust: Trust, horizon: int) -> str:
    if trust.word == "holds":
        return (
            f"Past {horizon}-week promises like this one"
            f" held {trust.held} of {trust.of} times,"
            " in line with the 85% promised."
        )
    if trust.word == "optimistic":
        return (
            f"Past {horizon}-week promises like this one held only"
            f" {trust.held} of {trust.of} times, fewer than the 85% promised."
        )
    return (
        f"There is too little history to check it: {trust.of} past"
        f" {horizon}-week promises could be replayed without overlap."
    )


def _clear_date_sentence(
    forecast: dict[str, Any],
    dates: DateSummary | None,
    issues: str = "open issues",
) -> str:
    if forecast["p85_date"] is None:
        sentence = (
            f"Not all {forecast['backlog']} {issues} will be done"
            " within 2 years at this pace"
        )
    else:
        sentence = (
            f"All {forecast['backlog']} {issues} done"
            f" by {forecast['p85_date']:%d %b %Y} (85% chance)"
        )
    if dates is not None and dates.judged >= MIN_INDEPENDENT_OUTCOMES:
        return f"{sentence}; past dates like it held {dates.held} of {dates.judged}."
    if dates is not None and dates.judged:
        return (
            f"{sentence}; only {dates.judged} past date"
            f"{'' if dates.judged == 1 else 's'} like it"
            f" {'has' if dates.judged == 1 else 'have'} come due, too few to check it."
        )
    # beyond the checked horizon nothing replays the date, and it leans optimistic
    return f"{sentence}; no past date like it has come due to check it."


def scope_verdict(jql: str, scope: ScopeResult, trust: Trust) -> list[str]:
    """Say when the release a forecast query names gets done, and what that rests on."""
    forecast = scope.forecast
    if not forecast:
        return [f"Release {jql}: nothing left to forecast, or too little history."]
    open_work = scope.open_work
    if scope.basis == "measured" and open_work:
        # the trust is earned by replaying the H-week promise, so it must follow
        # that promise; the clear date gets its own, separate check
        return [
            f"Release {jql}: at least {open_work['at_least_85']:.0f} of its"
            f" {open_work['n_open']} open issues done in {open_work['horizon']}"
            f" weeks, by {open_work['by_date']:%d %b %Y} (85% chance),"
            " paced by its own finishes.",
            _trust_sentence(trust, open_work["horizon"]),
            _clear_date_sentence(forecast, scope.dates, "of its open issues"),
        ]
    when = (
        "not within 2 years"
        if forecast["p85_date"] is None
        else f"by {forecast['p85_date']:%d %b %Y}"
    )
    return [
        f"Release {jql}: all {forecast['backlog']} open issues done {when}"
        " (85% chance), at an assumed share of the team's time.",
        "That share is not checked against the past.",
    ]


def diagnose_backtest(summaries: Sequence[BacktestSummary]) -> str:
    """Say whether past forecast errors drift or keep a steady bias, drift first.

    Fenton and Pfleeger recalibrate forecasts from past errors only when those
    errors are stationary, so drift at any horizon with enough independent
    outcomes rules correction out; a short horizon's test has the most of them.
    """
    tested = judgeable_summaries(summaries)
    if not tested:
        return "Too few independent outcomes to test forecast errors for bias or drift."
    drift = min(tested, key=lambda s: s.trend_p or 0.0)
    bias = min(tested, key=lambda s: s.bias_p or 0.0)
    horizons = _horizons(tested)
    if drift.trend_p is not None and drift.trend_p < SIGNIFICANCE:
        return (
            f"{drift.horizon}-week forecast errors drift over time"
            f" (y-plot p = {drift.trend_p:.3f}): the team's pace changes,"
            " so correcting forecasts by their past errors would not hold."
        )
    if bias.bias_p is not None and bias.bias_p < SIGNIFICANCE:
        return (
            f"{bias.horizon}-week forecasts err the same way throughout"
            f" (u-plot p = {bias.bias_p:.3f}), with no sign of drift at {horizons}:"
            " the case for recalibrating them by past errors."
        )
    return (
        f"No sign that forecasts over {horizons} are biased or drift over time"
        f" (lowest u-plot p = {bias.bias_p:.3f},"
        f" lowest y-plot p = {drift.trend_p:.3f})."
    )


def recalibration_note(raw: BacktestSummary, recalibrated: BacktestSummary) -> str:
    """Say what recalibrating past forecasts did, and whether the forecast is."""
    helps = recalibration_helps(raw, recalibrated)
    score = "and scored a better" if helps else "but scored a worse"
    return (
        f"Recalibrated by their past errors, {raw.horizon}-week forecasts kept"
        f" {recalibrated.held_85:.0%} of their 85% promises instead of"
        f" {raw.held_85:.0%} {score} CRPS"
        f" ({recalibrated.mean_crps:.1f} against {raw.mean_crps:.1f}),"
        f" so the forecast is {'' if helps else 'not '}recalibrated."
    )


def date_check_note(summary: DateSummary) -> str:
    """Say how past clear-date promises held, or that none has fallen due."""
    if summary.judged:
        return (
            f"Clear dates: held {summary.held} of {summary.judged} independent"
            f" past promises; {summary.not_due} not yet due."
        )
    if summary.not_due:
        return (
            f"Clear dates: 0 judged; all {summary.not_due} past promises"
            " fall beyond the data so far."
        )
    return "Clear dates: too little history to replay past promises."


def _horizons(summaries: Sequence[BacktestSummary]) -> str:
    weeks = [str(s.horizon) for s in sorted(summaries, key=lambda s: s.horizon)]
    listed = weeks[0] if len(weeks) == 1 else f"{', '.join(weeks[:-1])} or {weeks[-1]}"
    return f"{listed} weeks"


def build_stuck_rows(
    aging: pd.DataFrame,
    server_url: str,
    limit: int = 10,
) -> list[StuckRow]:
    """Top in-progress issues by age in current status, linked to Jira."""
    if aging.empty:
        return []
    base = server_url.rstrip("/")
    ordered = aging.sort_values("age_days", ascending=False).head(limit)
    return [
        StuckRow(
            key=str(row.key),
            status=str(row.status),
            age_days=round(float(row.age_days), 1),  # type: ignore[arg-type]
            url=f"{base}/browse/{row.key}",
        )
        for row in ordered.itertuples()
    ]


def build_delivery_tiles(
    weekly: dict[str, int],
    lead_times: pd.DataFrame,
    failure_rate: float | None,
    recovery_days: list[float],
) -> list[Tile]:
    """Build DORA's four keys as headline tiles."""
    lead = lead_times["lead_time_days"]
    return [
        Tile("Deploys", f"{fmean(weekly.values()):.1f}/wk" if weekly else "n/a"),
        Tile(
            "Change lead time p50",
            f"{float(lead.quantile(0.5)):.1f}d" if len(lead) else "n/a",
        ),
        Tile(
            "Change fail rate",
            f"{failure_rate:.0%}" if failure_rate is not None else "n/a",
        ),
        Tile(
            "Recovery time p50",
            f"{median(recovery_days):.1f}d" if recovery_days else "no failures",
        ),
    ]
