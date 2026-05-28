"""Tests for the tank query CLI command."""

from __future__ import annotations

from pathlib import Path

import pytest
from click.testing import CliRunner

from synd.cli.main import cli


def _fixture_path(name: str = "sample_docs") -> Path:
    return Path(__file__).parent.parent / "fixtures" / name


class TestQueryCommand:
    """Tests for 'tank query' subcommand."""

    def test_query_command_summary(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Query with detail=summary returns results with headings and summaries."""
        source = _fixture_path()
        build_out = tmp_path / "packs"
        monkeypatch.chdir(tmp_path)

        result = CliRunner().invoke(
            cli,
            [
                "build",
                "test-pkg@1.0.0",
                "--source",
                str(source),
                "--output",
                str(build_out),
            ],
        )
        assert result.exit_code == 0, f"build failed: {result.output}"

        ctx_path = build_out / "test-pkg@1.0.0.ctx"
        result = CliRunner().invoke(cli, ["add", str(ctx_path)])
        assert result.exit_code == 0, f"add failed: {result.output}"

        result = CliRunner().invoke(cli, ["query", "install", "--detail", "summary"])
        assert result.exit_code == 0, f"query failed: {result.output}"
        assert "getting-started" in result.output, (
            f"Expected heading_path in output: {result.output}"
        )

    def test_query_command_full(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Query with detail=full includes content in results."""
        source = _fixture_path()
        build_out = tmp_path / "packs"
        monkeypatch.chdir(tmp_path)

        result = CliRunner().invoke(
            cli,
            [
                "build",
                "test-pkg@1.0.0",
                "--source",
                str(source),
                "--output",
                str(build_out),
            ],
        )
        assert result.exit_code == 0, f"build failed: {result.output}"

        ctx_path = build_out / "test-pkg@1.0.0.ctx"
        result = CliRunner().invoke(cli, ["add", str(ctx_path)])
        assert result.exit_code == 0, f"add failed: {result.output}"

        result = CliRunner().invoke(cli, ["query", "install", "--detail", "full"])
        assert result.exit_code == 0, f"query failed: {result.output}"

    def test_query_does_not_crash_on_empty_db(self) -> None:
        """NEG: query with no imported packs must exit 0 with empty results, not crash or exit 1."""
        result = CliRunner().invoke(
            cli,
            ["query", "nonexistent"],
        )
        assert result.exit_code == 0, (
            f"query should exit 0 on empty db: {result.output}"
        )
        assert "Traceback" not in result.output
