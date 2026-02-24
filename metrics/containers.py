"""Dependency injection container for the metrics application."""

from __future__ import annotations

import logging.config

from dependency_injector import containers, providers

from metrics.repository.converter import JiraDataConverter
from metrics.repository.jira import JiraAPIRepository, JiraIssuesRepository
from metrics.services.calculator import (
    CumulativeQueueTimeCalculator,
    CycleTimeCalculator,
    LeadTimeCalculator,
    QueueTimeCalculator,
    ReturnToTestingCalculator,
    ThroughputCalculator,
)

from .services import MetricsService, VisService
from .utils import get_jira_client


class Container(containers.DeclarativeContainer):
    """Wires together repositories, calculators, and services."""

    logging = providers.Resource(
        logging.config.fileConfig,
        fname="metrics/logging.ini",
    )

    config = providers.Configuration()

    jira = providers.Factory(
        get_jira_client,
        config.jira.server,
        config.jira.token,
    )

    jira_api_repo = providers.Factory(
        JiraAPIRepository,
        jira,
        config.jira.jql,
    )
    jira_data_converter = providers.Factory(JiraDataConverter)

    repo = providers.Factory(
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
    )

    metrics_service = providers.Factory(
        MetricsService,
        cycle_time_calculator=cycle_time_calculator,
        lead_time_calculator=lead_time_calculator,
        queue_time_calculator=queue_time_calculator,
        throughput_calculator=throughput_calculator,
        cumulative_queue_time_calculator=cumulative_queue_time_calculator,
        return_to_testing_calculator=return_to_testing_calculator,
    )

    vis_service = providers.Factory(
        VisService,
    )
