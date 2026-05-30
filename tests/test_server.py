"""Tests for the MCP server module."""

from pathlib import Path
from typing import Any

import pytest

from synd.storage.db import Database
from synd.storage.models import Chunk, Pack, Page
from synd.server import (
    fetch_docs,
    search_docs,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


@pytest.fixture()
def db(tmp_path: Path) -> Database:
    """Create a fresh Database with schema and return it."""
    db_path = tmp_path / ".synd" / "index.db"
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
        Page(
            id=1,
            package="my-lib",
            version="1.0.0",
            url="docs/auth/oauth.md",
            title="Authentication",
        ),
        Page(
            id=2,
            package="my-lib",
            version="1.0.0",
            url="docs/config.md",
            title="Configuration",
        ),
    ]
    chunks = [
        Chunk(
            id=1,
            package="my-lib",
            version="1.0.0",
            content="To configure OAuth2 client credentials flow...",
            page_id=1,
            heading_path="docs/auth/oauth / Configure OAuth2",
            summary="Configure OAuth2 client credentials flow",
            token_count=387,
            source_url="docs/auth/oauth.md",
            source_commit="abc123",
            content_hash="sha256:c1",
        ),
        Chunk(
            id=2,
            package="my-lib",
            version="1.0.0",
            content="Set the max retries to 3.",
            page_id=2,
            heading_path="docs / Configuration",
            summary="Configure retry limits",
            token_count=50,
            source_url="docs/config.md",
            source_commit="abc123",
            content_hash="sha256:c2",
        ),
        Chunk(
            id=3,
            package="my-lib",
            version="1.0.0",
            content="OAuth2 requires a client ID and secret.",
            page_id=1,
            heading_path="docs/auth/oauth / OAuth2 Setup",
            summary="OAuth2 client ID setup",
            token_count=100,
            source_url="docs/auth/oauth.md",
            source_commit="abc123",
            content_hash="sha256:c3",
        ),
        Chunk(
            id=4,
            package="my-lib",
            version="1.0.0",
            content="The timeout setting controls request waits.",
            page_id=2,
            heading_path="docs / Timeout Configuration",
            summary="Configure timeout values",
            token_count=80,
            source_url="docs/config.md",
            source_commit="abc123",
            content_hash="sha256:c4",
        ),
        Chunk(
            id=5,
            package="my-lib",
            version="1.0.0",
            content="Logging can be enabled via config.",
            page_id=2,
            heading_path="docs / Logging",
            summary="Enable and configure logging",
            token_count=60,
            source_url="docs/config.md",
            source_commit="abc123",
            content_hash="sha256:c5",
        ),
    ]
    db.import_pack(pack, pages, chunks)
    return pack


def _seed_deprecated_pack(db: Database) -> Pack:
    pack = Pack(
        name="old-lib",
        version="0.9.0",
        lifecycle_state="deprecated",
        doc_version_status="archived",
        indexed_at="2026-01-01T00:00:00Z",
        policy_profile="internal-strict",
        pack_digest="sha256:dd1",
        normalized_content_hash="sha256:dd2",
        source_url="https://old-lib.example.com/docs",
        source_commit="dead01",
        owner="legacy-team",
    )
    pages = [
        Page(id=1, package="old-lib", version="0.9.0", url="docs/old.md", title="Old")
    ]
    chunks = [
        Chunk(
            id=10,
            package="old-lib",
            version="0.9.0",
            content="This is deprecated content.",
            page_id=1,
            heading_path="docs / Old Guide",
            summary="Deprecated guide content",
            token_count=30,
            source_url="docs/old.md",
            source_commit="dead01",
            content_hash="sha256:dd3",
        ),
    ]
    db.import_pack(pack, pages, chunks)
    return pack


def _seed_revoked_pack(db: Database) -> Pack:
    pack = Pack(
        name="bad-lib",
        version="1.0.0",
        lifecycle_state="revoked",
        doc_version_status="stable",
        indexed_at="2026-03-01T00:00:00Z",
        policy_profile="internal-strict",
        pack_digest="sha256:rv1",
        normalized_content_hash="sha256:rv2",
        source_url="https://bad-lib.example.com/docs",
        source_commit="bad01",
        owner="unknown",
    )
    pages = [
        Page(id=1, package="bad-lib", version="1.0.0", url="docs/bad.md", title="Bad")
    ]
    chunks = [
        Chunk(
            id=20,
            package="bad-lib",
            version="1.0.0",
            content="This is revoked content.",
            page_id=1,
            heading_path="docs / Bad Guide",
            summary="Revoked content",
            token_count=20,
            source_url="docs/bad.md",
            source_commit="bad01",
            content_hash="sha256:rv3",
        ),
    ]
    db.import_pack(pack, pages, chunks)
    return pack


# ---------------------------------------------------------------------------
# search_docs — summary MCP tool backend
# ---------------------------------------------------------------------------


def test_search_docs_returns_summaries(db: Database) -> None:
    _seed_approved_pack(db)

    result: dict[str, Any] = search_docs(db, query="OAuth2")
    assert "results" in result
    assert len(result["results"]) > 0

    for r in result["results"]:
        assert "chunk_id" in r
        assert "package" in r
        assert "summary" in r
        assert r.get("content") is None, "summary tool must never include content"
        assert "lifecycle_warning" not in r


def test_search_docs_no_content_field(db: Database) -> None:
    """Content must be absent (None) in every summary result."""
    _seed_approved_pack(db)

    result: dict[str, Any] = search_docs(db, query="configure")
    assert "results" in result
    for r in result["results"]:
        assert r.get("content") is None


def test_search_docs_empty_query_returns_empty(db: Database) -> None:
    _seed_approved_pack(db)

    result: dict[str, Any] = search_docs(db, query="")
    assert result == {"results": []}

    result_ws: dict[str, Any] = search_docs(db, query="   ")
    assert result_ws == {"results": []}


def test_search_docs_limit(db: Database) -> None:
    _seed_approved_pack(db)

    # "configure" matches chunks 1, 2, 4, 5 in the fixture (4 results).
    full = search_docs(db, query="configure")
    assert len(full["results"]) == 4

    capped = search_docs(db, query="configure", limit=2)
    assert len(capped["results"]) == 2

    # limit larger than available results should return all matches without error.
    uncapped = search_docs(db, query="configure", limit=100)
    assert len(uncapped["results"]) == 4


def test_search_docs_not_indexed_package(db: Database) -> None:
    _seed_approved_pack(db)

    result: dict[str, Any] = search_docs(
        db,
        query="anything",
        packages=["nonexistent-pkg"],
    )
    assert result["status"] == "not_indexed"


def test_search_docs_deprecated_warning(db: Database) -> None:
    _seed_deprecated_pack(db)

    result: dict[str, Any] = search_docs(db, query="deprecated")
    assert "results" in result

    found_deprecated = False
    for r in result["results"]:
        if r["package"] == "old-lib":
            assert "lifecycle_warning" in r
            assert "deprecated" in r["lifecycle_warning"].lower()
            found_deprecated = True
    assert found_deprecated


def test_search_docs_does_not_return_revoked(db: Database) -> None:
    """Revoked packs must return zero results.

    NEG: Any result with lifecycle_state='revoked' in summary output.
    """
    _seed_approved_pack(db)
    _seed_revoked_pack(db)

    result: dict[str, Any] = search_docs(db, query="content")
    assert "results" in result

    for r in result["results"]:
        assert r["lifecycle_state"] != "revoked", (
            f"summary must not return results from revoked packs, "
            f"but got package={r['package']}"
        )


def test_search_docs_max_tokens_large_budget(db: Database) -> None:
    _seed_approved_pack(db)

    unbounded = search_docs(db, query="configure")
    budgeted = search_docs(db, query="configure", max_tokens=10_000)

    assert budgeted["results"] == unbounded["results"]


def test_search_docs_max_tokens_trims_to_ranked_prefix(db: Database) -> None:
    _seed_approved_pack(db)

    unbounded = search_docs(db, query="configure")
    assert len(unbounded["results"]) > 1

    # Compute total estimated cost across all returned summaries.
    total_cost = sum(len(r["summary"] or "") // 4 for r in unbounded["results"])

    # A budget one token below the total must drop at least the last result.
    trimmed = search_docs(db, query="configure", max_tokens=total_cost - 1)
    assert len(trimmed["results"]) < len(unbounded["results"])

    # Retained results must be the top-ranked prefix — same order, same chunk IDs.
    for i, r in enumerate(trimmed["results"]):
        assert r["chunk_id"] == unbounded["results"][i]["chunk_id"]


# ---------------------------------------------------------------------------
# fetch_docs — detail MCP tool backend
# ---------------------------------------------------------------------------


def test_fetch_docs_returns_full_content(db: Database) -> None:
    _seed_approved_pack(db)

    result: dict[str, Any] = fetch_docs(db, chunk_ids=[1, 2])
    assert "results" in result
    assert len(result["results"]) == 2

    chunk_ids_in_result = {r["chunk_id"] for r in result["results"]}
    assert chunk_ids_in_result == {1, 2}

    for r in result["results"]:
        assert r.get("content") is not None
        assert len(r["content"]) > 0


def test_fetch_docs_empty_chunk_ids(db: Database) -> None:
    _seed_approved_pack(db)

    result: dict[str, Any] = fetch_docs(db, chunk_ids=[])
    assert result == {"results": []}


def test_fetch_docs_does_not_return_revoked(db: Database) -> None:
    """Revoked chunk IDs must be silently excluded from detail output.

    NEG: Any result with lifecycle_state='revoked' in detail output.
    """
    _seed_approved_pack(db)
    _seed_revoked_pack(db)

    # chunk ID 20 belongs to the revoked pack; chunk ID 1 to the approved pack.
    result: dict[str, Any] = fetch_docs(db, chunk_ids=[1, 20])
    assert "results" in result

    returned_ids = {r["chunk_id"] for r in result["results"]}
    assert 20 not in returned_ids, "detail must not return chunks from revoked packs"
    assert 1 in returned_ids


def test_fetch_docs_max_tokens(db: Database) -> None:
    _seed_approved_pack(db)

    # chunk_ids fetches full content; budget is applied against content length.
    # Chunk 1 content: "To configure OAuth2 client credentials flow..." (46 chars → 11 tokens)
    # Chunk 2 content: "Set the max retries to 3." (25 chars → 6 tokens)
    # Combined cost: 17 tokens.

    # Budget 17 fits both chunks.
    both = fetch_docs(db, chunk_ids=[1, 2], max_tokens=17)
    assert {r["chunk_id"] for r in both["results"]} == {1, 2}

    # Budget 11 fits chunk 1 (cost 11) but stops before chunk 2 (11+6=17 > 11).
    one = fetch_docs(db, chunk_ids=[1, 2], max_tokens=11)
    assert [r["chunk_id"] for r in one["results"]] == [1]

    # Budget 10 cannot fit chunk 1 (cost 11 > 10).
    none = fetch_docs(db, chunk_ids=[1, 2], max_tokens=10)
    assert none["results"] == []


def test_fetch_docs_max_tokens_large_budget(db: Database) -> None:
    _seed_approved_pack(db)

    unbounded = fetch_docs(db, chunk_ids=[1, 2, 3])
    budgeted = fetch_docs(db, chunk_ids=[1, 2, 3], max_tokens=10_000)

    assert budgeted["results"] == unbounded["results"]


# ---------------------------------------------------------------------------
# HTTP transport
# ---------------------------------------------------------------------------


def test_http_does_not_bind_external() -> None:
    """HTTP transport must bind to 127.0.0.1 only.

    NEG: Server binds to '0.0.0.0', '', or any non-loopback address.
    """
    import inspect
    import synd.server as srv

    assert srv._HTTP_HOST == "127.0.0.1", "_HTTP_HOST must be 127.0.0.1"
    source = inspect.getsource(srv.run_http)
    assert "_HTTP_HOST" in source, "run_http must use _HTTP_HOST constant"
    assert "0.0.0.0" not in source, "HTTP transport must not bind to 0.0.0.0"


# ---------------------------------------------------------------------------
# Tool response contract (tool-response.v1)
# ---------------------------------------------------------------------------


def test_tools_publish_canonical_output_schema() -> None:
    """Registered search/fetch tools advertise the tool-response.v1 schema.

    Clients discover the response contract via tools/list; it must be the exact
    canonical schema document the boundary validator uses (one source).
    """
    from synd.schemas import tool_response_schema
    from synd.server import create_server

    canonical = tool_response_schema()
    server = create_server()
    tools = {t.name: t for t in server._tool_manager.list_tools()}

    assert {"search", "fetch"} <= set(tools)
    for name in ("search", "fetch"):
        assert tools[name].output_schema == canonical, (
            f"{name} must advertise the tool-response.v1 schema"
        )


def test_search_docs_output_validates_against_contract(db: Database) -> None:
    """search_docs payloads satisfy the tool-response.v1 schema."""
    from synd.schemas import validate_tool_response

    validate_tool_response(dict(search_docs(db, query="OAuth2")))
    validate_tool_response(dict(search_docs(db, query="")))
    validate_tool_response(
        dict(search_docs(db, query="x", packages=["does-not-exist"]))
    )


def test_fetch_docs_output_validates_against_contract(db: Database) -> None:
    """fetch_docs payloads satisfy the tool-response.v1 schema."""
    from synd.schemas import validate_tool_response

    validate_tool_response(dict(fetch_docs(db, chunk_ids=[1, 2])))
    validate_tool_response(dict(fetch_docs(db, chunk_ids=[])))
