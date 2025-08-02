from datetime import UTC, datetime

from metrics.repository.converter import JiraDataConverter


def test_jiradataconverter_convert_data_to_issue():
    converter = JiraDataConverter()
    data_item = {
        "key": "ISSUE-1",
        "fields": {
            "created": "2024-01-01T00:00:00.000+0000",
            "status": {"name": "Done"},
        },
        "changelog": {"histories": []},
    }
    issue = converter.convert_data_to_issue(data_item)
    assert issue.key == "ISSUE-1"
    assert issue.status == "Done"
    assert issue.created_at == datetime(2024, 1, 1, 0, 0, 0, tzinfo=UTC)


def test_jiradataconverter_parse_changelog_item():
    converter = JiraDataConverter()
    created_at = datetime(2024, 1, 1, 0, 0, 0, tzinfo=UTC)
    changelog = {
        "histories": [
            {
                "created": "2024-01-02T00:00:00.000+0000",
                "items": [
                    {
                        "field": "status",
                        "fromString": "To Do",
                        "toString": "In Progress",
                    },
                ],
            },
            {
                "created": "2024-01-03T00:00:00.000+0000",
                "items": [
                    {
                        "field": "assignee",
                        "fromString": "user1",
                        "toString": "user2",
                    },
                ],
            },
        ],
    }
    result = converter._parse_changelog_item(created_at, changelog)
    assert "To Do" in result["statuses_x_periods"]
    assert "user1" in result["doers_x_periods"]
    assert result["status_history"] == ["created", "In Progress"]
