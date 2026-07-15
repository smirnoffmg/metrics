"""Tests for VisService chart rendering."""

from __future__ import annotations

from datetime import UTC, date, datetime
from pathlib import Path

import numpy as np
import pandas as pd

from metrics.services.vis import VisService, biggest_drop


def test_visservice_vis_df_creates_file(temp_png_file):
    vis = VisService()
    data = {"a": 1, "b": 2, "c": 3}
    vis.vis_df(temp_png_file, data, x_label="x", y_label="y")
    assert Path(temp_png_file).exists()


def test_visservice_vis_array_like_creates_file(temp_png_file):
    vis = VisService()
    arr = [1, 2, 2, 3, 3, 3]
    vis.vis_array_like(temp_png_file, arr, x_label="x", y_label="y")
    assert Path(temp_png_file).exists()


def test_visservice_vis_cumulative_queue_time_creates_file(
    temp_png_file,
):
    vis = VisService()
    df = pd.DataFrame(
        {
            "status": ["A", "B"],
            "median_hours": [1.5, 2.5],
            "count": [10, 20],
        },
    )
    vis.vis_cumulative_queue_time(temp_png_file, df)
    assert Path(temp_png_file).exists()


def test_visservice_vis_scatter_percentiles_creates_file(temp_png_file):
    df = pd.DataFrame(
        {
            "key": ["A-1", "A-2", "A-3"],
            "finished_at": [
                datetime(2024, 1, 5, tzinfo=UTC),
                datetime(2024, 1, 12, tzinfo=UTC),
                datetime(2024, 3, 19, tzinfo=UTC),
            ],
            "cycle_time_days": [2.0, 5.0, 40.0],
        },
    )
    VisService().vis_scatter_percentiles(temp_png_file, df)
    assert Path(temp_png_file).exists()


def test_visservice_vis_forecast_creates_file(temp_png_file):
    result = {
        "weeks": np.array([3, 4, 4, 5, 6]),
        "backlog": 10,
        "p50": 4.0,
        "p50_date": date(2026, 8, 12),
        "p85": 5.0,
        "p85_date": date(2026, 8, 19),
        "p95": 6.0,
        "p95_date": date(2026, 8, 26),
    }
    VisService().vis_forecast(temp_png_file, result)
    assert Path(temp_png_file).exists()


def test_visservice_vis_queue_grid_creates_file(temp_png_file):
    queue_time = {
        "New": [1.0, 2.0, 2.0],
        "In Progress": [3.0, 4.0],
        "Review": [1.0],
        "Blocked": [5.0, 6.0],
    }
    VisService().vis_queue_grid(temp_png_file, queue_time)
    assert Path(temp_png_file).exists()


def test_biggest_drop_finds_largest_band_decrease():
    df = pd.DataFrame(
        {"New": [5, 5, 2, 2], "In Progress": [0, 1, 1, 0]},
        index=pd.Index(
            [date(2024, 1, d) for d in (1, 2, 3, 4)],
            name="date",
        ),
    )
    assert biggest_drop(df) == (date(2024, 1, 3), "New", 3)


def test_biggest_drop_none_when_monotonic():
    df = pd.DataFrame({"New": [1, 2, 3]})
    assert biggest_drop(df) is None


def test_visservice_vis_aging_wip_creates_file(temp_png_file):
    df = pd.DataFrame(
        {
            "key": ["A", "B"],
            "status": ["In Progress", "New"],
            "age_days": [8.0, 5.0],
            "p85_days": [4.0, float("nan")],
        },
    )
    VisService().vis_aging_wip(temp_png_file, df)
    assert Path(temp_png_file).exists()


def test_visservice_vis_cfd_creates_file(temp_png_file):
    df = pd.DataFrame(
        {"New": [1, 2, 1], "In Progress": [0, 0, 1]},
        index=pd.Index(
            [date(2024, 1, 1), date(2024, 1, 2), date(2024, 1, 3)],
            name="date",
        ),
    )
    VisService().vis_cfd(temp_png_file, df)
    assert Path(temp_png_file).exists()


def test_visservice_vis_assignee_load_creates_file(temp_png_file):
    df = pd.DataFrame(
        {
            "assignee": ["alice", "bob"],
            "total_days": [4.0, 3.0],
            "issue_count": [2, 1],
        },
    )
    VisService().vis_assignee_load(temp_png_file, df, handoffs=[2, 1, 0])
    assert Path(temp_png_file).exists()
