"""Tests for the tank build CLI command."""

from __future__ import annotations

import json
import zipfile
from pathlib import Path

from click.testing import CliRunner

from tank.cli.main import cli


def _fixture_path(name: str = "sample_docs") -> Path:
    return Path(__file__).parent.parent / "fixtures" / name


class TestBuildCommand:
    """Tests for 'tank build' subcommand."""

    def test_build_command_success(self, tmp_path: Path) -> None:
        """Standard build: exit_code=0 and .ctx file is produced."""
        source = _fixture_path()
        output = tmp_path / "packs"
        result = CliRunner().invoke(
            cli,
            ["build", "my-lib@1.0.0", "--source", str(source), "--output", str(output)],
        )
        assert result.exit_code == 0, f"build failed: {result.output}"
        # The .ctx file should exist in output/
        ctx_files = list(output.glob("*.ctx"))
        assert len(ctx_files) == 1
        assert ctx_files[0].name == "my-lib@1.0.0.ctx"
        # Verify .ctx is a valid zip with expected contents
        with zipfile.ZipFile(ctx_files[0], "r") as zf:
            names = zf.namelist()
            assert "manifest.json" in names
            assert "chunks.jsonl" in names
            manifest = json.loads(zf.read("manifest.json"))
            assert manifest["package"] == "my-lib"
            assert manifest["version"] == "1.0.0"
            assert manifest["pack_digest"].startswith("sha256:")

    def test_build_command_missing_source(self, tmp_path: Path) -> None:
        """Building with a nonexistent --source must exit 1 with user-friendly error."""
        result = CliRunner().invoke(
            cli,
            ["build", "my-lib@1.0.0", "--source", "/nonexistent/path"],
        )
        assert result.exit_code == 1
        assert "error" in result.output.lower() or "does not exist" in result.output.lower()
        # Should NOT contain a Python traceback
        assert "Traceback" not in result.output

    def test_build_command_bad_package_format(self, tmp_path: Path) -> None:
        """Package string without '@' must be rejected."""
        source = _fixture_path()
        result = CliRunner().invoke(
            cli,
            ["build", "my-lib", "--source", str(source)],
        )
        assert result.exit_code == 1
        assert "error" in result.output.lower() or "missing" in result.output.lower() or "@" in result.output

    def test_build_multiple_at_signs_rejected(self, tmp_path: Path) -> None:
        """Package string with multiple '@' signs must be rejected."""
        source = _fixture_path()
        result = CliRunner().invoke(
            cli,
            ["build", "my@lib@1.0.0", "--source", str(source)],
        )
        assert result.exit_code == 1
        assert "error" in result.output.lower() or "invalid" in result.output.lower() or "@" in result.output

    def test_build_creates_output_dir(self, tmp_path: Path) -> None:
        """Output directory is created if it doesn't exist."""
        source = _fixture_path()
        output = tmp_path / "new" / "output"
        assert not output.exists()
        result = CliRunner().invoke(
            cli,
            ["build", "my-lib@1.0.0", "--source", str(source), "--output", str(output)],
        )
        assert result.exit_code == 0, f"build failed: {result.output}"
        assert output.exists()

    def test_build_with_lifecycle_option(self, tmp_path: Path) -> None:
        """Build with --lifecycle sets lifecycle_state in manifest."""
        source = _fixture_path()
        output = tmp_path / "packs"
        result = CliRunner().invoke(
            cli,
            ["build", "my-lib@1.0.0", "--source", str(source), "--output", str(output), "--lifecycle", "approved"],
        )
        assert result.exit_code == 0, f"build failed: {result.output}"
        ctx_files = list(output.glob("*.ctx"))
        with zipfile.ZipFile(ctx_files[0], "r") as zf:
            manifest = json.loads(zf.read("manifest.json"))
            assert manifest["lifecycle_state"] == "approved"

    def test_build_with_owner_option(self, tmp_path: Path) -> None:
        """Build with --owner sets owner in manifest."""
        source = _fixture_path()
        output = tmp_path / "packs"
        result = CliRunner().invoke(
            cli,
            ["build", "my-lib@1.0.0", "--source", str(source), "--output", str(output), "--owner", "team-a"],
        )
        assert result.exit_code == 0, f"build failed: {result.output}"
        ctx_files = list(output.glob("*.ctx"))
        with zipfile.ZipFile(ctx_files[0], "r") as zf:
            manifest = json.loads(zf.read("manifest.json"))
            assert manifest["owner"] == "team-a"
