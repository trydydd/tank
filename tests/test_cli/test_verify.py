"""Tests for the tank verify CLI command."""

from __future__ import annotations

import zipfile
from pathlib import Path

from click.testing import CliRunner

from synd.cli.main import cli


def _fixture_path(name: str = "sample_docs") -> Path:
    return Path(__file__).parent.parent / "fixtures" / name


class TestVerifyCommand:
    """Tests for 'tank verify' subcommand."""

    def test_verify_command_pass(self, tmp_path: Path) -> None:
        """A valid .ctx must pass verification."""
        source = _fixture_path()
        build_out = tmp_path / "build"
        result = CliRunner().invoke(
            cli,
            ["build", "my-lib@1.0.0", "--source", str(source), "--output", str(build_out)],
        )
        assert result.exit_code == 0, f"build setup failed: {result.output}"
        ctx_path = build_out / "my-lib@1.0.0.ctx"
        result = CliRunner().invoke(
            cli,
            ["verify", str(ctx_path)],
        )
        assert result.exit_code == 0, f"verify failed: {result.output}"
        assert (
            "passed" in result.output.lower()
            or "ok" in result.output.lower()
            or "valid" in result.output.lower()
        )

    def test_verify_command_fail(self, tmp_path: Path) -> None:
        """A malformed .ctx (corrupted manifest) must fail verification."""
        # Create a broken .ctx: valid zip but corrupted manifest
        ctx_path = tmp_path / "broken.ctx"
        with zipfile.ZipFile(ctx_path, "w") as zf:
            zf.writestr("manifest.json", "this is not json")
            zf.writestr("chunks.jsonl", "")
            zf.writestr("pages.json", "[]")
            zf.writestr("signatures/", "")

        result = CliRunner().invoke(
            cli,
            ["verify", str(ctx_path)],
        )
        assert result.exit_code == 1, f"verify should fail: {result.output}"
        assert "error" in result.output.lower() or "failed" in result.output.lower()

    def test_verify_missing_file(self) -> None:
        """Verifying a nonexistent file must exit 1."""
        result = CliRunner().invoke(
            cli,
            ["verify", "/nonexistent/file.ctx"],
        )
        assert result.exit_code == 1
        assert "error" in result.output.lower() or "not found" in result.output.lower()
