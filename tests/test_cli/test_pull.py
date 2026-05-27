"""Tests for the tank pull CLI command."""

from __future__ import annotations

import json
import sqlite3
import zipfile
from pathlib import Path

import pytest
from click.testing import CliRunner

from synd.builder.build import build_pack
from synd.builder.manifest import compute_pack_digest
from synd.cli.main import cli

_ZIP_EPOCH = (2021, 8, 8, 0, 0, 0)


def _rebuild_ctx_with_status(source_ctx: Path, dest: Path, status: str) -> None:
    """Copy a .ctx replacing doc_version_status, then recompute pack_digest."""
    with zipfile.ZipFile(source_ctx, "r") as zf:
        manifest = json.loads(zf.read("manifest.json"))
        chunks = zf.read("chunks.jsonl")
        pages = zf.read("pages.json")

    manifest["doc_version_status"] = status
    manifest["pack_digest"] = ""

    def _write(m: dict[str, object]) -> None:
        with zipfile.ZipFile(dest, "w", zipfile.ZIP_DEFLATED) as out:
            for name, content in [
                ("manifest.json", json.dumps(m, indent=2, sort_keys=True)),
                ("chunks.jsonl", chunks.decode()),
                ("pages.json", pages.decode()),
            ]:
                info = zipfile.ZipInfo(name, date_time=_ZIP_EPOCH)
                info.compress_type = zipfile.ZIP_DEFLATED
                out.writestr(info, content)
            sig_info = zipfile.ZipInfo("signatures/", date_time=_ZIP_EPOCH)
            sig_info.compress_type = zipfile.ZIP_STORED
            out.writestr(sig_info, "")

    _write(manifest)
    manifest["pack_digest"] = compute_pack_digest(dest)
    _write(manifest)


def _fixture_path(name: str = "sample_docs") -> Path:
    return Path(__file__).parent.parent / "fixtures" / name


def _make_valid_ctx(
    tmp_path: Path, package: str, version: str, source: Path | None = None
) -> Path:
    """Build and return a valid .ctx file."""
    src = source or _fixture_path()
    build_out = tmp_path / "build"
    build_out.mkdir(parents=True, exist_ok=True)
    ctx_path = build_pack(
        package=package,
        version=version,
        source=src,
        output=build_out,
    )
    return ctx_path


def _make_broken_ctx(tmp_path: Path) -> Path:
    """Create a .ctx with invalid JSON manifest."""
    ctx_path = tmp_path / "broken.ctx"
    with zipfile.ZipFile(ctx_path, "w") as zf:
        zf.writestr("manifest.json", "not json at all")
        zf.writestr("chunks.jsonl", "")
        zf.writestr("pages.json", "[]")
        zf.writestr("signatures/", "")
    return ctx_path


def _make_tampered_ctx(tmp_path: Path, valid_ctx: Path) -> Path:
    """Create a .ctx that is a copy of valid_ctx but with a modified chunk, invalidating the digest."""
    ctx_path = tmp_path / "tampered.ctx"
    with zipfile.ZipFile(valid_ctx, "r") as zf_in:
        with zipfile.ZipFile(ctx_path, "w", zipfile.ZIP_DEFLATED) as zf_out:
            for item in zf_in.infolist():
                data = zf_in.read(item.filename)
                if item.filename == "chunks.jsonl":
                    # Corrupt a line to invalidate the hash
                    text = data.decode("utf-8")
                    lines = text.strip().split("\n")
                    if lines:
                        lines[0] = lines[0] + "CORRUPTED"
                        data = "\n".join(lines).encode("utf-8")
                zf_out.writestr(item, data)
    return ctx_path


class TestPullCommand:
    """Tests for 'tank pull' subcommand."""

    def test_pull_command_success(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Pulling a valid .ctx imports the pack successfully."""
        monkeypatch.chdir(tmp_path)
        ctx_path = _make_valid_ctx(tmp_path, "my-lib", "1.0.0")
        result = CliRunner().invoke(
            cli,
            ["pull", str(ctx_path)],
        )
        assert result.exit_code == 0, f"pull failed: {result.output}"
        assert "success" in result.output.lower() or "imported" in result.output.lower()

        db_path = tmp_path / ".synd" / "index.db"
        assert db_path.exists()
        conn = sqlite3.connect(str(db_path))
        count = conn.execute("SELECT COUNT(*) FROM packages").fetchone()[0]
        conn.close()
        assert count == 1

    def test_pull_command_verify_fails(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Pulling a malformed .ctx must exit 1."""
        monkeypatch.chdir(tmp_path)
        broken = _make_broken_ctx(tmp_path)
        result = CliRunner().invoke(
            cli,
            ["pull", str(broken)],
        )
        assert result.exit_code == 1, f"pull should fail: {result.output}"

    def test_pull_command_duplicate_rejected(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Pulling the same .ctx twice without --force must reject the second."""
        monkeypatch.chdir(tmp_path)
        ctx_path = _make_valid_ctx(tmp_path, "my-lib", "1.0.0")

        result1 = CliRunner().invoke(cli, ["pull", str(ctx_path)])
        assert result1.exit_code == 0, f"first pull failed: {result1.output}"

        result2 = CliRunner().invoke(cli, ["pull", str(ctx_path)])
        assert result2.exit_code == 1, (
            f"second pull should be rejected: {result2.output}"
        )
        assert (
            "already" in result2.output.lower() or "duplicate" in result2.output.lower()
        )

    def test_pull_command_force_reimport(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Pulling with --force re-imports an existing pack."""
        monkeypatch.chdir(tmp_path)
        ctx_path = _make_valid_ctx(tmp_path, "my-lib", "1.0.0")

        result1 = CliRunner().invoke(cli, ["pull", str(ctx_path)])
        assert result1.exit_code == 0, f"first pull failed: {result1.output}"

        result2 = CliRunner().invoke(cli, ["pull", str(ctx_path)])
        assert result2.exit_code == 1

        result3 = CliRunner().invoke(cli, ["pull", str(ctx_path), "--force"])
        assert result3.exit_code == 0, f"force pull failed: {result3.output}"

    def test_pull_does_not_import_on_verify_failure(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """NEG: failed verify must leave packages table empty — query DB after pull with malformed .ctx."""
        monkeypatch.chdir(tmp_path)
        broken = _make_broken_ctx(tmp_path)
        result = CliRunner().invoke(cli, ["pull", str(broken)])
        assert result.exit_code == 1

        db_path = tmp_path / ".synd" / "index.db"
        if db_path.exists():
            conn = sqlite3.connect(str(db_path))
            count = conn.execute("SELECT COUNT(*) FROM packages").fetchone()[0]
            conn.close()
            assert count == 0, "packages table should be empty after failed pull"

    def test_pull_preserves_doc_version_status_from_manifest(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """doc_version_status in the DB must come from the manifest, not be hardcoded."""
        monkeypatch.chdir(tmp_path)
        ctx_path = _make_valid_ctx(tmp_path, "my-lib", "1.0.0")
        result = CliRunner().invoke(cli, ["pull", str(ctx_path)])
        assert result.exit_code == 0, f"pull failed: {result.output}"

        db_path = tmp_path / ".synd" / "index.db"
        conn = sqlite3.connect(str(db_path))
        status = conn.execute("SELECT doc_version_status FROM packages").fetchone()[0]
        conn.close()
        assert status == "stable"  # manifest hardcodes "stable"; "imported" is wrong

    def test_pull_unknown_doc_version_status_warns(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A manifest with doc_version_status='unknown' stores 'unknown' and warns."""
        monkeypatch.chdir(tmp_path)
        ctx_path = _make_valid_ctx(tmp_path, "my-lib", "1.0.0")
        unknown_ctx = tmp_path / "unknown.ctx"
        _rebuild_ctx_with_status(ctx_path, unknown_ctx, "unknown")

        result = CliRunner().invoke(cli, ["pull", str(unknown_ctx)])
        assert result.exit_code == 0, f"pull failed: {result.output}"
        assert "warning" in result.output.lower()
        assert "unknown" in result.output.lower()

        db_path = tmp_path / ".synd" / "index.db"
        conn = sqlite3.connect(str(db_path))
        status = conn.execute("SELECT doc_version_status FROM packages").fetchone()[0]
        conn.close()
        assert status == "unknown"

    def test_pull_force_does_not_skip_verify(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """NEG: --force allows reimport but does NOT skip 8-step verification — tampered .ctx with --force must still be rejected."""
        monkeypatch.chdir(tmp_path)
        ctx_path = _make_valid_ctx(tmp_path, "my-lib", "1.0.0")
        result = CliRunner().invoke(cli, ["pull", str(ctx_path)])
        assert result.exit_code == 0

        tampered = _make_tampered_ctx(tmp_path, ctx_path)
        result2 = CliRunner().invoke(cli, ["pull", str(tampered), "--force"])
        assert result2.exit_code == 1, (
            f"tampered pack with --force should fail: {result2.output}"
        )
