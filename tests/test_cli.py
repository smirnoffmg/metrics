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
                    "items": [
                        {
                            "field": "status",
                            "from": frm,
                            "fromString": frm,
                            "to": to,
                            "toString": to,
                        },
                    ],
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


def test_cli_classifies_statuses_by_category_unless_told_otherwise():
    issues = [
        _raw_issue(
            f"X-{i}",
            "Done",
            ("2026-06-02", "Open", "In Progress"),
            (f"2026-{6 + i % 3:02d}-{10 + i:02d}", "In Progress", "Done"),
            resolution="Fixed",
        )
        for i in range(12)
    ] + [
        _raw_issue("X-50", "Planning", ("2026-09-01", "Open", "Planning")),
        _raw_issue("X-51", "In Progress", ("2026-09-01", "Open", "In Progress")),
    ]
    snapshot = Snapshot(
        server="https://jira.example",
        jql="project = X",
        fetched_at=datetime(2026, 9, 15, tzinfo=UTC),
        issues=issues,
        statuses={
            "Open": "new",
            "Planning": "new",
            "In Progress": "indeterminate",
            "Done": "done",
        },
    )
    runner = CliRunner()
    with runner.isolated_filesystem():
        save_snapshot(snapshot, Path("raw.json"))
        by_category = runner.invoke(cli, ["--from-raw", "raw.json"])
        assert by_category.exit_code == 0, by_category.output
        by_category_report = Path("output/report.html").read_text()
        by_name = runner.invoke(
            cli,
            ["--from-raw", "raw.json", "--backlog-statuses", "open"],
        )
        assert by_name.exit_code == 0, by_name.output
        by_name_report = Path("output/report.html").read_text()
    assert "browse/X-50" not in by_category_report
    assert "browse/X-51" in by_category_report
    assert "browse/X-50" in by_name_report


def _finished_and_open_issues():
    return [
        _raw_issue(
            f"X-{i}",
            "Done",
            ("2026-06-02", "Open", "In Progress"),
            (f"2026-{6 + i % 3:02d}-{10 + i:02d}", "In Progress", "Done"),
            resolution="Fixed",
        )
        for i in range(12)
    ] + [_raw_issue("X-99", "In Progress", ("2026-09-01", "Open", "In Progress"))]


def test_cli_forecasts_the_scope_saved_in_a_snapshot():
    scope = [
        _raw_issue("X-99", "In Progress", ("2026-09-01", "Open", "In Progress")),
        _raw_issue("X-100", "Open"),
        _raw_issue(
            "X-3",
            "Done",
            ("2026-06-02", "Open", "In Progress"),
            ("2026-08-13", "In Progress", "Done"),
            resolution="Fixed",
        ),
    ]
    snapshot = Snapshot(
        server="https://jira.example",
        jql="project = X",
        fetched_at=datetime(2026, 9, 15, tzinfo=UTC),
        issues=_finished_and_open_issues(),
        forecast_jql="fixVersion = 7.2",
        forecast_issues=scope,
    )
    runner = CliRunner()
    with runner.isolated_filesystem():
        save_snapshot(snapshot, Path("raw.json"))
        result = runner.invoke(
            cli,
            ["--from-raw", "raw.json", "--forecast-focus", "0.5"],
        )
        assert result.exit_code == 0, result.output
        report = Path("output/report.html").read_text()
    assert "fixVersion = 7.2: 2 of 3 issues open" in result.output
    assert "50% of throughput" in result.output
    assert "85% of forecast scope done" in report
    assert "fixVersion = 7.2" in report


def test_cli_refuses_a_forecast_query_the_snapshot_was_not_saved_with():
    snapshot = Snapshot(
        server="https://jira.example",
        jql="project = X",
        fetched_at=datetime(2026, 9, 15, tzinfo=UTC),
        issues=_finished_and_open_issues(),
    )
    runner = CliRunner()
    with runner.isolated_filesystem():
        save_snapshot(snapshot, Path("raw.json"))
        result = runner.invoke(
            cli,
            ["--from-raw", "raw.json", "--forecast-jql", "fixVersion = 7.2"],
        )
    assert result.exit_code != 0
    assert "fixVersion = 7.2" in result.output


def test_validate_config_rejects_a_focus_outside_its_range():
    for focus in ("0", "1.5", "half"):
        errors = validate_config({"from_raw": "raw.json", "forecast_focus": focus})
        assert any("focus" in error for error in errors), focus
    assert validate_config({"from_raw": "raw.json", "forecast_focus": "0.4"}) == []


def _delivery_raw():
    def commit(sha, day, title="Change", author="alice"):
        return {
            "id": sha,
            "title": title,
            "author_name": author,
            "author_email": f"{author}@example.com",
            "committed_date": f"2026-08-{day:02d}T10:00:00.000Z",
        }

    def tag(name, sha, day):
        return {
            "name": name,
            "target": sha,
            "created_at": f"2026-08-{day:02d}T12:00:00.000Z",
            "commit": commit(sha, day),
        }

    return {
        "project": "group/app",
        "days": 90,
        "tags": [
            tag("v1.0.0", "c1", 3),
            tag("v1.1.0", "c3", 10),
            tag("v1.1.1", "c4", 11),
        ],
        "releases": [],
        "compares": {
            "v1.1.0": [commit("c2", 5), commit("c3", 9, author="srv_agent")],
            "v1.1.1": [commit("c4", 11, title='Revert "Cache"')],
        },
        "merge_requests": [],
    }


def test_cli_reports_delivery_metrics_saved_in_a_snapshot():
    snapshot = Snapshot(
        server="https://jira.example",
        jql="project = X",
        fetched_at=datetime(2026, 9, 15, tzinfo=UTC),
        issues=_finished_and_open_issues(),
        delivery=_delivery_raw(),
    )
    runner = CliRunner()
    with runner.isolated_filesystem():
        save_snapshot(snapshot, Path("raw.json"))
        result = runner.invoke(
            cli,
            ["--from-raw", "raw.json", "--agent-authors", "srv_agent"],
        )
        assert result.exit_code == 0, result.output
        report = Path("output/report.html").read_text()
    assert "group/app: 3 deploys" in result.output
    assert "Change fail rate" in report
    assert "<td>agents</td><td>1</td>" in report


def test_validate_config_checks_gitlab_settings():
    base = {"from_raw": "raw.json"}
    bad_pattern = validate_config({**base, "deploy_tag_pattern": "v(\\d"})
    assert any("pattern" in error for error in bad_pattern)
    for days in ("0", "-3", "a month"):
        errors = validate_config({**base, "delivery_days": days})
        assert any("days" in error.lower() for error in errors), days
    assert (
        validate_config({**base, "deploy_tag_pattern": "^v", "delivery_days": "30"})
        == []
    )
