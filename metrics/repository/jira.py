"""Jira-backed issue repository implementations."""

from __future__ import annotations

from typing import TYPE_CHECKING

from .base import BaseIssuesRepository
from .utils import get_issues

if TYPE_CHECKING:
    from jira import JIRA

    from metrics.entity import Issue

    from .converter import JiraDataConverter


class JiraAPIRepository:
    """Thin wrapper around the Jira API for fetching raw issue data."""

    def __init__(self, jira: JIRA, jql: str) -> None:
        """Initialize with a JIRA client and JQL query."""
        self.jira = jira
        self.jql = jql

    def get_raw_data(self) -> list[dict]:
        """Fetch raw issue dicts from the Jira API."""
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
