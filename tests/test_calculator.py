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
    assert all(isinstance(k, str) for k in result.keys())
    assert all(isinstance(v, int) for v in result.values())


def test_cumulative_queue_time_calculator(dummy_repo):
    import pandas as pd

    calculator = CumulativeQueueTimeCalculator(dummy_repo)
    result = calculator.calculate()
    assert isinstance(result, pd.DataFrame)
    assert set(result.columns) == {"status", "median_hours", "count"}


def test_return_to_testing_calculator(dummy_repo):
    calculator = ReturnToTestingCalculator(dummy_repo)
    result = calculator.calculate()
    assert isinstance(result, list)
