"""Self-contained HTML report: hero tiles, interactive charts, action table."""

from __future__ import annotations

import base64
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING

from .base import BaseService

if TYPE_CHECKING:
    from collections.abc import Iterable, Sequence

    from .stats import StuckRow, Tile

DELTA_GOOD = "#006300"
DELTA_BAD = "#d03b3b"

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
{sections}
<footer>Generated {generated_at}</footer>
</body>
</html>
"""


def _tile_html(tile: Tile) -> str:
    delta = ""
    if tile.delta_text:
        color = DELTA_GOOD if tile.delta_good else DELTA_BAD
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
        "<section><h2>Longest-waiting open issues</h2>"
        "<table><tr><th>Issue</th><th>Current status</th><th>Days in status</th></tr>"
        f"{body}</table></section>"
    )


class ReportService(BaseService):
    """Renders a single-file HTML report."""

    def render(
        self,
        filename: str,
        tiles: Sequence[Tile],
        images: Iterable[Path],
        fragments: Sequence[str] = (),
        stuck_rows: Sequence[StuckRow] = (),
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
            sections="\n".join(sections),
            generated_at=datetime.now(tz=UTC).strftime("%Y-%m-%d %H:%M UTC"),
        )
        Path(filename).write_text(html, encoding="utf-8")
        self.logger.info("Report written to %s", filename)
