"""Tests for interactive plotly HTML fragments."""

from __future__ import annotations

from datetime import UTC, date, datetime

import numpy as np
import pandas as pd

from metrics.services.interactive import InteractiveVisService

SERVER = "https://jira.example.com"


def _service():
    return InteractiveVisService(server_url=SERVER)


def _unescape(fragment: str) -> str:
    return fragment.replace("\\u002f", "/")


def test_scatter_fragment_contains_keys_and_links():
    df = pd.DataFrame(
        {
            "key": ["A-1", "A-2"],
            "finished_at": [
                datetime(2024, 1, 5, tzinfo=UTC),
                datetime(2024, 1, 12, tzinfo=UTC),
            ],
            "cycle_time_days": [2.0, 5.0],
        },
    )
    fragment = _service().scatter_fragment(df)
    assert "plotly" in fragment.lower()
    assert "A-1" in fragment
    assert f"{SERVER}/browse/A-2" in _unescape(fragment)


def test_scatter_fragment_embeds_js_only_on_request():
    df = pd.DataFrame(
        {
            "key": ["A-1"],
            "finished_at": [datetime(2024, 1, 5, tzinfo=UTC)],
            "cycle_time_days": [2.0],
        },
    )
    with_js = _service().scatter_fragment(df, include_js=True)
    without_js = _service().scatter_fragment(df)
    assert len(with_js) > len(without_js) * 2


def test_cfd_fragment_contains_statuses():
    df = pd.DataFrame(
        {"New": [1, 2, 1], "In Progress": [0, 0, 1]},
        index=pd.Index([date(2024, 1, d) for d in (1, 2, 3)], name="date"),
    )
    fragment = _service().cfd_fragment(df)
    assert "New" in fragment
    assert "In Progress" in fragment


def _fan_forecast() -> dict:
    return {
        "weeks": np.array([3, 4, 5]),
        "backlog": 7,
        "max_weeks": 6,
        "done_p50": np.array([2.0, 4.0, 6.0, 7.0, 7.0, 7.0]),
        "done_at_least_85": np.array([1.0, 3.0, 4.0, 6.0, 7.0, 7.0]),
        "p50": 4.0,
        "p50_date": date(2026, 8, 12),
        "p85": 5.0,
        "p85_date": date(2026, 8, 19),
        "p95": 5.0,
        "p95_date": date(2026, 8, 19),
    }


def test_forecast_fragment_draws_open_issues_left_week_by_week():
    fragment = _service().forecast_fragment(_fan_forecast(), promise=(4, 6.0))
    assert "weeks from now" in fragment
    assert "issues from today's list still open" in fragment
    assert "85% chance of at most" in fragment
    assert "all done by 19 Aug 2026" in fragment
    assert "in 4 weeks" in fragment


def test_forecast_fragment_marks_the_promised_number_not_the_fan():
    # the headline may be recalibrated, so the fan's own 85% line can differ
    fragment = _service().forecast_fragment(_fan_forecast(), promise=(4, 2.0))
    assert '"x":[4],"y":[5.0]' in fragment


def test_forecast_fragment_says_when_the_list_does_not_clear():
    result = {**_fan_forecast(), "p85": None, "p85_date": None}
    fragment = _service().forecast_fragment(result)
    assert "all done by" not in fragment


def test_aging_fragment_contains_keys_and_links():
    df = pd.DataFrame(
        {
            "key": ["B-1"],
            "status": ["Open"],
            "age_days": [3.0],
            "p85_days": [4.0],
        },
    )
    fragment = _service().aging_fragment(df)
    assert "B-1" in fragment
    assert f"{SERVER}/browse/B-1" in _unescape(fragment)
