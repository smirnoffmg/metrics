"""Visualization service for rendering metric charts."""

from __future__ import annotations

import math
from typing import TYPE_CHECKING

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import seaborn as sns
from matplotlib.container import BarContainer
from matplotlib.patches import Patch

from .base import BaseService

if TYPE_CHECKING:
    from typing import Any

    from matplotlib.artist import Artist
    from matplotlib.axes import Axes
    from matplotlib.figure import Figure

PERCENTILES = (50, 85, 95)
PERCENTILE_STYLES = ("--", "-.", ":")

CATEGORICAL = (
    "#2a78d6",
    "#1baf7a",
    "#eda100",
    "#008300",
    "#4a3aa7",
    "#e34948",
    "#e87ba4",
    "#eb6834",
)
SERIES = CATEGORICAL[0]
SURFACE = "#fcfcfb"
GRID = "#e1e0d9"
INK = "#0b0b0b"
INK_SECONDARY = "#52514e"
INK_MUTED = "#898781"
BASELINE = "#c3c2b7"

ZONE = "#e34948"
ZONE_ALPHA = 0.08

FIGSIZE = (10, 6)
WIDE_FIGSIZE = (12, 6)
DPI = 150
MAX_X_TICKS = 12
MAX_HUES = len(CATEGORICAL)
RECENT_DAYS = 28
GRID_COLS = 3
MIN_ANNOTATED_DROP = 3


def fold_rare_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Fold the smallest columns into "Other" to stay within 8 hues."""
    if len(df.columns) <= MAX_HUES:
        return df
    keep_count = MAX_HUES - 1
    keep = set(df.sum().nlargest(keep_count).index)
    folded = df[[c for c in df.columns if c in keep]].copy()
    folded["Other"] = df[[c for c in df.columns if c not in keep]].sum(axis=1)
    return folded


def biggest_drop(df: pd.DataFrame) -> tuple[Any, str, int] | None:
    """Find the largest one-step decrease in any column: (index, column, size)."""
    best: tuple[Any, str, int] | None = None
    for column in df.columns:
        diffs = df[column].diff()
        drop = diffs.min()
        if pd.notna(drop) and drop < 0 and (best is None or -drop > best[2]):
            best = (diffs.idxmin(), str(column), int(-drop))
    return best


class VisService(BaseService):
    """Renders and saves metric charts as PNG images."""

    def __init__(self) -> None:
        """Apply the chart theme once for all charts."""
        sns.set_theme(
            style="whitegrid",
            font_scale=1.1,
            rc={
                "figure.figsize": FIGSIZE,
                "figure.facecolor": SURFACE,
                "axes.facecolor": SURFACE,
                "savefig.facecolor": SURFACE,
                "grid.color": GRID,
                "grid.linestyle": "-",
                "grid.linewidth": 0.8,
                "axes.edgecolor": BASELINE,
                "axes.linewidth": 0.8,
                "text.color": INK,
                "axes.labelcolor": INK_SECONDARY,
                "xtick.color": INK_MUTED,
                "ytick.color": INK_MUTED,
                "legend.frameon": True,
                "legend.facecolor": SURFACE,
                "legend.edgecolor": GRID,
                "legend.framealpha": 0.9,
            },
        )
        super().__init__()

    def _save_figure(self, fig: Figure, filename: str) -> None:
        try:
            fig.savefig(filename, dpi=DPI, bbox_inches="tight")
        except Exception as err:
            self.logger.exception(
                "Failed to save figure to %s",
                filename,
            )
            msg = f"Failed to save figure to {filename}: {err}"
            raise RuntimeError(msg) from err
        finally:
            plt.close(fig)

    def vis_df(
        self,
        filename: str,
        data: dict,
        x_label: str = "x_label",
        y_label: str = "y_label",
    ) -> None:
        """Render a labeled bar chart with a trend line from a dict."""
        fig, ax = plt.subplots()
        labels = list(data)
        values = list(data.values())
        if labels:
            positions = list(range(len(labels)))
            recent_start = max(0, len(labels) - 4)
            colors = [SERIES if i >= recent_start else INK_MUTED for i in positions]
            ax.bar(positions, values, color=colors, width=0.8)
            tick_step = max(1, math.ceil(len(labels) / MAX_X_TICKS))
            shown = positions[::tick_step]
            ax.set_xticks(shown, labels=[labels[i] for i in shown])
            plt.setp(ax.get_xticklabels(), rotation=45, ha="right")
            peak = int(np.argmax(values))
            ax.annotate(
                f"{values[peak]} finished",
                xy=(peak, values[peak]),
                xytext=(0, 6),
                textcoords="offset points",
                ha="center",
                color=INK_SECONDARY,
            )
            handles: list[Artist] = [Patch(color=SERIES, label="last 4 weeks")]
            if recent_start > 0:
                handles.append(Patch(color=INK_MUTED, label="earlier"))
            if len(values) > 1:
                slope, intercept = np.polyfit(positions, values, 1)
                trend = [slope * x + intercept for x in positions]
                (trend_line,) = ax.plot(
                    positions,
                    trend,
                    color=INK_SECONDARY,
                    linewidth=2,
                    label="trend",
                )
                handles.append(trend_line)
            ax.legend(handles=handles)
        ax.set_xlabel(x_label.replace("_", " "))
        ax.set_ylabel(y_label.replace("_", " "))
        self._save_figure(fig, filename)

    def vis_cumulative_queue_time(
        self,
        filename: str,
        df: pd.DataFrame,
    ) -> None:
        """Render a horizontal bar chart of cumulative queue time."""
        fig, ax = plt.subplots()
        if not df.empty:
            df = df.sort_values(by="median_hours", ascending=False)
            hbars = ax.barh(
                y=df["status"],
                width=df["median_hours"],
                color=SERIES,
            )
            ax.set_yticks(
                df["status"],
                labels=(df["status"] + " (" + df["count"].astype(str) + ")"),
            )
            ax.invert_yaxis()
            ax.bar_label(
                hbars,
                labels=df["median_hours"].astype(str) + "h",
                padding=4,
                color=INK_SECONDARY,
            )
            ax.set_xlim(right=max(df["median_hours"]) * 1.3)
        ax.set_xlabel("Median hours")
        ax.set_ylabel("Status")
        ax.set_title("Median Hours in Each Status")
        ax.grid(axis="x")
        self._save_figure(fig, filename)

    def _percentile_lines(
        self,
        ax: Axes,
        values: list[float],
        labels: list[str],
        *,
        vertical: bool = False,
    ) -> None:
        """Draw p50/p85/p95 reference lines labeled through the legend."""
        for style, value, label in zip(
            PERCENTILE_STYLES,
            values,
            labels,
            strict=True,
        ):
            line_fn = ax.axvline if vertical else ax.axhline
            line_fn(
                value,
                linestyle=style,
                color=INK_SECONDARY,
                linewidth=1.5,
                label=label,
            )
        ax.legend()

    def vis_scatter_percentiles(self, filename: str, df: pd.DataFrame) -> None:
        """Render cycle-time scatter with percentile lines and a slow zone."""
        fig, ax = plt.subplots()
        if not df.empty:
            cutoff = df["finished_at"].max() - pd.Timedelta(days=RECENT_DAYS)
            recent = df["finished_at"] >= cutoff
            if (~recent).any():
                ax.scatter(
                    df.loc[~recent, "finished_at"],
                    df.loc[~recent, "cycle_time_days"],
                    color=INK_MUTED,
                    alpha=0.45,
                    s=42,
                    label="earlier",
                )
            ax.scatter(
                df.loc[recent, "finished_at"],
                df.loc[recent, "cycle_time_days"],
                color=SERIES,
                alpha=0.8,
                s=42,
                label="last 4 weeks",
            )
            values = [
                float(np.percentile(df["cycle_time_days"], p)) for p in PERCENTILES
            ]
            self._percentile_lines(
                ax,
                values,
                [f"p{p} = {v:.1f}d" for p, v in zip(PERCENTILES, values, strict=True)],
            )
            top = max(float(df["cycle_time_days"].max()) * 1.08, values[1] * 1.05)
            ax.set_ylim(top=top)
            ax.axhspan(values[1], top, color=ZONE, alpha=ZONE_ALPHA, label="slow zone")
            slowest = df.loc[df["cycle_time_days"].idxmax()]
            ax.annotate(
                str(slowest["key"]),
                xy=(slowest["finished_at"], float(slowest["cycle_time_days"])),  # type: ignore[arg-type]
                xytext=(-10, -12),
                textcoords="offset points",
                ha="right",
                color=INK_SECONDARY,
            )
            ax.legend()
            fig.autofmt_xdate()
        ax.set_xlabel("finished")
        ax.set_ylabel("cycle time, days")
        ax.set_title("Cycle Time per Issue")
        self._save_figure(fig, filename)

    def vis_forecast(self, filename: str, result: dict[str, Any]) -> None:
        """Render the Monte Carlo weeks-to-complete histogram."""
        fig, ax = plt.subplots()
        weeks = result["weeks"]
        ax.hist(
            weeks,
            bins=range(int(weeks.min()), int(weeks.max()) + 2),
            rwidth=0.9,
            align="left",
            color=SERIES,
        )
        self._percentile_lines(
            ax,
            [result[f"p{p}"] for p in PERCENTILES],
            [
                f"p{p} = {result[f'p{p}']:.0f}w (by {result[f'p{p}_date']:%d %b %Y})"
                for p in PERCENTILES
            ],
            vertical=True,
        )
        ax.set_xlabel("weeks to complete backlog")
        ax.set_ylabel("simulations")
        ax.set_title(f"Monte Carlo Forecast ({result['backlog']} open issues)")
        self._save_figure(fig, filename)

    def vis_aging_wip(self, filename: str, df: pd.DataFrame) -> None:
        """Render open-issue age per status with historical p85 markers."""
        fig, ax = plt.subplots()
        if not df.empty:
            statuses = list(df["status"].unique())
            sns.stripplot(
                data=df,
                x="status",
                y="age_days",
                order=statuses,
                color=SERIES,
                alpha=0.8,
                jitter=0.2,
                size=9,
                ax=ax,
            )
            labeled = False
            top = float(df["age_days"].max()) * 1.1
            ax.set_ylim(top=top)
            for i, status in enumerate(statuses):
                ref = df.loc[df["status"] == status, "p85_days"].iloc[0]
                if pd.notna(ref):
                    ax.hlines(
                        ref,
                        i - 0.4,
                        i + 0.4,
                        colors=INK_SECONDARY,
                        linestyles="--",
                        linewidth=2,
                        label="_nolegend_" if labeled else "historical p85",
                    )
                    if ref < top:
                        ax.fill_between(
                            [i - 0.4, i + 0.4],
                            ref,
                            top,
                            color=ZONE,
                            alpha=ZONE_ALPHA,
                        )
                    labeled = True
            if labeled:
                ax.legend()
        ax.set_xlabel("current status")
        ax.set_ylabel("age in status, days")
        ax.set_title("Aging Work-in-Progress")
        self._save_figure(fig, filename)

    def vis_cfd(self, filename: str, df: pd.DataFrame) -> None:
        """Render the cumulative flow diagram as a stacked area chart."""
        fig, ax = plt.subplots(figsize=WIDE_FIGSIZE)
        if not df.empty:
            df = fold_rare_columns(df)
            ax.stackplot(
                df.index,
                [df[column] for column in df.columns],
                labels=list(df.columns),
                colors=[
                    INK_MUTED if column == "Other" else CATEGORICAL[i % MAX_HUES]
                    for i, column in enumerate(df.columns)
                ],
                alpha=0.85,
            )
            ax.legend(loc="upper left", bbox_to_anchor=(1.02, 1))
            drop = biggest_drop(df)
            if drop is not None and drop[2] >= MIN_ANNOTATED_DROP:
                day, column, size = drop
                ax.annotate(
                    f"{column}: -{size} in one day",
                    xy=(day, float(df.sum(axis=1).loc[day])),
                    xytext=(0, 18),
                    textcoords="offset points",
                    ha="center",
                    color=INK_SECONDARY,
                    arrowprops={"arrowstyle": "->", "color": INK_MUTED},
                )
            fig.autofmt_xdate()
        ax.set_xlabel("date")
        ax.set_ylabel("issues")
        ax.set_title("Cumulative Flow Diagram")
        self._save_figure(fig, filename)

    def vis_assignee_load(
        self,
        filename: str,
        df: pd.DataFrame,
        handoffs: list[int],
    ) -> None:
        """Render per-assignee time-in-flight and handoffs distribution."""
        fig, (ax_load, ax_handoffs) = plt.subplots(1, 2, figsize=WIDE_FIGSIZE)
        if not df.empty:
            bars = ax_load.barh(df["assignee"], df["total_days"], color=SERIES)
            ax_load.set_yticks(
                df["assignee"],
                labels=(df["assignee"] + " (" + df["issue_count"].astype(str) + ")"),
            )
            ax_load.invert_yaxis()
            ax_load.bar_label(
                bars,
                fmt="%.1fd",
                padding=4,
                color=INK_SECONDARY,
            )
        ax_load.set_xlabel("total days in flight (issue count)")
        ax_load.set_title("Assignee Load")
        ax_load.grid(axis="x")
        if handoffs:
            ax_handoffs.hist(
                handoffs,
                bins=range(min(handoffs), max(handoffs) + 2),
                rwidth=0.9,
                align="left",
                color=SERIES,
            )
        ax_handoffs.set_xlabel("handoffs per issue")
        ax_handoffs.set_ylabel("issues")
        ax_handoffs.set_title("Handoffs")
        fig.tight_layout()
        self._save_figure(fig, filename)

    def vis_queue_grid(
        self,
        filename: str,
        queue_time: dict[str, list[float]],
    ) -> None:
        """Render one faceted figure of days-in-status histograms."""
        count = max(len(queue_time), 1)
        cols = min(GRID_COLS, count)
        rows = math.ceil(count / cols)
        fig, axes = plt.subplots(
            rows,
            cols,
            figsize=(4 * cols, 3.2 * rows),
            squeeze=False,
        )
        flat = [ax for row in axes for ax in row]
        for ax, (status, values) in zip(flat, queue_time.items(), strict=False):
            ax.hist(values, bins=5, rwidth=0.9, color=SERIES)
            ax.set_title(status, fontsize=11, color=INK_SECONDARY)
        for ax in flat[len(queue_time) :]:
            ax.set_visible(False)
        fig.suptitle("Days in Each Status")
        fig.supxlabel("days")
        fig.supylabel("number of issues")
        fig.tight_layout()
        self._save_figure(fig, filename)

    def vis_array_like(
        self,
        filename: str,
        arr: list[int] | list[float],
        x_label: str = "x_label",
        y_label: str = "y_label",
    ) -> None:
        """Render a histogram from an array and save to file."""
        fig, ax = plt.subplots()
        counts, _, bars = ax.hist(
            arr,
            bins=5,
            rwidth=0.9,
            align="mid",
            color=SERIES,
        )
        if isinstance(bars, BarContainer):
            ax.bar_label(
                bars,
                labels=[f"{int(c)}" if c else "" for c in counts],
                padding=3,
                color=INK_SECONDARY,
            )
        ax.set_xlabel(x_label)
        ax.set_ylabel(y_label)
        self._save_figure(fig, filename)
