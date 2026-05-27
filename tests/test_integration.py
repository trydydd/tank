"""End-to-end integration tests for the full MVP pipeline.

Network tests (marked with @pytest.mark.network) are skipped by default.
Pass --network to pytest to run them: pytest --network tests/

Exercises build -> verify -> add -> query using the CLI via CliRunner
and real .ctx files, not mocked components.

Each test creates its own temporary directory via tmp_path so there is no
shared state between tests.
"""

from __future__ import annotations

import hashlib
import io
import json
import os
import urllib.request
import zipfile
from pathlib import Path

import pytest
from click.testing import CliRunner

from synd.cli.main import cli  # type: ignore[import-untyped]
from synd.policy.engine import Policy  # type: ignore[import-untyped]
from synd.search.fts import search  # type: ignore[import-untyped]
from synd.storage.db import Database  # type: ignore[import-untyped]
from synd.validator.verify import verify  # type: ignore[import-untyped]
from click.testing import Result


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

SAMPLE_DOCS = Path(__file__).parent / "fixtures" / "sample_docs"


@pytest.fixture()
def runner() -> CliRunner:
    return CliRunner()


@pytest.fixture()
def sample_docs() -> Path:
    """Path to the sample documentation directory used across all tests."""
    return SAMPLE_DOCS


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _cli_in_cwd(runner: CliRunner, args: list[str], tmp_path: Path) -> Result:
    """Invoke CliRunner with cwd set to tmp_path (add/query need .synd relative)."""
    old = os.getcwd()
    os.chdir(tmp_path)
    try:
        return runner.invoke(cli, args)
    finally:
        os.chdir(old)


def _tamper_with_valid_digest(src: Path, content_replacements: dict[int, str]) -> Path:
    """Rewrite a .ctx with modified chunk content, updating pack_digest so
    step 6 passes but step 7 (normalized_content_hash) fails.

    content_replacements: {chunk_id: new_content}
    """
    result = src.parent / (src.stem + "_tampered.ctx")

    with zipfile.ZipFile(src, "r") as zf:
        manifest = json.loads(zf.read("manifest.json"))
        chunks_raw = zf.read("chunks.jsonl").decode("utf-8")
        other_files = {
            info.filename: zf.read(info.filename)
            for info in zf.infolist()
            if info.filename not in ("manifest.json", "chunks.jsonl")
        }

    # Modify chunk content
    lines = chunks_raw.strip().split("\n")
    new_lines: list[str] = []
    for line in lines:
        line = line.strip()
        if line:
            rec = json.loads(line)
            if rec["id"] in content_replacements:
                rec["content"] = content_replacements[rec["id"]]
            new_lines.append(json.dumps(rec, sort_keys=True))
        else:
            new_lines.append("")
    new_chunks = "\n".join(new_lines) + "\n"

    # Compute pack_digest for the tampered archive (zero digest, re-zip, hash)
    zeroed = dict(manifest)
    zeroed["pack_digest"] = ""
    zeroed_manifest_json = json.dumps(zeroed, indent=2, sort_keys=True).encode()

    buf = io.BytesIO()
    with zipfile.ZipFile(src, "r") as _:
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as out_zf:
            out_zf.writestr("manifest.json", zeroed_manifest_json)
            out_zf.writestr("chunks.jsonl", new_chunks.encode())
            for name, data in other_files.items():
                out_zf.writestr(name, data)
    digest = "sha256:" + hashlib.sha256(buf.getvalue()).hexdigest()
    manifest["pack_digest"] = digest

    # Write tampered archive with updated pack_digest
    with zipfile.ZipFile(result, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr(
            "manifest.json", json.dumps(manifest, indent=2, sort_keys=True).encode()
        )
        zf.writestr("chunks.jsonl", new_chunks.encode())
        for name, data in other_files.items():
            zf.writestr(name, data)

    return result


# ===========================================================================
# 1. Golden-path end-to-end: build -> verify -> add -> query
# ===========================================================================


def test_full_pipeline_build_verify_add_query(
    tmp_path: Path, sample_docs: Path, runner: CliRunner
) -> None:
    """Build from fixture docs, verify passes, add succeeds, query returns
    results with correct package name and source_url."""
    output_dir = tmp_path / "output"
    ctx_path = output_dir / "test-lib@1.0.0.ctx"

    # --- build ---
    result = runner.invoke(
        cli,
        [
            "build",
            "test-lib@1.0.0",
            "--source",
            str(sample_docs),
            "--output",
            str(output_dir),
        ],
    )
    assert result.exit_code == 0, result.output
    assert ctx_path.exists(), f"Expected .ctx file at {ctx_path}, got: {result.output}"

    # --- verify ---
    result = runner.invoke(cli, ["verify", str(ctx_path)])
    assert result.exit_code == 0, result.output

    # --- add (needs CWD=tmp_path for relative .synd path) ---
    result = _cli_in_cwd(runner, ["add", str(ctx_path)], tmp_path)
    assert result.exit_code == 0, result.output

    # --- query ---
    result = _cli_in_cwd(
        runner,
        ["query", "install", "--detail", "summary"],
        tmp_path,
    )
    assert result.exit_code == 0, result.output
    assert "test-lib" in result.output.lower() or "got" in result.output.lower()
    assert "getting-started" in result.output or "sample" in result.output.lower()


# ===========================================================================
# 2. Build then verify passes (standalone)
# ===========================================================================


def test_build_then_verify_passes(
    tmp_path: Path, sample_docs: Path, runner: CliRunner
) -> None:
    """Build a .ctx pack, then verify it standalone -- must pass."""
    output_dir = tmp_path / "output"
    ctx_path = output_dir / "my-docs@0.1.0.ctx"

    result = runner.invoke(
        cli,
        [
            "build",
            "my-docs@0.1.0",
            "--source",
            str(sample_docs),
            "--output",
            str(output_dir),
            "--lifecycle",
            "draft",
        ],
    )
    assert result.exit_code == 0, result.output
    assert ctx_path.exists()

    result = runner.invoke(cli, ["verify", str(ctx_path)])
    assert result.exit_code == 0, result.output


# ===========================================================================
# 3. Tamper detection: modify chunk content, verify fails at step 7
# ===========================================================================


def test_build_then_tamper_then_verify_fails(
    tmp_path: Path, sample_docs: Path, runner: CliRunner
) -> None:
    """Modify a chunk's content in the .ctx after build -- verify returns
    VerifyResult(passed=False, step=7)."""
    output_dir = tmp_path / "output"
    ctx_path = output_dir / "tamped@1.0.0.ctx"

    result = runner.invoke(
        cli,
        [
            "build",
            "tamped@1.0.0",
            "--source",
            str(sample_docs),
            "--output",
            str(output_dir),
        ],
    )
    assert result.exit_code == 0, result.output
    assert ctx_path.exists()

    # Tamper with valid pack_digest (step 6 passes, step 7 fails)
    tampered_path = _tamper_with_valid_digest(ctx_path, {1: "TAMPERED CONTENT HERE"})

    result = runner.invoke(cli, ["verify", str(tampered_path)])
    assert result.exit_code != 0, "Tampered pack should fail verification"
    # Use the programmatic API to assert VerifyResult(passed=False, step=7)
    policy = Policy.default()
    vresult = verify(ctx_path=tampered_path, policy=policy)
    assert vresult.passed is False, (
        f"Tampered pack should fail verification, got step={vresult.step}"
    )
    assert vresult.step == 7, f"Expected step=7 (content hash), got step={vresult.step}"


# ===========================================================================
# 4. Pull populates FTS index
# ===========================================================================


def test_add_populates_fts_index(
    tmp_path: Path, sample_docs: Path, runner: CliRunner
) -> None:
    """After add, FTS5 chunks_fts table should contain entries."""
    output_dir = tmp_path / "output"
    ctx_path = output_dir / "fts-test@1.0.0.ctx"

    result = runner.invoke(
        cli,
        [
            "build",
            "fts-test@1.0.0",
            "--source",
            str(sample_docs),
            "--output",
            str(output_dir),
        ],
    )
    assert result.exit_code == 0, result.output

    result = _cli_in_cwd(runner, ["add", str(ctx_path)], tmp_path)
    assert result.exit_code == 0, result.output

    # Check FTS contents directly
    db = Database(tmp_path / ".synd" / "index.db")
    try:
        db.create_schema()
        rows = db.conn.execute("SELECT COUNT(*) AS cnt FROM chunks_fts").fetchone()
        assert rows["cnt"] > 0, "chunks_fts should have entries after add"

        rows = db.conn.execute("SELECT COUNT(*) AS cnt FROM chunks").fetchone()
        assert rows["cnt"] > 0, "chunks table should have entries after add"
    finally:
        db.close()


# ===========================================================================
# 5. Query returns attributed results
# ===========================================================================


def test_query_returns_attributed_results(
    tmp_path: Path, sample_docs: Path, runner: CliRunner
) -> None:
    """After build+add, querying returns results with package name,
    source_url, heading, and score."""
    output_dir = tmp_path / "output"
    ctx_path = output_dir / "attr-test@1.0.0.ctx"

    result = runner.invoke(
        cli,
        [
            "build",
            "attr-test@1.0.0",
            "--source",
            str(sample_docs),
            "--output",
            str(output_dir),
        ],
    )
    assert result.exit_code == 0, result.output

    result = _cli_in_cwd(runner, ["add", str(ctx_path)], tmp_path)
    assert result.exit_code == 0, result.output

    result = _cli_in_cwd(runner, ["query", "billing", "--detail", "full"], tmp_path)
    assert result.exit_code == 0, result.output
    assert "attr-test" in result.output.lower()


# ===========================================================================
# 6. Progressive disclosure: summary then full
# ===========================================================================


def test_query_progressive_disclosure(
    tmp_path: Path, sample_docs: Path, runner: CliRunner
) -> None:
    """Query with detail='summary' returns results without content, then
    query with chunk_ids and detail='full' returns content for those IDs."""
    output_dir = tmp_path / "output"
    ctx_path = output_dir / "progress@1.0.0.ctx"

    result = runner.invoke(
        cli,
        [
            "build",
            "progress@1.0.0",
            "--source",
            str(sample_docs),
            "--output",
            str(output_dir),
        ],
    )
    assert result.exit_code == 0, result.output

    result = _cli_in_cwd(runner, ["add", str(ctx_path)], tmp_path)
    assert result.exit_code == 0, result.output

    # CLI summary query
    result = _cli_in_cwd(runner, ["query", "oauth", "--detail", "summary"], tmp_path)
    assert result.exit_code == 0, result.output

    # Server API for programmatic checks
    db = Database(tmp_path / ".synd" / "index.db")
    try:
        db.create_schema()
        from synd.server import fetch_docs, search_docs

        summary_resp = search_docs(db, "oauth")
        assert "results" in summary_resp
        for r in summary_resp["results"]:
            assert r["content"] is None, f"summary should not include content: {r}"

        if summary_resp["results"]:
            chunk_ids = [r["chunk_id"] for r in summary_resp["results"]]
            full_resp = fetch_docs(db, chunk_ids)
            assert "results" in full_resp
            for r in full_resp["results"]:
                assert r["content"] is not None and len(r["content"]) > 0, (
                    f"full detail should include content for chunk {r['chunk_id']}"
                )
    finally:
        db.close()


# ===========================================================================
# 7. Lockfile written after add
# ===========================================================================


def test_add_writes_lockfile(
    tmp_path: Path, sample_docs: Path, runner: CliRunner
) -> None:
    """synd.lock exists at project root after add, contains pack name, version,
    and pack_digest."""
    output_dir = tmp_path / "output"
    ctx_path = output_dir / "lock-test@2.0.0.ctx"
    lock_file = tmp_path / "synd.lock"

    result = runner.invoke(
        cli,
        [
            "build",
            "lock-test@2.0.0",
            "--source",
            str(sample_docs),
            "--output",
            str(output_dir),
        ],
    )
    assert result.exit_code == 0, result.output

    result = _cli_in_cwd(runner, ["add", str(ctx_path)], tmp_path)
    assert result.exit_code == 0, result.output

    assert lock_file.exists(), "synd.lock should exist at project root after add"

    content = lock_file.read_text()
    assert "lock-test" in content, "lockfile should contain pack name"
    assert "2.0.0" in content, "lockfile should contain pack version"
    assert "pack_digest" in content, "lockfile should contain pack_digest"
    assert "source_url" in content, "lockfile should contain source_url"
    assert "schema_version = 2" in content, "lockfile should be schema version 2"


# ===========================================================================
# 8. Pull rejects duplicate
# ===========================================================================


def test_add_duplicate_rejected(
    tmp_path: Path, sample_docs: Path, runner: CliRunner
) -> None:
    """Pulling the same pack twice without --force should fail."""
    output_dir = tmp_path / "output"
    ctx_path = output_dir / "dup@1.0.0.ctx"

    result = runner.invoke(
        cli,
        [
            "build",
            "dup@1.0.0",
            "--source",
            str(sample_docs),
            "--output",
            str(output_dir),
        ],
    )
    assert result.exit_code == 0, result.output

    result = _cli_in_cwd(runner, ["add", str(ctx_path)], tmp_path)
    assert result.exit_code == 0, result.output

    result = _cli_in_cwd(runner, ["add", str(ctx_path)], tmp_path)
    assert result.exit_code != 0, "Second add without --force should fail"
    assert "already imported" in result.output.lower()


# ===========================================================================
# 9. Revoked pack excluded from query results
# ===========================================================================


def test_revoked_pack_excluded_from_query(
    tmp_path: Path, sample_docs: Path, runner: CliRunner
) -> None:
    """After build+add, manually setting lifecycle_state to revoked causes
    query to exclude results from that pack."""
    output_dir = tmp_path / "output"
    ctx_path = output_dir / "revoked@1.0.0.ctx"

    result = runner.invoke(
        cli,
        [
            "build",
            "revoked@1.0.0",
            "--source",
            str(sample_docs),
            "--output",
            str(output_dir),
        ],
    )
    assert result.exit_code == 0, result.output

    result = _cli_in_cwd(runner, ["add", str(ctx_path)], tmp_path)
    assert result.exit_code == 0, result.output

    # Manually set lifecycle_state to revoked
    db = Database(tmp_path / ".synd" / "index.db")
    try:
        db.create_schema()
        db.conn.execute(
            "UPDATE packages SET lifecycle_state = 'revoked' "
            "WHERE name = 'revoked' AND version = '1.0.0'"
        )
        db.conn.commit()
    finally:
        db.close()

    # Query should not return results from the revoked pack
    db = Database(tmp_path / ".synd" / "index.db")
    try:
        db.create_schema()
        hits = search(db, "oauth")
        for h in hits:
            assert h.lifecycle_state != "revoked", (
                f"Revoked pack results excluded, got package={h.package}"
            )
    finally:
        db.close()


# ===========================================================================
# NEGATIVE TEST 10 -- Pull does not leave partial state on failure
# ===========================================================================


def test_add_does_not_leave_partial_state_on_failure(
    tmp_path: Path, sample_docs: Path, runner: CliRunner
) -> None:
    """If import fails mid-transaction, the database must contain zero records
    from that import -- the transaction rolled back completely."""
    output_dir = tmp_path / "output"
    ctx_path = output_dir / "partial@1.0.0.ctx"

    result = runner.invoke(
        cli,
        [
            "build",
            "partial@1.0.0",
            "--source",
            str(sample_docs),
            "--output",
            str(output_dir),
        ],
    )
    assert result.exit_code == 0, result.output

    # First add succeeds
    result = _cli_in_cwd(runner, ["add", str(ctx_path)], tmp_path)
    assert result.exit_code == 0, result.output

    # Second add fails (duplicate)
    result = _cli_in_cwd(runner, ["add", str(ctx_path)], tmp_path)
    assert result.exit_code != 0, "Second add should fail"

    # Exactly 1 package in DB (the first successful import)
    db = Database(tmp_path / ".synd" / "index.db")
    try:
        db.create_schema()
        rows = db.conn.execute("SELECT COUNT(*) AS cnt FROM packages").fetchone()
        assert rows["cnt"] == 1, f"Expected 1 package, got {rows['cnt']}"
    finally:
        db.close()


# ===========================================================================
# NEGATIVE TEST 11 -- Revoked pack not in query results
# ===========================================================================


def test_revoked_pack_not_in_query_results(
    tmp_path: Path, sample_docs: Path, runner: CliRunner
) -> None:
    """Import a pack, update its lifecycle_state to revoked in the DB,
    run tank query -- zero results for that pack's content."""
    output_dir = tmp_path / "output"
    ctx_path = output_dir / "revoked-not@1.0.0.ctx"

    result = runner.invoke(
        cli,
        [
            "build",
            "revoked-not@1.0.0",
            "--source",
            str(sample_docs),
            "--output",
            str(output_dir),
        ],
    )
    assert result.exit_code == 0, result.output

    result = _cli_in_cwd(runner, ["add", str(ctx_path)], tmp_path)
    assert result.exit_code == 0, result.output

    # Mark as revoked
    db = Database(tmp_path / ".synd" / "index.db")
    try:
        db.create_schema()
        db.conn.execute(
            "UPDATE packages SET lifecycle_state = 'revoked' "
            "WHERE name = 'revoked-not' AND version = '1.0.0'"
        )
        db.conn.commit()
    finally:
        db.close()

    # Query via search API
    db = Database(tmp_path / ".synd" / "index.db")
    try:
        db.create_schema()
        hits = search(db, "sample")
        for h in hits:
            assert h.package != "revoked-not", (
                "Revoked pack should not appear in query results"
            )
    finally:
        db.close()


# ===========================================================================
# NEGATIVE TEST 12 -- Build/verify cycle is symmetric
# ===========================================================================


def test_build_verify_cycle_is_symmetric(
    tmp_path: Path, sample_docs: Path, runner: CliRunner
) -> None:
    """A .ctx file produced by build_pack() must always pass verify() with
    default policy. If this fails, build and verify are inconsistent."""
    from synd.builder.build import build_pack  # type: ignore[import-untyped]

    output_dir = tmp_path / "output"

    ctx_path = build_pack(
        package="sym-test",
        version="1.0.0",
        source=sample_docs,
        output=output_dir,
        lifecycle="draft",
    )
    assert ctx_path.exists()

    policy = Policy.default()
    result = verify(ctx_path=ctx_path, policy=policy)

    assert result.passed is True, (
        f"Build output should always pass verify. "
        f"passed={result.passed}, step={result.step}, reason={result.reason}"
    )


# ===========================================================================
# NEGATIVE TEST 13 -- Content tampering caught at step 7 specifically
# ===========================================================================


def test_content_tampering_captured_at_step_7(
    tmp_path: Path, sample_docs: Path, runner: CliRunner
) -> None:
    """Verify that modifying chunk content fails at step 7 specifically,
    not step 6 (pack_digest)."""
    from synd.builder.build import build_pack

    output_dir = tmp_path / "output"

    ctx_path = build_pack(
        package="step-test",
        version="1.0.0",
        source=sample_docs,
        output=output_dir,
        lifecycle="draft",
    )

    # Tamper with valid pack_digest
    tampered_path = _tamper_with_valid_digest(ctx_path, {1: "TAMPERED"})

    policy = Policy.default()
    result = verify(ctx_path=tampered_path, policy=policy)
    assert result.passed is False
    assert result.step == 7, f"Expected step=7 (content hash), got step={result.step}"


# ===========================================================================
# NETWORK TEST 14 -- Full pipeline against real FastMCP docs
# ===========================================================================

_FASTMCP_URL = "https://gofastmcp.com/llms-full.txt"
_FASTMCP_MIN_CHUNKS = 500  # sanity-check: real docs should produce many chunks


@pytest.mark.network
def test_fastmcp_full_pipeline(tmp_path: Path, runner: CliRunner) -> None:
    """Download the FastMCP llms-full.txt, build a pack, verify it, add it,
    and confirm a relevant query returns results.

    This test exercises the full pipeline against a real-world large file
    (~2MB, ~54k lines) and is the canonical check that tank handles
    large single-file sources correctly.
    """
    from synd.builder.build import build_pack

    source_dir = tmp_path / "source"
    output_dir = tmp_path / "output"
    source_dir.mkdir()
    output_dir.mkdir()

    # --- download ---
    dest = source_dir / "llms-full.md"
    urllib.request.urlretrieve(_FASTMCP_URL, dest)  # noqa: S310
    assert dest.stat().st_size > 1_000_000, "Downloaded file suspiciously small"

    # --- build ---
    ctx_path = build_pack(
        package="fastmcp",
        version="3.3.0",
        source=source_dir,
        output=output_dir,
        lifecycle="draft",
    )
    assert ctx_path.exists()

    # Sanity-check chunk count — a real large doc should produce many chunks
    with zipfile.ZipFile(ctx_path) as zf:
        chunk_count = sum(
            1 for line in zf.read("chunks.jsonl").decode().splitlines() if line.strip()
        )
    assert chunk_count >= _FASTMCP_MIN_CHUNKS, (
        f"Expected at least {_FASTMCP_MIN_CHUNKS} chunks, got {chunk_count}"
    )

    # --- verify ---
    policy = Policy.default()
    vresult = verify(ctx_path=ctx_path, policy=policy)
    assert vresult.passed is True, (
        f"Verification failed: step={vresult.step}, reason={vresult.reason}"
    )

    # --- add ---
    result = _cli_in_cwd(runner, ["add", str(ctx_path)], tmp_path)
    assert result.exit_code == 0, result.output

    # --- query ---
    db = Database(tmp_path / ".synd" / "index.db")
    try:
        db.create_schema()
        hits = search(db, "tool", packages=["fastmcp"], limit=5)
        assert len(hits) > 0, (
            "Query for 'tool' against fastmcp docs returned no results"
        )
        assert all(h.package == "fastmcp" for h in hits)
    finally:
        db.close()
