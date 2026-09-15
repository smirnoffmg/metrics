"""Dependency injection container for the metrics application."""

from __future__ import annotations

import logging.config
from pathlib import Path

from dependency_injector import containers, providers

from metrics.repository.converter import JiraDataConverter
from metrics.repository.jira import JiraAPIRepository, JiraIssuesRepository

from .services import (
    InteractiveVisService,
    ReportService,
    VisService,
)
from .utils import get_jira_client


class Container(containers.DeclarativeContainer):
    """Wires together the Jira client, the issue repository, and services."""

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
        discarded_statuses=config.jira.discarded_statuses,
        backlog_statuses=config.jira.backlog_statuses,
        discarded_resolutions=config.jira.discarded_resolutions,
    )

    repo = providers.Singleton(
        JiraIssuesRepository,
        api_repo=jira_api_repo,
        converter=jira_data_converter,
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
