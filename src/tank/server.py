"""MCP server with query-docs and resolve-deps tools.

Invokable as: python -m tank.server
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any

from mcp.server.fastmcp import FastMCP

from tank.search.fts import SearchResult, get_chunks_by_id, search
from tank.storage.db import Database

_DEFAULT_DB_PATH = Path(".tank") / "index.db"
_HTTP_HOST = "127.0.0.1"


def _db_path(project_path: str | None = None) -> Path:
    """Return the path to the index database."""
    if project_path:
        return Path(project_path) / _DEFAULT_DB_PATH
    return _DEFAULT_DB_PATH


def resolve_deps(db: Database) -> dict[str, Any]:
    """Read-only health check — list of imported packs with their state."""
    packages = db.get_packages()
    packs = []
    for p in packages:
        row = db.conn.execute(
            "SELECT COUNT(*) AS cnt FROM chunks WHERE package = ? AND version = ?",
            (p.name, p.version),
        ).fetchone()
        chunks = row["cnt"]
        packs.append(
            {
                "package": p.name,
                "version": p.version,
                "lifecycle_state": p.lifecycle_state,
                "doc_version_status": p.doc_version_status,
                "chunks": chunks,
                "indexed_at": p.indexed_at,
            }
        )
    return {"status": "ok", "packs": packs}


def query_docs(
    db: Database,
    query: str,
    packages: list[str] | None = None,
    detail: str = "summary",
    chunk_ids: list[int] | None = None,
) -> dict[str, Any]:
    """FTS5 search with attribution.

    Supports summary/full detail levels and chunk_ids for targeted retrieval.
    """
    if chunk_ids:
        results = get_chunks_by_id(db, chunk_ids, detail="full")
        return {"results": [_to_dict(r) for r in results]}

    if not query.strip():
        return {"results": []}

    if packages:
        placeholders = ",".join("?" for _ in packages)
        row = db.conn.execute(
            f"SELECT COUNT(*) AS cnt FROM packages WHERE name IN ({placeholders})",
            packages,
        ).fetchone()
        if row["cnt"] < len(packages):
            return {"status": "not_indexed"}

    hits = search(db, query, packages=packages, detail=detail)
    return {"results": [_to_dict(r) for r in hits]}


def _to_dict(r: SearchResult) -> dict[str, Any]:
    """Convert a SearchResult to a dict for JSON serialisation."""
    out: dict[str, Any] = {
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
    """Register query-docs and resolve-deps tools on the given server."""

    @mcp.tool(name="resolve-deps")
    def resolve_deps_tool(project_path: str | None = None) -> str:
        """Read-only index health check — list of imported packs."""
        db = Database(_db_path(project_path))
        try:
            result = resolve_deps(db)
            return json.dumps(result)
        finally:
            db.close()

    @mcp.tool(name="query-docs")
    def query_docs_tool(
        query: str = "",
        packages: list[str] | None = None,
        max_tokens: int | None = None,
        detail: str = "summary",
        chunk_ids: list[int] | None = None,
    ) -> str:
        """FTS5 full-text search across indexed documentation."""
        db = Database(_db_path())
        try:
            result = query_docs(db, query, packages, detail, chunk_ids)
            return json.dumps(result)
        finally:
            db.close()


def create_server() -> FastMCP:
    """Create the MCP server with query-docs and resolve-deps tools."""
    mcp = FastMCP("tank")
    _register_tools(mcp)
    return mcp


def run_http() -> None:
    """Start the MCP server over Streamable HTTP bound to 127.0.0.1 only."""
    mcp = FastMCP("tank", host=_HTTP_HOST)
    _register_tools(mcp)
    asyncio.run(mcp.run_streamable_http_async())


if __name__ == "__main__":
    create_server().run()
