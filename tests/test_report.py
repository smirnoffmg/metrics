"""Tests for the self-contained HTML report."""

from __future__ import annotations

import base64

import pandas as pd

from metrics.services.backtest import BacktestSummary
from metrics.services.report import ReportService
from metrics.services.stats import StuckRow, Tile

ONE_PIXEL_PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJ"
    "AAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg==",
)


def test_report_renders_tiles_fragments_stuck_and_images(tmp_path):
    charts = []
    for name in ("cycle_time", "throughput"):
        png = tmp_path / f"{name}.png"
        png.write_bytes(ONE_PIXEL_PNG)
        charts.append(png)
    out = tmp_path / "report.html"

    ReportService().render(
        str(out),
        tiles=[
            Tile("Cycle time p50", "4.0d", "↓ 6.0d", delta_good=True),
            Tile("Work in progress", "3", None, delta_good=None),
        ],
        images=charts,
        fragments=["<div class='plotly-graph-div'>FAKE_PLOTLY</div>"],
        stuck_rows=[
            StuckRow(
                key="B-2",
                status="In Progress",
                age_days=12.5,
                url="https://jira.example.com/browse/B-2",
            ),
        ],
    )

    html = out.read_text(encoding="utf-8")
    expected_images = 2
    assert html.count("data:image/png;base64,") == expected_images
    assert "4.0d" in html
    assert "↓ 6.0d" in html
    assert "FAKE_PLOTLY" in html
    assert 'href="https://jira.example.com/browse/B-2"' in html
    assert "12.5" in html


def test_report_renders_the_agent_comparison(tmp_path):
    out = tmp_path / "report.html"
    comparison = pd.DataFrame.from_dict(
        {
            "agents": {
                "changes": 3,
                "lead_time_p50_days": 1.25,
                "change_failure_rate": 0.5,
            },
            "people": {
                "changes": 9,
                "lead_time_p50_days": None,
                "change_failure_rate": None,
            },
        },
        orient="index",
    )
    ReportService().render(str(out), tiles=[], images=[], agent_comparison=comparison)
    html = out.read_text(encoding="utf-8")
    assert "Agents and people" in html
    assert "<td>agents</td><td>3</td><td>1.2d</td><td>50%</td>" in html
    assert "<td>people</td><td>9</td><td>n/a</td><td>n/a</td>" in html


def test_report_draws_an_unjudged_delta_in_muted_ink(tmp_path):
    out = tmp_path / "report.html"
    tile = Tile("of 68 past 30-week 85% forecasts held", "63%", "only 3 independent")
    ReportService().render(str(out), tiles=[tile], images=[])
    html = out.read_text(encoding="utf-8")
    assert '<div class="delta" style="color:#898781">only 3 independent</div>' in html


def test_report_renders_the_backtest_by_window_and_horizon(tmp_path):
    out = tmp_path / "report.html"

    def summary(horizon: int, crps_mean: float) -> BacktestSummary:
        return BacktestSummary(
            horizon=horizon,
            count=97,
            independent=25,
            held_85=0.904,
            kolmogorov=0.161,
            mean_crps=crps_mean,
        )

    ReportService().render(
        str(out),
        tiles=[],
        images=[],
        backtests={12: [summary(4, 61.3)], 52: [summary(4, 40.6)]},
        forecast_window=52,
    )
    html = out.read_text(encoding="utf-8")
    assert "Forecast backtest by window and horizon" in html
    assert (
        "<tr><td>12 weeks</td><td>4 weeks</td><td>97</td><td>25</td><td>90%</td>"
        "<td>0.16</td><td>61.3</td></tr>"
    ) in html
    assert "<tr><td><b>52 weeks, used</b></td><td>4 weeks</td>" in html
