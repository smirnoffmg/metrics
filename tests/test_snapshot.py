"""Tests for saving and loading raw Jira snapshots."""

from __future__ import annotations

import json
from datetime import UTC, datetime

import pytest

from metrics.repository.snapshot import Snapshot, load_snapshot, save_snapshot
from tests.fakes import make_raw_issue


def _snapshot() -> Snapshot:
    return Snapshot(
        server="https://jira.example",
        jql="project = X",
        fetched_at=datetime(2026, 9, 15, 12, 30, tzinfo=UTC),
        issues=[make_raw_issue("X-1"), make_raw_issue("X-2")],
        statuses={"1": "new", "3": "indeterminate", "6": "done"},
        forecast_jql="fixVersion = 7.2",
        forecast_issues=[make_raw_issue("X-2")],
    )


def test_snapshot_round_trips_through_a_file(tmp_path):
    path = tmp_path / "raw.json"
    save_snapshot(_snapshot(), path)
    assert load_snapshot(path) == _snapshot()


def test_load_snapshot_refuses_an_unknown_format(tmp_path):
    path = tmp_path / "raw.json"
    path.write_text(json.dumps({"version": 99, "issues": []}))
    with pytest.raises(ValueError, match="version"):
        load_snapshot(path)


def test_load_snapshot_saved_before_status_categories(tmp_path):
    path = tmp_path / "raw.json"
    path.write_text(
        json.dumps(
            {
                "version": 1,
                "server": "https://jira.example",
                "jql": "project = X",
                "fetched_at": "2026-09-15T12:30:00+00:00",
                "issues": [],
            },
        ),
    )
    snapshot = load_snapshot(path)
    assert snapshot.statuses == {}
    assert snapshot.forecast_jql == ""
    assert snapshot.forecast_issues == []
