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


def test_backtest_tile_says_how_often_the_85_percent_claim_held():
    summary = BacktestSummary(count=40, held_85=0.725, kolmogorov=0.2, mean_crps=9.0)
    tile = backtest_tile(summary, horizon=8)
    assert tile.value == "72%"
    assert tile.label == "of 40 past 8-week 85% forecasts held"
    assert tile.delta_good is False


def test_backtest_tile_without_enough_history():
    assert backtest_tile(None, horizon=8).value == "n/a"


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
