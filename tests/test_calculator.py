"""Tests for metric calculators."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

import pandas as pd

from metrics.entity.issues import Issue, StatusTransition
from metrics.services.calculator import (
    AgingWipCalculator,
    AssigneeLoadCalculator,
    CumulativeFlowCalculator,
    CumulativeQueueTimeCalculator,
    CycleTimeCalculator,
    CycleTimeScatterCalculator,
    FlowEfficiencyCalculator,
    LeadTimeCalculator,
    MonteCarloForecastCalculator,
    QueueTimeCalculator,
    ReturnToTestingCalculator,
    ThroughputCalculator,
)


class StubRepo:
    def __init__(self, issues):
        self.issues = issues

    def all(self):
        return self.issues


def test_cycle_time_calculator(dummy_repo):
    calculator = CycleTimeCalculator(dummy_repo)
    result = calculator.calculate()
    assert isinstance(result, list)
    assert result[0] >= 1


def test_lead_time_calculator(dummy_repo):
    calculator = LeadTimeCalculator(dummy_repo)
    result = calculator.calculate()
    assert isinstance(result, list)
    assert result[0] >= 1


def test_queue_time_calculator(dummy_repo):
    calculator = QueueTimeCalculator(dummy_repo)
    result = calculator.calculate()
    assert isinstance(result, dict)
    assert any(isinstance(v, list) for v in result.values())


def test_throughput_calculator(dummy_repo):
    calculator = ThroughputCalculator(dummy_repo)
    result = calculator.calculate()
    assert isinstance(result, dict)
    assert all(isinstance(k, str) for k in result)
    assert all(isinstance(v, int) for v in result.values())


def _repo_with_finishes(*finished_at):
    issues = [
        Issue(
            key=f"ISSUE-{i}",
            status="Done",
            created_at=finish - timedelta(days=1),
            last_finish_status_at=finish,
        )
        for i, finish in enumerate(finished_at)
    ]

    class Repo:
        def all(self):
            return issues

    return Repo()


def test_throughput_calculator_uses_iso_year_for_week_key():
    repo = _repo_with_finishes(datetime(2025, 12, 29, 12, 0, 0))
    result = ThroughputCalculator(repo).calculate()
    assert result == {"2026W01": 1}


def test_throughput_calculator_sorted_with_gap_weeks_zero_filled():
    repo = _repo_with_finishes(
        datetime(2024, 1, 17, 12, 0, 0),
        datetime(2024, 1, 3, 12, 0, 0),
        datetime(2024, 1, 3, 18, 0, 0),
    )
    result = ThroughputCalculator(repo).calculate()
    assert list(result.items()) == [
        ("2024W01", 2),
        ("2024W02", 0),
        ("2024W03", 1),
    ]


def test_throughput_calculator_empty_repo():
    result = ThroughputCalculator(_repo_with_finishes()).calculate()
    assert result == {}


def test_queue_time_calculators_handle_issue_without_status_periods():
    issue = Issue(key="ISSUE-1", status="New", created_at=datetime(2024, 1, 1))

    class Repo:
        def all(self):
            return [issue]

    assert QueueTimeCalculator(Repo()).calculate() == {}
    assert CumulativeQueueTimeCalculator(Repo()).calculate().empty


def test_cumulative_queue_time_calculator(dummy_repo):
    calculator = CumulativeQueueTimeCalculator(dummy_repo)
    result = calculator.calculate()
    assert isinstance(result, pd.DataFrame)
    assert set(result.columns) == {"status", "median_hours", "count"}


def test_return_to_testing_calculator(dummy_repo):
    calculator = ReturnToTestingCalculator(dummy_repo)
    result = calculator.calculate()
    assert isinstance(result, list)


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
    calc = ReturnToTestingCalculator(
        StubRepo([bounced, straight]),
        testing_statuses=["In Review"],
    )
    assert calc.calculate() == [2]


def test_cycle_time_scatter_uncapped_days():
    done = Issue(
        key="A",
        status="Done",
        created_at=datetime(2024, 1, 1, tzinfo=UTC),
        first_status_change_at=datetime(2024, 1, 1, tzinfo=UTC),
        last_finish_status_at=datetime(2024, 3, 1, tzinfo=UTC),
    )
    open_issue = Issue(
        key="B",
        status="New",
        created_at=datetime(2024, 1, 1, tzinfo=UTC),
    )
    df = CycleTimeScatterCalculator(StubRepo([done, open_issue])).calculate()
    assert list(df.columns) == ["key", "finished_at", "cycle_time_days"]
    assert len(df) == 1
    assert df.iloc[0]["key"] == "A"
    assert df.iloc[0]["finished_at"] == datetime(2024, 3, 1, tzinfo=UTC)
    assert df.iloc[0]["cycle_time_days"] == 60.0  # noqa: PLR2004


class StubThroughput:
    def __init__(self, weekly):
        self.weekly = weekly

    def calculate(self):
        return self.weekly


def _open_issues(n):
    return [
        Issue(key=f"O-{i}", status="New", created_at=datetime(2024, 1, 1, tzinfo=UTC))
        for i in range(n)
    ]


def test_monte_carlo_constant_throughput_is_deterministic():
    throughput = StubThroughput({f"2024W{w:02d}": 2 for w in range(1, 7)})
    calc = MonteCarloForecastCalculator(StubRepo(_open_issues(6)), throughput)
    result = calc.calculate(
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


def test_flow_efficiency_share_of_active_time():
    done = Issue(
        key="A",
        status="Done",
        created_at=datetime(2024, 1, 1, tzinfo=UTC),
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
    calc = FlowEfficiencyCalculator(
        StubRepo([done, still_open]),
        active_statuses=["In Progress"],
    )
    assert calc.calculate() == 0.25  # noqa: PLR2004


def test_flow_efficiency_empty_repo():
    assert FlowEfficiencyCalculator(StubRepo([])).calculate() == 0.0


def test_monte_carlo_empty_without_backlog():
    throughput = StubThroughput({f"2024W{w:02d}": 2 for w in range(1, 7)})
    calc = MonteCarloForecastCalculator(StubRepo([]), throughput)
    assert calc.calculate(seed=1) == {}


def test_monte_carlo_empty_with_short_history():
    throughput = StubThroughput({"2024W01": 2, "2024W02": 3})
    calc = MonteCarloForecastCalculator(StubRepo(_open_issues(5)), throughput)
    assert calc.calculate(seed=1) == {}


def test_aging_wip_ages_open_issues_in_current_status():
    now = datetime(2024, 1, 10, tzinfo=UTC)
    stuck = Issue(
        key="A",
        status="In Progress",
        created_at=datetime(2024, 1, 1, tzinfo=UTC),
        status_transitions=[
            StatusTransition(
                at=datetime(2024, 1, 2, tzinfo=UTC),
                from_status="New",
                to_status="In Progress",
            ),
        ],
    )
    fresh = Issue(
        key="B",
        status="New",
        created_at=datetime(2024, 1, 5, tzinfo=UTC),
    )
    done = Issue(
        key="C",
        status="Done",
        created_at=datetime(2024, 1, 1, tzinfo=UTC),
        last_finish_status_at=datetime(2024, 1, 5, tzinfo=UTC),
        statuses_x_periods={"In Progress": timedelta(days=4)},
    )
    df = AgingWipCalculator(StubRepo([stuck, fresh, done])).calculate(now=now)
    assert list(df["key"]) == ["A", "B"]
    assert list(df["status"]) == ["In Progress", "New"]
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
    df = CumulativeFlowCalculator(StubRepo([moved, still])).calculate(now=now)
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
    df, handoffs = AssigneeLoadCalculator(StubRepo([first, second])).calculate()
    assert list(df.columns) == ["assignee", "total_days", "issue_count"]
    assert list(df["assignee"]) == ["alice", "bob"]
    assert list(df["total_days"]) == [4.0, 3.0]
    assert list(df["issue_count"]) == [2, 1]
    assert handoffs == [2, 1]
