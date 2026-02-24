"""Base repository for issue data retrieval and caching."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from metrics.entity import Issue


class BaseIssuesRepository:
    """In-memory repository that fetches and caches issues."""

    issues: dict[str, Issue]

    def __init__(self) -> None:
        """Fetch all issues and index them by key."""
        self.issues = {issue.key: issue for issue in self.get_issues()}

    def get(self, key: str) -> Issue | None:
        """Return an issue by key, or None if not found."""
        return self.issues.get(key)

    def all(self) -> list[Issue]:
        """Return all cached issues."""
        return list(self.issues.values())

    def convert_data_to_issue(self, data_item: dict) -> Issue:
        """Convert a raw data dict into an Issue entity."""
        raise NotImplementedError

    def get_raw_data(self) -> list[dict]:
        """Fetch raw issue data from the underlying source."""
        raise NotImplementedError

    def get_issues(self) -> list[Issue]:
        """Fetch raw data and convert each item to an Issue."""
        return [
            self.convert_data_to_issue(data_item) for data_item in self.get_raw_data()
        ]
