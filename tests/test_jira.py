from unittest.mock import MagicMock

from metrics.repository.converter import JiraDataConverter
from metrics.repository.jira import JiraAPIRepository, JiraIssuesRepository


def test_jiraapirepository_get_raw_data():
    mock_jira = MagicMock()
    mock_jira.search_issues.return_value = {"issues": [{"key": "ISSUE-1"}]}
    repo = JiraAPIRepository(mock_jira, "dummy jql")
    with MagicMock() as mock_get_issues:
        repo.get_raw_data = mock_get_issues
        result = repo.get_raw_data()
        mock_get_issues.assert_called_once()


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
