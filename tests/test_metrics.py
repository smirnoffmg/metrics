from metrics.services.metrics import MetricsService

# All tests use the dummy_repo fixture from conftest.py


def test_metricsservice_get_cycle_time(dummy_repo):
    service = MetricsService(dummy_repo)
    result = service.get_cycle_time()
    assert isinstance(result, list)
    assert result[0] >= 1


def test_metricsservice_get_lead_time(dummy_repo):
    service = MetricsService(dummy_repo)
    result = service.get_lead_time()
    assert isinstance(result, list)
    assert result[0] >= 1


def test_metricsservice_get_queue_time(dummy_repo):
    service = MetricsService(dummy_repo)
    result = service.get_queue_time()
    assert isinstance(result, dict)
    assert any(isinstance(v, list) for v in result.values())


def test_metricsservice_get_throughput(dummy_repo):
    service = MetricsService(dummy_repo)
    result = service.get_throughput()
    assert isinstance(result, dict)
    assert all(isinstance(k, str) for k in result.keys())
    assert all(isinstance(v, int) for v in result.values())


def test_metricsservice_get_cumulative_queue_time(dummy_repo):
    service = MetricsService(dummy_repo)
    result = service.get_cumulative_queue_time()
    import pandas as pd

    assert isinstance(result, pd.DataFrame)
    assert set(result.columns) == {"status", "median_hours", "count"}


def test_metricsservice_get_return_to_testing(dummy_repo):
    service = MetricsService(dummy_repo)
    result = service.get_return_to_testing()
    assert isinstance(result, list)
