"""Tests for the CLI entrypoint."""

from __future__ import annotations

from click.testing import CliRunner

from metrics.__main__ import cli, parse_bool, parse_status_list, validate_config
from metrics.consts import DONE_STATUSES, TESTING_STATUSES


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
