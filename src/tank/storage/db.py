import sqlite3
from pathlib import Path

from tank.storage.models import Chunk, Pack, Page


_CREATE_SCHEMA = """\
CREATE TABLE IF NOT EXISTS packages (
    name                    TEXT NOT NULL,
    version                 TEXT NOT NULL,
    lifecycle_state         TEXT NOT NULL DEFAULT 'draft',
    policy_profile          TEXT,
    pack_digest             TEXT,
    normalized_content_hash TEXT,
    doc_version_status      TEXT,
    source_url              TEXT,
    source_commit           TEXT,
    owner                   TEXT,
    indexed_at              TEXT NOT NULL,
    PRIMARY KEY (name, version)
);

CREATE TABLE IF NOT EXISTS pages (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    package       TEXT NOT NULL,
    version       TEXT NOT NULL,
    url           TEXT NOT NULL,
    content_hash  TEXT,
    UNIQUE(package, version, url),
    FOREIGN KEY (package, version) REFERENCES packages(name, version)
);

CREATE TABLE IF NOT EXISTS chunks (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    package         TEXT NOT NULL,
    version         TEXT NOT NULL,
    page_id         INTEGER REFERENCES pages(id),
    heading_path    TEXT,
    summary         TEXT,
    content         TEXT NOT NULL,
    token_count     INTEGER,
    source_url      TEXT,
    source_commit   TEXT,
    content_hash    TEXT,
    FOREIGN KEY (package, version) REFERENCES packages(name, version)
);

CREATE VIRTUAL TABLE IF NOT EXISTS chunks_fts USING fts5(
    summary, content,
    content='chunks',
    content_rowid='id'
);

CREATE TRIGGER IF NOT EXISTS chunks_ai AFTER INSERT ON chunks BEGIN
    INSERT INTO chunks_fts(rowid, summary, content)
    VALUES (new.id, new.summary, new.content);
END;

CREATE TRIGGER IF NOT EXISTS chunks_ad AFTER DELETE ON chunks BEGIN
    INSERT INTO chunks_fts(chunks_fts, rowid, summary, content)
    VALUES ('delete', old.id, old.summary, old.content);
END;
"""


class Database:
    """Manages a SQLite database with FTS5 full-text search."""

    def __init__(self, db_path: Path) -> None:
        self._db_path = db_path
        # Ensure parent directory exists
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(db_path))
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA busy_timeout=5000")
        self._conn.commit()

    def create_schema(self) -> None:
        self._conn.executescript(_CREATE_SCHEMA)
        self._conn.commit()

    def import_pack(
        self,
        pack: Pack,
        pages: list[Page],
        chunks: list[Chunk],
    ) -> None:
        from tank.errors import ImportError_

        cursor = self._conn.cursor()
        cursor.execute(
            "SELECT COUNT(*) FROM packages WHERE name = ? AND version = ?",
            (pack.name, pack.version),
        )
        if cursor.fetchone()[0] > 0:
            raise ImportError_(f"Pack {pack.name}@{pack.version} is already imported")

        cursor.execute("BEGIN")
        try:
            cursor.execute(
                "INSERT INTO packages (name, version, lifecycle_state, doc_version_status, "
                "indexed_at, policy_profile, pack_digest, normalized_content_hash, "
                "source_url, source_commit, owner) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    pack.name,
                    pack.version,
                    pack.lifecycle_state,
                    pack.doc_version_status,
                    pack.indexed_at,
                    pack.policy_profile,
                    pack.pack_digest,
                    pack.normalized_content_hash,
                    pack.source_url,
                    pack.source_commit,
                    pack.owner,
                ),
            )

            for page in pages:
                cursor.execute(
                    "INSERT INTO pages (package, version, url, content_hash) "
                    "VALUES (?, ?, ?, ?)",
                    (page.package, page.version, page.url, page.content_hash),
                )

            for chunk in chunks:
                cursor.execute(
                    "INSERT INTO chunks (package, version, page_id, heading_path, "
                    "summary, content, token_count, source_url, source_commit, content_hash) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        chunk.package,
                        chunk.version,
                        chunk.page_id,
                        chunk.heading_path,
                        chunk.summary,
                        chunk.content,
                        chunk.token_count,
                        chunk.source_url,
                        chunk.source_commit,
                        chunk.content_hash,
                    ),
                )

            self._conn.commit()
        except Exception:
            self._conn.rollback()
            raise

    def get_packages(self) -> list[Pack]:
        rows = self._conn.execute(
            "SELECT name, version, lifecycle_state, doc_version_status, "
            "indexed_at, policy_profile, pack_digest, normalized_content_hash, "
            "source_url, source_commit, owner FROM packages ORDER BY name, version"
        ).fetchall()
        return [
            Pack(
                name=r["name"],
                version=r["version"],
                lifecycle_state=r["lifecycle_state"],
                doc_version_status=r["doc_version_status"],
                indexed_at=r["indexed_at"],
                policy_profile=r["policy_profile"],
                pack_digest=r["pack_digest"],
                normalized_content_hash=r["normalized_content_hash"],
                source_url=r["source_url"],
                source_commit=r["source_commit"],
                owner=r["owner"],
            )
            for r in rows
        ]

    def get_pack(self, name: str, version: str) -> Pack | None:
        row = self._conn.execute(
            "SELECT name, version, lifecycle_state, doc_version_status, "
            "indexed_at, policy_profile, pack_digest, normalized_content_hash, "
            "source_url, source_commit, owner FROM packages "
            "WHERE name = ? AND version = ?",
            (name, version),
        ).fetchone()
        if row is None:
            return None
        return Pack(
            name=row["name"],
            version=row["version"],
            lifecycle_state=row["lifecycle_state"],
            doc_version_status=row["doc_version_status"],
            indexed_at=row["indexed_at"],
            policy_profile=row["policy_profile"],
            pack_digest=row["pack_digest"],
            normalized_content_hash=row["normalized_content_hash"],
            source_url=row["source_url"],
            source_commit=row["source_commit"],
            owner=row["owner"],
        )

    def pack_exists(self, name: str, version: str) -> bool:
        row = self._conn.execute(
            "SELECT COUNT(*) FROM packages WHERE name = ? AND version = ?",
            (name, version),
        ).fetchone()
        return int(row[0]) > 0

    def delete_pack(self, name: str, version: str) -> None:
        self._conn.execute(
            "DELETE FROM chunks WHERE package = ? AND version = ?",
            (name, version),
        )
        self._conn.execute(
            "DELETE FROM pages WHERE package = ? AND version = ?",
            (name, version),
        )
        self._conn.execute(
            "DELETE FROM packages WHERE name = ? AND version = ?",
            (name, version),
        )
        self._conn.commit()

    def close(self) -> None:
        self._conn.close()

    @property
    def conn(self) -> sqlite3.Connection:
        """Expose the underlying connection for advanced queries."""
        return self._conn
