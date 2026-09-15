"""Dependency injection container for the metrics application."""

from __future__ import annotations

import logging.config
from pathlib import Path

from dependency_injector import containers, providers

from metrics.repository.converter import JiraDataConverter
from metrics.repository.gitlab import GitLabDeliverySource, SnapshotWithDelivery
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
        server=config.jira.server,
        forecast_jql=config.jira.forecast_jql,
        cloud=config.jira.cloud,
    )
    jira_data_converter = providers.Factory(
        JiraDataConverter,
        done_statuses=config.jira.done_statuses,
        discarded_statuses=config.jira.discarded_statuses,
        backlog_statuses=config.jira.backlog_statuses,
        discarded_resolutions=config.jira.discarded_resolutions,
    )

    gitlab_delivery = providers.Factory(
        GitLabDeliverySource,
        url=config.gitlab.url,
        token=config.gitlab.token,
        project=config.gitlab.project,
        tag_pattern=config.gitlab.deploy_tag_pattern,
        days=config.gitlab.delivery_days,
    )
    snapshot_source = providers.Factory(
        SnapshotWithDelivery,
        jira_api_repo,
        gitlab_delivery,
    )

    repo = providers.Singleton(
        JiraIssuesRepository,
        api_repo=snapshot_source,
        converter=jira_data_converter,
        save_path=config.jira.save_raw,
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
