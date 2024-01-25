from collections import defaultdict

from metrics.consts import CALC_LIMIT, ONE_DAY
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
