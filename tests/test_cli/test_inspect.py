"""Tests for the tank inspect CLI command."""

from __future__ import annotations

from pathlib import Path

import pytest
from click.testing import CliRunner

from tank.cli.main import cli
from tank.builder.build import build_pack


def _fixture_path(name: str = "sample_docs") -> Path:
    return Path(__file__).parent.parent / "fixtures" / name


class TestInspectCommand:
    """Tests for 'tank inspect' subcommand."""

    def test_inspect_ctx_file(self, tmp_path: Path) -> None:
        """Inspecting a valid .ctx file prints manifest information."""
        source = _fixture_path()
        build_out = tmp_path / "build"
        build_pack(
            package="test-pkg",
            version="1.0.0",
            source=source,
            output=build_out,
        )
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
        build_pack(
            package="test-pkg",
            version="1.0.0",
            source=source,
            output=build_out,
        )
        ctx_path = build_out / "test-pkg@1.0.0.ctx"

        monkeypatch.chdir(tmp_path)
        result = CliRunner().invoke(cli, ["pull", str(ctx_path)])
        assert result.exit_code == 0, f"pull failed: {result.output}"

        db_path = tmp_path / ".tank" / "index.db"
        result = CliRunner().invoke(
            cli,
            ["inspect", str(db_path)],
        )
        assert result.exit_code == 0, f"inspect failed: {result.output}"
        assert "test-pkg" in result.output
