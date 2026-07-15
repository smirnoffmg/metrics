"""Dependency injection container for the metrics application."""

from __future__ import annotations

import logging.config
from pathlib import Path

from dependency_injector import containers, providers

from metrics.repository.converter import JiraDataConverter
from metrics.repository.jira import JiraAPIRepository, JiraIssuesRepository
from metrics.services.calculator import (
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

from .services import (
    InteractiveVisService,
    MetricsService,
    ReportService,
    VisService,
)
from .utils import get_jira_client


class Container(containers.DeclarativeContainer):
    """Wires together repositories, calculators, and services."""

    logging = providers.Resource(
        logging.config.fileConfig,
        fname=str(Path(__file__).parent / "logging.ini"),
    )

    config = providers.Configuration()

    jira = providers.Factory(
        get_jira_client,
        config.jira.server,
        config.jira.token,
        config.jira.email,
        config.jira.anonymous,
    )

    jira_api_repo = providers.Factory(
        JiraAPIRepository,
        jira,
        config.jira.jql,
        cloud=config.jira.cloud,
    )
    jira_data_converter = providers.Factory(
        JiraDataConverter,
        done_statuses=config.jira.done_statuses,
    )

    repo = providers.Singleton(
        JiraIssuesRepository,
        api_repo=jira_api_repo,
        converter=jira_data_converter,
    )

    cycle_time_calculator = providers.Factory(CycleTimeCalculator, repo)
    lead_time_calculator = providers.Factory(LeadTimeCalculator, repo)
    queue_time_calculator = providers.Factory(
        QueueTimeCalculator,
        repo,
    )
    throughput_calculator = providers.Factory(
        ThroughputCalculator,
        repo,
    )
    cumulative_queue_time_calculator = providers.Factory(
        CumulativeQueueTimeCalculator,
        repo,
    )
    return_to_testing_calculator = providers.Factory(
        ReturnToTestingCalculator,
        repo,
        testing_statuses=config.jira.testing_statuses,
    )
    cycle_time_scatter_calculator = providers.Factory(
        CycleTimeScatterCalculator,
        repo,
    )
    monte_carlo_forecast_calculator = providers.Factory(
        MonteCarloForecastCalculator,
        repo,
        throughput_calculator,
    )
    aging_wip_calculator = providers.Factory(AgingWipCalculator, repo)
    cumulative_flow_calculator = providers.Factory(CumulativeFlowCalculator, repo)
    assignee_load_calculator = providers.Factory(AssigneeLoadCalculator, repo)
    flow_efficiency_calculator = providers.Factory(
        FlowEfficiencyCalculator,
        repo,
        active_statuses=config.jira.active_statuses,
    )

    metrics_service = providers.Factory(
        MetricsService,
        cycle_time_calculator=cycle_time_calculator,
        lead_time_calculator=lead_time_calculator,
        queue_time_calculator=queue_time_calculator,
        throughput_calculator=throughput_calculator,
        cumulative_queue_time_calculator=cumulative_queue_time_calculator,
        return_to_testing_calculator=return_to_testing_calculator,
        cycle_time_scatter_calculator=cycle_time_scatter_calculator,
        monte_carlo_forecast_calculator=monte_carlo_forecast_calculator,
        aging_wip_calculator=aging_wip_calculator,
        cumulative_flow_calculator=cumulative_flow_calculator,
        assignee_load_calculator=assignee_load_calculator,
        flow_efficiency_calculator=flow_efficiency_calculator,
    )

    vis_service = providers.Factory(
        VisService,
    )

    interactive_vis_service = providers.Factory(
        InteractiveVisService,
        server_url=config.jira.server,
    )

    report_service = providers.Factory(
        ReportService,
    )
