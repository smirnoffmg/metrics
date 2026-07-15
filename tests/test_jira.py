"""Tests for Jira repository implementations."""

from __future__ import annotations

from unittest.mock import MagicMock

from metrics.repository.converter import JiraDataConverter
from metrics.repository.jira import JiraAPIRepository, JiraIssuesRepository
from tests.fakes import FakeCloudJira, FakeJira, make_raw_issue


def test_jiraapirepository_cloud_uses_enhanced_search():
    fake = FakeCloudJira([make_raw_issue(f"ISSUE-{i}") for i in range(3)], page_size=2)
    repo = JiraAPIRepository(fake, "dummy jql", cloud=True)
    raw = repo.get_raw_data()
    assert [item["key"] for item in raw] == ["ISSUE-0", "ISSUE-1", "ISSUE-2"]


def test_jiraapirepository_get_raw_data():
    fake = FakeJira([make_raw_issue("ISSUE-1"), make_raw_issue("ISSUE-2")])
    repo = JiraAPIRepository(fake, "dummy jql")
    raw = repo.get_raw_data()
    assert [item["key"] for item in raw] == ["ISSUE-1", "ISSUE-2"]
    assert all(isinstance(item, dict) for item in raw)


def test_jiraissuesrepository_all():
    mock_api_repo = MagicMock()
    mock_api_repo.get_raw_data.return_value = [
        {
            "key": "ISSUE-1",
            "fields": {
                "created": "2024-01-01T00:00:00.000+0000",
                "status": {"name": "Done"},
            },
            "changelog": {"histories": []},
        },
    ]
    mock_converter = JiraDataConverter()
    repo = JiraIssuesRepository(mock_api_repo, mock_converter)
    issues = repo.all()
    assert len(issues) == 1
    assert issues[0].key == "ISSUE-1"
    mock_api_repo.get_raw_data.assert_called_once()
