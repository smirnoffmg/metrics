"""Tests for the CLI entrypoint."""

from __future__ import annotations

from click.testing import CliRunner

from metrics.__main__ import cli


def test_cli_missing_config():
    runner = CliRunner()
    result = runner.invoke(cli, [])
    assert result.exit_code != 0
    assert "Error" in result.output or "error" in result.output
