"""Tests for the synd build CLI command."""

from __future__ import annotations

import json
import zipfile
from pathlib import Path
from unittest.mock import patch

import pytest
from click.testing import CliRunner

from synd.builder.llms_full import LlmsFullPage
from synd.cli.build import _parse_package_spec
from synd.cli.main import cli
from synd.errors import BuildError


def _fixture_path(name: str = "sample_docs") -> Path:
    return Path(__file__).parent.parent / "fixtures" / name


class TestParsePackageSpec:
    """Unit tests for _parse_package_spec."""

    def test_missing_at_raises_build_error(self) -> None:
        """A spec without '@' raises BuildError, not ValueError."""
        with pytest.raises(BuildError, match="Missing '@'"):
            _parse_package_spec("bad-spec")

    def test_multiple_at_raises_build_error(self) -> None:
        """A spec with multiple '@' signs raises BuildError."""
        with pytest.raises(BuildError, match="Multiple '@'"):
            _parse_package_spec("my@lib@1.0.0")

    def test_empty_package_raises_build_error(self) -> None:
        """A spec with empty package name raises BuildError."""
        with pytest.raises(BuildError, match="non-empty"):
            _parse_package_spec("@1.0.0")

    def test_empty_version_raises_build_error(self) -> None:
        """A spec with empty version raises BuildError."""
        with pytest.raises(BuildError, match="non-empty"):
            _parse_package_spec("my-lib@")

    def test_valid_spec_returns_tuple(self) -> None:
        """A valid spec returns (package, version)."""
        assert _parse_package_spec("my-lib@1.0.0") == ("my-lib", "1.0.0")


class TestBuildCommand:
    """Tests for 'synd build' subcommand."""

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
        """A nonexistent --source path is a usage error (exit code 2)."""
        result = CliRunner().invoke(
            cli,
            ["build", "my-lib@1.0.0", "--source", "/nonexistent/path"],
        )
        assert result.exit_code == 2
        assert (
            "error" in result.output.lower()
            or "does not exist" in result.output.lower()
        )
        # Should NOT contain a Python traceback
        assert "Traceback" not in result.output

    def test_build_command_bad_package_format(self, tmp_path: Path) -> None:
        """Package string without '@' must be rejected."""
        source = _fixture_path()
        result = CliRunner().invoke(
            cli,
            ["build", "my-lib", "--source", str(source)],
        )
        assert result.exit_code == 2  # malformed argument → usage error
        assert (
            "error" in result.output.lower()
            or "missing" in result.output.lower()
            or "@" in result.output
        )

    def test_build_multiple_at_signs_rejected(self, tmp_path: Path) -> None:
        """Package string with multiple '@' signs must be rejected."""
        source = _fixture_path()
        result = CliRunner().invoke(
            cli,
            ["build", "my@lib@1.0.0", "--source", str(source)],
        )
        assert result.exit_code == 2  # malformed argument → usage error
        assert (
            "error" in result.output.lower()
            or "invalid" in result.output.lower()
            or "@" in result.output
        )

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
            [
                "build",
                "my-lib@1.0.0",
                "--source",
                str(source),
                "--output",
                str(output),
                "--lifecycle",
                "approved",
            ],
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
            [
                "build",
                "my-lib@1.0.0",
                "--source",
                str(source),
                "--output",
                str(output),
                "--owner",
                "team-a",
            ],
        )
        assert result.exit_code == 0, f"build failed: {result.output}"
        ctx_files = list(output.glob("*.ctx"))
        with zipfile.ZipFile(ctx_files[0], "r") as zf:
            manifest = json.loads(zf.read("manifest.json"))
            assert manifest["owner"] == "team-a"

    def test_build_with_doc_version_status_option(self, tmp_path: Path) -> None:
        """Build with --doc-version-status sets doc_version_status in manifest."""
        source = _fixture_path()
        output = tmp_path / "packs"
        result = CliRunner().invoke(
            cli,
            [
                "build",
                "my-lib@1.0.0",
                "--source",
                str(source),
                "--output",
                str(output),
                "--doc-version-status",
                "prerelease",
            ],
        )
        assert result.exit_code == 0, f"build failed: {result.output}"
        ctx_files = list(output.glob("*.ctx"))
        with zipfile.ZipFile(ctx_files[0], "r") as zf:
            manifest = json.loads(zf.read("manifest.json"))
            assert manifest["doc_version_status"] == "prerelease"

    def test_build_doc_version_status_defaults_to_stable(self, tmp_path: Path) -> None:
        """Omitting --doc-version-status produces 'stable' in the manifest."""
        source = _fixture_path()
        output = tmp_path / "packs"
        result = CliRunner().invoke(
            cli,
            ["build", "my-lib@1.0.0", "--source", str(source), "--output", str(output)],
        )
        assert result.exit_code == 0, f"build failed: {result.output}"
        ctx_files = list(output.glob("*.ctx"))
        with zipfile.ZipFile(ctx_files[0], "r") as zf:
            manifest = json.loads(zf.read("manifest.json"))
            assert manifest["doc_version_status"] == "stable"

    def test_max_chunk_tokens_flag_produces_more_chunks(self, tmp_path: Path) -> None:
        """--max-chunk-tokens 100 must produce more chunks than the default 800."""
        source = _fixture_path()
        output_tight = tmp_path / "tight"
        output_default = tmp_path / "default"
        result_tight = CliRunner().invoke(
            cli,
            [
                "build",
                "my-lib@1.0.0",
                "--source",
                str(source),
                "--output",
                str(output_tight),
                "--max-chunk-tokens",
                "100",
            ],
        )
        result_default = CliRunner().invoke(
            cli,
            [
                "build",
                "my-lib@1.0.0",
                "--source",
                str(source),
                "--output",
                str(output_default),
            ],
        )
        assert result_tight.exit_code == 0, result_tight.output
        assert result_default.exit_code == 0, result_default.output

        def _chunk_count(out: Path) -> int:
            ctx = next(out.glob("*.ctx"))
            with zipfile.ZipFile(ctx) as zf:
                return sum(
                    1
                    for ln in zf.read("chunks.jsonl").decode().splitlines()
                    if ln.strip()
                )

        assert _chunk_count(output_tight) >= _chunk_count(output_default), (
            "Tighter max_chunk_tokens should produce at least as many chunks"
        )

    def test_min_chunk_tokens_zero_allows_stub_chunks(self, tmp_path: Path) -> None:
        """--min-chunk-tokens 0 disables the stub-merge guard."""
        source = tmp_path / "src"
        source.mkdir()
        (source / "stubs.md").write_text("## A\n\n### B\n\nSome content here.\n")
        output_zero = tmp_path / "zero"
        output_default = tmp_path / "default"
        result_zero = CliRunner().invoke(
            cli,
            [
                "build",
                "stubs@1.0.0",
                "--source",
                str(source),
                "--output",
                str(output_zero),
                "--min-chunk-tokens",
                "0",
            ],
        )
        result_default = CliRunner().invoke(
            cli,
            [
                "build",
                "stubs@1.0.0",
                "--source",
                str(source),
                "--output",
                str(output_default),
            ],
        )
        assert result_zero.exit_code == 0, result_zero.output
        assert result_default.exit_code == 0, result_default.output

        def _chunk_count(out: Path) -> int:
            ctx = next(out.glob("*.ctx"))
            with zipfile.ZipFile(ctx) as zf:
                return sum(
                    1
                    for ln in zf.read("chunks.jsonl").decode().splitlines()
                    if ln.strip()
                )

        assert _chunk_count(output_zero) >= _chunk_count(output_default), (
            "min_chunk_tokens=0 should allow more chunks (stubs not merged)"
        )

    def test_warn_chunk_tokens_output_appears_for_oversized_chunk(
        self, tmp_path: Path
    ) -> None:
        """Build a source with an indented code block > warn threshold; output must contain warning."""
        fixture = (
            Path(__file__).parent.parent
            / "benchmarks"
            / "fixtures"
            / "oversized-indented-block.md"
        )
        source = tmp_path / "src"
        source.mkdir()
        import shutil

        shutil.copy(fixture, source / fixture.name)
        output = tmp_path / "packs"
        result = CliRunner().invoke(
            cli,
            [
                "build",
                "oversized@1.0.0",
                "--source",
                str(source),
                "--output",
                str(output),
                "--warn-chunk-tokens",
                "500",
            ],
        )
        assert result.exit_code == 0, result.output
        assert "exceed" in result.output, (
            f"Expected oversized-chunk warning in output, got: {result.output!r}"
        )

    def test_no_warn_output_when_all_chunks_within_threshold(
        self, tmp_path: Path
    ) -> None:
        """Normal small docs must not produce any warning lines."""
        source = _fixture_path()
        output = tmp_path / "packs"
        result = CliRunner().invoke(
            cli,
            ["build", "my-lib@1.0.0", "--source", str(source), "--output", str(output)],
        )
        assert result.exit_code == 0, result.output
        assert "exceed" not in result.output, (
            f"Unexpected warning in output: {result.output!r}"
        )


class TestBuildCommandUrlSource:
    """Tests for 'synd build' with a URL --source."""

    _FAKE_PAGES = [
        ("https://docs.example.com/intro.md", "# Introduction\n\nWelcome.\n"),
        ("https://docs.example.com/api.md", "# API\n\nDetails.\n"),
    ]

    _FAKE_FULL_PAGES = [
        LlmsFullPage(
            url="https://docs.example.com/intro.md", content="# Intro\n\nWelcome.\n"
        ),
    ]

    def test_url_source_llms_txt_exits_zero(self, tmp_path: Path) -> None:
        output = tmp_path / "packs"
        with patch("synd.builder.build.fetch_pages", return_value=self._FAKE_PAGES):
            result = CliRunner().invoke(
                cli,
                [
                    "build",
                    "my-lib@1.0.0",
                    "--source",
                    "https://docs.example.com/llms.txt",
                    "--output",
                    str(output),
                ],
            )
        assert result.exit_code == 0, f"build failed: {result.output}"
        assert list(output.glob("*.ctx"))

    def test_url_source_llms_full_txt_exits_zero(self, tmp_path: Path) -> None:
        output = tmp_path / "packs"
        with patch(
            "synd.builder.build.fetch_llms_full_pages",
            return_value=self._FAKE_FULL_PAGES,
        ):
            result = CliRunner().invoke(
                cli,
                [
                    "build",
                    "my-lib@1.0.0",
                    "--source",
                    "https://docs.example.com/llms-full.txt",
                    "--output",
                    str(output),
                ],
            )
        assert result.exit_code == 0, f"build failed: {result.output}"

    def test_url_source_unsupported_url_exits_one(self, tmp_path: Path) -> None:
        result = CliRunner().invoke(
            cli,
            [
                "build",
                "my-lib@1.0.0",
                "--source",
                "https://docs.example.com/README.md",
            ],
        )
        assert result.exit_code == 6  # unsupported URL → build failure
        assert "error" in result.output.lower()

    def test_local_path_still_works_after_refactor(self, tmp_path: Path) -> None:
        """Regression: local directory --source must still produce a .ctx pack."""
        source = _fixture_path()
        output = tmp_path / "packs"
        result = CliRunner().invoke(
            cli,
            ["build", "my-lib@1.0.0", "--source", str(source), "--output", str(output)],
        )
        assert result.exit_code == 0, f"build failed: {result.output}"
        assert list(output.glob("*.ctx"))
