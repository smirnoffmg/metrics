"""Headline stat tiles and stuck-ticket rows for the report."""

from __future__ import annotations

from dataclasses import dataclass
from statistics import fmean, median
from typing import TYPE_CHECKING, Any

from .backtest import (
    MIN_INDEPENDENT_OUTCOMES,
    SIGNIFICANCE,
    judgeable_summaries,
    recalibration_helps,
)

if TYPE_CHECKING:
    from collections.abc import Sequence

    import pandas as pd

    from .backtest import BacktestSummary

CLAIMED_CHANCE = 0.85


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


def _forecast_tile(forecast: dict[str, Any], label: str) -> Tile:
    if not forecast:
        return Tile(label, "n/a")
    if forecast.get("recalibrated"):
        label = f"{label}, recalibrated"
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


def build_headline_tiles(  # noqa: PLR0913
    scatter: pd.DataFrame,
    aging: pd.DataFrame,
    forecast: dict[str, Any],
    throughput: dict[str, int],
    flow_efficiency: float,
    scope_tile: Tile | None = None,
    backtest: Tile | None = None,
) -> list[Tile]:
    """Build the report hero row; scope_tile is None without a forecast query."""
    tiles = [
        _cycle_tile(scatter),
        _forecast_tile(forecast, "85% of backlog done"),
        *([backtest] if backtest is not None else []),
        Tile("Work in progress", str(len(aging))),
        _throughput_tile(throughput),
        Tile("Flow efficiency", f"{flow_efficiency:.0%}"),
    ]
    if scope_tile is not None:
        tiles.insert(2, scope_tile)
    return tiles


def scope_forecast_tile(forecast: dict[str, Any], open_count: int) -> Tile:
    """Headline tile for the forecast query's issues."""
    label = "85% of forecast scope done"
    if open_count == 0:
        return Tile(label, "all done")
    return _forecast_tile(forecast, label)


def backtest_tile(summary: BacktestSummary | None) -> Tile:
    """How often past 85% forecasts over the horizon came true."""
    if summary is None:
        return Tile("85% forecasts held", "n/a")
    held = summary.held_85
    label = f"of {summary.count} past {summary.horizon}-week 85% forecasts held"
    if summary.independent < MIN_INDEPENDENT_OUTCOMES:
        return Tile(
            label,
            f"{held:.0%}",
            f"only {summary.independent} independent outcomes",
        )
    return Tile(
        label,
        f"{held:.0%}",
        "as promised" if held >= CLAIMED_CHANCE else "fewer than promised",
        held >= CLAIMED_CHANCE,
    )


def diagnose_backtest(summaries: Sequence[BacktestSummary]) -> str:
    """Say whether past forecast errors drift or keep a steady bias, drift first.

    Fenton and Pfleeger recalibrate forecasts from past errors only when those
    errors are stationary, so drift at any horizon with enough independent
    outcomes rules correction out; a short horizon's test has the most of them.
    """
    tested = judgeable_summaries(summaries)
    if not tested:
        return "Too few independent outcomes to test forecast errors for bias or drift."
    drift = min(tested, key=lambda s: s.trend_p or 0.0)
    bias = min(tested, key=lambda s: s.bias_p or 0.0)
    horizons = _horizons(tested)
    if drift.trend_p is not None and drift.trend_p < SIGNIFICANCE:
        return (
            f"{drift.horizon}-week forecast errors drift over time"
            f" (y-plot p = {drift.trend_p:.3f}): the team's pace changes,"
            " so correcting forecasts by their past errors would not hold."
        )
    if bias.bias_p is not None and bias.bias_p < SIGNIFICANCE:
        return (
            f"{bias.horizon}-week forecasts err the same way throughout"
            f" (u-plot p = {bias.bias_p:.3f}), with no sign of drift at {horizons}:"
            " the case for recalibrating them by past errors."
        )
    return (
        f"No sign that forecasts over {horizons} are biased or drift over time"
        f" (lowest u-plot p = {bias.bias_p:.3f},"
        f" lowest y-plot p = {drift.trend_p:.3f})."
    )


def recalibration_note(raw: BacktestSummary, recalibrated: BacktestSummary) -> str:
    """Say what recalibrating past forecasts did, and whether the forecast is."""
    helps = recalibration_helps(raw, recalibrated)
    score = "and scored a better" if helps else "but scored a worse"
    return (
        f"Recalibrated by their past errors, {raw.horizon}-week forecasts kept"
        f" {recalibrated.held_85:.0%} of their 85% promises instead of"
        f" {raw.held_85:.0%} {score} CRPS"
        f" ({recalibrated.mean_crps:.1f} against {raw.mean_crps:.1f}),"
        f" so the forecast is {'' if helps else 'not '}recalibrated."
    )


def _horizons(summaries: Sequence[BacktestSummary]) -> str:
    weeks = [str(s.horizon) for s in sorted(summaries, key=lambda s: s.horizon)]
    listed = weeks[0] if len(weeks) == 1 else f"{', '.join(weeks[:-1])} or {weeks[-1]}"
    return f"{listed} weeks"


def build_stuck_rows(
    aging: pd.DataFrame,
    server_url: str,
    limit: int = 10,
) -> list[StuckRow]:
    """Top in-progress issues by age in current status, linked to Jira."""
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


def build_delivery_tiles(
    weekly: dict[str, int],
    lead_times: pd.DataFrame,
    failure_rate: float | None,
    recovery_days: list[float],
) -> list[Tile]:
    """Build DORA's four keys as headline tiles."""
    lead = lead_times["lead_time_days"]
    return [
        Tile("Deploys", f"{fmean(weekly.values()):.1f}/wk" if weekly else "n/a"),
        Tile(
            "Change lead time p50",
            f"{float(lead.quantile(0.5)):.1f}d" if len(lead) else "n/a",
        ),
        Tile(
            "Change fail rate",
            f"{failure_rate:.0%}" if failure_rate is not None else "n/a",
        ),
        Tile(
            "Recovery time p50",
            f"{median(recovery_days):.1f}d" if recovery_days else "no failures",
        ),
    ]
