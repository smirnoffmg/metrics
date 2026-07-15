"""Test doubles mirroring the real jira client contract."""

from __future__ import annotations

from typing import Any


def make_raw_issue(key: str, created: str = "2024-01-01T00:00:00.000+0000") -> dict:
    return {
        "key": key,
        "fields": {
            "created": created,
            "status": {"name": "Done"},
        },
        "changelog": {"histories": []},
    }


class _NotSubscriptable:
    """Stands in for jira.Issue, which has no __getitem__."""


class FakeJira:
    """Mimics JIRA.search_issues: returns dicts only when json_result=True.

    Without json_result=True the real client returns ResultList[jira.Issue],
    whose items are not subscriptable - modelled here by _NotSubscriptable.
    """

    def __init__(self, issues: list[dict]) -> None:
        self.issues = issues
        self.search_calls: list[dict[str, Any]] = []

    def search_issues(self, jql_str: str, **kwargs: Any) -> Any:  # noqa: ARG002
        self.search_calls.append(kwargs)
        start = kwargs.get("startAt", 0)
        limit = kwargs.get("maxResults", 50)
        page = self.issues[start : start + limit]
        if kwargs.get("json_result"):
            return {"total": len(self.issues), "issues": page}
        return [_NotSubscriptable() for _ in page]


class FakeCloudJira:
    """Mimics JIRA.enhanced_search_issues nextPageToken pagination."""

    def __init__(self, issues: list[dict], page_size: int = 2) -> None:
        self.issues = issues
        self.page_size = page_size
        self.search_calls: list[dict[str, Any]] = []

    def enhanced_search_issues(self, jql_str: str, **kwargs: Any) -> Any:  # noqa: ARG002
        self.search_calls.append(kwargs)
        token = kwargs.get("nextPageToken")
        start = int(token) if token else 0
        page = self.issues[start : start + self.page_size]
        if not kwargs.get("json_result"):
            return [_NotSubscriptable() for _ in page]
        response: dict[str, Any] = {"issues": page}
        next_start = start + self.page_size
        if next_start < len(self.issues):
            response["nextPageToken"] = str(next_start)
            response["isLast"] = False
        else:
            response["isLast"] = True
        return response
