"""Tests for repository utilities and container wiring."""

from __future__ import annotations

from datetime import datetime
from unittest.mock import MagicMock, patch

import pytest
from jira.exceptions import JIRAError

from metrics.containers import Container
from metrics.entity.issues import Issue
from metrics.repository.base import BaseIssuesRepository
from metrics.repository.jira import JiraIssuesRepository
from metrics.repository.utils import (
    get_issues,
    get_issues_cloud,
    get_issues_slice,
    get_issues_total,
)
from metrics.services.metrics import MetricsService
from metrics.services.vis import VisService
from metrics.utils import get_jira_client
from tests.fakes import FakeCloudJira, FakeJira, make_raw_issue


class DummyBaseRepo(BaseIssuesRepository):
    def get_raw_data(self):
        return [
            {
                "key": "ISSUE-1",
                "fields": {
                    "created": "2024-01-01T00:00:00.000+0000",
                    "status": {"name": "Done"},
                },
                "changelog": {"histories": []},
            },
        ]

    def convert_data_to_issue(self, data_item):
        return Issue(
            key=data_item["key"],
            status=data_item["fields"]["status"]["name"],
            created_at=datetime(2024, 1, 1, 0, 0, 0),
        )


def test_get_issues_total_counts_without_fetching_pages():
    issue_count = 3
    fake = FakeJira([make_raw_issue(f"ISSUE-{i}") for i in range(issue_count)])
    total = get_issues_total(fake, "project=TEST")
    assert total == issue_count
    (call,) = fake.search_calls
    assert call.get("json_result") is True
    assert call.get("maxResults") == 1


def test_get_issues_slice_returns_raw_dicts():
    fake = FakeJira([make_raw_issue(f"ISSUE-{i}") for i in range(5)])
    result = get_issues_slice(fake, "project=TEST", offset=2, limit=2)
    assert [item["key"] for item in result] == ["ISSUE-2", "ISSUE-3"]


def test_get_issues_fetches_all_pages_as_dicts():
    issue_count = 120
    issues = [make_raw_issue(f"ISSUE-{i}") for i in range(issue_count)]
    fake = FakeJira(issues)
    result = get_issues(fake, "project=TEST")
    assert len(result) == issue_count
    assert {item["key"] for item in result} == {issue["key"] for issue in issues}


def test_baseissuesrepository_get_and_all():
    repo = DummyBaseRepo()
    all_issues = repo.all()
    assert isinstance(all_issues, list)
    assert repo.get("ISSUE-1") is not None
    assert repo.get("NONEXISTENT") is None


def test_baseissuesrepository_not_implemented():
    class DummyBase(BaseIssuesRepository):
        def get_issues(self):
            return []

    base = DummyBase()
    with pytest.raises(NotImplementedError):
        base.get_raw_data()
    with pytest.raises(NotImplementedError):
        base.convert_data_to_issue({})


def test_get_jira_client_success():
    with patch("metrics.utils.JIRA") as mock_jira:
        mock_jira.return_value = MagicMock(name="JIRA")
        client = get_jira_client("http://example.com", "token")
        assert client is mock_jira.return_value


def test_get_jira_client_failure():
    get_jira_client.cache_clear()
    with patch("metrics.utils.JIRA") as mock_jira:
        mock_jira.side_effect = JIRAError("fail connect")
        with pytest.raises(RuntimeError, match="fail connect"):
            get_jira_client("http://example.com", "token")


def test_get_jira_client_generic_exception():
    get_jira_client.cache_clear()
    with patch("metrics.utils.JIRA") as mock_jira:
        mock_jira.side_effect = Exception("unexpected fail")
        with pytest.raises(Exception, match="unexpected fail"):
            get_jira_client("http://example.com", "token")


def test_get_issues_cloud_follows_next_page_token():
    issue_count = 5
    issues = [make_raw_issue(f"ISSUE-{i}") for i in range(issue_count)]
    fake = FakeCloudJira(issues, page_size=2)
    result = get_issues_cloud(fake, "project=TEST")
    expected_keys = [f"ISSUE-{i}" for i in range(issue_count)]
    assert [item["key"] for item in result] == expected_keys
    expected_pages = 3
    assert len(fake.search_calls) == expected_pages
    assert fake.search_calls[0].get("nextPageToken") is None
    assert all(call.get("json_result") is True for call in fake.search_calls)


def test_get_jira_client_cloud_uses_basic_auth():
    get_jira_client.cache_clear()
    with patch("metrics.utils.JIRA") as mock_jira:
        get_jira_client("https://x.atlassian.net", "token", "me@example.com")
        mock_jira.assert_called_once_with(
            server="https://x.atlassian.net",
            basic_auth=("me@example.com", "token"),
        )


def test_get_jira_client_anonymous_sends_no_auth():
    get_jira_client.cache_clear()
    with patch("metrics.utils.JIRA") as mock_jira:
        get_jira_client("https://public.jira", None, None, anonymous=True)
        mock_jira.assert_called_once_with(server="https://public.jira")


def test_get_jira_client_server_uses_token_auth():
    get_jira_client.cache_clear()
    with patch("metrics.utils.JIRA") as mock_jira:
        get_jira_client("https://jira.corp", "token")
        mock_jira.assert_called_once_with(
            server="https://jira.corp",
            token_auth="token",  # noqa: S106
        )


def test_container_resolves_metrics_service_with_single_fetch():
    with patch.object(
        JiraIssuesRepository,
        "get_raw_data",
        return_value=[],
    ) as mock_fetch:
        container = Container()
        container.jira.override(MagicMock(name="JIRA"))
        container.config.from_dict(
            {
                "jira": {
                    "server": "http://example.com",
                    "token": "dummy-token",
                    "jql": "project=TEST",
                },
            },
        )
        container.metrics_service()
        assert mock_fetch.call_count == 1


def test_container_provides_services():
    container = Container()
    container.jira.override(MagicMock(name="JIRA"))
    container.config.from_dict(
        {
            "jira": {
                "server": "http://example.com",
                "token": "dummy-token",
                "jql": "project=TEST",
            },
        },
    )
    container.init_resources()
    metrics_service = container.metrics_service()
    vis_service = container.vis_service()

    assert isinstance(metrics_service, MetricsService)
    assert isinstance(vis_service, VisService)
    assert metrics_service.cycle_time_calculator is not None
    assert metrics_service.lead_time_calculator is not None
    assert metrics_service.queue_time_calculator is not None
    assert metrics_service.throughput_calculator is not None
    assert metrics_service.cumulative_queue_time_calculator is not None
    assert metrics_service.return_to_testing_calculator is not None
