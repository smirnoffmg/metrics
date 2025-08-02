from abc import ABC, abstractmethod
from collections import defaultdict

import numpy as np
import pandas as pd

from metrics.consts import CALC_LIMIT, ONE_DAY, ONE_HOUR
from metrics.repository import BaseIssuesRepository


class MetricCalculator(ABC):
    def __init__(self, repo: BaseIssuesRepository):
        self.repo = repo

    @abstractmethod
    def calculate(self):
        pass


class TimeMetricCalculator(MetricCalculator):
    def _calculate_time_metric(
        self, metric_name: str, timeslot: int, limit: int,
    ) -> list[float]:
        res = []
        for issue in self.repo.all():
            metric_value = getattr(issue, metric_name)
            if metric_value:
                time_in_days = max(1, metric_value.total_seconds() // timeslot)
                time_in_days = min(time_in_days, limit)
                res.append(time_in_days)
        return res


class CycleTimeCalculator(TimeMetricCalculator):
    def calculate(
        self, timeslot: int = ONE_DAY, limit: int = CALC_LIMIT,
    ) -> list[float]:
        return self._calculate_time_metric("cycle_time", timeslot, limit)


class LeadTimeCalculator(TimeMetricCalculator):
    def calculate(
        self, timeslot: int = ONE_DAY, limit: int = CALC_LIMIT,
    ) -> list[float]:
        return self._calculate_time_metric("lead_time", timeslot, limit)


class QueueTimeCalculator(MetricCalculator):
    def calculate(
        self, timeslot: int = ONE_DAY, limit: int = CALC_LIMIT,
    ) -> dict[str, list[float]]:
        tmp = defaultdict(list)
        for issue in self.repo.all():
            for status, td in issue.statuses_x_periods.items():
                period_in_status = max(1, td.total_seconds() // timeslot)
                period_in_status = min(period_in_status, limit)
                tmp[status].append(period_in_status)
        return dict(tmp)


class ThroughputCalculator(MetricCalculator):
    def calculate(self) -> dict[str, int]:
        tmp = defaultdict(int)
        for issue in self.repo.all():
            if issue.last_finish_status_at:
                key = issue.last_finish_status_at.strftime("%YW%V")
                tmp[key] += 1
        return dict(tmp)


class CumulativeQueueTimeCalculator(MetricCalculator):
    def calculate(self, timeslot: int = ONE_HOUR, limit: int = 1000) -> pd.DataFrame:
        tmp = defaultdict(list)
        for issue in self.repo.all():
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


class ReturnToTestingCalculator(MetricCalculator):
    def calculate(
        self,
        testing_statuses: list[str] | None = None,
        min_testing_count: int = 1,
    ) -> list[int]:
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
