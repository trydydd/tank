"""Tests for the MCP server module (chunk-10)."""

from pathlib import Path
from typing import Any

import pytest

from tank.storage.db import Database
from tank.storage.models import Chunk, Pack, Page
from tank.server import (
    query_docs,
    resolve_deps,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


@pytest.fixture()
def db(tmp_path: Path) -> Database:
    """Create a fresh Database with schema and return it."""
    db_path = tmp_path / ".tank" / "index.db"
    db = Database(db_path)
    db.create_schema()
    return db


def _seed_approved_pack(db: Database) -> Pack:
    pack = Pack(
        name="my-lib",
        version="1.0.0",
        lifecycle_state="approved",
        doc_version_status="stable",
        indexed_at="2026-05-14T10:30:00Z",
        policy_profile="internal-strict",
        pack_digest="sha256:aaa",
        normalized_content_hash="sha256:bbb",
        source_url="https://my-lib.example.com/docs",
        source_commit="abc123",
        owner="platform-team",
    )
    pages = [
        Page(id=1, package="my-lib", version="1.0.0", url="docs/auth/oauth.md", title="Authentication"),
        Page(id=2, package="my-lib", version="1.0.0", url="docs/config.md", title="Configuration"),
    ]
    chunks = [
        Chunk(id=1, package="my-lib", version="1.0.0", content="To configure OAuth2 client credentials flow...",
              page_id=1, heading_path="docs/auth/oauth / Configure OAuth2",
              summary="Configure OAuth2 client credentials flow", token_count=387,
              source_url="docs/auth/oauth.md", source_commit="abc123", content_hash="sha256:c1"),
        Chunk(id=2, package="my-lib", version="1.0.0", content="Set the max retries to 3.",
              page_id=2, heading_path="docs / Configuration",
              summary="Configure retry limits", token_count=50,
              source_url="docs/config.md", source_commit="abc123", content_hash="sha256:c2"),
        Chunk(id=3, package="my-lib", version="1.0.0", content="OAuth2 requires a client ID and secret.",
              page_id=1, heading_path="docs/auth/oauth / OAuth2 Setup",
              summary="OAuth2 client ID setup", token_count=100,
              source_url="docs/auth/oauth.md", source_commit="abc123", content_hash="sha256:c3"),
        Chunk(id=4, package="my-lib", version="1.0.0", content="The timeout setting controls request waits.",
              page_id=2, heading_path="docs / Timeout Configuration",
              summary="Configure timeout values", token_count=80,
              source_url="docs/config.md", source_commit="abc123", content_hash="sha256:c4"),
        Chunk(id=5, package="my-lib", version="1.0.0", content="Logging can be enabled via config.",
              page_id=2, heading_path="docs / Logging",
              summary="Enable and configure logging", token_count=60,
              source_url="docs/config.md", source_commit="abc123", content_hash="sha256:c5"),
    ]
    db.import_pack(pack, pages, chunks)
    return pack


def _seed_deprecated_pack(db: Database) -> Pack:
    pack = Pack(
        name="old-lib", version="0.9.0", lifecycle_state="deprecated",
        doc_version_status="archived", indexed_at="2026-01-01T00:00:00Z",
        policy_profile="internal-strict", pack_digest="sha256:dd1",
        normalized_content_hash="sha256:dd2", source_url="https://old-lib.example.com/docs",
        source_commit="dead01", owner="legacy-team",
    )
    pages = [Page(id=1, package="old-lib", version="0.9.0", url="docs/old.md", title="Old")]
    chunks = [
        Chunk(id=10, package="old-lib", version="0.9.0", content="This is deprecated content.",
              page_id=1, heading_path="docs / Old Guide", summary="Deprecated guide content",
              token_count=30, source_url="docs/old.md", source_commit="dead01", content_hash="sha256:dd3"),
    ]
    db.import_pack(pack, pages, chunks)
    return pack


def _seed_revoked_pack(db: Database) -> Pack:
    pack = Pack(
        name="bad-lib", version="1.0.0", lifecycle_state="revoked",
        doc_version_status="stable", indexed_at="2026-03-01T00:00:00Z",
        policy_profile="internal-strict", pack_digest="sha256:rv1",
        normalized_content_hash="sha256:rv2", source_url="https://bad-lib.example.com/docs",
        source_commit="bad01", owner="unknown",
    )
    pages = [Page(id=1, package="bad-lib", version="1.0.0", url="docs/bad.md", title="Bad")]
    chunks = [
        Chunk(id=20, package="bad-lib", version="1.0.0", content="This is revoked content.",
              page_id=1, heading_path="docs / Bad Guide", summary="Revoked content",
              token_count=20, source_url="docs/bad.md", source_commit="bad01", content_hash="sha256:rv3"),
    ]
    db.import_pack(pack, pages, chunks)
    return pack


# ---------------------------------------------------------------------------
# test_resolve_deps_returns_packs
# ---------------------------------------------------------------------------


def test_resolve_deps_returns_packs(db: Database) -> None:
    _seed_approved_pack(db)

    # Import a second pack to verify multi-pack behavior
    pack2 = Pack(
        name="other-lib", version="2.1.0", lifecycle_state="approved",
        doc_version_status="stable", indexed_at="2026-05-15T12:00:00Z",
        policy_profile="internal-strict", pack_digest="sha256:ee1",
        normalized_content_hash="sha256:ee2", source_url="https://other-lib.example.com/docs",
        source_commit="def456", owner="backend-team",
    )
    pages2 = [Page(id=1, package="other-lib", version="2.1.0", url="docs/api.md", title="API")]
    chunks2 = [
        Chunk(id=1, package="other-lib", version="2.1.0", content="The API accepts JSON payloads.", page_id=1, heading_path="docs / API", summary="API accepts JSON", token_count=50, source_url="docs/api.md", source_commit="def456", content_hash="sha256:ff1"),
    ]
    db.import_pack(pack2, pages2, chunks2)

    result: dict[str, Any] = resolve_deps(db)
    assert result["status"] == "ok"
    assert len(result["packs"]) == 2

    packages_seen = {p["package"] for p in result["packs"]}
    assert packages_seen == {"my-lib", "other-lib"}

    my_lib = next(p for p in result["packs"] if p["package"] == "my-lib")
    assert my_lib["version"] == "1.0.0"
    assert my_lib["lifecycle_state"] == "approved"
    assert my_lib["chunks"] == 5

    other_lib = next(p for p in result["packs"] if p["package"] == "other-lib")
    assert other_lib["version"] == "2.1.0"
    assert other_lib["lifecycle_state"] == "approved"
    assert other_lib["chunks"] == 1


# ---------------------------------------------------------------------------
# test_resolve_deps_empty_index
# ---------------------------------------------------------------------------


def test_resolve_deps_empty_index(db: Database) -> None:
    result: dict[str, Any] = resolve_deps(db)
    assert result["status"] == "ok"
    assert result["packs"] == []


# ---------------------------------------------------------------------------
# test_query_docs_summary_mode
# ---------------------------------------------------------------------------


def test_query_docs_summary_mode(db: Database) -> None:
    _seed_approved_pack(db)

    result: dict[str, Any] = query_docs(
        db, query="OAuth2", packages=None, detail="summary", chunk_ids=None,
    )
    assert "results" in result
    assert len(result["results"]) > 0

    for r in result["results"]:
        assert "chunk_id" in r
        assert "package" in r
        assert "summary" in r
        assert r.get("content") is None
        assert "lifecycle_warning" not in r


# ---------------------------------------------------------------------------
# test_query_docs_full_mode
# ---------------------------------------------------------------------------


def test_query_docs_full_mode(db: Database) -> None:
    _seed_approved_pack(db)

    result: dict[str, Any] = query_docs(
        db, query="configure", packages=None, detail="full", chunk_ids=None,
    )
    assert "results" in result
    assert len(result["results"]) > 0

    for r in result["results"]:
        assert r.get("content") is not None
        assert len(r["content"]) > 0


# ---------------------------------------------------------------------------
# test_query_docs_chunk_ids
# ---------------------------------------------------------------------------


def test_query_docs_chunk_ids(db: Database) -> None:
    _seed_approved_pack(db)

    result: dict[str, Any] = query_docs(
        db, query="", packages=None, detail="summary", chunk_ids=[1, 2],
    )
    assert "results" in result
    assert len(result["results"]) == 2
    chunk_ids_in_result = {r["chunk_id"] for r in result["results"]}
    assert chunk_ids_in_result == {1, 2}
    for r in result["results"]:
        assert r.get("content") is not None
        assert len(r["content"]) > 0


# ---------------------------------------------------------------------------
# test_query_docs_not_indexed_package
# ---------------------------------------------------------------------------


def test_query_docs_not_indexed_package(db: Database) -> None:
    _seed_approved_pack(db)

    result: dict[str, Any] = query_docs(
        db, query="anything", packages=["nonexistent-pkg"],
        detail="summary", chunk_ids=None,
    )
    assert result["status"] == "not_indexed"


# ---------------------------------------------------------------------------
# test_query_docs_deprecated_warning
# ---------------------------------------------------------------------------


def test_query_docs_deprecated_warning(db: Database) -> None:
    _seed_deprecated_pack(db)

    result: dict[str, Any] = query_docs(
        db, query="deprecated", packages=None, detail="summary", chunk_ids=None,
    )
    assert "results" in result

    found_deprecated = False
    for r in result["results"]:
        if r["package"] == "old-lib":
            assert "lifecycle_warning" in r
            assert "deprecated" in r["lifecycle_warning"].lower()
            found_deprecated = True
    assert found_deprecated


# ---------------------------------------------------------------------------
# NEG: test_http_does_not_bind_external
# ---------------------------------------------------------------------------


def test_http_does_not_bind_external() -> None:
    """HTTP transport must bind to 127.0.0.1 only.

    NEG: Server binds to '0.0.0.0', '', or any non-loopback address.
    """
    import inspect
    import tank.server as srv

    assert srv._HTTP_HOST == "127.0.0.1", "_HTTP_HOST must be 127.0.0.1"
    source = inspect.getsource(srv.run_http)
    assert "_HTTP_HOST" in source, "run_http must use _HTTP_HOST constant"
    assert "0.0.0.0" not in source, "HTTP transport must not bind to 0.0.0.0"


# ---------------------------------------------------------------------------
# NEG: test_query_docs_does_not_return_revoked
# ---------------------------------------------------------------------------


def test_query_docs_does_not_return_revoked(db: Database) -> None:
    """Revoked packs must return zero results.

    NEG: Any result with lifecycle_state='revoked' in query-docs output.
    """
    _seed_approved_pack(db)
    _seed_revoked_pack(db)

    result: dict[str, Any] = query_docs(
        db, query="content", packages=None, detail="full", chunk_ids=None,
    )
    assert "results" in result

    for r in result["results"]:
        assert r["lifecycle_state"] != "revoked", (
            f"query-docs must not return results from revoked packs, "
            f"but got package={r['package']}"
        )


# ---------------------------------------------------------------------------
# NEG: test_resolve_deps_does_not_omit_deprecated
# ---------------------------------------------------------------------------


def test_resolve_deps_does_not_omit_deprecated(db: Database) -> None:
    """Deprecated packs must appear in resolve-deps output.

    NEG: A deprecated pack missing from resolve-deps output.
    """
    _seed_approved_pack(db)
    _seed_deprecated_pack(db)

    result: dict[str, Any] = resolve_deps(db)
    assert result["status"] == "ok"
    assert len(result["packs"]) == 2

    packages_seen = {p["package"] for p in result["packs"]}
    assert "old-lib" in packages_seen, (
        "resolve-deps must include deprecated packs in its output"
    )
