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
        {},
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


def _issue_moving_through(
    *steps: tuple[str, str, str],
    resolution: str | None = None,
) -> dict:
    """Build a raw issue created 2024-01-01 from (date, from, to) status steps."""
    return {
        "key": "FLOW-1",
        "fields": {
            "created": "2024-01-01T00:00:00.000+0000",
            "status": {"name": steps[-1][2] if steps else "Open"},
            "resolution": {"name": resolution} if resolution else None,
        },
        "changelog": {
            "histories": [
                {
                    "created": f"{day}T00:00:00.000+0000",
                    "items": [
                        {"field": "status", "fromString": frm, "toString": to},
                    ],
                }
                for day, frm, to in steps
            ],
        },
    }


def test_converter_reopened_issue_is_no_longer_done():
    issue = JiraDataConverter().convert_data_to_issue(
        _issue_moving_through(
            ("2024-01-02", "Open", "In Progress"),
            ("2024-01-03", "In Progress", "Done"),
            ("2024-01-10", "Done", "In Progress"),
        ),
    )
    assert not issue.was_done
    assert issue.is_open
    assert issue.cycle_time is None


def test_converter_reopened_and_finished_again_uses_last_finish():
    issue = JiraDataConverter().convert_data_to_issue(
        _issue_moving_through(
            ("2024-01-02", "Open", "In Progress"),
            ("2024-01-03", "In Progress", "Done"),
            ("2024-01-10", "Done", "In Progress"),
            ("2024-01-12", "In Progress", "Done"),
        ),
    )
    assert issue.last_finish_status_at == datetime(2024, 1, 12, tzinfo=UTC)
    assert issue.cycle_time == timedelta(days=10)


def test_converter_cancelled_issue_is_discarded_not_done():
    issue = JiraDataConverter().convert_data_to_issue(
        _issue_moving_through(
            ("2024-01-02", "Open", "Backlog"),
            ("2024-06-01", "Backlog", "Cancelled"),
        ),
    )
    assert issue.discarded
    assert not issue.was_done
    assert not issue.is_open
    assert issue.lead_time is None
    assert issue.cycle_time is None


def test_converter_accepts_custom_discarded_statuses():
    data_item = _issue_moving_through(("2024-01-02", "Open", "Rejected"))
    issue = JiraDataConverter(discarded_statuses=["rejected"]).convert_data_to_issue(
        data_item,
    )
    assert issue.discarded
    assert not JiraDataConverter().convert_data_to_issue(data_item).discarded


def test_converter_restored_discarded_issue_is_open_again():
    issue = JiraDataConverter().convert_data_to_issue(
        _issue_moving_through(
            ("2024-01-02", "Open", "Cancelled"),
            ("2024-01-05", "Cancelled", "Open"),
        ),
    )
    assert not issue.discarded
    assert issue.is_open


def test_converter_backlog_triage_does_not_start_cycle_time():
    issue = JiraDataConverter().convert_data_to_issue(
        _issue_moving_through(
            ("2024-01-02", "Open", "Backlog"),
            ("2024-01-10", "Backlog", "In Progress"),
            ("2024-01-12", "In Progress", "Done"),
        ),
    )
    assert issue.started_at == datetime(2024, 1, 10, tzinfo=UTC)
    assert issue.cycle_time == timedelta(days=2)
    assert issue.lead_time == timedelta(days=11)


def test_converter_issue_closed_straight_from_backlog_has_no_cycle_time():
    issue = JiraDataConverter().convert_data_to_issue(
        _issue_moving_through(("2024-01-05", "Open", "Done")),
    )
    assert issue.was_done
    assert issue.started_at is None
    assert issue.cycle_time is None
    assert issue.lead_time == timedelta(days=4)


def test_converter_accepts_custom_backlog_statuses():
    data_item = _issue_moving_through(
        ("2024-01-02", "Open", "Ready"),
        ("2024-01-04", "Ready", "In Progress"),
    )
    issue = JiraDataConverter(backlog_statuses=["open", "ready"]).convert_data_to_issue(
        data_item,
    )
    assert issue.started_at == datetime(2024, 1, 4, tzinfo=UTC)
    default = JiraDataConverter().convert_data_to_issue(data_item)
    assert default.started_at == datetime(2024, 1, 2, tzinfo=UTC)


def test_converter_closed_as_wont_fix_is_discarded_not_done():
    issue = JiraDataConverter().convert_data_to_issue(
        _issue_moving_through(
            ("2024-01-02", "Open", "In Progress"),
            ("2024-01-05", "In Progress", "Closed"),
            resolution="Won't Fix",
        ),
    )
    assert issue.discarded
    assert not issue.was_done
    assert not issue.is_open
    assert issue.cycle_time is None


def test_converter_closed_as_fixed_stays_done():
    issue = JiraDataConverter().convert_data_to_issue(
        _issue_moving_through(
            ("2024-01-02", "Open", "In Progress"),
            ("2024-01-05", "In Progress", "Closed"),
            resolution="Fixed",
        ),
    )
    assert issue.was_done
    assert not issue.discarded


def test_converter_accepts_custom_discarded_resolutions():
    data_item = _issue_moving_through(
        ("2024-01-05", "Open", "Done"),
        resolution="Out of scope",
    )
    converter = JiraDataConverter(discarded_resolutions=["out of scope"])
    assert converter.convert_data_to_issue(data_item).discarded
    assert JiraDataConverter().convert_data_to_issue(data_item).was_done


def _issue_through_ids(*steps: tuple[str, str, str], current: str) -> dict:
    """Like _issue_moving_through, with status ids as Jira sends them."""
    raw = _issue_moving_through(*steps)
    for history in raw["changelog"]["histories"]:
        for item in history["items"]:
            item["from"] = f"id-{item['fromString']}"
            item["to"] = f"id-{item['toString']}"
    raw["fields"]["status"] = {"id": f"id-{current}", "name": current}
    return raw


CATEGORIES = {
    "id-New": "new",
    "id-Planning": "new",
    "id-Awaiting response": "new",
    "id-Waiting for review": "indeterminate",
    "id-Shipped": "done",
    "id-Cancelled": "done",
}


def test_status_category_new_does_not_start_cycle_time():
    raw = _issue_through_ids(
        ("2024-01-02", "New", "Planning"),
        ("2024-01-05", "Planning", "Awaiting response"),
        ("2024-01-10", "Awaiting response", "Waiting for review"),
        current="Waiting for review",
    )
    issue = JiraDataConverter().convert_data_to_issue(raw, CATEGORIES)
    assert issue.started_at == datetime(2024, 1, 10, tzinfo=UTC)
    # without categories the names are unknown, so Planning counts as started
    assert JiraDataConverter().convert_data_to_issue(raw).started_at == datetime(
        2024, 1, 2, tzinfo=UTC
    )


def test_status_category_done_finishes_a_status_named_anything():
    raw = _issue_through_ids(
        ("2024-01-02", "New", "Waiting for review"),
        ("2024-01-06", "Waiting for review", "Shipped"),
        current="Shipped",
    )
    issue = JiraDataConverter().convert_data_to_issue(raw, CATEGORIES)
    assert issue.last_finish_status_at == datetime(2024, 1, 6, tzinfo=UTC)
    assert issue.cycle_time == timedelta(days=4)


def test_discarded_status_names_win_over_the_done_category():
    raw = _issue_through_ids(
        ("2024-01-02", "New", "Cancelled"),
        current="Cancelled",
    )
    issue = JiraDataConverter().convert_data_to_issue(raw, CATEGORIES)
    assert issue.discarded
    assert not issue.was_done


def test_explicit_status_lists_override_categories():
    raw = _issue_through_ids(
        ("2024-01-02", "New", "Waiting for review"),
        ("2024-01-06", "Waiting for review", "Shipped"),
        current="Shipped",
    )
    converter = JiraDataConverter(
        backlog_statuses=["new", "waiting for review"],
        done_statuses=["done"],
    )
    issue = converter.convert_data_to_issue(raw, CATEGORIES)
    # by category work starts in Waiting for review and ends in Shipped
    assert issue.started_at == datetime(2024, 1, 6, tzinfo=UTC)
    assert not issue.was_done
