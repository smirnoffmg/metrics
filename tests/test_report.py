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


def test_report_renders_the_backtest_by_pace_and_horizon(tmp_path):
    out = tmp_path / "report.html"

    def summary(horizon: int, crps_mean: float) -> BacktestSummary:
        return BacktestSummary(
            horizon=horizon,
            count=97,
            independent=25,
            held_85=0.904,
            kolmogorov=0.161,
            mean_crps=crps_mean,
            bias_p=0.0661,
            trend_p=None,
            held_independent=22,
        )

    ReportService().render(
        str(out),
        tiles=[],
        images=[],
        backtests={
            "last 12 weeks": [summary(4, 61.3)],
            "half-life 4 weeks, recalibrated": [summary(4, 40.6)],
        },
        used_model="half-life 4 weeks, recalibrated",
        backtest_note="No evidence of drift.",
    )
    html = _method_section(out.read_text(encoding="utf-8"))
    assert "Forecast backtest by model and horizon" in html
    assert (
        "<tr><td>last 12 weeks</td><td>4 weeks</td><td>97</td><td>22 of 25</td>"
        "<td>90%</td><td>0.16</td><td>61.3</td><td>0.066</td><td>n/a</td></tr>"
    ) in html
    assert (
        "<tr><td><b>half-life 4 weeks, recalibrated, used</b></td><td>4 weeks</td>"
        in html
    )
    assert "<p>No evidence of drift.</p>" in html


def _method_section(html: str) -> str:
    start = html.index("<details><summary>How the forecast was checked</summary>")
    return html[start : html.index("</details>", start)]


def test_render_puts_verdict_before_tiles(tmp_path):
    out = tmp_path / "report.html"
    ReportService().render(
        str(out),
        tiles=[Tile("Work in progress", "3")],
        images=[],
        verdict=["At least 31 of the 151 open issues will be done.", "Commit."],
    )
    html = out.read_text(encoding="utf-8")
    assert "<h1>Delivery forecast</h1>" in html
    verdict = html.index('<section class="verdict">')
    assert html.index("<h1>") < verdict < html.index('<div class="tiles">')
    assert "<p>At least 31 of the 151 open issues will be done.</p>" in html
    assert "don't turn them into targets" in html


def test_backtest_table_note_and_chart_sit_inside_details(tmp_path):
    chart = tmp_path / "forecast_backtest.png"
    chart.write_bytes(ONE_PIXEL_PNG)
    out = tmp_path / "report.html"
    ReportService().render(
        str(out),
        tiles=[],
        images=[],
        backtests={
            "open work": [
                BacktestSummary(
                    horizon=8,
                    count=60,
                    independent=12,
                    held_85=0.9,
                    kolmogorov=0.1,
                    mean_crps=4.0,
                    held_independent=11,
                ),
            ],
        },
        used_model="open work",
        backtest_note="No sign of drift (lowest y-plot p = 0.400).",
        method_images=[chart],
    )
    html = out.read_text(encoding="utf-8")
    method = _method_section(html)
    assert "Forecast backtest by model and horizon" in method
    assert "y-plot p = 0.400" in method
    assert "data:image/png;base64," in method
    before = html[: html.index("<details>")]
    for jargon in ("CRPS", "u-plot", "y-plot", "Kolmogorov", "p ="):
        assert jargon not in before


def test_delivery_sits_inside_details(tmp_path):
    out = tmp_path / "report.html"
    comparison = pd.DataFrame.from_dict(
        {"agents": {"changes": 3, "lead_time_p50_days": 1.0, "change_failure_rate": 0}},
        orient="index",
    )
    ReportService().render(
        str(out),
        tiles=[Tile("Work in progress", "3")],
        images=[],
        delivery_tiles=[Tile("Deploys", "2.0/wk")],
        agent_comparison=comparison,
    )
    html = out.read_text(encoding="utf-8")
    start = html.index("<details><summary>Delivery (DORA)</summary>")
    delivery = html[start : html.index("</details>", start)]
    assert "Deploys" in delivery
    assert "Agents and people" in delivery
    assert "Deploys" not in html[:start]


def test_render_leaves_out_empty_details(tmp_path):
    out = tmp_path / "report.html"
    ReportService().render(str(out), tiles=[], images=[])
    assert "<details>" not in out.read_text(encoding="utf-8")


def test_method_note_survives_without_a_backtest_table(tmp_path):
    out = tmp_path / "report.html"
    ReportService().render(
        str(out),
        tiles=[],
        images=[],
        backtests={},
        backtest_note="Clear dates: 0 judged; all 12 past promises fall beyond.",
    )
    method = _method_section(out.read_text(encoding="utf-8"))
    assert "<p>Clear dates: 0 judged; all 12 past promises fall beyond.</p>" in method
    assert "Forecast backtest by model and horizon" not in method
