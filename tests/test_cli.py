"""Tests for the CLI entrypoint."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from click.testing import CliRunner

from metrics.__main__ import cli, parse_bool, parse_status_list, validate_config
from metrics.consts import (
    BACKLOG_STATUSES,
    DISCARDED_RESOLUTIONS,
    DISCARDED_STATUSES,
    DONE_STATUSES,
    TESTING_STATUSES,
)
from metrics.repository.snapshot import Snapshot, save_snapshot


def test_cli_missing_config():
    runner = CliRunner()
    result = runner.invoke(cli, [])
    assert result.exit_code != 0
    assert "Error" in result.output or "error" in result.output


def test_parse_status_list_from_comma_string():
    assert parse_status_list("Done, Resolved ,CLOSED", DONE_STATUSES) == [
        "done",
        "resolved",
        "closed",
    ]


def test_parse_status_list_from_list():
    assert parse_status_list(["Fertig", "GESCHLOSSEN"], DONE_STATUSES) == [
        "fertig",
        "geschlossen",
    ]


def test_validate_config_anonymous_needs_no_token():
    cfg = {"server": "https://x", "jql": "project=X", "anonymous": True}
    assert validate_config(cfg) == []


def test_validate_config_anonymous_conflicts_with_credentials():
    base = {"server": "https://x", "jql": "project=X", "anonymous": True}
    with_token = validate_config({**base, "token": "t"})
    assert any("--anonymous" in error for error in with_token)
    with_email = validate_config({**base, "email": "me@x.com"})
    assert any("--anonymous" in error for error in with_email)


def test_validate_config_still_requires_token_without_anonymous():
    errors = validate_config({"server": "https://x", "jql": "project=X"})
    assert any("token" in error.lower() for error in errors)


def test_parse_bool():
    assert parse_bool(value=True) is True
    assert parse_bool(None) is False
    assert parse_bool("1") is True
    assert parse_bool("true") is True
    assert parse_bool("no") is False


def test_parse_status_list_defaults():
    assert parse_status_list(None, DONE_STATUSES) == DONE_STATUSES
    assert parse_status_list(None, TESTING_STATUSES) == TESTING_STATUSES


def test_parse_status_list_defaults_for_discarded_and_backlog():
    assert parse_status_list(None, DISCARDED_STATUSES) == DISCARDED_STATUSES
    assert "cancelled" not in DONE_STATUSES
    assert "cancelled" in DISCARDED_STATUSES
    assert "backlog" in BACKLOG_STATUSES


def test_default_discarded_resolutions_cover_jira_defaults():
    assert parse_status_list(None, DISCARDED_RESOLUTIONS) == DISCARDED_RESOLUTIONS
    for resolution in ("won't do", "duplicate", "cannot reproduce"):
        assert resolution in DISCARDED_RESOLUTIONS
    assert "done" not in DISCARDED_RESOLUTIONS
    assert "fixed" not in DISCARDED_RESOLUTIONS


def test_cli_accepts_discarded_resolutions():
    result = CliRunner().invoke(cli, ["--help"])
    assert "--discarded-resolutions" in result.output


def test_validate_config_from_raw_needs_no_jira_settings():
    assert validate_config({"from_raw": "raw.json"}) == []


def _raw_issue(key, status, *steps, resolution=None):
    return {
        "key": key,
        "fields": {
            "created": "2026-06-01T00:00:00.000+0000",
            "status": {"name": status},
            "resolution": {"name": resolution} if resolution else None,
            "assignee": {"displayName": "alice"},
        },
        "changelog": {
            "histories": [
                {
                    "created": f"{day}T00:00:00.000+0000",
                    "items": [{"field": "status", "fromString": frm, "toString": to}],
                }
                for day, frm, to in steps
            ],
        },
    }


def test_cli_builds_the_report_from_a_saved_snapshot_without_jira():
    issues = [
        _raw_issue(
            f"X-{i}",
            "Done",
            ("2026-06-02", "Open", "In Progress"),
            (f"2026-{6 + i % 3:02d}-{10 + i:02d}", "In Progress", "Done"),
            resolution="Fixed",
        )
        for i in range(12)
    ] + [_raw_issue("X-99", "In Progress", ("2026-09-01", "Open", "In Progress"))]
    snapshot = Snapshot(
        server="https://jira.example",
        jql="project = X",
        fetched_at=datetime(2026, 9, 15, tzinfo=UTC),
        issues=issues,
    )
    runner = CliRunner()
    with runner.isolated_filesystem():
        save_snapshot(snapshot, Path("raw.json"))
        result = runner.invoke(cli, ["--from-raw", "raw.json"])
        assert result.exit_code == 0, result.output
        report = Path("output/report.html").read_text()
    assert "https://jira.example/browse/X-99" in report
