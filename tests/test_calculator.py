"""Tests for metric calculators."""

from __future__ import annotations

from datetime import datetime, timedelta

import pandas as pd

from metrics.entity.issues import Issue
from metrics.services.calculator import (
    CumulativeQueueTimeCalculator,
    CycleTimeCalculator,
    LeadTimeCalculator,
    QueueTimeCalculator,
    ReturnToTestingCalculator,
    ThroughputCalculator,
)


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
