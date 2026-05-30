"""Tests for the `synd serve` CLI command."""

from __future__ import annotations

from click.testing import CliRunner

from synd.cli.main import cli


def test_serve_registered_in_help() -> None:
    """'synd serve' appears in the top-level help output."""
    runner = CliRunner()
    result = runner.invoke(cli, ["--help"])
    assert result.exit_code == 0
    assert "serve" in result.output


def test_serve_help_text() -> None:
    """'synd serve --help' exits cleanly and describes the command."""
    runner = CliRunner()
    result = runner.invoke(cli, ["serve", "--help"])
    assert result.exit_code == 0
    assert "stdio" in result.output.lower()
