"""Tests for rewinding raw Jira issues to an earlier moment."""

from __future__ import annotations

from datetime import UTC, datetime

from metrics.repository.converter import JiraDataConverter
from metrics.repository.rewind import rewind_issue


def _history(created: str, field: str, from_: tuple, to: tuple) -> dict:
    return {
        "created": created,
        "items": [
            {
                "field": field,
                "from": from_[0],
                "fromString": from_[1],
                "to": to[0],
                "toString": to[1],
            },
        ],
    }


def _reopened_issue() -> dict:
    """Created 1 Jan, done 10 Jan as Fixed, reopened 20 Jan, done again 30 Jan."""
    return {
        "key": "X-1",
        "fields": {
            "created": "2024-01-01T00:00:00.000+0000",
            "status": {"id": "6", "name": "Done"},
            "resolution": {"name": "Fixed"},
            "assignee": {"displayName": "Carol"},
        },
        "changelog": {
            "histories": [
                _history(
                    "2024-01-05T00:00:00.000+0000",
                    "status",
                    ("1", "Open"),
                    ("3", "In Progress"),
                ),
                _history(
                    "2024-01-10T00:00:00.000+0000",
                    "status",
                    ("3", "In Progress"),
                    ("6", "Done"),
                ),
                _history(
                    "2024-01-10T00:00:00.000+0000",
                    "resolution",
                    (None, None),
                    ("1", "Fixed"),
                ),
                _history(
                    "2024-01-20T00:00:00.000+0000",
                    "status",
                    ("6", "Done"),
                    ("4", "Reopened"),
                ),
                _history(
                    "2024-01-20T00:00:00.000+0000",
                    "resolution",
                    ("1", "Fixed"),
                    (None, None),
                ),
                _history(
                    "2024-01-25T00:00:00.000+0000",
                    "assignee",
                    ("bob", "Bob"),
                    ("carol", "Carol"),
                ),
                _history(
                    "2024-01-30T00:00:00.000+0000",
                    "status",
                    ("4", "Reopened"),
                    ("6", "Done"),
                ),
                _history(
                    "2024-01-30T00:00:00.000+0000",
                    "resolution",
                    (None, None),
                    ("1", "Fixed"),
                ),
            ],
        },
    }


def test_an_issue_not_created_yet_is_left_out():
    assert rewind_issue(_reopened_issue(), datetime(2023, 12, 31, tzinfo=UTC)) is None


def test_rewinding_to_now_changes_nothing():
    raw = _reopened_issue()
    assert rewind_issue(raw, datetime(2024, 2, 1, tzinfo=UTC)) == raw


def test_rewound_issue_keeps_only_history_up_to_the_moment():
    rewound = rewind_issue(_reopened_issue(), datetime(2024, 1, 15, tzinfo=UTC))
    assert rewound is not None
    assert [h["created"][:10] for h in rewound["changelog"]["histories"]] == [
        "2024-01-05",
        "2024-01-10",
        "2024-01-10",
    ]


def test_rewound_fields_hold_the_values_from_before_later_changes():
    rewound = rewind_issue(_reopened_issue(), datetime(2024, 1, 22, tzinfo=UTC))
    assert rewound is not None
    assert rewound["fields"]["status"] == {"id": "4", "name": "Reopened"}
    assert rewound["fields"]["resolution"] is None
    assert rewound["fields"]["assignee"] == {"displayName": "Bob"}


def test_rewinding_leaves_the_original_untouched():
    raw = _reopened_issue()
    rewind_issue(raw, datetime(2024, 1, 3, tzinfo=UTC))
    assert raw == _reopened_issue()


def test_rewound_issue_converts_to_what_jira_showed_then():
    converter = JiraDataConverter(done_statuses=["done"])
    raw = _reopened_issue()

    finished = rewind_issue(raw, datetime(2024, 1, 15, tzinfo=UTC))
    reopened = rewind_issue(raw, datetime(2024, 1, 22, tzinfo=UTC))
    assert finished is not None
    assert reopened is not None

    then = converter.convert_data_to_issue(finished)
    assert then.last_finish_status_at == datetime(2024, 1, 10, tzinfo=UTC)
    assert then.status == "Done"
    assert converter.convert_data_to_issue(reopened).is_open
