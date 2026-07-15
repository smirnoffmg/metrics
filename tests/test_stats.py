"""Tests for headline tiles and stuck-ticket rows."""

from __future__ import annotations

from datetime import UTC, date, datetime

import pandas as pd

from metrics.services.stats import Tile, build_headline_tiles, build_stuck_rows


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
        Tile("Open issues", "3", None, delta_good=None),
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
