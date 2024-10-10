from datetime import UTC, datetime, timedelta
from typing import Final

import pytest

from metrics.repository.jira import parse_changelog_item

INITIAL_TS: Final[datetime] = datetime(2021, 1, 1, 0, 0, 0, tzinfo=UTC)


@pytest.fixture()
def changelog_w_assignee_change() -> dict:
    return {
        "histories": [
            {
                "created": "2021-01-01T01:00:00.000+0000",
                "items": [
                    {
                        "field": "assignee",
                        "fromString": "Bob",
                        "toString": "Alice",
                    },
                ],
            },
            {
                "created": "2021-01-01T02:00:00.000+0000",
                "items": [
                    {
                        "field": "assignee",
                        "fromString": "Alice",
                        "toString": "Bob",
                    },
                ],
            },
        ],
    }


@pytest.fixture()
def changelog_w_status_change() -> dict:
    return {
        "histories": [
            {
                "created": "2021-01-01T01:00:00.000+0000",
                "items": [
                    {
                        "field": "status",
                        "fromString": "To Do",
                        "toString": "In Progress",
                    },
                ],
            },
            {
                "created": "2021-01-01T02:00:00.000+0000",
                "items": [
                    {
                        "field": "status",
                        "fromString": "In Progress",
                        "toString": "Testing",
                    },
                ],
            },
            {
                "created": "2021-01-01T03:00:00.000+0000",
                "items": [
                    {
                        "field": "status",
                        "fromString": "Testing",
                        "toString": "Done",
                    },
                ],
            },
        ],
    }


def test_parse_changelog_item_assignee(changelog_w_assignee_change: dict) -> None:
    parsed = parse_changelog_item(
        issue_created_at=INITIAL_TS,
        changelog=changelog_w_assignee_change,
    )
    assert parsed["doers_x_periods"]["Bob"] == timedelta(hours=1)
    assert parsed["doers_x_periods"]["Alice"] == timedelta(hours=1)

    assert parsed["first_assignee_changed_at"] == datetime(2021, 1, 1, 1, 0, tzinfo=UTC)
    assert parsed["last_assignee_changed_at"] == datetime(2021, 1, 1, 2, 0, tzinfo=UTC)


def test_parse_changelog_item_status(changelog_w_status_change: dict) -> None:
    parsed = parse_changelog_item(
        issue_created_at=INITIAL_TS,
        changelog=changelog_w_status_change,
    )
    assert parsed["statuses_x_periods"]["To Do"] == timedelta(hours=1)
    assert parsed["statuses_x_periods"]["In Progress"] == timedelta(hours=1)
    assert parsed["statuses_x_periods"]["Testing"] == timedelta(hours=1)

    assert parsed["first_status_changed_at"] == datetime(2021, 1, 1, 1, 0, tzinfo=UTC)
    assert parsed["last_status_changed_at"] == datetime(2021, 1, 1, 3, 0, tzinfo=UTC)
    assert parsed["last_finish_status_at"] == datetime(2021, 1, 1, 3, 0, tzinfo=UTC)


def test_parse_changelog_item_no_changes() -> None:
    parsed = parse_changelog_item(
        issue_created_at=INITIAL_TS,
        changelog={"histories": []},
    )
    assert parsed["doers_x_periods"] == {}
    assert parsed["statuses_x_periods"] == {}

    assert parsed["first_status_changed_at"] is None
    assert parsed["last_status_changed_at"] == INITIAL_TS
    assert parsed["first_assignee_changed_at"] is None
    assert parsed["last_assignee_changed_at"] == INITIAL_TS
    assert parsed["last_finish_status_at"] is None


def test_parse_changelog_no_status_change(changelog_w_assignee_change: dict) -> None:
    parsed = parse_changelog_item(
        issue_created_at=INITIAL_TS,
        changelog=changelog_w_assignee_change,
    )
    assert parsed["statuses_x_periods"] == {}
    assert parsed["first_status_changed_at"] is None
    assert parsed["last_status_changed_at"] == INITIAL_TS
    assert parsed["last_finish_status_at"] is None


def test_parse_changelog_no_assignee_change(changelog_w_status_change: dict) -> None:
    parsed = parse_changelog_item(
        issue_created_at=INITIAL_TS,
        changelog=changelog_w_status_change,
    )
    assert parsed["doers_x_periods"] == {}
    assert parsed["first_assignee_changed_at"] is None
    assert parsed["last_assignee_changed_at"] == INITIAL_TS
