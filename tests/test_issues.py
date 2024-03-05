from datetime import datetime, timedelta

import pytest

from metrics.entity import Issue


@pytest.fixture()
def test_issue() -> Issue:
    return Issue(
        key="TEST-1",
        status="In progress",
        created_at=datetime(2021, 1, 1, 0, 0, 0),
        first_status_change_at=datetime(2021, 1, 1, 1, 0, 0),
        last_finish_status_at=datetime(2021, 1, 1, 2, 0, 0),
    )


def test_empty_issue() -> None:
    issue = Issue(
        key="TEST-1",
        status="New",
        created_at=datetime(2021, 1, 1, 0, 0, 0),
    )
    assert issue.first_status_change_at is None
    assert issue.last_finish_status_at is None
    assert issue.doers_x_periods is None
    assert issue.statuses_x_periods is None
    assert issue.was_done is False
    assert issue.lead_time is None
    assert issue.cycle_time is None


def test_issue_was_done(test_issue: Issue) -> None:
    assert test_issue.was_done is True


def test_issue_lead_time(test_issue: Issue) -> None:
    assert test_issue.lead_time == timedelta(hours=2)


def test_issue_cycle_time(test_issue: Issue) -> None:
    assert test_issue.cycle_time == timedelta(hours=1)
