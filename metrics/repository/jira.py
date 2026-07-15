"""Jira-backed issue repository implementations."""

from __future__ import annotations

from typing import TYPE_CHECKING

from .base import BaseIssuesRepository
from .utils import get_issues, get_issues_cloud

if TYPE_CHECKING:
    from jira import JIRA

    from metrics.entity import Issue

    from .converter import JiraDataConverter


class JiraAPIRepository:
    """Thin wrapper around the Jira API for fetching raw issue data."""

    def __init__(self, jira: JIRA, jql: str, *, cloud: bool | None = None) -> None:
        """Initialize with a JIRA client, JQL query, and deployment kind.

        cloud=None auto-detects from the client's serverInfo deploymentType.
        """
        self.jira = jira
        self.jql = jql
        self.cloud = cloud

    def _is_cloud(self) -> bool:
        if self.cloud is None:
            return getattr(self.jira, "deploymentType", None) == "Cloud"
        return self.cloud

    def get_raw_data(self) -> list[dict]:
        """Fetch raw issue dicts from the Jira API."""
        if self._is_cloud():
            return get_issues_cloud(self.jira, self.jql)
        return get_issues(self.jira, self.jql)


class JiraIssuesRepository(BaseIssuesRepository):
    """Repository that fetches issues from Jira and converts them."""

    def __init__(
        self,
        api_repo: JiraAPIRepository,
        converter: JiraDataConverter,
    ) -> None:
        """Initialize with an API repository and data converter."""
        self.api_repo = api_repo
        self.converter = converter
        super().__init__()

    def get_raw_data(self) -> list[dict]:
        """Delegate raw data fetching to the API repository."""
        return self.api_repo.get_raw_data()

    def convert_data_to_issue(self, data_item: dict) -> Issue:
        """Convert a raw Jira dict to an Issue via the converter."""
        return self.converter.convert_data_to_issue(data_item)
