"""Tests for the CLI entrypoint."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
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


def test_cli_report_names_no_assignee():
    passed_on = _raw_issue(
        "X-1",
        "Done",
        ("2026-06-02", "Open", "In Progress"),
        ("2026-06-20", "In Progress", "Done"),
        resolution="Fixed",
    )
    passed_on["fields"]["assignee"] = {"displayName": "Zelda Quartermain"}
    passed_on["changelog"]["histories"].append(
        {
            "created": "2026-06-10T00:00:00.000+0000",
            "items": [
                {
                    "field": "assignee",
                    "from": "bob",
                    "fromString": "Bob Lindqvist",
                    "to": "zelda",
                    "toString": "Zelda Quartermain",
                },
            ],
        },
    )
    snapshot = Snapshot(
        server="https://jira.example",
        jql="project = X",
        fetched_at=datetime(2026, 9, 15, tzinfo=UTC),
        issues=[passed_on],
    )
    runner = CliRunner()
    with runner.isolated_filesystem():
        save_snapshot(snapshot, Path("raw.json"))
        result = runner.invoke(cli, ["--from-raw", "raw.json"])
        assert result.exit_code == 0, result.output
        report = Path("output/report.html").read_text()
        assert not list(Path("output").glob("assignee*"))
        assert Path("output/handoffs.png").exists()
    assert "Zelda" not in report
    assert "Lindqvist" not in report
    assert "assignee" not in report.lower()


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
    assert "50% of team throughput, assumed, not checked" in result.output
    assert "all 3 issues of the scope done (85% chance)" in report
    assert "fixVersion = 7.2" in report


def _release_and_team_issues():
    """A release finishing one issue a week, ten left; the team finishes ten a week."""
    scope, team = [], []
    for week in range(32):
        tuesday = date(2026, 2, 3) + timedelta(weeks=week)
        scope.append(
            _raw_issue(
                f"S-{week}",
                "Done",
                (str(tuesday), "Open", "Done"),
                resolution="Fixed",
            ),
        )
        for n in range(9):
            raw = _raw_issue(
                f"T-{week}-{n}",
                "Done",
                (str(tuesday + timedelta(days=1)), "Open", "Done"),
                resolution="Fixed",
            )
            raw["fields"]["created"] = f"{tuesday}T00:00:00.000+0000"
            team.append(raw)
    scope += [_raw_issue(f"S-open-{n}", "Open") for n in range(10)]
    for raw in scope:
        raw["fields"]["created"] = "2026-02-02T00:00:00.000+0000"
    return scope, team + scope


def _run_release(*args):
    scope, issues = _release_and_team_issues()
    snapshot = Snapshot(
        server="https://jira.example",
        jql="project = X",
        fetched_at=datetime(2026, 9, 18, tzinfo=UTC),
        issues=issues,
        forecast_jql="fixVersion = 7.2",
        forecast_issues=scope,
    )
    runner = CliRunner()
    with runner.isolated_filesystem():
        save_snapshot(snapshot, Path("raw.json"))
        result = runner.invoke(cli, ["--from-raw", "raw.json", *args])
        assert result.exit_code == 0, result.output
        report = Path("output/report.html").read_text()
    return result.output, report


def test_scope_forecast_uses_scope_throughput_when_history_suffices():
    output, report = _run_release()
    # at all of the team's ten a week, all ten would be promised
    assert "Scope: at least 8 of 10 open issues done in 8 weeks (85%)" in output
    assert "from the scope's own finishes" in output
    assert "Scope backtest: held " in output
    assert "<td>scope: open work</td>" in report
    assert "all 42 issues of the scope done (85% chance)" in report


def test_forecast_focus_given_overrides_measured_scope():
    output, _ = _run_release("--forecast-focus", "0.5")
    assert "50% of team throughput, assumed, not checked" in output
    assert "Scope: at least" not in output
    assert "Scope backtest" not in output


def test_scope_without_history_says_not_checked():
    scope = [
        _raw_issue("X-99", "In Progress", ("2026-09-01", "Open", "In Progress")),
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
        result = runner.invoke(cli, ["--from-raw", "raw.json"])
        assert result.exit_code == 0, result.output
    assert "at team throughput, not checked" in result.output
    assert "Scope backtest" not in result.output


def test_cli_reports_a_list_that_does_not_clear_within_two_years():
    never_cleared = [_raw_issue(f"X-{100 + i}", "Open") for i in range(300)]
    snapshot = Snapshot(
        server="https://jira.example",
        jql="project = X",
        fetched_at=datetime(2026, 9, 15, tzinfo=UTC),
        issues=_finished_and_open_issues() + never_cleared,
        forecast_jql="fixVersion = 7.2",
        forecast_issues=never_cleared,
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
    assert "not within 2 years" in result.output
    assert "not within 2 years" in report


def _late_arrivals_first_issues():
    """Each week three arrive: one done that week, one the next, one never."""
    issues = []
    for week in range(32):
        tuesday = date(2026, 2, 3) + timedelta(weeks=week)
        for name, done_after in (("A", 9), ("B", 2), (None, None)):
            key = f"{name or 'C'}-{week}"
            if done_after is None:
                raw = _raw_issue(key, "Open")
            else:
                raw = _raw_issue(
                    key,
                    "Done",
                    (str(tuesday + timedelta(days=done_after)), "Open", "Done"),
                    resolution="Fixed",
                )
            raw["fields"]["created"] = f"{tuesday}T00:00:00.000+0000"
            issues.append(raw)
    return issues


def test_backtest_replays_issues_open_at_each_monday():
    snapshot = Snapshot(
        server="https://jira.example",
        jql="project = X",
        fetched_at=datetime(2026, 9, 18, tzinfo=UTC),
        issues=_late_arrivals_first_issues(),
    )
    runner = CliRunner()
    with runner.isolated_filesystem():
        save_snapshot(snapshot, Path("raw.json"))
        result = runner.invoke(cli, ["--from-raw", "raw.json"])
        assert result.exit_code == 0, result.output
        report = Path("output/report.html").read_text()
    assert "Forecast: at least 1 of 32 open issues done in" in result.output
    assert "of 32 open issues done in" in report
    assert "Baseline (all throughput to open issues): held 0 of" in result.output
    assert "85% of backlog done" not in report
    assert "<td>throughput, last 12 weeks, pace used</td>" in report
    assert "Clear dates: " in result.output


def test_cli_notes_no_share_for_a_forecast_it_does_not_make():
    issues = [
        _raw_issue(
            f"X-{i}",
            "Done",
            ("2026-09-01", "Open", "In Progress"),
            (f"2026-09-{2 + i:02d}", "In Progress", "Done"),
            resolution="Fixed",
        )
        for i in range(3)
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
    assert "not measured" not in result.output


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
