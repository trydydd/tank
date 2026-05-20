from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from tank.storage.db import Database


@dataclass
class SearchResult:
    chunk_id: int
    package: str
    version: str
    heading_path: str | None
    summary: str | None
    content: str | None  # None when detail='summary'
    source_url: str | None
    source_commit: str | None
    content_hash: str | None
    lifecycle_state: str
    doc_version_status: str | None
    indexed_at: str
    score: float
    lifecycle_warning: str | None  # set when lifecycle_state == 'deprecated'


def search(
    db: "Database",
    query: str,
    packages: list[str] | None = None,
    detail: str = "summary",
    limit: int = 10,
) -> list[SearchResult]:
    if not query.strip():
        return []

    conn = db.conn

    try:
        # Build the WHERE clause for optional package filtering
        pkg_where = ""
        params: list[Any] = []
        if packages:
            placeholders = ",".join("?" for _ in packages)
            pkg_where = f" AND p.name IN ({placeholders})"
            params.extend(packages)

        if detail == "full":
            select_cols = (
                "c.id, p.name, p.version, c.heading_path, c.summary, "
                "c.content, c.source_url, c.source_commit, c.content_hash, "
                "p.lifecycle_state, p.doc_version_status, p.indexed_at, "
            )
        else:
            select_cols = (
                "c.id, p.name, p.version, c.heading_path, c.summary, "
                "NULL, c.source_url, c.source_commit, c.content_hash, "
                "p.lifecycle_state, p.doc_version_status, p.indexed_at, "
            )

        sql = f"""\
SELECT {select_cols}
       -bm25(chunks_fts, 1.0, 1.0, 1.0) AS score
FROM chunks_fts, chunks c, packages p
WHERE chunks_fts.rowid = c.id
  AND c.package = p.name
  AND c.version = p.version
  AND p.lifecycle_state != 'revoked'{pkg_where}
  AND chunks_fts MATCH ?
ORDER BY score DESC
LIMIT ?"""

        params.append(query)
        params.append(limit)

        rows = conn.execute(sql, params).fetchall()
    except Exception:
        return []

    # SELECT columns: 0=id, 1=package, 2=version, 3=heading_path, 4=summary,
    # 5=content, 6=source_url, 7=source_commit, 8=content_hash,
    # 9=lifecycle_state, 10=doc_version_status, 11=indexed_at, 12=score
    results: list[SearchResult] = []
    for row in rows:
        lifecycle_state = row[9]
        results.append(
            SearchResult(
                chunk_id=row[0],
                package=row[1],
                version=row[2],
                heading_path=row[3],
                summary=row[4],
                content=row[5],
                source_url=row[6],
                source_commit=row[7],
                content_hash=row[8],
                lifecycle_state=lifecycle_state,
                doc_version_status=row[10],
                indexed_at=row[11],
                score=row[12],
                lifecycle_warning="This package is deprecated"
                if lifecycle_state == "deprecated"
                else None,
            )
        )

    return results


def get_chunks_by_id(
    db: "Database",
    chunk_ids: list[int],
    detail: str = "full",
) -> list[SearchResult]:
    if not chunk_ids:
        return []

    conn = db.conn

    placeholders = ",".join("?" for _ in chunk_ids)
    sql = (
        "SELECT c.id, p.name, p.version, c.heading_path, c.summary, c.content, "
        "c.source_url, c.source_commit, c.content_hash, "
        "p.lifecycle_state, p.doc_version_status, p.indexed_at "
        "FROM chunks c, packages p "
        "WHERE c.package = p.name AND c.version = p.version "
        "  AND c.id IN (" + placeholders + ") "
        "  AND p.lifecycle_state != 'revoked' "
        "ORDER BY c.id"
    )

    rows = conn.execute(sql, chunk_ids).fetchall()
    # SELECT columns: 0=id, 1=package, 2=version, 3=heading_path, 4=summary,
    # 5=content, 6=source_url, 7=source_commit, 8=content_hash,
    # 9=lifecycle_state, 10=doc_version_status, 11=indexed_at
    results: list[SearchResult] = []
    for row in rows:
        lifecycle_state = row[9]
        results.append(
            SearchResult(
                chunk_id=row[0],
                package=row[1],
                version=row[2],
                heading_path=row[3],
                summary=row[4],
                content=row[5] if detail == "full" else None,
                source_url=row[6],
                source_commit=row[7],
                content_hash=row[8],
                lifecycle_state=lifecycle_state,
                doc_version_status=row[10],
                indexed_at=row[11],
                score=0.0,
                lifecycle_warning="This package is deprecated"
                if lifecycle_state == "deprecated"
                else None,
            )
        )

    return results
