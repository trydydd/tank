"""MCP server with search and fetch tools.

Invokable as: python -m synd.server

The search/fetch response shape is the ``tool-response.v1`` contract
(``synd/schemas/tool-response.v1.schema.json``). It is enforced two ways:
``search_docs``/``fetch_docs`` validate every payload against the schema before
returning (boundary validation), and the registered MCP tools publish that same
schema as their ``outputSchema`` so clients can discover the shape via
``tools/list``.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

from mcp.server.fastmcp import FastMCP

from synd.schemas import tool_response_schema, validate_tool_response
from synd.schemas.types import ToolResponse, ToolResultItem
from synd.search.fts import SearchResult, get_chunks_by_id, search
from synd.storage.db import Database

_DEFAULT_DB_PATH = Path(".synd") / "index.db"
_HTTP_HOST = "127.0.0.1"


def _db_path(project_path: str | None = None) -> Path:
    """Return the path to the index database."""
    if project_path:
        return Path(project_path) / _DEFAULT_DB_PATH
    return _DEFAULT_DB_PATH


def search_docs(
    db: Database,
    query: str,
    packages: list[str] | None = None,
    limit: int = 10,
    max_tokens: int | None = None,
) -> ToolResponse:
    """FTS5 search returning chunk summaries only.

    Returns heading_path, summary, chunk_id, and provenance fields for each
    matched chunk. Content is never included — call fetch_docs with the
    chunk_ids you select to retrieve full text.

    When packages contains a package that is not indexed, returns
    {"status": "not_indexed"} rather than silently returning empty results.

    When max_tokens is set, results are accumulated in BM25 rank order and
    stopped before the estimated token cost (len(summary) // 4) would exceed
    the budget. Whole chunks only — no partial truncation.

    The returned payload always satisfies the tool-response.v1 contract.
    """
    if not query.strip():
        return _validated({"results": []})

    if packages:
        placeholders = ",".join("?" for _ in packages)
        row = db.conn.execute(
            f"SELECT COUNT(*) AS cnt FROM packages WHERE name IN ({placeholders})",
            packages,
        ).fetchone()
        if row["cnt"] < len(packages):
            return _validated({"status": "not_indexed"})

    hits = [
        _to_dict(r)
        for r in search(db, query, packages=packages, detail="summary", limit=limit)
    ]
    if max_tokens is not None:
        hits = _apply_token_budget(hits, max_tokens, "summary")
    return _validated({"results": hits})


def fetch_docs(
    db: Database,
    chunk_ids: list[int],
    max_tokens: int | None = None,
) -> ToolResponse:
    """Fetch full content for specific chunks by ID.

    Returns complete content, heading_path, summary, and provenance fields for
    each requested chunk. Revoked chunks are excluded even if their IDs are
    provided directly.

    When max_tokens is set, chunks are returned in ID order and stopped before
    the estimated token cost (len(content) // 4) would exceed the budget.
    Whole chunks only — no partial truncation.

    The returned payload always satisfies the tool-response.v1 contract.
    """
    results = get_chunks_by_id(db, chunk_ids, detail="full")
    hits = [_to_dict(r) for r in results]
    if max_tokens is not None:
        hits = _apply_token_budget(hits, max_tokens, "full")
    return _validated({"results": hits})


def _validated(response: ToolResponse) -> ToolResponse:
    """Validate an outgoing response against the tool-response.v1 contract.

    A failure here means the server produced an off-contract payload — a bug —
    so it raises rather than emitting bad data.
    """
    validate_tool_response(dict(response))
    return response


def _apply_token_budget(
    hits: list[ToolResultItem], max_tokens: int, detail: str
) -> list[ToolResultItem]:
    """Return the longest prefix of hits that fits within max_tokens.

    Token cost per chunk: len(content) // 4 for full detail,
    len(summary) // 4 for summary detail. Matches the token_count estimator
    used at build time. Whole chunks only — no partial truncation.
    """
    budget = 0
    kept: list[ToolResultItem] = []
    for hit in hits:
        if detail == "full":
            cost = len(hit.get("content") or "") // 4
        else:
            cost = len(hit.get("summary") or "") // 4
        if budget + cost > max_tokens:
            break
        budget += cost
        kept.append(hit)
    return kept


def _to_dict(r: SearchResult) -> ToolResultItem:
    """Convert a SearchResult to a tool-response result item."""
    out: ToolResultItem = {
        "chunk_id": r.chunk_id,
        "package": r.package,
        "version": r.version,
        "lifecycle_state": r.lifecycle_state,
        "doc_version_status": r.doc_version_status,
        "heading_path": r.heading_path,
        "summary": r.summary,
        "content": r.content,
        "source_url": r.source_url,
        "source_commit": r.source_commit,
        "content_hash": r.content_hash,
        "indexed_at": r.indexed_at,
        "score": r.score,
    }
    if r.lifecycle_warning is not None:
        out["lifecycle_warning"] = r.lifecycle_warning
    return out


def _register_tools(mcp: FastMCP) -> None:
    """Register search and fetch tools on the given server."""

    @mcp.tool(name="search")
    def search_tool(
        query: str,
        packages: list[str] | None = None,
        limit: int = 10,
        max_tokens: int | None = None,
    ) -> str:
        """Returns summaries and chunk_ids for matching docs — no content.
        Call fetch with the chunk_ids to get full text.
        Keywords only: rephrase natural-language queries to search terms before calling.
        Unknown package name → {"status": "not_indexed"}.
        """
        db = Database(_db_path())
        try:
            result = search_docs(
                db,
                query=query,
                packages=packages,
                limit=limit,
                max_tokens=max_tokens,
            )
            return json.dumps(result)
        finally:
            db.close()

    @mcp.tool(name="fetch")
    def fetch_tool(
        chunk_ids: list[int],
        max_tokens: int | None = None,
    ) -> str:
        """Returns full content for chunk_ids obtained from search."""
        db = Database(_db_path())
        try:
            result = fetch_docs(db, chunk_ids=chunk_ids, max_tokens=max_tokens)
            return json.dumps(result)
        finally:
            db.close()

    _publish_output_schema(mcp)


def _publish_output_schema(mcp: FastMCP) -> None:
    """Advertise the tool-response.v1 schema as each tool's outputSchema.

    FastMCP has no public decorator parameter for outputSchema, so we set
    tool.output_schema directly on the internal Tool objects (accessible via the
    private _tool_manager). Wrapped in try/except so a future FastMCP version
    that changes its internals degrades gracefully rather than crashing startup.
    The boundary validation in _validated() still enforces correctness regardless.
    """
    schema = tool_response_schema()
    try:
        for tool in mcp._tool_manager.list_tools():
            tool.output_schema = schema
    except AttributeError:
        pass  # FastMCP internals changed; outputSchema advertisement skipped


def create_server() -> FastMCP:
    """Create the MCP server with search and fetch tools."""
    mcp = FastMCP("synaptic-drift")
    _register_tools(mcp)
    return mcp


def run_http() -> None:
    """Start the MCP server over Streamable HTTP bound to 127.0.0.1 only."""
    mcp = FastMCP("tank", host=_HTTP_HOST)
    _register_tools(mcp)
    asyncio.run(mcp.run_streamable_http_async())


if __name__ == "__main__":
    create_server().run()
