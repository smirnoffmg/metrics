"""Interactive plotly chart fragments for the HTML report."""

from __future__ import annotations

import html
from typing import TYPE_CHECKING, Any

import numpy as np
import plotly.graph_objects as go

from .base import BaseService
from .vis import (
    CATEGORICAL,
    INK,
    INK_MUTED,
    INK_SECONDARY,
    MAX_HUES,
    PERCENTILES,
    SERIES,
    SURFACE,
    fan_lines,
    fold_rare_columns,
)

if TYPE_CHECKING:
    import pandas as pd

LINE_DASHES = ("dash", "dashdot", "dot")
FRAGMENT_HEIGHT = 480

# plotly replaces the literal {plot_id} token in post_script with the div id
OPEN_LINK_SCRIPT = (
    "document.getElementById('{plot_id}').on('plotly_click', function(e)"
    " { var url = e.points[0].customdata[1]; if (url) { window.open(url); } });"
)


class InteractiveVisService(BaseService):
    """Builds self-contained plotly HTML fragments."""

    def __init__(self, server_url: str | None = None) -> None:
        """Initialize with the Jira base URL for click-through links."""
        self.server_url = (server_url or "").rstrip("/")
        super().__init__()

    def _browse_url(self, key: object) -> str:
        return f"{self.server_url}/browse/{key}" if self.server_url else ""

    def _to_fragment(
        self,
        fig: go.Figure,
        *,
        include_js: bool,
        clickthrough: bool = False,
    ) -> str:
        fig.update_layout(
            paper_bgcolor=SURFACE,
            plot_bgcolor=SURFACE,
            font={
                "family": 'system-ui, -apple-system, "Segoe UI", sans-serif',
                "color": INK,
            },
            margin={"l": 70, "r": 40, "t": 70, "b": 60},
        )
        return fig.to_html(
            full_html=False,
            include_plotlyjs=include_js,
            default_height=FRAGMENT_HEIGHT,
            post_script=OPEN_LINK_SCRIPT if clickthrough else None,
            config={"displaylogo": False},
        )

    def scatter_fragment(self, df: pd.DataFrame, *, include_js: bool = False) -> str:
        """Cycle-time scatter with per-issue hover and click-through."""
        fig = go.Figure()
        if not df.empty:
            fig.add_trace(
                go.Scatter(
                    x=df["finished_at"],
                    y=df["cycle_time_days"],
                    mode="markers",
                    marker={"color": SERIES, "size": 9, "opacity": 0.75},
                    customdata=[[key, self._browse_url(key)] for key in df["key"]],
                    hovertemplate=(
                        "<b>%{customdata[0]}</b><br>%{y:.1f} days"
                        "<br>finished %{x|%d %b %Y}"
                        "<br><i>click to open</i><extra></extra>"
                    ),
                ),
            )
            for pct, dash in zip(PERCENTILES, LINE_DASHES, strict=True):
                value = float(np.percentile(df["cycle_time_days"], pct))
                fig.add_hline(
                    y=value,
                    line_dash=dash,
                    line_color=INK_SECONDARY,
                    annotation_text=f"p{pct} = {value:.1f}d",
                    annotation_font_color=INK_SECONDARY,
                )
        fig.update_layout(
            title="Cycle Time per Issue — hover a dot, click to open the ticket",
            xaxis_title="finished",
            yaxis_title="cycle time, days",
            showlegend=False,
        )
        return self._to_fragment(fig, include_js=include_js, clickthrough=True)

    def forecast_fragment(
        self,
        result: dict[str, Any],
        *,
        include_js: bool = False,
        title: str | None = None,
        promise: tuple[int, float] | None = None,
    ) -> str:
        """Issues of today's list still open week by week, at the median and at 85%."""
        weeks, median_left, left_85 = fan_lines(result)
        fig = go.Figure()
        fig.add_trace(
            go.Scatter(
                x=weeks,
                y=left_85,
                mode="lines",
                line={"color": SERIES, "width": 2},
                name="85% chance of at most",
                hovertemplate="week %{x}: at most %{y:.0f} open (85%)<extra></extra>",
            ),
        )
        fig.add_trace(
            go.Scatter(
                x=weeks,
                y=median_left,
                mode="lines",
                fill="tonexty",
                fillcolor="rgba(42,120,214,0.12)",
                line={"color": INK_SECONDARY, "width": 1.5, "dash": "dash"},
                name="50% chance of at most",
                hovertemplate="week %{x}: %{y:.0f} open (median)<extra></extra>",
            ),
        )
        if promise is not None and promise[0] < len(weeks):
            fig.add_trace(
                go.Scatter(
                    x=[promise[0]],
                    y=[result["backlog"] - promise[1]],
                    mode="markers+text",
                    marker={"color": SERIES, "size": 11},
                    text=[f"in {promise[0]} weeks"],
                    textposition="bottom right",
                    showlegend=False,
                    hoverinfo="skip",
                ),
            )
        if result["p85"] is not None:
            fig.add_vline(
                x=result["p85"],
                line_dash="dot",
                line_color=INK_SECONDARY,
                annotation_text=f"all done by {result['p85_date']:%d %b %Y} (85%)",
                annotation_font_color=INK_SECONDARY,
            )
        fig.update_layout(
            # plotly renders HTML tags in titles, and JQL is full of < and >
            title=html.escape(title).replace("\n", "<br>")
            if title
            else f"How many of the {result['backlog']} open issues stay open",
            xaxis_title="weeks from now",
            yaxis_title="issues from today's list still open",
            yaxis_rangemode="tozero",
            legend={"x": 0.99, "xanchor": "right", "y": 0.99},
        )
        return self._to_fragment(fig, include_js=include_js)

    def cfd_fragment(self, df: pd.DataFrame, *, include_js: bool = False) -> str:
        """Cumulative flow diagram as stacked areas with per-band hover."""
        fig = go.Figure()
        if not df.empty:
            df = fold_rare_columns(df)
            for i, column in enumerate(df.columns):
                color = INK_MUTED if column == "Other" else CATEGORICAL[i % MAX_HUES]
                fig.add_trace(
                    go.Scatter(
                        x=list(df.index),
                        y=df[column],
                        name=str(column),
                        stackgroup="one",
                        mode="lines",
                        line={"width": 0.6, "color": color},
                        hovertemplate="%{y} issues<extra>" + str(column) + "</extra>",
                    ),
                )
        fig.update_layout(
            title="Cumulative Flow Diagram",
            xaxis_title="date",
            yaxis_title="issues",
        )
        return self._to_fragment(fig, include_js=include_js)

    def aging_fragment(self, df: pd.DataFrame, *, include_js: bool = False) -> str:
        """Aging WIP dots with click-through and p85 markers."""
        fig = go.Figure()
        if not df.empty:
            fig.add_trace(
                go.Scatter(
                    x=df["status"],
                    y=df["age_days"],
                    mode="markers",
                    marker={"color": SERIES, "size": 10, "opacity": 0.8},
                    customdata=[[key, self._browse_url(key)] for key in df["key"]],
                    hovertemplate=(
                        "<b>%{customdata[0]}</b><br>%{y:.1f} days in %{x}"
                        "<br><i>click to open</i><extra></extra>"
                    ),
                ),
            )
            for i, status in enumerate(df["status"].unique()):
                ref = df.loc[df["status"] == status, "p85_days"].iloc[0]
                if not np.isnan(ref):
                    fig.add_shape(
                        type="line",
                        x0=i - 0.4,
                        x1=i + 0.4,
                        y0=float(ref),
                        y1=float(ref),
                        line={"dash": "dash", "color": INK_SECONDARY, "width": 2},
                    )
        fig.update_layout(
            title="Aging Work-in-Progress — dashes mark the historical p85",
            xaxis_title="current status",
            yaxis_title="age in status, days",
            showlegend=False,
        )
        return self._to_fragment(fig, include_js=include_js, clickthrough=True)
