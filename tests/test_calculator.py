"""Tests for metric functions."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

import pandas as pd
import pytest

from metrics.entity.issues import Issue, StatusTransition
from metrics.services.calculator import (
    aging_wip,
    assignee_load,
    cumulative_flow,
    cycle_time_points,
    cycle_times,
    flow_efficiency,
    lead_times,
    median_queue_hours,
    monte_carlo_forecast,
    queue_times,
    returns_to_testing,
    weekly_throughput,
)


def test_cycle_times(dummy_issue):
    result = cycle_times([dummy_issue])
    assert isinstance(result, list)
    assert result[0] >= 1


def test_lead_times(dummy_issue):
    result = lead_times([dummy_issue])
    assert isinstance(result, list)
    assert result[0] >= 1


def test_queue_times(dummy_issue):
    result = queue_times([dummy_issue])
    assert isinstance(result, dict)
    assert any(isinstance(v, list) for v in result.values())


def test_weekly_throughput(dummy_issue):
    result = weekly_throughput([dummy_issue])
    assert isinstance(result, dict)
    assert all(isinstance(k, str) for k in result)
    assert all(isinstance(v, int) for v in result.values())


def _finished_on(*finished_at):
    return [
        Issue(
            key=f"ISSUE-{i}",
            status="Done",
            created_at=finish - timedelta(days=1),
            last_finish_status_at=finish,
        )
        for i, finish in enumerate(finished_at)
    ]


def test_throughput_calculator_uses_iso_year_for_week_key():
    issues = _finished_on(datetime(2025, 12, 29, 12, 0, 0, tzinfo=UTC))
    result = weekly_throughput(issues, now=datetime(2026, 1, 5, tzinfo=UTC))
    assert result == {"2026W01": 1}


def test_throughput_calculator_sorted_with_gap_weeks_zero_filled():
    issues = _finished_on(
        datetime(2024, 1, 17, 12, 0, 0, tzinfo=UTC),
        datetime(2024, 1, 3, 12, 0, 0, tzinfo=UTC),
        datetime(2024, 1, 3, 18, 0, 0, tzinfo=UTC),
    )
    result = weekly_throughput(issues, now=datetime(2024, 1, 22, tzinfo=UTC))
    assert list(result.items()) == [
        ("2024W01", 2),
        ("2024W02", 0),
        ("2024W03", 1),
    ]


def test_throughput_leaves_out_the_week_still_in_progress():
    issues = _finished_on(
        datetime(2024, 1, 3, 12, 0, 0, tzinfo=UTC),
        datetime(2024, 1, 16, 12, 0, 0, tzinfo=UTC),
    )
    result = weekly_throughput(issues, now=datetime(2024, 1, 17, tzinfo=UTC))
    assert list(result.items()) == [("2024W01", 1), ("2024W02", 0)]


def test_throughput_counts_idle_weeks_up_to_now():
    issues = _finished_on(datetime(2024, 1, 3, 12, 0, 0, tzinfo=UTC))
    result = weekly_throughput(issues, now=datetime(2024, 1, 31, tzinfo=UTC))
    assert list(result.items()) == [
        ("2024W01", 1),
        ("2024W02", 0),
        ("2024W03", 0),
        ("2024W04", 0),
    ]


def test_weekly_throughput_without_issues():
    assert weekly_throughput([]) == {}


def test_queue_times_handle_issue_without_status_periods():
    issue = Issue(key="ISSUE-1", status="New", created_at=datetime(2024, 1, 1))
    assert queue_times([issue]) == {}
    assert median_queue_hours([issue]).empty


def test_median_queue_hours(dummy_issue):
    result = median_queue_hours([dummy_issue])
    assert isinstance(result, pd.DataFrame)
    assert set(result.columns) == {"status", "median_hours", "count"}


def test_returns_to_testing(dummy_issue):
    assert isinstance(returns_to_testing([dummy_issue]), list)


def test_return_to_testing_with_custom_statuses():
    bounced = Issue(
        key="A",
        status="Done",
        created_at=datetime(2024, 1, 1, tzinfo=UTC),
        status_history=["created", "In review", "In Progress", "In review", "Done"],
    )
    straight = Issue(
        key="B",
        status="Done",
        created_at=datetime(2024, 1, 1, tzinfo=UTC),
        status_history=["created", "In review", "Done"],
    )
    assert returns_to_testing([bounced, straight], ["In Review"]) == [2]


def test_cycle_time_scatter_uncapped_days():
    done = Issue(
        key="A",
        status="Done",
        created_at=datetime(2024, 1, 1, tzinfo=UTC),
        started_at=datetime(2024, 1, 1, tzinfo=UTC),
        last_finish_status_at=datetime(2024, 3, 1, tzinfo=UTC),
    )
    open_issue = Issue(
        key="B",
        status="New",
        created_at=datetime(2024, 1, 1, tzinfo=UTC),
    )
    df = cycle_time_points([done, open_issue])
    assert list(df.columns) == ["key", "finished_at", "cycle_time_days"]
    assert len(df) == 1
    assert df.iloc[0]["key"] == "A"
    assert df.iloc[0]["finished_at"] == datetime(2024, 3, 1, tzinfo=UTC)
    assert df.iloc[0]["cycle_time_days"] == 60.0  # noqa: PLR2004


def _open_issues(n, started_at=None):
    return [
        Issue(
            key=f"O-{i}",
            status="New",
            created_at=datetime(2024, 1, 1, tzinfo=UTC),
            started_at=started_at,
        )
        for i in range(n)
    ]


def test_monte_carlo_constant_throughput_is_deterministic():
    throughput = {f"2024W{w:02d}": 2 for w in range(1, 7)}
    result = monte_carlo_forecast(
        _open_issues(6),
        throughput,
        simulations=200,
        seed=42,
        now=datetime(2026, 7, 15, tzinfo=UTC),
    )
    expected_weeks = 3.0
    assert result["backlog"] == 6  # noqa: PLR2004
    assert result["p50"] == expected_weeks
    assert result["p85"] == expected_weeks
    assert result["p95"] == expected_weeks
    assert result["p50_date"] == date(2026, 8, 5)
    assert result["p85_date"] == date(2026, 8, 5)
    assert result["p95_date"] == date(2026, 8, 5)
    assert len(result["weeks"]) == 200  # noqa: PLR2004


def test_monte_carlo_forecast_scales_throughput_by_focus():
    throughput = {f"2024W{w:02d}": 2 for w in range(1, 7)}
    result = monte_carlo_forecast(
        _open_issues(6),
        throughput,
        simulations=100,
        seed=1,
        now=datetime(2026, 7, 15, tzinfo=UTC),
        focus=0.5,
    )
    assert result["p85"] == 6.0  # noqa: PLR2004
    assert result["focus"] == 0.5  # noqa: PLR2004


@pytest.mark.parametrize("focus", [0.0, -0.5, 1.5])
def test_monte_carlo_forecast_rejects_a_focus_outside_its_range(focus):
    with pytest.raises(ValueError, match="focus"):
        monte_carlo_forecast(_open_issues(1), {"2024W01": 1}, focus=focus)


def test_flow_efficiency_share_of_active_time():
    done = Issue(
        key="A",
        status="Done",
        created_at=datetime(2024, 1, 1, tzinfo=UTC),
        started_at=datetime(2024, 1, 1, tzinfo=UTC),
        last_finish_status_at=datetime(2024, 1, 9, tzinfo=UTC),
        statuses_x_periods={
            "In Progress": timedelta(days=2),
            "Waiting for review": timedelta(days=6),
        },
    )
    still_open = Issue(
        key="B",
        status="In Progress",
        created_at=datetime(2024, 1, 1, tzinfo=UTC),
        statuses_x_periods={"In Progress": timedelta(days=100)},
    )
    assert flow_efficiency([done, still_open], ["In Progress"]) == 0.25  # noqa: PLR2004


def test_flow_efficiency_ignores_waiting_before_work_started():
    done = Issue(
        key="A",
        status="Done",
        created_at=datetime(2024, 1, 1, tzinfo=UTC),
        started_at=datetime(2024, 4, 1, tzinfo=UTC),
        last_finish_status_at=datetime(2024, 4, 3, tzinfo=UTC),
        statuses_x_periods={
            "Open": timedelta(days=91),
            "In Progress": timedelta(days=2),
        },
    )
    assert flow_efficiency([done], ["In Progress"]) == 1.0


def test_flow_efficiency_skips_issues_closed_without_being_started():
    closed_from_backlog = Issue(
        key="A",
        status="Done",
        created_at=datetime(2024, 1, 1, tzinfo=UTC),
        last_finish_status_at=datetime(2024, 1, 9, tzinfo=UTC),
        statuses_x_periods={"Open": timedelta(days=8)},
    )
    assert flow_efficiency([closed_from_backlog, _finished_after(2)]) == 1.0


def test_flow_efficiency_without_issues():
    assert flow_efficiency([]) == 0.0


def test_monte_carlo_samples_only_recent_weeks():
    old_pace = {f"2023W{w:02d}": 10 for w in range(1, 31)}
    recent_pace = {f"2024W{w:02d}": 1 for w in range(1, 13)}
    result = monte_carlo_forecast(
        _open_issues(6),
        {**old_pace, **recent_pace},
        simulations=100,
        seed=1,
        now=datetime(2024, 3, 25, tzinfo=UTC),
    )
    assert result["p50"] == 6.0  # noqa: PLR2004
    assert result["p95"] == 6.0  # noqa: PLR2004


def test_monte_carlo_empty_without_backlog():
    throughput = {f"2024W{w:02d}": 2 for w in range(1, 7)}
    assert monte_carlo_forecast([], throughput, seed=1) == {}


def test_monte_carlo_empty_with_short_history():
    throughput = {"2024W01": 2, "2024W02": 3}
    assert monte_carlo_forecast(_open_issues(5), throughput, seed=1) == {}


def test_aging_wip_ages_open_issues_in_current_status():
    now = datetime(2024, 1, 10, tzinfo=UTC)
    stuck = Issue(
        key="A",
        status="In Progress",
        created_at=datetime(2024, 1, 1, tzinfo=UTC),
        started_at=datetime(2024, 1, 2, tzinfo=UTC),
        status_transitions=[
            StatusTransition(
                at=datetime(2024, 1, 2, tzinfo=UTC),
                from_status="New",
                to_status="In Progress",
            ),
        ],
    )
    in_review = Issue(
        key="B",
        status="Review",
        created_at=datetime(2024, 1, 3, tzinfo=UTC),
        started_at=datetime(2024, 1, 5, tzinfo=UTC),
        status_transitions=[
            StatusTransition(
                at=datetime(2024, 1, 5, tzinfo=UTC),
                from_status="New",
                to_status="Review",
            ),
        ],
    )
    never_started = Issue(
        key="D",
        status="New",
        created_at=datetime(2023, 1, 1, tzinfo=UTC),
    )
    done = Issue(
        key="C",
        status="Done",
        created_at=datetime(2024, 1, 1, tzinfo=UTC),
        last_finish_status_at=datetime(2024, 1, 5, tzinfo=UTC),
        statuses_x_periods={"In Progress": timedelta(days=4)},
    )
    df = aging_wip([stuck, in_review, never_started, done], now=now)
    assert list(df["key"]) == ["A", "B"]
    assert list(df["status"]) == ["In Progress", "Review"]
    assert list(df["age_days"]) == [8.0, 5.0]
    assert df.iloc[0]["p85_days"] == 4.0  # noqa: PLR2004
    assert pd.isna(df.iloc[1]["p85_days"])


def test_cumulative_flow_daily_counts():
    now = datetime(2024, 1, 5, tzinfo=UTC)
    moved = Issue(
        key="A",
        status="In Progress",
        created_at=datetime(2024, 1, 1, tzinfo=UTC),
        status_transitions=[
            StatusTransition(
                at=datetime(2024, 1, 3, tzinfo=UTC),
                from_status="New",
                to_status="In Progress",
            ),
        ],
    )
    still = Issue(
        key="B",
        status="New",
        created_at=datetime(2024, 1, 2, tzinfo=UTC),
    )
    df = cumulative_flow([moved, still], now=now)
    assert list(df.columns) == ["New", "In Progress"]
    assert list(df["New"]) == [1, 2, 1, 1, 1]
    assert list(df["In Progress"]) == [0, 0, 1, 1, 1]


def test_assignee_load_aggregates_and_drops_unassigned():
    first = Issue(
        key="A",
        status="Done",
        created_at=datetime(2024, 1, 1, tzinfo=UTC),
        doers_x_periods={"alice": timedelta(days=2), None: timedelta(days=1)},
        handoffs=2,
    )
    second = Issue(
        key="B",
        status="Done",
        created_at=datetime(2024, 1, 1, tzinfo=UTC),
        doers_x_periods={"alice": timedelta(days=2), "bob": timedelta(days=3)},
        handoffs=1,
    )
    df, handoffs = assignee_load([first, second])
    assert list(df.columns) == ["assignee", "total_days", "issue_count"]
    assert list(df["assignee"]) == ["alice", "bob"]
    assert list(df["total_days"]) == [4.0, 3.0]
    assert list(df["issue_count"]) == [2, 1]
    assert handoffs == [2, 1]


def test_monte_carlo_backlog_excludes_discarded_issues():
    throughput = {f"2024W{w:02d}": 2 for w in range(1, 7)}
    discarded = Issue(
        key="X",
        status="Cancelled",
        created_at=datetime(2024, 1, 1, tzinfo=UTC),
        discarded=True,
    )
    result = monte_carlo_forecast([*_open_issues(4), discarded], throughput, seed=1)
    assert result["backlog"] == 4  # noqa: PLR2004


def test_aging_wip_skips_discarded_issues():
    discarded = Issue(
        key="X",
        status="Cancelled",
        created_at=datetime(2024, 1, 1, tzinfo=UTC),
        discarded=True,
    )
    started = _open_issues(1, started_at=datetime(2024, 1, 2, tzinfo=UTC))
    df = aging_wip([*started, discarded], now=datetime(2024, 1, 10, tzinfo=UTC))
    assert list(df["key"]) == ["O-0"]


def _finished_after(days: int) -> Issue:
    start = datetime(2024, 1, 1, tzinfo=UTC)
    return Issue(
        key="LONG",
        status="Done",
        created_at=start,
        started_at=start,
        last_finish_status_at=start + timedelta(days=days),
        statuses_x_periods={"In Progress": timedelta(days=days)},
    )


def test_time_metrics_keep_the_tail_of_the_distribution():
    issues = [_finished_after(59), _finished_after(30)]
    assert cycle_times(issues) == [59, 30]
    assert lead_times(issues) == [59, 30]
    assert queue_times(issues) == {"In Progress": [59, 30]}
