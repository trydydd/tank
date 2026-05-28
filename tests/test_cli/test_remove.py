"""Tests for the tank remove CLI command."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest
from click.testing import CliRunner

from synd.cli.main import cli

_FIXTURE_DOCS = Path(__file__).parent.parent / "fixtures" / "sample_docs"


def _make_ctx(tmp_path: Path, package: str = "my-lib", version: str = "1.0.0") -> Path:
    out = tmp_path / "build"
    result = CliRunner().invoke(
        cli,
        [
            "build",
            f"{package}@{version}",
            "--source",
            str(_FIXTURE_DOCS),
            "--output",
            str(out),
        ],
    )
    assert result.exit_code == 0, f"build setup failed: {result.output}"
    return out / f"{package}@{version}.ctx"


def _add_pack(tmp_path: Path, ctx_path: Path) -> None:
    """Helper: add a pack via the CLI (sets up .synd/index.db and synd.lock)."""
    result = CliRunner().invoke(cli, ["add", str(ctx_path)])
    assert result.exit_code == 0, f"add setup failed: {result.output}"


class TestRemoveCommand:
    """Tests for 'tank remove'."""

    def test_remove_pack_success(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Removing an imported pack succeeds and updates DB + lockfile."""
        monkeypatch.chdir(tmp_path)
        ctx_path = _make_ctx(tmp_path)
        _add_pack(tmp_path, ctx_path)

        result = CliRunner().invoke(cli, ["remove", "my-lib@1.0.0"])
        assert result.exit_code == 0, f"remove failed: {result.output}"
        assert "removed" in result.output.lower()

        db_path = tmp_path / ".synd" / "index.db"
        conn = sqlite3.connect(str(db_path))
        count = conn.execute("SELECT COUNT(*) FROM packages").fetchone()[0]
        conn.close()
        assert count == 0

    def test_remove_updates_lockfile(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """After remove, synd.lock no longer contains the removed pack."""
        monkeypatch.chdir(tmp_path)
        ctx_path = _make_ctx(tmp_path)
        _add_pack(tmp_path, ctx_path)

        lock_before = (tmp_path / "synd.lock").read_text()
        assert "my-lib" in lock_before

        CliRunner().invoke(cli, ["remove", "my-lib@1.0.0"])

        lock_after = (tmp_path / "synd.lock").read_text()
        assert "my-lib" not in lock_after

    def test_remove_nonexistent_pack_exits_1(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Removing a pack that is not in the index exits 1 with an error."""
        monkeypatch.chdir(tmp_path)
        # Set up an empty index
        ctx_path = _make_ctx(tmp_path)
        _add_pack(tmp_path, ctx_path)
        CliRunner().invoke(cli, ["remove", "my-lib@1.0.0"])  # remove it first

        result = CliRunner().invoke(cli, ["remove", "my-lib@1.0.0"])
        assert result.exit_code == 1
        assert (
            "not in the index" in result.output.lower()
            or "not found" in result.output.lower()
        )

    def test_remove_no_index_exits_1(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Remove exits 1 with a clear error when no index.db exists yet."""
        monkeypatch.chdir(tmp_path)
        result = CliRunner().invoke(cli, ["remove", "some-lib@1.0.0"])
        assert result.exit_code == 1
        assert (
            "not in the index" in result.output.lower()
            or "error" in result.output.lower()
        )

    def test_remove_malformed_spec_exits_1(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A PKG_SPEC without '@' exits 1 with a helpful error."""
        monkeypatch.chdir(tmp_path)
        result = CliRunner().invoke(cli, ["remove", "no-version-here"])
        assert result.exit_code == 1
        assert (
            "package@version" in result.output.lower()
            or "invalid" in result.output.lower()
        )

    def test_remove_only_one_pack_from_two(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Removing one pack from two leaves the other intact in DB and lockfile."""
        monkeypatch.chdir(tmp_path)
        ctx_a = _make_ctx(tmp_path, "lib-a", "1.0.0")
        ctx_b = _make_ctx(tmp_path, "lib-b", "2.0.0")
        _add_pack(tmp_path, ctx_a)
        _add_pack(tmp_path, ctx_b)

        result = CliRunner().invoke(cli, ["remove", "lib-a@1.0.0"])
        assert result.exit_code == 0

        db_path = tmp_path / ".synd" / "index.db"
        conn = sqlite3.connect(str(db_path))
        names = [r[0] for r in conn.execute("SELECT name FROM packages").fetchall()]
        conn.close()
        assert names == ["lib-b"]

        lock = (tmp_path / "synd.lock").read_text()
        assert "lib-a" not in lock
        assert "lib-b" in lock

    def test_remove_then_query_returns_nothing(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """After removing the only pack, querying returns no results."""
        monkeypatch.chdir(tmp_path)
        ctx_path = _make_ctx(tmp_path)
        _add_pack(tmp_path, ctx_path)

        CliRunner().invoke(cli, ["remove", "my-lib@1.0.0"])

        result = CliRunner().invoke(cli, ["query", "authentication"])
        assert result.exit_code == 0
        assert "my-lib" not in result.output
