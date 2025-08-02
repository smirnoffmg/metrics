from unittest.mock import MagicMock

from metrics.services.metrics import MetricsService


def test_metricsservice_get_cycle_time():
    cycle_time_calculator = MagicMock()
    cycle_time_calculator.calculate.return_value = [1.0]
    service = MetricsService(
        cycle_time_calculator=cycle_time_calculator,
        lead_time_calculator=MagicMock(),
        queue_time_calculator=MagicMock(),
        throughput_calculator=MagicMock(),
        cumulative_queue_time_calculator=MagicMock(),
        return_to_testing_calculator=MagicMock(),
    )
    result = service.get_cycle_time()
    assert result == [1.0]
    cycle_time_calculator.calculate.assert_called_once()


def test_metricsservice_get_lead_time():
    lead_time_calculator = MagicMock()
    lead_time_calculator.calculate.return_value = [2.0]
    service = MetricsService(
        cycle_time_calculator=MagicMock(),
        lead_time_calculator=lead_time_calculator,
        queue_time_calculator=MagicMock(),
        throughput_calculator=MagicMock(),
        cumulative_queue_time_calculator=MagicMock(),
        return_to_testing_calculator=MagicMock(),
    )
    result = service.get_lead_time()
    assert result == [2.0]
    lead_time_calculator.calculate.assert_called_once()


def test_metricsservice_get_queue_time():
    queue_time_calculator = MagicMock()
    queue_time_calculator.calculate.return_value = {"In Progress": [3.0]}
    service = MetricsService(
        cycle_time_calculator=MagicMock(),
        lead_time_calculator=MagicMock(),
        queue_time_calculator=queue_time_calculator,
        throughput_calculator=MagicMock(),
        cumulative_queue_time_calculator=MagicMock(),
        return_to_testing_calculator=MagicMock(),
    )
    result = service.get_queue_time()
    assert result == {"In Progress": [3.0]}
    queue_time_calculator.calculate.assert_called_once()


def test_metricsservice_get_throughput():
    throughput_calculator = MagicMock()
    throughput_calculator.calculate.return_value = {"2024W01": 5}
    service = MetricsService(
        cycle_time_calculator=MagicMock(),
        lead_time_calculator=MagicMock(),
        queue_time_calculator=MagicMock(),
        throughput_calculator=throughput_calculator,
        cumulative_queue_time_calculator=MagicMock(),
        return_to_testing_calculator=MagicMock(),
    )
    result = service.get_throughput()
    assert result == {"2024W01": 5}
    throughput_calculator.calculate.assert_called_once()


def test_metricsservice_get_cumulative_queue_time():
    import pandas as pd

    cumulative_queue_time_calculator = MagicMock()
    df = pd.DataFrame({"status": ["To Do"], "median_hours": [10], "count": [100]})
    cumulative_queue_time_calculator.calculate.return_value = df
    service = MetricsService(
        cycle_time_calculator=MagicMock(),
        lead_time_calculator=MagicMock(),
        queue_time_calculator=MagicMock(),
        throughput_calculator=MagicMock(),
        cumulative_queue_time_calculator=cumulative_queue_time_calculator,
        return_to_testing_calculator=MagicMock(),
    )
    result = service.get_cumulative_queue_time()
    pd.testing.assert_frame_equal(result, df)
    cumulative_queue_time_calculator.calculate.assert_called_once()


def test_metricsservice_get_return_to_testing():
    return_to_testing_calculator = MagicMock()
    return_to_testing_calculator.calculate.return_value = [2, 3]
    service = MetricsService(
        cycle_time_calculator=MagicMock(),
        lead_time_calculator=MagicMock(),
        queue_time_calculator=MagicMock(),
        throughput_calculator=MagicMock(),
        cumulative_queue_time_calculator=MagicMock(),
        return_to_testing_calculator=return_to_testing_calculator,
    )
    result = service.get_return_to_testing()
    assert result == [2, 3]
    return_to_testing_calculator.calculate.assert_called_once()
