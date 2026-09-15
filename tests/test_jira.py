"""Tests for Jira repository implementations."""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import MagicMock

from metrics.repository.converter import JiraDataConverter
from metrics.repository.jira import JiraAPIRepository, JiraIssuesRepository
from metrics.repository.snapshot import Snapshot
from tests.fakes import FakeCloudJira, FakeJira, FakeStatus, make_raw_issue


def test_jiraapirepository_cloud_uses_enhanced_search():
    fake = FakeCloudJira([make_raw_issue(f"ISSUE-{i}") for i in range(3)], page_size=2)
    repo = JiraAPIRepository(fake, "dummy jql", cloud=True)
    raw = repo.get_raw_data()
    assert [item["key"] for item in raw] == ["ISSUE-0", "ISSUE-1", "ISSUE-2"]


def test_jiraapirepository_autodetects_cloud():
    fake = FakeCloudJira([make_raw_issue("ISSUE-0")], page_size=50)
    repo = JiraAPIRepository(fake, "dummy jql", cloud=None)
    assert [item["key"] for item in repo.get_raw_data()] == ["ISSUE-0"]


def test_jiraapirepository_autodetects_server():
    fake = FakeJira([make_raw_issue("ISSUE-0")])
    repo = JiraAPIRepository(fake, "dummy jql", cloud=None)
    assert [item["key"] for item in repo.get_raw_data()] == ["ISSUE-0"]


def test_jiraapirepository_get_raw_data():
    fake = FakeJira([make_raw_issue("ISSUE-1"), make_raw_issue("ISSUE-2")])
    repo = JiraAPIRepository(fake, "dummy jql")
    raw = repo.get_raw_data()
    assert [item["key"] for item in raw] == ["ISSUE-1", "ISSUE-2"]
    assert all(isinstance(item, dict) for item in raw)


def test_jiraissuesrepository_all():
    mock_api_repo = MagicMock()
    mock_api_repo.get_snapshot.return_value = Snapshot(
        server="https://jira.example",
        jql="project = X",
        fetched_at=datetime(2024, 1, 2, tzinfo=UTC),
        issues=[make_raw_issue("ISSUE-1")],
    )
    mock_converter = JiraDataConverter()
    repo = JiraIssuesRepository(mock_api_repo, mock_converter)
    issues = repo.all()
    assert len(issues) == 1
    assert issues[0].key == "ISSUE-1"
    mock_api_repo.get_snapshot.assert_called_once()


def test_snapshot_carries_status_categories():
    fake = FakeJira(
        [make_raw_issue("X-1")],
        statuses=[FakeStatus("1", "Open", "new"), FakeStatus("6", "Closed", "done")],
    )
    snapshot = JiraAPIRepository(fake, "project = X", cloud=False).get_snapshot()
    assert snapshot.statuses == {"1": "new", "6": "done"}


def test_repository_learns_categories_of_statuses_the_status_list_missed():
    issue = make_raw_issue("X-1")
    issue["fields"]["status"] = {
        "id": "10500",
        "name": "Shipped",
        "statusCategory": {"key": "done"},
    }
    issue["changelog"]["histories"] = [
        {
            "created": "2024-01-03T00:00:00.000+0000",
            "items": [
                {
                    "field": "status",
                    "from": "1",
                    "fromString": "Open",
                    "to": "10500",
                    "toString": "Shipped",
                },
            ],
        },
    ]
    source = MagicMock()
    source.get_snapshot.return_value = Snapshot(
        server="https://jira.example",
        jql="project = X",
        fetched_at=datetime(2024, 1, 5, tzinfo=UTC),
        issues=[issue],
        statuses={"1": "new"},
    )
    repo = JiraIssuesRepository(source, JiraDataConverter())
    assert repo.all()[0].was_done


def test_snapshot_carries_the_issues_to_forecast():
    fake = FakeJira(
        [make_raw_issue("X-1"), make_raw_issue("X-2")],
        by_jql={"fixVersion = 7.2": [make_raw_issue("X-2")]},
    )
    snapshot = JiraAPIRepository(
        fake,
        "project = X",
        forecast_jql="fixVersion = 7.2",
        cloud=False,
    ).get_snapshot()
    assert snapshot.forecast_jql == "fixVersion = 7.2"
    assert [item["key"] for item in snapshot.forecast_issues] == ["X-2"]


def test_snapshot_without_a_forecast_query_fetches_nothing_more():
    fake = FakeJira([make_raw_issue("X-1")])
    snapshot = JiraAPIRepository(fake, "project = X", cloud=False).get_snapshot()
    assert snapshot.forecast_issues == []
    assert len(fake.search_calls) == 2  # noqa: PLR2004 - total, then one page


def test_repository_converts_the_issues_to_forecast():
    source = MagicMock()
    source.get_snapshot.return_value = Snapshot(
        server="https://jira.example",
        jql="project = X",
        fetched_at=datetime(2024, 1, 5, tzinfo=UTC),
        issues=[make_raw_issue("X-1")],
        forecast_jql="fixVersion = 7.2",
        forecast_issues=[make_raw_issue("X-2"), make_raw_issue("X-3")],
    )
    repo = JiraIssuesRepository(source, JiraDataConverter())
    assert [issue.key for issue in repo.forecast_issues()] == ["X-2", "X-3"]
