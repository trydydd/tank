"""Tests for the tank sync CLI command."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest
from click.testing import CliRunner

from synd.builder.build import build_pack
from synd.cli.main import cli

_FIXTURE_DOCS = Path(__file__).parent.parent / "fixtures" / "sample_docs"


def _make_ctx(tmp_path: Path, package: str, version: str) -> Path:
    out = tmp_path / "build"
    out.mkdir(parents=True, exist_ok=True)
    return build_pack(
        package=package, version=version, source=_FIXTURE_DOCS, output=out
    )


def _write_lockfile(tmp_path: Path, entries: dict[str, dict[str, str]]) -> None:
    """Write a minimal synd.lock with the given pack entries."""
    lines = [
        "[meta]",
        "schema_version = 2",
        'generated_at = "2026-01-01T00:00:00Z"',
        "",
    ]
    for spec, fields in entries.items():
        lines.append(f'[packs."{spec}"]')
        for k, v in fields.items():
            lines.append(f'{k} = "{v}"')
        lines.append("")
    (tmp_path / "synd.lock").write_text("\n".join(lines), encoding="utf-8")


class TestSyncCommand:
    """Tests for 'tank sync'."""

    def test_sync_imports_packs_from_lockfile(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """sync imports all packs listed in synd.lock that aren't already in the index."""
        monkeypatch.chdir(tmp_path)
        ctx1 = _make_ctx(tmp_path, "lib-a", "1.0.0")
        ctx2 = _make_ctx(tmp_path, "lib-b", "2.0.0")

        # Build digests from the actual .ctx files
        from synd.builder.manifest import compute_pack_digest

        digest1 = compute_pack_digest(ctx1)
        digest2 = compute_pack_digest(ctx2)

        _write_lockfile(
            tmp_path,
            {
                "lib-a@1.0.0": {
                    "pack_digest": digest1,
                    "lifecycle_state": "draft",
                    "indexed_at": "2026-01-01T00:00:00Z",
                    "source_url": str(ctx1),
                },
                "lib-b@2.0.0": {
                    "pack_digest": digest2,
                    "lifecycle_state": "draft",
                    "indexed_at": "2026-01-01T00:00:00Z",
                    "source_url": str(ctx2),
                },
            },
        )

        result = CliRunner().invoke(cli, ["sync"])
        assert result.exit_code == 0, f"sync failed: {result.output}"
        assert "2 imported" in result.output

        db_path = tmp_path / ".synd" / "index.db"
        conn = sqlite3.connect(str(db_path))
        count = conn.execute("SELECT COUNT(*) FROM packages").fetchone()[0]
        conn.close()
        assert count == 2

    def test_sync_skips_already_imported_packs(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """sync skips packs that are already present in the index."""
        monkeypatch.chdir(tmp_path)
        ctx1 = _make_ctx(tmp_path, "lib-a", "1.0.0")

        from synd.builder.manifest import compute_pack_digest

        digest1 = compute_pack_digest(ctx1)

        _write_lockfile(
            tmp_path,
            {
                "lib-a@1.0.0": {
                    "pack_digest": digest1,
                    "lifecycle_state": "draft",
                    "indexed_at": "2026-01-01T00:00:00Z",
                    "source_url": str(ctx1),
                },
            },
        )

        # First sync: imports
        result1 = CliRunner().invoke(cli, ["sync"])
        assert result1.exit_code == 0, f"first sync failed: {result1.output}"
        assert "1 imported" in result1.output

        # Second sync: skips
        result2 = CliRunner().invoke(cli, ["sync"])
        assert result2.exit_code == 0, f"second sync failed: {result2.output}"
        assert "1 skipped" in result2.output

        # DB still has exactly 1 pack
        db_path = tmp_path / ".synd" / "index.db"
        conn = sqlite3.connect(str(db_path))
        count = conn.execute("SELECT COUNT(*) FROM packages").fetchone()[0]
        conn.close()
        assert count == 1

    def test_sync_digest_mismatch_aborts_pack(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """sync refuses to import a pack whose digest doesn't match the lockfile."""
        monkeypatch.chdir(tmp_path)
        ctx1 = _make_ctx(tmp_path, "lib-a", "1.0.0")

        _write_lockfile(
            tmp_path,
            {
                "lib-a@1.0.0": {
                    "pack_digest": "sha256:deadbeefdeadbeefdeadbeefdeadbeef",
                    "lifecycle_state": "draft",
                    "indexed_at": "2026-01-01T00:00:00Z",
                    "source_url": str(ctx1),
                },
            },
        )

        result = CliRunner().invoke(cli, ["sync"])
        assert result.exit_code == 1, (
            f"sync should fail on digest mismatch: {result.output}"
        )
        assert (
            "digest mismatch" in result.output.lower()
            or "mismatch" in result.output.lower()
        )

        # Nothing was imported
        db_path = tmp_path / ".synd" / "index.db"
        if db_path.exists():
            conn = sqlite3.connect(str(db_path))
            count = conn.execute("SELECT COUNT(*) FROM packages").fetchone()[0]
            conn.close()
            assert count == 0

    def test_sync_https_source_url_raises_fetch_error(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """sync fails gracefully when source_url is an HTTPS URL (fetcher not yet available)."""
        monkeypatch.chdir(tmp_path)

        _write_lockfile(
            tmp_path,
            {
                "remote-lib@1.0.0": {
                    "pack_digest": "sha256:aaaa",
                    "lifecycle_state": "draft",
                    "indexed_at": "2026-01-01T00:00:00Z",
                    "source_url": "https://example.com/remote-lib@1.0.0.ctx",
                },
            },
        )

        result = CliRunner().invoke(cli, ["sync"])
        assert result.exit_code == 1
        # Should mention that URL fetching is not yet supported
        assert (
            "not yet supported" in result.output.lower()
            or "url" in result.output.lower()
        )

    def test_sync_frozen_flag_blocks_https(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """--frozen causes sync to fail immediately for HTTPS source_urls."""
        monkeypatch.chdir(tmp_path)

        _write_lockfile(
            tmp_path,
            {
                "remote-lib@1.0.0": {
                    "pack_digest": "sha256:aaaa",
                    "lifecycle_state": "draft",
                    "indexed_at": "2026-01-01T00:00:00Z",
                    "source_url": "https://example.com/remote-lib@1.0.0.ctx",
                },
            },
        )

        result = CliRunner().invoke(cli, ["sync", "--frozen"])
        assert result.exit_code == 1
        assert "frozen" in result.output.lower() or "network" in result.output.lower()

    def test_sync_missing_lockfile_exits_1(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """sync exits 1 with a helpful error when synd.lock does not exist."""
        monkeypatch.chdir(tmp_path)
        result = CliRunner().invoke(cli, ["sync"])
        assert result.exit_code == 1
        assert "synd.lock" in result.output or "tank add" in result.output

    def test_sync_empty_lockfile_is_noop(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """sync with an empty [packs] section exits 0 and prints nothing-to-do message."""
        monkeypatch.chdir(tmp_path)
        _write_lockfile(tmp_path, {})

        result = CliRunner().invoke(cli, ["sync"])
        assert result.exit_code == 0
        assert "nothing" in result.output.lower() or "no packs" in result.output.lower()
