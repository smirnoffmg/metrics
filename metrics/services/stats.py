"""Headline stat tiles and stuck-ticket rows for the report."""

from __future__ import annotations

from dataclasses import dataclass
from statistics import fmean
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    import pandas as pd


@dataclass(frozen=True)
class Tile:
    """One headline number for the report hero row."""

    label: str
    value: str
    delta_text: str | None = None
    delta_good: bool | None = None


@dataclass(frozen=True)
class StuckRow:
    """One open issue for the stuck-tickets action table."""

    key: str
    status: str
    age_days: float
    url: str


def _cycle_tile(scatter: pd.DataFrame) -> Tile:
    label = "Cycle time p50"
    if scatter.empty:
        return Tile(label, "n/a")
    current, previous = _split_halves(scatter)
    value = float(current["cycle_time_days"].quantile(0.5))
    if previous.empty or current.empty:
        return Tile(label, f"{value:.1f}d")
    delta = value - float(previous["cycle_time_days"].quantile(0.5))
    if delta == 0:
        return Tile(label, f"{value:.1f}d")
    arrow = "↓" if delta < 0 else "↑"
    # lower cycle time is the good direction
    return Tile(label, f"{value:.1f}d", f"{arrow} {abs(delta):.1f}d", delta < 0)


def _split_halves(scatter: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    start = scatter["finished_at"].min()
    end = scatter["finished_at"].max()
    midpoint = start + (end - start) / 2
    current = scatter[scatter["finished_at"] >= midpoint]
    previous = scatter[scatter["finished_at"] < midpoint]
    return current, previous


def _forecast_tile(forecast: dict[str, Any]) -> Tile:
    label = "85% of backlog done"
    if not forecast:
        return Tile(label, "n/a")
    return Tile(label, f"by {forecast['p85_date']:%d %b %Y}")


def _throughput_tile(throughput: dict[str, int]) -> Tile:
    label = "Throughput"
    if not throughput:
        return Tile(label, "n/a")
    values = list(throughput.values())
    half = len(values) // 2
    current = values[half:]
    value = fmean(current)
    if half < 2:  # noqa: PLR2004
        return Tile(label, f"{value:.1f}/wk")
    delta = value - fmean(values[:half])
    if delta == 0:
        return Tile(label, f"{value:.1f}/wk")
    arrow = "↑" if delta > 0 else "↓"
    # higher throughput is the good direction
    return Tile(label, f"{value:.1f}/wk", f"{arrow} {abs(delta):.1f}", delta > 0)


def build_headline_tiles(
    scatter: pd.DataFrame,
    aging: pd.DataFrame,
    forecast: dict[str, Any],
    throughput: dict[str, int],
    flow_efficiency: float,
) -> list[Tile]:
    """Build the report hero row from the calculated metrics."""
    return [
        _cycle_tile(scatter),
        _forecast_tile(forecast),
        Tile("Open issues", str(len(aging))),
        _throughput_tile(throughput),
        Tile("Flow efficiency", f"{flow_efficiency:.0%}"),
    ]


def build_stuck_rows(
    aging: pd.DataFrame,
    server_url: str,
    limit: int = 10,
) -> list[StuckRow]:
    """Top open issues by age in current status, linked to Jira."""
    if aging.empty:
        return []
    base = server_url.rstrip("/")
    ordered = aging.sort_values("age_days", ascending=False).head(limit)
    return [
        StuckRow(
            key=str(row.key),
            status=str(row.status),
            age_days=round(float(row.age_days), 1),  # type: ignore[arg-type]
            url=f"{base}/browse/{row.key}",
        )
        for row in ordered.itertuples()
    ]
