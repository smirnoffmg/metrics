"""Tests for headline tiles and stuck-ticket rows."""

from __future__ import annotations

from datetime import UTC, date, datetime

import pandas as pd

from metrics.services.backtest import BacktestSummary
from metrics.services.stats import (
    Tile,
    backtest_tile,
    build_delivery_tiles,
    build_headline_tiles,
    build_stuck_rows,
    diagnose_backtest,
    recalibration_note,
    scope_forecast_tile,
)


def _scatter_df():
    return pd.DataFrame(
        {
            "key": ["A-1", "A-2", "A-3", "A-4"],
            "finished_at": [
                datetime(2024, 1, 5, tzinfo=UTC),
                datetime(2024, 1, 6, tzinfo=UTC),
                datetime(2024, 1, 15, tzinfo=UTC),
                datetime(2024, 1, 16, tzinfo=UTC),
            ],
            "cycle_time_days": [10.0, 10.0, 4.0, 4.0],
        },
    )


def _aging_df():
    return pd.DataFrame(
        {
            "key": ["B-1", "B-2", "B-3"],
            "status": ["Open", "In Progress", "Open"],
            "age_days": [3.0, 12.5, 8.0],
            "p85_days": [4.0, 9.0, 4.0],
        },
    )


def test_build_headline_tiles_values_and_deltas():
    tiles = build_headline_tiles(
        scatter=_scatter_df(),
        aging=_aging_df(),
        forecast={"p85": 5.0, "p85_date": date(2024, 3, 1)},
        throughput={"2024W01": 2, "2024W02": 2, "2024W03": 4, "2024W04": 4},
        flow_efficiency=0.25,
    )
    assert tiles == [
        Tile("Cycle time p50", "4.0d", "↓ 6.0d", delta_good=True),
        Tile("85% of backlog done", "by 01 Mar 2024", None, delta_good=None),
        Tile("Work in progress", "3", None, delta_good=None),
        Tile("Throughput", "4.0/wk", "↑ 2.0", delta_good=True),
        Tile("Flow efficiency", "25%", None, delta_good=None),
    ]


def test_build_headline_tiles_without_forecast_or_history():
    tiles = build_headline_tiles(
        scatter=pd.DataFrame({"key": [], "finished_at": [], "cycle_time_days": []}),
        aging=_aging_df(),
        forecast={},
        throughput={"2024W01": 2},
        flow_efficiency=0.0,
    )
    labels = [tile.label for tile in tiles]
    assert "85% of backlog done" in labels
    forecast_tile = tiles[labels.index("85% of backlog done")]
    assert forecast_tile.value == "n/a"
    cycle_tile = tiles[labels.index("Cycle time p50")]
    assert cycle_tile.value == "n/a"
    assert cycle_tile.delta_text is None


def test_build_stuck_rows_sorted_and_linked():
    rows = build_stuck_rows(_aging_df(), "https://jira.example.com", limit=2)
    assert [(row.key, row.age_days) for row in rows] == [
        ("B-2", 12.5),
        ("B-3", 8.0),
    ]
    assert rows[0].url == "https://jira.example.com/browse/B-2"
    assert rows[0].status == "In Progress"


def test_build_stuck_rows_empty():
    empty = pd.DataFrame({"key": [], "status": [], "age_days": [], "p85_days": []})
    assert build_stuck_rows(empty, "https://x") == []


def test_build_headline_tiles_adds_the_scope_tile():
    scope = scope_forecast_tile(
        {"p85": 3.0, "p85_date": date(2024, 2, 1)}, open_count=4
    )
    tiles = build_headline_tiles(
        scatter=_scatter_df(),
        aging=_aging_df(),
        forecast={},
        throughput={"2024W01": 2},
        flow_efficiency=0.0,
        scope_tile=scope,
    )
    assert Tile("85% of forecast scope done", "by 01 Feb 2024") in tiles


def test_scope_forecast_tile_says_when_nothing_is_left():
    assert scope_forecast_tile({}, open_count=0) == Tile(
        "85% of forecast scope done", "all done"
    )
    assert scope_forecast_tile({}, open_count=3).value == "n/a"


def test_build_headline_tiles_leave_out_the_scope_tile_without_a_scope():
    tiles = build_headline_tiles(
        scatter=_scatter_df(),
        aging=_aging_df(),
        forecast={},
        throughput={"2024W01": 2},
        flow_efficiency=0.0,
    )
    assert "85% of forecast scope done" not in [tile.label for tile in tiles]


def test_build_delivery_tiles():
    lead_times = pd.DataFrame({"lead_time_days": [1.0, 3.0, 5.0]})
    tiles = build_delivery_tiles(
        weekly={"2026W36": 1, "2026W37": 3},
        lead_times=lead_times,
        failure_rate=0.25,
        recovery_days=[0.5, 1.5],
    )
    assert tiles == [
        Tile("Deploys", "2.0/wk"),
        Tile("Change lead time p50", "3.0d"),
        Tile("Change fail rate", "25%"),
        Tile("Recovery time p50", "1.0d"),
    ]


def test_build_delivery_tiles_without_enough_deploys():
    tiles = build_delivery_tiles(
        weekly={},
        lead_times=pd.DataFrame({"lead_time_days": []}),
        failure_rate=None,
        recovery_days=[],
    )
    assert [tile.value for tile in tiles] == ["n/a", "n/a", "n/a", "no failures"]


def _summary(held_85: float, independent: int) -> BacktestSummary:
    return BacktestSummary(
        horizon=8,
        count=40,
        independent=independent,
        held_85=held_85,
        kolmogorov=0.2,
        mean_crps=9.0,
    )


def test_backtest_tile_says_how_often_the_85_percent_claim_held():
    tile = backtest_tile(_summary(0.725, independent=12))
    assert tile.value == "72%"
    assert tile.label == "of 40 past 8-week 85% forecasts held"
    assert tile.delta_text == "fewer than promised"
    assert tile.delta_good is False


def test_backtest_tile_does_not_judge_on_few_independent_outcomes():
    tile = backtest_tile(_summary(0.5, independent=3))
    assert tile.value == "50%"
    assert tile.delta_text == "only 3 independent outcomes"
    assert tile.delta_good is None


def test_backtest_tile_without_enough_history():
    assert backtest_tile(None).value == "n/a"


def test_build_headline_tiles_puts_the_backtest_beside_the_forecast():
    backtest = Tile("of 40 past 8-week 85% forecasts held", "72%")
    tiles = build_headline_tiles(
        _scatter_df(),
        pd.DataFrame(),
        {},
        {},
        0.5,
        backtest=backtest,
    )
    assert tiles[2] is backtest


def _tested(
    horizon: int,
    independent: int,
    bias_p: float | None,
    trend_p: float | None,
) -> BacktestSummary:
    return BacktestSummary(
        horizon=horizon,
        count=90,
        independent=independent,
        held_85=0.78,
        kolmogorov=0.2,
        mean_crps=50.0,
        bias_p=bias_p,
        trend_p=trend_p,
    )


def test_diagnosis_finds_drift_at_any_horizon_with_enough_outcomes():
    note = diagnose_backtest(
        [
            _tested(4, 24, bias_p=0.052, trend_p=0.035),
            _tested(8, 12, bias_p=0.013, trend_p=0.298),
            _tested(41, 2, bias_p=0.5, trend_p=0.0),
        ],
    )
    assert note == (
        "4-week forecast errors drift over time (y-plot p = 0.035): the team's pace"
        " changes, so correcting forecasts by their past errors would not hold."
    )


def test_diagnosis_of_steady_bias():
    note = diagnose_backtest(
        [
            _tested(4, 24, bias_p=0.2, trend_p=0.4),
            _tested(8, 12, bias_p=0.011, trend_p=0.26),
        ],
    )
    assert note == (
        "8-week forecasts err the same way throughout (u-plot p = 0.011), with no"
        " sign of drift at 4 or 8 weeks:"
        " the case for recalibrating them by past errors."
    )


def test_diagnosis_without_evidence_of_bias_or_drift():
    note = diagnose_backtest(
        [
            _tested(4, 24, bias_p=0.4, trend_p=0.3),
            _tested(8, 12, bias_p=0.6, trend_p=0.2),
        ],
    )
    assert note == (
        "No sign that forecasts over 4 or 8 weeks are biased or drift over time"
        " (lowest u-plot p = 0.400, lowest y-plot p = 0.200)."
    )


def test_diagnosis_needs_enough_independent_outcomes():
    note = diagnose_backtest([_tested(8, 3, bias_p=0.01, trend_p=0.01)])
    assert (
        note
        == "Too few independent outcomes to test forecast errors for bias or drift."
    )


def _scored_crps(held_85: float, crps_mean: float) -> BacktestSummary:
    return BacktestSummary(
        horizon=8,
        count=74,
        independent=10,
        held_85=held_85,
        kolmogorov=0.2,
        mean_crps=crps_mean,
    )


def test_recalibration_note_when_the_correction_scores_worse():
    note = recalibration_note(_scored_crps(0.51, 37.6), _scored_crps(0.80, 40.2))
    assert note == (
        "Recalibrated by their past errors, 8-week forecasts kept 80% of their 85%"
        " promises instead of 51% but scored a worse CRPS (40.2 against 37.6),"
        " so the forecast is not recalibrated."
    )


def test_recalibration_note_when_the_correction_scores_better():
    note = recalibration_note(_scored_crps(0.51, 40.2), _scored_crps(0.80, 37.6))
    assert note == (
        "Recalibrated by their past errors, 8-week forecasts kept 80% of their 85%"
        " promises instead of 51% and scored a better CRPS (37.6 against 40.2),"
        " so the forecast is recalibrated."
    )


def test_build_headline_tiles_say_when_the_forecast_is_recalibrated():
    forecast = {"p85_date": date(2027, 6, 29), "recalibrated": True}
    tiles = build_headline_tiles(_scatter_df(), pd.DataFrame(), forecast, {}, 0.5)
    assert tiles[1] == Tile("85% of backlog done, recalibrated", "by 29 Jun 2027")
