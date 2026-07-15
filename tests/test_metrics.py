"""Tests for MetricsService."""

from __future__ import annotations

from unittest.mock import MagicMock

import pandas as pd

from metrics.services.metrics import MetricsService

CALCULATORS = (
    "cycle_time_calculator",
    "lead_time_calculator",
    "queue_time_calculator",
    "throughput_calculator",
    "cumulative_queue_time_calculator",
    "return_to_testing_calculator",
    "cycle_time_scatter_calculator",
    "monte_carlo_forecast_calculator",
    "aging_wip_calculator",
    "cumulative_flow_calculator",
    "assignee_load_calculator",
    "flow_efficiency_calculator",
)


def make_service(**overrides) -> MetricsService:
    kwargs = {name: MagicMock() for name in CALCULATORS}
    kwargs.update(overrides)
    return MetricsService(**kwargs)


def test_metricsservice_get_cycle_time():
    calculator = MagicMock()
    calculator.calculate.return_value = [1.0]
    service = make_service(cycle_time_calculator=calculator)
    assert service.get_cycle_time() == [1.0]
    calculator.calculate.assert_called_once()


def test_metricsservice_get_lead_time():
    calculator = MagicMock()
    calculator.calculate.return_value = [2.0]
    service = make_service(lead_time_calculator=calculator)
    assert service.get_lead_time() == [2.0]
    calculator.calculate.assert_called_once()


def test_metricsservice_get_queue_time():
    calculator = MagicMock()
    calculator.calculate.return_value = {"In Progress": [3.0]}
    service = make_service(queue_time_calculator=calculator)
    assert service.get_queue_time() == {"In Progress": [3.0]}
    calculator.calculate.assert_called_once()


def test_metricsservice_get_throughput():
    calculator = MagicMock()
    calculator.calculate.return_value = {"2024W01": 5}
    service = make_service(throughput_calculator=calculator)
    assert service.get_throughput() == {"2024W01": 5}
    calculator.calculate.assert_called_once()


def test_metricsservice_get_cumulative_queue_time():
    calculator = MagicMock()
    df = pd.DataFrame(
        {
            "status": ["To Do"],
            "median_hours": [10],
            "count": [100],
        },
    )
    calculator.calculate.return_value = df
    service = make_service(cumulative_queue_time_calculator=calculator)
    pd.testing.assert_frame_equal(service.get_cumulative_queue_time(), df)
    calculator.calculate.assert_called_once()


def test_metricsservice_get_return_to_testing():
    calculator = MagicMock()
    calculator.calculate.return_value = [2, 3]
    service = make_service(return_to_testing_calculator=calculator)
    assert service.get_return_to_testing() == [2, 3]
    calculator.calculate.assert_called_once()


def test_metricsservice_get_cycle_time_scatter():
    calculator = MagicMock()
    df = pd.DataFrame({"finished_at": [], "cycle_time_days": []})
    calculator.calculate.return_value = df
    service = make_service(cycle_time_scatter_calculator=calculator)
    pd.testing.assert_frame_equal(service.get_cycle_time_scatter(), df)
    calculator.calculate.assert_called_once()


def test_metricsservice_get_forecast():
    calculator = MagicMock()
    calculator.calculate.return_value = {"backlog": 5}
    service = make_service(monte_carlo_forecast_calculator=calculator)
    assert service.get_forecast() == {"backlog": 5}
    calculator.calculate.assert_called_once()


def test_metricsservice_get_aging_wip():
    calculator = MagicMock()
    df = pd.DataFrame({"key": [], "status": [], "age_days": []})
    calculator.calculate.return_value = df
    service = make_service(aging_wip_calculator=calculator)
    pd.testing.assert_frame_equal(service.get_aging_wip(), df)
    calculator.calculate.assert_called_once()


def test_metricsservice_get_cumulative_flow():
    calculator = MagicMock()
    df = pd.DataFrame({"New": [1]})
    calculator.calculate.return_value = df
    service = make_service(cumulative_flow_calculator=calculator)
    pd.testing.assert_frame_equal(service.get_cumulative_flow(), df)
    calculator.calculate.assert_called_once()


def test_metricsservice_get_assignee_load():
    calculator = MagicMock()
    df = pd.DataFrame({"assignee": ["a"], "total_days": [1.0], "issue_count": [1]})
    calculator.calculate.return_value = (df, [2, 1])
    service = make_service(assignee_load_calculator=calculator)
    load, handoffs = service.get_assignee_load()
    pd.testing.assert_frame_equal(load, df)
    assert handoffs == [2, 1]
    calculator.calculate.assert_called_once()
