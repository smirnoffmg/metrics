from .base import BaseService
from .calculator import (
    CumulativeQueueTimeCalculator,
    CycleTimeCalculator,
    LeadTimeCalculator,
    QueueTimeCalculator,
    ReturnToTestingCalculator,
    ThroughputCalculator,
)


class MetricsService(BaseService):
    def __init__(
        self,
        cycle_time_calculator: CycleTimeCalculator,
        lead_time_calculator: LeadTimeCalculator,
        queue_time_calculator: QueueTimeCalculator,
        throughput_calculator: ThroughputCalculator,
        cumulative_queue_time_calculator: CumulativeQueueTimeCalculator,
        return_to_testing_calculator: ReturnToTestingCalculator,
    ) -> None:
        self.cycle_time_calculator = cycle_time_calculator
        self.lead_time_calculator = lead_time_calculator
        self.queue_time_calculator = queue_time_calculator
        self.throughput_calculator = throughput_calculator
        self.cumulative_queue_time_calculator = cumulative_queue_time_calculator
        self.return_to_testing_calculator = return_to_testing_calculator
        super().__init__()

    def get_cycle_time(self) -> list[float]:
        self.logger.debug("Calculating cycle time...")
        return self.cycle_time_calculator.calculate()

    def get_lead_time(self) -> list[float]:
        self.logger.debug("Calculating lead time...")
        return self.lead_time_calculator.calculate()

    def get_queue_time(self) -> dict[str, list[float]]:
        self.logger.debug("Calculating queue time...")
        return self.queue_time_calculator.calculate()

    def get_throughput(self) -> dict[str, int]:
        self.logger.debug("Calculating throughput...")
        return self.throughput_calculator.calculate()

    def get_cumulative_queue_time(self) -> dict[str, int]:
        self.logger.debug("Calculating cumulative queue time...")
        return self.cumulative_queue_time_calculator.calculate()

    def get_return_to_testing(self) -> list[int]:
        self.logger.debug("Calculating return to testing...")
        return self.return_to_testing_calculator.calculate()
