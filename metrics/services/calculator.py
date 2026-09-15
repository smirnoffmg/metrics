"""Metric functions for Jira issue analytics."""

from __future__ import annotations

from collections import Counter, defaultdict
from datetime import UTC, date, datetime, timedelta
from statistics import fmean
from typing import TYPE_CHECKING, Final

import numpy as np
import pandas as pd

from metrics.consts import (
    ACTIVE_STATUSES,
    ONE_DAY,
    ONE_HOUR,
    TESTING_STATUSES,
)

if TYPE_CHECKING:
    from collections.abc import Sequence
    from typing import Any

    from metrics.entity import Issue

MIN_FORECAST_HISTORY_WEEKS: Final[int] = 6
# A quarter of weekly throughput: long enough to smooth single weeks, short
# enough that a team's pace from years ago doesn't forecast today's backlog.
FORECAST_WINDOW_WEEKS: Final[int] = 12
CFD_MAX_DAILY_SPAN: Final[int] = 180


def cycle_times(issues: Sequence[Issue], timeslot: int = ONE_DAY) -> list[float]:
    """Cycle time of each done issue in whole timeslots, at least one."""
    return [
        max(1, issue.cycle_time.total_seconds() // timeslot)
        for issue in issues
        if issue.cycle_time
    ]


def lead_times(issues: Sequence[Issue], timeslot: int = ONE_DAY) -> list[float]:
    """Lead time of each done issue in whole timeslots, at least one."""
    return [
        max(1, issue.lead_time.total_seconds() // timeslot)
        for issue in issues
        if issue.lead_time
    ]


def queue_times(
    issues: Sequence[Issue],
    timeslot: int = ONE_DAY,
) -> dict[str, list[float]]:
    """Time spent in each status, per status, in whole timeslots."""
    tmp: dict[str, list[float]] = defaultdict(list)
    for issue in issues:
        for status, td in issue.statuses_x_periods.items():
            tmp[status].append(max(1, td.total_seconds() // timeslot))
    return dict(tmp)


def weekly_throughput(
    issues: Sequence[Issue],
    now: datetime | None = None,
) -> dict[str, int]:
    """Count issues completed per finished ISO week, up to the one before now.

    The current week is left out, since a partial week reads as a slump;
    weeks with no completions up to now count as zero.
    """
    finished = [
        issue.last_finish_status_at.date()
        for issue in issues
        if issue.last_finish_status_at
    ]
    return weekly_counts(finished, now)


def weekly_counts(days: list[date], now: datetime | None = None) -> dict[str, int]:
    """Count days per finished ISO week, from the first up to the week before now."""
    now = now or datetime.now(tz=UTC)
    current_week = _week_start(now.date())
    counts: dict[str, int] = defaultdict(int)
    counted = []
    for day in days:
        if _week_start(day) < current_week:
            counts[day.strftime("%GW%V")] += 1
            counted.append(day)
    if not counts:
        return {}

    week = _week_start(min(counted))
    result: dict[str, int] = {}
    while week < current_week:
        key = week.strftime("%GW%V")
        result[key] = counts.get(key, 0)
        week += timedelta(weeks=1)
    return result


def _week_start(day: date) -> date:
    return date.fromisocalendar(*day.isocalendar()[:2], 1)


def median_queue_hours(
    issues: Sequence[Issue],
    timeslot: int = ONE_HOUR,
    limit: int = 1000,
) -> pd.DataFrame:
    """Median time spent in each status, with how many periods it covers."""
    tmp: dict[str, list[float]] = defaultdict(list)
    for issue in issues:
        for status, td in issue.statuses_x_periods.items():
            period_in_status = max(1, td.total_seconds() // timeslot)
            if period_in_status == 1 or period_in_status > limit:
                continue
            tmp[status].append(period_in_status)
    res = pd.DataFrame(columns=["status", "median_hours", "count"])
    res["status"] = list(tmp.keys())
    res["median_hours"] = [np.median(periods) for periods in tmp.values()]
    res["count"] = [len(periods) for periods in tmp.values()]
    return res


def cycle_time_points(issues: Sequence[Issue]) -> pd.DataFrame:
    """Return finished_at x uncapped cycle time in days per done issue."""
    rows = [
        (
            issue.key,
            issue.last_finish_status_at,
            issue.cycle_time.total_seconds() / ONE_DAY,
        )
        for issue in issues
        if issue.cycle_time is not None
    ]
    return pd.DataFrame(rows, columns=["key", "finished_at", "cycle_time_days"])


def monte_carlo_forecast(  # noqa: PLR0913
    issues: Sequence[Issue],
    throughput: dict[str, int],
    simulations: int = 10_000,
    seed: int | None = None,
    now: datetime | None = None,
    focus: float = 1.0,
    window: int = FORECAST_WINDOW_WEEKS,
) -> dict[str, Any]:
    """Simulate clearing the open issues; empty dict when data is insufficient.

    focus is the share of the team's throughput spent on these issues: a
    release worked on alongside everything else gets only part of it.
    window is how many recent weeks of throughput the simulation draws from.
    """
    if not 0 < focus <= 1:
        msg = f"focus must be in (0, 1], got {focus}"
        raise ValueError(msg)
    now = now or datetime.now(tz=UTC)
    weekly = list(throughput.values())
    samples = np.array(weekly[-window:], dtype=float) * focus
    backlog = sum(1 for issue in issues if issue.is_open)
    if backlog == 0 or len(samples) < MIN_FORECAST_HISTORY_WEEKS or samples.sum() == 0:
        return {}
    rng = np.random.default_rng(seed)
    weeks = np.zeros(simulations, dtype=np.int64)
    remaining = np.full(simulations, float(backlog))
    active = remaining > 0
    while active.any():
        remaining[active] -= rng.choice(samples, size=int(active.sum()))
        weeks[active] += 1
        active = remaining > 0
    result: dict[str, Any] = {
        "weeks": weeks,
        "backlog": backlog,
        "focus": focus,
        "window": window,
    }
    for pct in (50, 85, 95):
        value = float(np.percentile(weeks, pct))
        result[f"p{pct}"] = value
        result[f"p{pct}_date"] = (now + timedelta(weeks=value)).date()
    return result


def aging_wip(issues: Sequence[Issue], now: datetime | None = None) -> pd.DataFrame:
    """Return key/status/age_days/p85_days per started, unfinished issue."""
    now = now or datetime.now(tz=UTC)
    history: dict[str, list[float]] = defaultdict(list)
    rows = []
    for issue in issues:
        if issue.was_done:
            for status, td in issue.statuses_x_periods.items():
                history[status].append(td.total_seconds() / ONE_DAY)
        if not issue.is_open or issue.started_at is None:
            continue
        since = (
            issue.status_transitions[-1].at
            if issue.status_transitions
            else issue.created_at
        )
        age_days = (now - since).total_seconds() / ONE_DAY
        rows.append((issue.key, issue.status, age_days))
    df = pd.DataFrame(rows, columns=["key", "status", "age_days"])
    p85 = {
        status: float(np.percentile(values, 85)) for status, values in history.items()
    }
    df["p85_days"] = df["status"].map(p85)
    return df


def cumulative_flow(
    issues: Sequence[Issue],
    now: datetime | None = None,
) -> pd.DataFrame:
    """Return a date-indexed frame of per-status issue counts."""
    now = now or datetime.now(tz=UTC)
    if not issues:
        return pd.DataFrame()
    timelines: list[list[tuple[date, str]]] = []
    positions: dict[str, list[int]] = defaultdict(list)
    for issue in issues:
        initial = (
            issue.status_transitions[0].from_status or issue.status
            if issue.status_transitions
            else issue.status
        )
        steps = [(issue.created_at.date(), initial)] + [
            (t.at.date(), t.to_status) for t in issue.status_transitions
        ]
        timelines.append(steps)
        for idx, (_, status) in enumerate(steps):
            positions[status].append(idx)

    start = min(steps[0][0] for steps in timelines)
    span = (now.date() - start).days
    step = 7 if span > CFD_MAX_DAILY_SPAN else 1
    sample_days = [start + timedelta(days=k) for k in range(0, span + 1, step)]

    order = sorted(positions, key=lambda s: (fmean(positions[s]), s))
    data: dict[str, list[int]] = {status: [] for status in order}
    for day in sample_days:
        tally: Counter[str] = Counter()
        for steps in timelines:
            if steps[0][0] > day:
                continue
            current = steps[0][1]
            for changed_on, status in steps:
                if changed_on <= day:
                    current = status
            tally[current] += 1
        for status in order:
            data[status].append(tally.get(status, 0))
    return pd.DataFrame(data, index=pd.Index(sample_days, name="date"))


def assignee_load(
    issues: Sequence[Issue],
    top: int = 15,
) -> tuple[pd.DataFrame, list[int]]:
    """Return (per-assignee time-in-flight frame, handoffs per issue)."""
    totals: dict[str, float] = defaultdict(float)
    issue_counts: dict[str, int] = defaultdict(int)
    handoffs = []
    for issue in issues:
        handoffs.append(issue.handoffs)
        for assignee, td in issue.doers_x_periods.items():
            if assignee is None:
                continue
            totals[assignee] += td.total_seconds() / ONE_DAY
            issue_counts[assignee] += 1
    df = pd.DataFrame(
        {
            "assignee": list(totals),
            "total_days": [totals[a] for a in totals],
            "issue_count": [issue_counts[a] for a in totals],
        },
    )
    df = df.sort_values("total_days", ascending=False).head(top).reset_index(drop=True)
    return df, handoffs


def flow_efficiency(
    issues: Sequence[Issue],
    active_statuses: Sequence[str] | None = None,
) -> float:
    """Return active time / cycle time over done issues (0.0-1.0)."""
    active_names = {status.lower() for status in active_statuses or ACTIVE_STATUSES}
    active = 0.0
    total = 0.0
    for issue in issues:
        if issue.cycle_time is None:
            continue
        total += issue.cycle_time.total_seconds()
        active += sum(
            period.total_seconds()
            for status, period in issue.statuses_x_periods.items()
            if status.lower() in active_names
        )
    return active / total if total else 0.0


def returns_to_testing(
    issues: Sequence[Issue],
    testing_statuses: Sequence[str] | None = None,
    min_testing_count: int = 1,
) -> list[int]:
    """Count visits to testing statuses per issue that visited more than once."""
    testing_names = {status.lower() for status in testing_statuses or TESTING_STATUSES}
    res = []
    for issue in issues:
        testing_count = sum(
            1 for status in issue.status_history if status.lower() in testing_names
        )
        if testing_count > min_testing_count:
            res.append(testing_count)
    return res
