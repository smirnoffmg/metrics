"""Tests for JiraDataConverter."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from metrics.entity.issues import StatusTransition
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
    result = converter._parse_changelog_item(  # noqa: SLF001
        created_at,
        changelog,
    )
    assert "To Do" in result["statuses_x_periods"]
    assert "user1" in result["doers_x_periods"]
    assert result["status_history"] == ["created", "In Progress"]


def test_converter_treats_resolved_as_done():
    converter = JiraDataConverter()
    data_item = {
        "key": "KAFKA-1",
        "fields": {
            "created": "2024-01-01T00:00:00.000+0000",
            "status": {"name": "Resolved"},
        },
        "changelog": {
            "histories": [
                {
                    "created": "2024-01-04T00:00:00.000+0000",
                    "items": [
                        {
                            "field": "status",
                            "fromString": "Patch Available",
                            "toString": "Resolved",
                        },
                    ],
                },
            ],
        },
    }
    issue = converter.convert_data_to_issue(data_item)
    assert issue.was_done
    assert issue.last_finish_status_at == datetime(2024, 1, 4, tzinfo=UTC)


def test_converter_accepts_custom_done_statuses():
    converter = JiraDataConverter(done_statuses=["geschlossen"])
    data_item = {
        "key": "DE-1",
        "fields": {
            "created": "2024-01-01T00:00:00.000+0000",
            "status": {"name": "Geschlossen"},
        },
        "changelog": {
            "histories": [
                {
                    "created": "2024-01-04T00:00:00.000+0000",
                    "items": [
                        {
                            "field": "status",
                            "fromString": "In Arbeit",
                            "toString": "Geschlossen",
                        },
                    ],
                },
            ],
        },
    }
    issue = converter.convert_data_to_issue(data_item)
    assert issue.was_done

    default_converter = JiraDataConverter()
    assert not default_converter.convert_data_to_issue(data_item).was_done


def test_converter_credits_trailing_period_to_current_assignee():
    converter = JiraDataConverter()
    data_item = {
        "key": "HHH-1",
        "fields": {
            "created": "2024-01-01T00:00:00.000+0000",
            "status": {"name": "Done"},
            "assignee": {"displayName": "alice"},
        },
        "changelog": {
            "histories": [
                {
                    "created": "2024-01-02T00:00:00.000+0000",
                    "items": [
                        {
                            "field": "assignee",
                            "fromString": "bob",
                            "toString": "alice",
                        },
                    ],
                },
                {
                    "created": "2024-01-05T00:00:00.000+0000",
                    "items": [
                        {
                            "field": "status",
                            "fromString": "In Progress",
                            "toString": "Done",
                        },
                    ],
                },
            ],
        },
    }
    issue = converter.convert_data_to_issue(data_item)
    assert issue.doers_x_periods["bob"] == timedelta(days=1)
    assert issue.doers_x_periods["alice"] == timedelta(days=3)


def test_converter_credits_never_reassigned_issue_to_its_assignee():
    converter = JiraDataConverter()
    data_item = {
        "key": "HHH-2",
        "fields": {
            "created": "2024-01-01T00:00:00.000+0000",
            "status": {"name": "Done"},
            "assignee": {"displayName": "steve"},
        },
        "changelog": {
            "histories": [
                {
                    "created": "2024-01-04T00:00:00.000+0000",
                    "items": [
                        {
                            "field": "status",
                            "fromString": "In Progress",
                            "toString": "Done",
                        },
                    ],
                },
            ],
        },
    }
    issue = converter.convert_data_to_issue(data_item)
    assert issue.doers_x_periods == {"steve": timedelta(days=3)}


def test_converter_handles_unassigned_issue():
    converter = JiraDataConverter()
    data_item = {
        "key": "HHH-3",
        "fields": {
            "created": "2024-01-01T00:00:00.000+0000",
            "status": {"name": "New"},
            "assignee": None,
        },
        "changelog": {"histories": []},
    }
    issue = converter.convert_data_to_issue(data_item)
    assert issue.doers_x_periods == {}


def test_converter_records_status_transitions_and_handoffs():
    converter = JiraDataConverter()
    data_item = {
        "key": "ISSUE-1",
        "fields": {
            "created": "2024-01-01T00:00:00.000+0000",
            "status": {"name": "Done"},
        },
        "changelog": {
            "histories": [
                {
                    "created": "2024-01-02T00:00:00.000+0000",
                    "items": [
                        {
                            "field": "status",
                            "fromString": "To Do",
                            "toString": "In Progress",
                        },
                        {
                            "field": "assignee",
                            "fromString": "user1",
                            "toString": "user2",
                        },
                    ],
                },
                {
                    "created": "2024-01-05T00:00:00.000+0000",
                    "items": [
                        {
                            "field": "assignee",
                            "fromString": "user2",
                            "toString": "user3",
                        },
                        {
                            "field": "status",
                            "fromString": "In Progress",
                            "toString": "Done",
                        },
                    ],
                },
            ],
        },
    }
    issue = converter.convert_data_to_issue(data_item)
    assert issue.status_transitions == [
        StatusTransition(
            at=datetime(2024, 1, 2, 0, 0, 0, tzinfo=UTC),
            from_status="To Do",
            to_status="In Progress",
        ),
        StatusTransition(
            at=datetime(2024, 1, 5, 0, 0, 0, tzinfo=UTC),
            from_status="In Progress",
            to_status="Done",
        ),
    ]
    expected_handoffs = 2
    assert issue.handoffs == expected_handoffs
