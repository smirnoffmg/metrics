import logging.config

from dependency_injector import containers, providers

from metrics.repository import JiraAPIRepository

from .services import MetricsService, VisService
from .utils import get_jira_client


class Container(containers.DeclarativeContainer):
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

    repo = providers.Factory(JiraAPIRepository, jira, config.jira.jql)

    metrics_service = providers.Factory(
        MetricsService,
        repo,
    )

    vis_service = providers.Factory(
        VisService,
    )
