"""Metric calculators for Jira issue analytics."""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections import defaultdict
from typing import TYPE_CHECKING

import numpy as np
import pandas as pd

from metrics.consts import CALC_LIMIT, ONE_DAY, ONE_HOUR

if TYPE_CHECKING:
    from metrics.repository import BaseIssuesRepository


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
        """Calculate number of issues completed per week."""
        tmp: dict[str, int] = defaultdict(int)
        for issue in self.repo.all():
            if issue.last_finish_status_at:
                key = issue.last_finish_status_at.strftime("%YW%V")
                tmp[key] += 1
        return dict(tmp)


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


class ReturnToTestingCalculator(MetricCalculator):
    """Calculate how often issues return to testing."""

    def calculate(
        self,
        testing_statuses: list[str] | None = None,
        min_testing_count: int = 1,
    ) -> list[int]:
        """Calculate count of testing transitions per issue."""
        if testing_statuses is None:
            testing_statuses = ["testing"]
        testing_statuses = [s.lower() for s in testing_statuses]
        res = []
        for issue in self.repo.all():
            if issue.status_history:
                testing_count = sum(
                    1
                    for status in issue.status_history
                    if status.lower() in testing_statuses
                )
                if testing_count > min_testing_count:
                    res.append(testing_count)
        return res
