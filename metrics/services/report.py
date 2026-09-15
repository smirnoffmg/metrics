"""Self-contained HTML report: hero tiles, interactive charts, action table."""

from __future__ import annotations

import base64
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING

import pandas as pd

from .base import BaseService

if TYPE_CHECKING:
    from collections.abc import Iterable, Sequence

    from .backtest import BacktestSummary
    from .stats import StuckRow, Tile

DELTA_GOOD = "#006300"
DELTA_BAD = "#d03b3b"
DELTA_UNJUDGED = "#898781"

_PAGE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8"/>
<title>Jira Metrics Report</title>
<style>
body {{ font-family: system-ui, -apple-system, "Segoe UI", sans-serif;
       margin: 2rem auto; max-width: 1080px; color: #0b0b0b; background: #f9f9f7; }}
.tiles {{ display: flex; flex-wrap: wrap; gap: 1rem; margin-bottom: 2rem; }}
.tile {{ background: #fcfcfb; border: 1px solid rgba(11,11,11,0.10);
        border-radius: 8px; padding: 1rem 1.4rem; min-width: 150px; }}
.tile .value {{ font-size: 1.9rem; font-weight: 650; }}
.tile .label {{ color: #52514e; font-size: 0.85rem; margin-top: 0.2rem; }}
.tile .delta {{ font-size: 0.9rem; margin-top: 0.3rem; }}
table {{ border-collapse: collapse; margin-bottom: 2rem; background: #fcfcfb; }}
th, td {{ border: 1px solid #e1e0d9; padding: 0.4rem 0.8rem; text-align: left; }}
th {{ color: #52514e; }}
a {{ color: #2a78d6; }}
img {{ max-width: 100%; }}
section {{ margin-bottom: 2rem; background: #fcfcfb; border-radius: 8px;
          border: 1px solid rgba(11,11,11,0.10); padding: 1rem; }}
h2 {{ text-transform: capitalize; font-size: 1.1rem; color: #52514e; }}
footer {{ color: #898781; font-size: 0.8rem; }}
</style>
</head>
<body>
<h1>Jira Metrics Report</h1>
<div class="tiles">{tiles}</div>
{fragments}
{stuck_table}
{agent_table}
{backtest_table}
{sections}
<footer>Generated {generated_at}</footer>
</body>
</html>
"""


def _tile_html(tile: Tile) -> str:
    delta = ""
    if tile.delta_text:
        color = {True: DELTA_GOOD, False: DELTA_BAD, None: DELTA_UNJUDGED}[
            tile.delta_good
        ]
        delta = f'<div class="delta" style="color:{color}">{tile.delta_text}</div>'
    return (
        f'<div class="tile"><div class="value">{tile.value}</div>'
        f'<div class="label">{tile.label}</div>{delta}</div>'
    )


def _stuck_table_html(rows: Sequence[StuckRow]) -> str:
    if not rows:
        return ""
    body = "".join(
        f'<tr><td><a href="{row.url}">{row.key}</a></td>'
        f"<td>{row.status}</td><td>{row.age_days}</td></tr>"
        for row in rows
    )
    return (
        "<section><h2>Longest-waiting work in progress</h2>"
        "<table><tr><th>Issue</th><th>Current status</th><th>Days in status</th></tr>"
        f"{body}</table></section>"
    )


def _agent_table_html(comparison: pd.DataFrame | None) -> str:
    if comparison is None:
        return ""

    def days(value: float | None) -> str:
        return "n/a" if pd.isna(value) else f"{value:.1f}d"

    def share(value: float | None) -> str:
        return "n/a" if pd.isna(value) else f"{value:.0%}"

    body = "".join(
        f"<tr><td>{group}</td><td>{int(row['changes'])}</td>"
        f"<td>{days(row['lead_time_p50_days'])}</td>"
        f"<td>{share(row['change_failure_rate'])}</td></tr>"
        for group, row in comparison.iterrows()
    )
    return (
        "<section><h2>Agents and people</h2>"
        "<table><tr><th></th><th>Changes shipped</th><th>Change lead time p50</th>"
        f"<th>Change fail rate</th></tr>{body}</table></section>"
    )


def _backtest_table_html(summaries: Sequence[BacktestSummary]) -> str:
    if not summaries:
        return ""
    body = "".join(
        f"<tr><td>{s.horizon} weeks</td><td>{s.count}</td><td>{s.independent}</td>"
        f"<td>{s.held_85:.0%}</td><td>{s.kolmogorov:.2f}</td>"
        f"<td>{s.mean_crps:.1f}</td></tr>"
        for s in summaries
    )
    return (
        "<section><h2>Forecast backtest by horizon</h2>"
        "<table><tr><th>Horizon</th><th>Past forecasts</th>"
        "<th>Independent outcomes</th><th>85% forecasts held</th>"
        "<th>Kolmogorov distance</th><th>Mean CRPS</th></tr>"
        f"{body}</table></section>"
    )


class ReportService(BaseService):
    """Renders a single-file HTML report."""

    def render(  # noqa: PLR0913
        self,
        filename: str,
        tiles: Sequence[Tile],
        images: Iterable[Path],
        fragments: Sequence[str] = (),
        stuck_rows: Sequence[StuckRow] = (),
        agent_comparison: pd.DataFrame | None = None,
        backtests: Sequence[BacktestSummary] = (),
    ) -> None:
        """Write the report: tiles, interactive charts, stuck table, PNGs."""
        sections = []
        for image in images:
            encoded = base64.b64encode(image.read_bytes()).decode("ascii")
            title = image.stem.replace("_", " ")
            sections.append(
                f'<section><h2>{title}</h2><img alt="{title}" '
                f'src="data:image/png;base64,{encoded}"/></section>',
            )
        html = _PAGE.format(
            tiles="".join(_tile_html(tile) for tile in tiles),
            fragments="\n".join(f"<section>{f}</section>" for f in fragments),
            stuck_table=_stuck_table_html(stuck_rows),
            agent_table=_agent_table_html(agent_comparison),
            backtest_table=_backtest_table_html(backtests),
            sections="\n".join(sections),
            generated_at=datetime.now(tz=UTC).strftime("%Y-%m-%d %H:%M UTC"),
        )
        Path(filename).write_text(html, encoding="utf-8")
        self.logger.info("Report written to %s", filename)
