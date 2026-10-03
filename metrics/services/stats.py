"""Headline stat tiles and stuck-ticket rows for the report."""

from __future__ import annotations

from dataclasses import dataclass, replace
from statistics import fmean, median
from typing import TYPE_CHECKING, Any, Literal

from scipy import stats

from .backtest import (
    MIN_INDEPENDENT_OUTCOMES,
    SIGNIFICANCE,
    judgeable_summaries,
    judged_summary,
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
BULK_CLOSURE_FACTOR = 5


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

    word: Literal["holds", "optimistic", "cautious", "unchecked"]
    held: int
    of: int
    # set when a shorter replayed horizon than the forecast's judged it
    horizon: int | None = None


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


def build_headline_tiles(  # noqa: PLR0913
    scatter: pd.DataFrame,
    aging: pd.DataFrame,
    open_work: dict[str, Any],
    forecast: dict[str, Any],
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
    if flow is None:
        return Tile("Arrivals and finishes", "n/a")
    label = "Arrivals and finishes" + (f", {flow.pace.label}" if flow.pace else "")
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
    scope: ScopeResult,
    open_count: int,
    total: int,
    *,
    note: str | None = None,
) -> Tile:
    """Headline tile for the forecast query's issues; note says what it rests on.

    Paced by its own finishes, it promises a count as the team's tile does;
    stragglers can push out the date all of them are done, so it comes second.
    """
    if open_count == 0:
        return Tile(f"none of its {total} issues open", "Release done")
    if scope.why_not:
        return Tile(f"{_open_issues(open_count)} of the scope", "n/a", scope.why_not)
    open_work = scope.open_work
    if not open_work:
        label = f"all {_open_issues(open_count)} of the scope done (85% chance)"
        tile = _forecast_tile(scope.forecast, label)
        return Tile(tile.label, tile.value, note)
    forecast = scope.forecast
    all_done = (
        "not all within 2 years"
        if forecast["p85_date"] is None
        else f"all by {forecast['p85_date']:%d %b %Y}"
    )
    if scope.created_after_start:
        all_done += f"; {scope.created_after_start} created after its first finish"
    return Tile(
        f"of {_open_issues(open_work['n_open'])} of the scope done"
        f" in {open_work['horizon']} weeks (85% chance)",
        f"≥ {open_work['at_least_85']:.0f}",
        all_done,
    )


def backtest_tile(
    summary: BacktestSummary | None,
    summaries: Sequence[BacktestSummary] = (),
) -> Tile:
    """How many past promises came true, of those not overlapping.

    It reads the horizon heeded_trust judges by, as the verdict does, so a
    shorter horizon that rejects the forecast is the one shown.
    """
    if summary is None:
        return Tile("past promises held", "n/a")
    heeded = heeded_trust(summary, summaries)
    label = f"past {heeded.horizon or summary.horizon}-week promises held"
    value = f"{heeded.held} of {heeded.of}"
    word = heeded.word
    if word == "optimistic":
        return Tile(label, value, "fewer than promised", delta_good=False)
    if word == "cautious":
        return Tile(label, value, "more than promised")
    if word == "unchecked":
        return Tile(label, value, f"only {heeded.of} independent outcomes")
    return Tile(label, value, "as promised", delta_good=True)


def trust(summary: BacktestSummary | None) -> Trust:
    """Judge past promises held among those not overlapping, as backtest_tile does.

    A share held too far from 85% to be chance rejects the promise at any
    count, but confirming it takes MIN_INDEPENDENT_OUTCOMES.
    """
    if summary is None:
        return Trust("unchecked", 0, 0)
    held, of = summary.held_independent, summary.independent
    if not _held_as_promised(held, of):
        return Trust("optimistic", held, of)
    if _held_beyond_promise(held, of):
        return Trust("cautious", held, of)
    if of < MIN_INDEPENDENT_OUTCOMES:
        return Trust("unchecked", held, of)
    return Trust("holds", held, of)


def heeded_trust(
    judged: BacktestSummary | None,
    summaries: Sequence[BacktestSummary],
) -> Trust:
    """Trust at the judged horizon, unless a shorter one of the same model rejects it.

    The judged horizon may have too few outcomes to say anything, while a
    shorter one already shows its promises failing beyond chance.
    """
    judged_trust = trust(judged)
    if judged is None or judged_trust.word == "optimistic":
        return judged_trust
    shorter = sorted(
        (s for s in summaries if s.horizon < judged.horizon),
        key=lambda s: s.horizon,
        reverse=True,
    )
    for summary in shorter:
        if (found := trust(summary)).word == "optimistic":
            return replace(found, horizon=summary.horizon)
    return judged_trust


def _held_as_promised(held: int, of: int) -> bool:
    # an honest 85% promise scores 9 or fewer of 11 about half the time, so only
    # a share too low to be chance shows the forecast is optimistic
    return bool(stats.binom.cdf(held, of, CLAIMED_CHANCE) >= SIGNIFICANCE)


def _held_beyond_promise(held: int, of: int) -> bool:
    # the other tail: 55 of 55 is not "as promised" but a number set too low;
    # it takes 19 outcomes before even all of them held can be told from chance
    return bool(stats.binom.sf(held - 1, of, CLAIMED_CHANCE) < SIGNIFICANCE)


def forecast_verdict(  # noqa: PLR0913
    open_work: dict[str, Any],
    forecast: dict[str, Any],
    trust: Trust,
    flow: BacklogFlow | None,
    dates: DateSummary | None,
    release: Sequence[str] = (),
    *,
    release_trust: Trust | None = None,
    release_at_least: float | None = None,
) -> list[str]:
    """Say what to expect of the open issues, how far to trust it and what to do.

    Natural frequencies ("held 17 of 20 times") rather than percentages, and
    an action last, so the page answers whether to act before any chart.
    The release's lines go just before the action, which also heeds the
    release's own trust and number when it was paced by its own finishes.
    """
    if not open_work or not forecast:
        # the first week may start before the query's window and is left out
        return [
            "No forecast: no open issues, or fewer than"
            f" {MIN_FORECAST_HISTORY_WEEKS + 1} weeks of finished work.",
            *release,
        ]
    promise = (
        f"At least {open_work['at_least_85']:.0f} of the {open_work['n_open']}"
        " open issues will be done"
        if open_work["at_least_85"]
        else f"None of the {open_work['n_open']} open issues can be promised done"
    )
    verdict = [
        f"{promise} in {open_work['horizon']} weeks,"
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
    if not open_work["at_least_85"]:
        verdict.append(
            "Don't commit to a number or a date yet:"
            " the forecast cannot promise any of the open issues.",
        )
        return verdict
    action = _ACTIONS[trust.word]
    # a release with no number of its own has none to treat as optimistic
    if (
        release_at_least
        and release_trust is not None
        and release_trust.word == "optimistic"
    ):
        action = (
            "Treat the release's number as optimistic"
            " and commit to fewer of its issues."
        )
    if behind or forecast["p85_date"] is None:
        action = f"{action[:-1]}, but don't promise a date for all of it" + (
            "."
            if release
            else "; forecast a specific release instead (--forecast-jql)."
        )
    verdict.append(action)
    if release_at_least == 0:
        verdict.append(
            "For the release, don't commit to a number or a date yet:"
            " the forecast cannot promise any of its issues.",
        )
    return verdict


_ACTIONS: dict[str, str] = {
    "holds": "Commit to the number.",
    "optimistic": "Treat the number as optimistic and commit to fewer.",
    "cautious": "Commit to the number and expect more.",
    "unchecked": "Treat the number as a guess until more history builds up.",
}


def _trust_sentence(trust: Trust, horizon: int) -> str:
    if trust.horizon is not None and trust.horizon != horizon:
        return (
            f"Past {trust.horizon}-week promises of this forecast held only"
            f" {trust.held} of {trust.of} times, fewer than the 85% promised."
        )
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
    if trust.word == "cautious":
        return (
            f"Past {horizon}-week promises like this one held {trust.held}"
            f" of {trust.of} times, more than the 85% promised:"
            " the number is cautious."
        )
    return (
        f"There is too little history to check it: {trust.of} past"
        f" {horizon}-week {_plural(trust.of, 'promise')} could be replayed"
        " without overlap."
    )


def _clear_date_sentence(
    forecast: dict[str, Any],
    dates: DateSummary | None,
    whose: str = "",
) -> str:
    n = forecast["backlog"]
    if n == 1 and forecast["p85_date"] is None:
        sentence = "The 1 open issue will not be done within 2 years at this pace"
    elif n == 1:
        sentence = (
            f"The 1 open issue done by {forecast['p85_date']:%d %b %Y} (85% chance)"
        )
    elif forecast["p85_date"] is None:
        sentence = (
            f"Not all {n} {whose}open issues will be done within 2 years at this pace"
        )
    else:
        sentence = (
            f"All {n} {whose}open issues done"
            f" by {forecast['p85_date']:%d %b %Y} (85% chance)"
        )
    if dates is not None and not _held_as_promised(dates.held, dates.judged):
        return (
            f"{sentence}; past dates like it held only {dates.held}"
            f" of {dates.judged}, fewer than the 85% promised."
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


def promised_done(open_work: dict[str, Any], whose: str = "") -> str:
    """At least how many of the open issues get done, or that none can be promised.

    whose, such as "its ", goes before the count of open issues.
    """
    n = open_work["n_open"]
    if n == 1:
        verb = "done" if open_work["at_least_85"] else "cannot be promised done"
        return f"the 1 open issue {verb}"
    if not open_work["at_least_85"]:
        return f"none of {whose}{n} open issues can be promised done"
    return f"at least {open_work['at_least_85']:.0f} of {whose}{n} open issues done"


def assumed_pace_note(focus: float) -> str:
    """Say what a scope forecast not paced by its own finishes rests on."""
    return f"at an assumed {focus:.0%} of the team's pace, not checked"


def scope_verdict(  # noqa: PLR0913
    jql: str,
    scope: ScopeResult,
    trust: Trust,
    focus: float | None = None,
    *,
    open_count: int,
    total: int,
) -> list[str]:
    """Say when the release a forecast query names gets done, and what that rests on.

    focus is the share of the team's pace assumed for the release, if given;
    open_count and total count its issues open now and all of them.
    """
    if open_count == 0:
        return [f"Release {jql} done: none of its {total} issues open."]
    forecast = scope.forecast
    if scope.why_not or not forecast:
        return [f"Release {jql}: {scope.why_not or 'too little history'}."]
    open_work = scope.open_work
    if scope.basis == "measured" and open_work:
        # the trust is earned by replaying the H-week promise, so it must follow
        # that promise; the clear date gets its own, separate check
        verdict = [
            f"Release {jql}: {promised_done(open_work, 'its ')} in"
            f" {open_work['horizon']} weeks, by {open_work['by_date']:%d %b %Y}"
            " (85% chance), paced by its own finishes.",
            _trust_sentence(trust, open_work["horizon"]),
            _clear_date_sentence(forecast, scope.dates, "of its "),
        ]
        if scope.created_after_start:
            verdict.append(
                f"{scope.created_after_start} of its {total} issues were created"
                " after its first finish.",
            )
        return verdict
    done = (
        f"not all {_open_issues(forecast['backlog'])} done within 2 years"
        if forecast["p85_date"] is None
        else f"all {_open_issues(forecast['backlog'])} done"
        f" by {forecast['p85_date']:%d %b %Y}"
    )
    return [f"Release {jql}: {done} (85% chance), {assumed_pace_note(focus or 1.0)}."]


def _open_issues(n: int) -> str:
    return f"{n} open {_plural(n, 'issue')}"


def _plural(n: int, word: str) -> str:
    return word if n == 1 else f"{word}s"


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
        judged = judged_summary(summaries)
        # the verdict reads the judged horizon, so its own test must show too
        also = (
            f"; at {judged.horizon} weeks, the horizon judged,"
            f" y-plot p = {judged.trend_p:.3f}"
            if judged is not None
            and judged.horizon != drift.horizon
            and judged.trend_p is not None
            else ""
        )
        return (
            f"{drift.horizon}-week forecast errors drift over time"
            f" (y-plot p = {drift.trend_p:.3f}{also}): the team's pace changes,"
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
    """Say how past clear-date promises held, and why the others were not judged.

    A promise past the cap never falls due, while one not yet due still may.
    """
    unjudged = [
        *([f"{summary.not_due} not yet due"] if summary.not_due else []),
        *(
            [f"{summary.beyond_cap} past the 2-year cap and never due"]
            if summary.beyond_cap
            else []
        ),
    ]
    rest = f"; {', '.join(unjudged)}." if unjudged else "."
    if summary.judged:
        return (
            f"Clear dates: held {summary.held} of {summary.judged} independent"
            f" past {_plural(summary.judged, 'promise')}{rest}"
        )
    if unjudged:
        total = summary.not_due + summary.beyond_cap
        return (
            f"Clear dates: none of {total} past {_plural(total, 'promise')}"
            f" judged{rest}"
        )
    return "Clear dates: too little history to replay past promises."


def unmeasured_share_note(open_work: dict[str, Any], subject: str) -> str | None:
    """Say the forecast assumed all finishes go to the open issues, if it did."""
    if not open_work or open_work.get("share_measured", True):
        return None
    return (
        f"share of finishes going to {subject} not measured"
        f" (too few past {open_work['horizon']}-week windows); assuming all of them"
    )


def bulk_closure_note(
    throughput: dict[str, int],
    delivered: dict[str, int],
) -> str | None:
    """Name the biggest week finishing over BULK_CLOSURE_FACTOR times the median.

    delivered counts each week's finishes resolved as delivery: when most of
    the week's are, it was a release batch-close, and discarding its
    resolution would drop real work.
    """
    typical = median(throughput.values()) if throughput else 0
    if not typical:
        return None
    bulk = sorted(
        (count, week)
        for week, count in throughput.items()
        if count > BULK_CLOSURE_FACTOR * typical
    )
    if not bulk:
        return None
    count, week = bulk[-1]
    more = len(bulk) - 1
    also = f" ({more} more such week{'s' if more > 1 else ''})" if more else ""
    spike = (
        f"Bulk closure: {week} finished {count} issues, over {BULK_CLOSURE_FACTOR}"
        f" times the median week's {typical:g}{also}"
    )
    if 2 * delivered.get(week, 0) > count:
        return (
            f"{spike}; most were resolved as delivered, so a release closed in"
            " one week inflates the pace."
        )
    return (
        f"{spike}; it inflates the pace. If these were not delivered, add their"
        " resolution to --discarded-resolutions."
    )


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
