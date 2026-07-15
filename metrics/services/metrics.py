"""Service for computing Jira engineering metrics."""

from __future__ import annotations

from typing import TYPE_CHECKING

from .base import BaseService

if TYPE_CHECKING:
    from typing import Any

    import pandas as pd

    from .calculator import (
        AgingWipCalculator,
        AssigneeLoadCalculator,
        CumulativeFlowCalculator,
        CumulativeQueueTimeCalculator,
        CycleTimeCalculator,
        CycleTimeScatterCalculator,
        FlowEfficiencyCalculator,
        LeadTimeCalculator,
        MonteCarloForecastCalculator,
        QueueTimeCalculator,
        ReturnToTestingCalculator,
        ThroughputCalculator,
    )


class MetricsService(BaseService):
    """Orchestrates metric calculators to produce analytics results."""

    def __init__(  # noqa: PLR0913
        self,
        cycle_time_calculator: CycleTimeCalculator,
        lead_time_calculator: LeadTimeCalculator,
        queue_time_calculator: QueueTimeCalculator,
        throughput_calculator: ThroughputCalculator,
        cumulative_queue_time_calculator: CumulativeQueueTimeCalculator,
        return_to_testing_calculator: ReturnToTestingCalculator,
        cycle_time_scatter_calculator: CycleTimeScatterCalculator,
        monte_carlo_forecast_calculator: MonteCarloForecastCalculator,
        aging_wip_calculator: AgingWipCalculator,
        cumulative_flow_calculator: CumulativeFlowCalculator,
        assignee_load_calculator: AssigneeLoadCalculator,
        flow_efficiency_calculator: FlowEfficiencyCalculator,
    ) -> None:
        """Initialize with all metric calculators."""
        self.cycle_time_calculator = cycle_time_calculator
        self.lead_time_calculator = lead_time_calculator
        self.queue_time_calculator = queue_time_calculator
        self.throughput_calculator = throughput_calculator
        self.cumulative_queue_time_calculator = cumulative_queue_time_calculator
        self.return_to_testing_calculator = return_to_testing_calculator
        self.cycle_time_scatter_calculator = cycle_time_scatter_calculator
        self.monte_carlo_forecast_calculator = monte_carlo_forecast_calculator
        self.aging_wip_calculator = aging_wip_calculator
        self.cumulative_flow_calculator = cumulative_flow_calculator
        self.assignee_load_calculator = assignee_load_calculator
        self.flow_efficiency_calculator = flow_efficiency_calculator
        super().__init__()

    def get_cycle_time(self) -> list[float]:
        """Calculate cycle time for all issues."""
        self.logger.debug("Calculating cycle time...")
        return self.cycle_time_calculator.calculate()

    def get_lead_time(self) -> list[float]:
        """Calculate lead time for all issues."""
        self.logger.debug("Calculating lead time...")
        return self.lead_time_calculator.calculate()

    def get_queue_time(self) -> dict[str, list[float]]:
        """Calculate queue time per status for all issues."""
        self.logger.debug("Calculating queue time...")
        return self.queue_time_calculator.calculate()

    def get_throughput(self) -> dict[str, int]:
        """Calculate weekly throughput of completed issues."""
        self.logger.debug("Calculating throughput...")
        return self.throughput_calculator.calculate()

    def get_cumulative_queue_time(self) -> pd.DataFrame:
        """Calculate cumulative median queue time per status."""
        self.logger.debug("Calculating cumulative queue time...")
        return self.cumulative_queue_time_calculator.calculate()

    def get_return_to_testing(self) -> list[int]:
        """Calculate how often issues return to testing."""
        self.logger.debug("Calculating return to testing...")
        return self.return_to_testing_calculator.calculate()

    def get_cycle_time_scatter(self) -> pd.DataFrame:
        """Collect per-issue cycle-time points for the scatterplot."""
        self.logger.debug("Calculating cycle time scatter...")
        return self.cycle_time_scatter_calculator.calculate()

    def get_forecast(self) -> dict[str, Any]:
        """Run the Monte Carlo backlog forecast."""
        self.logger.debug("Calculating Monte Carlo forecast...")
        return self.monte_carlo_forecast_calculator.calculate()

    def get_aging_wip(self) -> pd.DataFrame:
        """Calculate age of open issues in their current status."""
        self.logger.debug("Calculating aging WIP...")
        return self.aging_wip_calculator.calculate()

    def get_cumulative_flow(self) -> pd.DataFrame:
        """Build the cumulative flow diagram data."""
        self.logger.debug("Calculating cumulative flow...")
        return self.cumulative_flow_calculator.calculate()

    def get_assignee_load(self) -> tuple[pd.DataFrame, list[int]]:
        """Aggregate assignee load and handoff counts."""
        self.logger.debug("Calculating assignee load...")
        return self.assignee_load_calculator.calculate()

    def get_flow_efficiency(self) -> float:
        """Calculate the share of time spent actively working."""
        self.logger.debug("Calculating flow efficiency...")
        return self.flow_efficiency_calculator.calculate()
