"""Tests for the tank inspect CLI command."""

from __future__ import annotations

from pathlib import Path

import pytest
from click.testing import CliRunner

from synd.cli.main import cli


def _fixture_path(name: str = "sample_docs") -> Path:
    return Path(__file__).parent.parent / "fixtures" / name


class TestInspectCommand:
    """Tests for 'tank inspect' subcommand."""

    def test_inspect_ctx_file(self, tmp_path: Path) -> None:
        """Inspecting a valid .ctx file prints manifest information."""
        source = _fixture_path()
        build_out = tmp_path / "build"
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
        assert result.exit_code == 0, f"build setup failed: {result.output}"
        ctx_path = build_out / "test-pkg@1.0.0.ctx"

        result = CliRunner().invoke(
            cli,
            ["inspect", str(ctx_path)],
        )
        assert result.exit_code == 0, f"inspect failed: {result.output}"
        assert "test-pkg" in result.output
        assert "1.0.0" in result.output

    def test_inspect_index_db(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Inspecting an index.db lists imported packs."""
        source = _fixture_path()
        build_out = tmp_path / "build"
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
        assert result.exit_code == 0, f"build setup failed: {result.output}"
        ctx_path = build_out / "test-pkg@1.0.0.ctx"

        monkeypatch.chdir(tmp_path)
        result = CliRunner().invoke(cli, ["add", str(ctx_path)])
        assert result.exit_code == 0, f"add failed: {result.output}"

        db_path = tmp_path / ".synd" / "index.db"
        result = CliRunner().invoke(
            cli,
            ["inspect", str(db_path)],
        )
        assert result.exit_code == 0, f"inspect failed: {result.output}"
        assert "test-pkg" in result.output
