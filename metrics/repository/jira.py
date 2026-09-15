"""Jira-backed issue repository implementations."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING, Protocol

from .base import BaseIssuesRepository
from .snapshot import Snapshot, current_status_categories, save_snapshot
from .utils import get_issues, get_issues_cloud, get_status_categories

if TYPE_CHECKING:
    from jira import JIRA

    from metrics.entity import Issue

    from .converter import JiraDataConverter


class JiraAPIRepository:
    """Thin wrapper around the Jira API for fetching raw issue data."""

    def __init__(
        self,
        jira: JIRA,
        jql: str,
        *,
        server: str = "",
        cloud: bool | None = None,
    ) -> None:
        """Initialize with a JIRA client, JQL query, server URL and deployment kind.

        cloud=None auto-detects from the client's serverInfo deploymentType.
        """
        self.jira = jira
        self.jql = jql
        self.server = server
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

    def get_snapshot(self) -> Snapshot:
        """Fetch raw issues, stamped with the server, query and time of fetch."""
        fetched_at = datetime.now(tz=UTC)
        return Snapshot(
            server=self.server,
            jql=self.jql,
            fetched_at=fetched_at,
            issues=self.get_raw_data(),
            statuses=get_status_categories(self.jira),
        )


class SnapshotSource(Protocol):
    """Anything that can hand over a snapshot: the Jira API or a saved file."""

    def get_snapshot(self) -> Snapshot:
        """Return raw issues with where and when they were fetched."""
        ...


class JiraIssuesRepository(BaseIssuesRepository):
    """Repository that converts a snapshot of Jira issues, live or saved."""

    snapshot: Snapshot

    def __init__(
        self,
        api_repo: SnapshotSource,
        converter: JiraDataConverter,
        save_path: str | None = None,
    ) -> None:
        """Initialize with a snapshot source, a converter and where to save raw data."""
        self.api_repo = api_repo
        self.converter = converter
        self.save_path = save_path
        super().__init__()

    def get_raw_data(self) -> list[dict]:
        """Take a snapshot from the source, saving it first if asked to."""
        self.snapshot = self.api_repo.get_snapshot()
        if self.save_path:
            save_snapshot(self.snapshot, self.save_path)
        return self.snapshot.issues

    def get_issues(self) -> list[Issue]:
        """Convert the snapshot's issues, classifying statuses by category."""
        raw = self.get_raw_data()
        categories = {**self.snapshot.statuses, **current_status_categories(raw)}
        return [self.converter.convert_data_to_issue(item, categories) for item in raw]

    def convert_data_to_issue(self, data_item: dict) -> Issue:
        """Convert a raw Jira dict to an Issue via the converter."""
        return self.converter.convert_data_to_issue(data_item, self.snapshot.statuses)
