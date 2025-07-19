from collections import defaultdict

import numpy as np
import pandas as pd

from metrics.consts import CALC_LIMIT, ONE_DAY, ONE_HOUR
from metrics.repository import BaseIssuesRepository

from .base import BaseService


class MetricsService(BaseService):
    def __init__(self, repo: BaseIssuesRepository) -> None:
        self.repo = repo
        super().__init__()

    def get_statuses(self) -> dict[str, int]:
        self.logger.debug("Calculating statuses info...")
        tmp = defaultdict(int)

        for issue in self.repo.all():
            tmp[issue.status] += 1

        return dict(tmp)

    def get_cycle_time(
        self,
        timeslot: int = ONE_DAY,
        limit: int = CALC_LIMIT,
    ) -> list[float]:
        self.logger.debug("Calculating cycle time...")
        res = []
        for issue in self.repo.all():
            if issue.cycle_time:
                cycle_time = max(1, issue.cycle_time.total_seconds() // timeslot)
                cycle_time = min(cycle_time, limit)
                res.append(cycle_time)
        return res

    def get_lead_time(
        self,
        timeslot: int = ONE_DAY,
        limit: int = CALC_LIMIT,
    ) -> list[float]:
        self.logger.debug("Calculating lead time...")
        res = []
        for issue in self.repo.all():
            if issue.lead_time:
                lead_time = max(1, issue.lead_time.total_seconds() // timeslot)
                lead_time = min(lead_time, limit)
                res.append(lead_time)
        return res

    def get_queue_time(
        self,
        timeslot: int = ONE_DAY,
        limit: int = CALC_LIMIT,
    ) -> dict[str, list[float]]:
        self.logger.debug("Calculating queue time...")
        tmp = defaultdict(list)

        for issue in self.repo.all():
            for status, td in issue.statuses_x_periods.items():
                period_in_status = max(1, td.total_seconds() // timeslot)
                period_in_status = min(period_in_status, limit)
                tmp[status].append(period_in_status)

        return dict(tmp)

    def get_throughput(self) -> dict[str, int]:
        self.logger.debug("Calculating throughput...")
        tmp = defaultdict(int)

        for issue in self.repo.all():
            if issue.last_finish_status_at:
                key = issue.last_finish_status_at.strftime("%YW%V")  # example: 2024W03

                tmp[key] += 1

        return dict(tmp)

    def get_cumulative_queue_time(
        self,
        timeslot: int = ONE_HOUR,
        limit: int = 1000,
    ) -> pd.DataFrame:
        """Считаем p50 время в каждом статусе по всему множеству задач
        Минимальное время в статусе задаётся через timeslot
        """
        self.logger.debug("Calculating cumulative queue time...")
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

    def get_return_to_testing(
        self,
        testing_statuses: list[str] | None = None,
        min_testing_count: int = 1,
    ) -> list[int]:
        if testing_statuses is None:
            testing_statuses = ["testing"]

        testing_statuses = [s.lower() for s in testing_statuses]

        self.logger.debug("Calculating return to testing...")
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
