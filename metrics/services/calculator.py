"""Metric calculators for Jira issue analytics."""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections import Counter, defaultdict
from datetime import UTC, date, datetime, timedelta
from statistics import fmean
from typing import TYPE_CHECKING, Final

import numpy as np
import pandas as pd

from metrics.consts import (
    ACTIVE_STATUSES,
    CALC_LIMIT,
    ONE_DAY,
    ONE_HOUR,
    TESTING_STATUSES,
)

if TYPE_CHECKING:
    from typing import Any

    from metrics.repository import BaseIssuesRepository

MIN_FORECAST_HISTORY_WEEKS: Final[int] = 6
CFD_MAX_DAILY_SPAN: Final[int] = 180


class MetricCalculator(ABC):
    """Base class for all metric calculators."""

    def __init__(self, repo: BaseIssuesRepository) -> None:
        """Initialize with an issues repository."""
        self.repo = repo

    @abstractmethod
    def calculate(self) -> object:
        """Calculate the metric and return the result."""


class TimeMetricCalculator(MetricCalculator):
    """Base calculator for time-based metrics (cycle time, lead time)."""

    def _calculate_time_metric(
        self,
        metric_name: str,
        timeslot: int,
        limit: int,
    ) -> list[float]:
        res = []
        for issue in self.repo.all():
            metric_value = getattr(issue, metric_name)
            if metric_value:
                time_in_days = max(
                    1,
                    metric_value.total_seconds() // timeslot,
                )
                time_in_days = min(time_in_days, limit)
                res.append(time_in_days)
        return res


class CycleTimeCalculator(TimeMetricCalculator):
    """Calculate cycle time for issues."""

    def calculate(
        self,
        timeslot: int = ONE_DAY,
        limit: int = CALC_LIMIT,
    ) -> list[float]:
        """Calculate cycle time in the given timeslot units."""
        return self._calculate_time_metric(
            "cycle_time",
            timeslot,
            limit,
        )


class LeadTimeCalculator(TimeMetricCalculator):
    """Calculate lead time for issues."""

    def calculate(
        self,
        timeslot: int = ONE_DAY,
        limit: int = CALC_LIMIT,
    ) -> list[float]:
        """Calculate lead time in the given timeslot units."""
        return self._calculate_time_metric(
            "lead_time",
            timeslot,
            limit,
        )


class QueueTimeCalculator(MetricCalculator):
    """Calculate time spent in each status."""

    def calculate(
        self,
        timeslot: int = ONE_DAY,
        limit: int = CALC_LIMIT,
    ) -> dict[str, list[float]]:
        """Calculate queue time per status in the given timeslot units."""
        tmp: dict[str, list[float]] = defaultdict(list)
        for issue in self.repo.all():
            for status, td in issue.statuses_x_periods.items():
                period_in_status = max(
                    1,
                    td.total_seconds() // timeslot,
                )
                period_in_status = min(period_in_status, limit)
                tmp[status].append(period_in_status)
        return dict(tmp)


class ThroughputCalculator(MetricCalculator):
    """Calculate weekly throughput of completed issues."""

    def calculate(self) -> dict[str, int]:
        """Calculate issues completed per ISO week, gap weeks zero-filled."""
        counts: dict[str, int] = defaultdict(int)
        finish_dates = []
        for issue in self.repo.all():
            if issue.last_finish_status_at:
                counts[issue.last_finish_status_at.strftime("%GW%V")] += 1
                finish_dates.append(issue.last_finish_status_at.date())
        if not counts:
            return {}

        week = date.fromisocalendar(*min(finish_dates).isocalendar()[:2], 1)
        last_week = date.fromisocalendar(*max(finish_dates).isocalendar()[:2], 1)
        result: dict[str, int] = {}
        while week <= last_week:
            key = week.strftime("%GW%V")
            result[key] = counts.get(key, 0)
            week += timedelta(weeks=1)
        return result


class CumulativeQueueTimeCalculator(MetricCalculator):
    """Calculate cumulative median queue time per status."""

    def calculate(
        self,
        timeslot: int = ONE_HOUR,
        limit: int = 1000,
    ) -> pd.DataFrame:
        """Calculate median time spent in each status."""
        tmp: dict[str, list[float]] = defaultdict(list)
        for issue in self.repo.all():
            for status, td in issue.statuses_x_periods.items():
                period_in_status = max(
                    1,
                    td.total_seconds() // timeslot,
                )
                if period_in_status == 1 or period_in_status > limit:
                    continue
                tmp[status].append(period_in_status)
        res = pd.DataFrame(columns=["status", "median_hours", "count"])
        res["status"] = list(tmp.keys())
        res["median_hours"] = [np.median(periods) for periods in tmp.values()]
        res["count"] = [len(periods) for periods in tmp.values()]
        return res


class CycleTimeScatterCalculator(MetricCalculator):
    """Prepare per-issue cycle-time points for the percentile scatterplot."""

    def calculate(self) -> pd.DataFrame:
        """Return finished_at x uncapped cycle time in days per done issue."""
        rows = [
            (
                issue.key,
                issue.last_finish_status_at,
                issue.cycle_time.total_seconds() / ONE_DAY,
            )
            for issue in self.repo.all()
            if issue.cycle_time is not None
        ]
        return pd.DataFrame(rows, columns=["key", "finished_at", "cycle_time_days"])


class MonteCarloForecastCalculator(MetricCalculator):
    """Forecast weeks to clear the open backlog from throughput history."""

    def __init__(
        self,
        repo: BaseIssuesRepository,
        throughput_calculator: ThroughputCalculator,
    ) -> None:
        """Initialize with the repository and a throughput calculator."""
        super().__init__(repo)
        self.throughput_calculator = throughput_calculator

    def calculate(
        self,
        simulations: int = 10_000,
        seed: int | None = None,
        now: datetime | None = None,
    ) -> dict[str, Any]:
        """Simulate backlog completion; empty dict when data is insufficient."""
        now = now or datetime.now(tz=UTC)
        samples = np.array(
            list(self.throughput_calculator.calculate().values()),
            dtype=float,
        )
        backlog = sum(1 for issue in self.repo.all() if not issue.was_done)
        if (
            backlog == 0
            or len(samples) < MIN_FORECAST_HISTORY_WEEKS
            or samples.sum() == 0
        ):
            return {}
        rng = np.random.default_rng(seed)
        weeks = np.zeros(simulations, dtype=np.int64)
        remaining = np.full(simulations, float(backlog))
        active = remaining > 0
        while active.any():
            remaining[active] -= rng.choice(samples, size=int(active.sum()))
            weeks[active] += 1
            active = remaining > 0
        result: dict[str, Any] = {"weeks": weeks, "backlog": backlog}
        for pct in (50, 85, 95):
            value = float(np.percentile(weeks, pct))
            result[f"p{pct}"] = value
            result[f"p{pct}_date"] = (now + timedelta(weeks=value)).date()
        return result


class AgingWipCalculator(MetricCalculator):
    """Age of open issues in their current status vs historical p85."""

    def calculate(self, now: datetime | None = None) -> pd.DataFrame:
        """Return key/status/age_days/p85_days per open issue."""
        now = now or datetime.now(tz=UTC)
        history: dict[str, list[float]] = defaultdict(list)
        rows = []
        for issue in self.repo.all():
            if issue.was_done:
                for status, td in issue.statuses_x_periods.items():
                    history[status].append(td.total_seconds() / ONE_DAY)
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
            status: float(np.percentile(values, 85))
            for status, values in history.items()
        }
        df["p85_days"] = df["status"].map(p85)
        return df


class CumulativeFlowCalculator(MetricCalculator):
    """Issue counts per status over time, replayed from transitions."""

    def calculate(self, now: datetime | None = None) -> pd.DataFrame:
        """Return a date-indexed frame of per-status issue counts."""
        now = now or datetime.now(tz=UTC)
        issues = self.repo.all()
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


class AssigneeLoadCalculator(MetricCalculator):
    """Time-in-flight per assignee plus handoff counts per issue."""

    def calculate(self, top: int = 15) -> tuple[pd.DataFrame, list[int]]:
        """Return (per-assignee load frame, handoffs per issue)."""
        totals: dict[str, float] = defaultdict(float)
        issue_counts: dict[str, int] = defaultdict(int)
        handoffs = []
        for issue in self.repo.all():
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
        df = (
            df.sort_values("total_days", ascending=False)
            .head(top)
            .reset_index(drop=True)
        )
        return df, handoffs


class FlowEfficiencyCalculator(MetricCalculator):
    """Share of done issues' status time spent in active (working) statuses."""

    def __init__(
        self,
        repo: BaseIssuesRepository,
        active_statuses: list[str] | None = None,
    ) -> None:
        """Initialize with the statuses that count as active work."""
        super().__init__(repo)
        self.active_statuses = [
            status.lower() for status in (active_statuses or ACTIVE_STATUSES)
        ]

    def calculate(self) -> float:
        """Return active time / total status time over done issues (0.0-1.0)."""
        active = 0.0
        total = 0.0
        for issue in self.repo.all():
            if not issue.was_done:
                continue
            for status, period in issue.statuses_x_periods.items():
                seconds = period.total_seconds()
                total += seconds
                if status.lower() in self.active_statuses:
                    active += seconds
        return active / total if total else 0.0


class ReturnToTestingCalculator(MetricCalculator):
    """Calculate how often issues return to testing."""

    def __init__(
        self,
        repo: BaseIssuesRepository,
        testing_statuses: list[str] | None = None,
    ) -> None:
        """Initialize with the statuses that count as testing/QA."""
        super().__init__(repo)
        self.testing_statuses = [
            status.lower() for status in (testing_statuses or TESTING_STATUSES)
        ]

    def calculate(self, min_testing_count: int = 1) -> list[int]:
        """Calculate count of testing transitions per issue."""
        res = []
        for issue in self.repo.all():
            if issue.status_history:
                testing_count = sum(
                    1
                    for status in issue.status_history
                    if status.lower() in self.testing_statuses
                )
                if testing_count > min_testing_count:
                    res.append(testing_count)
        return res
