from unittest.mock import MagicMock, patch

from jira.exceptions import JIRAError

from metrics.containers import Container
from metrics.repository.base import BaseIssuesRepository
from metrics.repository.jira import JiraAPIRepository
from metrics.utils import get_jira_client


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
        from datetime import datetime

        from metrics.entity.issues import Issue

        return Issue(
            key=data_item["key"],
            status=data_item["fields"]["status"]["name"],
            created_at=datetime(2024, 1, 1, 0, 0, 0),
        )


class MockJira:
    def __init__(self):
        self.called = False

    def search_issues(self, *args, **kwargs):
        self.called = True
        return {
            "total": 1,
            "issues": [
                {
                    "key": "ISSUE-1",
                    "fields": {
                        "created": "2024-01-01T00:00:00.000+0000",
                        "status": {"name": "Done"},
                    },
                    "changelog": {"histories": []},
                },
            ],
        }


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
    try:
        base.get_raw_data()
    except NotImplementedError:
        pass
    else:
        assert False, "Expected NotImplementedError"
    try:
        base.convert_data_to_issue({})
    except NotImplementedError:
        pass
    else:
        assert False, "Expected NotImplementedError"


def test_jiraapirepository_get_raw_data_and_convert():
    mock_jira = MockJira()
    repo = JiraAPIRepository(mock_jira, "dummy jql")
    raw = repo.get_raw_data()
    assert isinstance(raw, list)
    issue = repo.convert_data_to_issue(raw[0])
    assert issue.key == "ISSUE-1"
    assert issue.status == "Done"


def test_get_jira_client_success():
    with patch("metrics.utils.JIRA") as mock_jira:
        mock_jira.return_value = MagicMock(name="JIRA")
        client = get_jira_client("http://example.com", "token")
        assert client is mock_jira.return_value


def test_get_jira_client_failure():
    get_jira_client.cache_clear()
    with patch("metrics.utils.JIRA") as mock_jira:
        mock_jira.side_effect = JIRAError("fail connect")
        try:
            get_jira_client("http://example.com", "token")
        except RuntimeError as e:
            assert "fail connect" in str(e)
        else:
            assert False, "Expected RuntimeError"


def test_get_jira_client_generic_exception():
    get_jira_client.cache_clear()
    with patch("metrics.utils.JIRA") as mock_jira:
        mock_jira.side_effect = Exception("unexpected fail")
        try:
            get_jira_client("http://example.com", "token")
        except Exception as e:
            assert "unexpected fail" in str(e)
        else:
            assert False, "Expected Exception"


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
    from metrics.services.metrics import MetricsService
    from metrics.services.vis import VisService

    assert isinstance(metrics_service, MetricsService)
    assert isinstance(vis_service, VisService)
