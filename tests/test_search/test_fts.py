from pathlib import Path
import tempfile

from tank.search.fts import search, get_chunks_by_id
from tank.storage.db import Database
from tank.storage.models import Chunk, Page, Pack


def _make_db() -> Database:
    with tempfile.TemporaryDirectory() as tmp:
        db_path = Path(tmp) / "test.db"
        db = Database(db_path)
        db.create_schema()
        return db


def _import_pack(db: Database, pack: Pack, pages: list[Page], chunks: list[Chunk]) -> None:
    db.import_pack(pack, pages, chunks)


def test_search_returns_ranked_results() -> None:
    db = _make_db()
    pack = Pack(
        name="docs", version="1.0.0",
        lifecycle_state="approved", doc_version_status="stable",
        indexed_at="2026-01-01T00:00:00Z",
    )
    pages = [Page(id=1, package="docs", version="1.0.0", url="index.md")]
    chunks = [
        Chunk(id=1, package="docs", version="1.0.0", page_id=1,
              heading_path="Introduction", summary="Welcome to docs",
              content="Welcome to the documentation",
              source_url="index.md"),
    ]
    _import_pack(db, pack, pages, chunks)

    results = search(db, "Welcome")
    assert len(results) == 1
    assert results[0].heading_path == "Introduction"
    assert results[0].score > 0


def test_search_excludes_revoked() -> None:
    db = _make_db()
    pack_approved = Pack(
        name="docs", version="1.0.0",
        lifecycle_state="approved", doc_version_status="stable",
        indexed_at="2026-01-01T00:00:00Z",
    )
    pack_revoked = Pack(
        name="other", version="1.0.0",
        lifecycle_state="revoked", doc_version_status="stable",
        indexed_at="2026-01-01T00:00:00Z",
    )
    approved_pages = [Page(id=1, package="docs", version="1.0.0", url="index.md")]
    approved_chunks = [
        Chunk(id=1, package="docs", version="1.0.0", page_id=1,
              heading_path="Intro", summary="Welcome",
              content="Welcome to docs",
              source_url="index.md"),
    ]
    revoked_pages = [Page(id=2, package="other", version="1.0.0", url="index.md")]
    revoked_chunks = [
        Chunk(id=2, package="other", version="1.0.0", page_id=2,
              heading_path="Intro", summary="Other intro",
              content="This is the other package",
              source_url="index.md"),
    ]
    _import_pack(db, pack_approved, approved_pages, approved_chunks)
    _import_pack(db, pack_revoked, revoked_pages, revoked_chunks)

    results = search(db, "Welcome")
    assert len(results) == 1
    assert results[0].package == "docs"

    results_other = search(db, "other")
    assert len(results_other) == 0


def test_search_filters_by_package() -> None:
    db = _make_db()
    pack_a = Pack(
        name="alpha", version="1.0.0",
        lifecycle_state="approved", doc_version_status="stable",
        indexed_at="2026-01-01T00:00:00Z",
    )
    pack_b = Pack(
        name="beta", version="1.0.0",
        lifecycle_state="approved", doc_version_status="stable",
        indexed_at="2026-01-01T00:00:00Z",
    )
    pages_a = [Page(id=1, package="alpha", version="1.0.0", url="a.md")]
    chunks_a = [
        Chunk(id=1, package="alpha", version="1.0.0", page_id=1,
              heading_path="X", summary="Alpha content",
              content="Alpha package content here",
              source_url="a.md"),
    ]
    pages_b = [Page(id=2, package="beta", version="1.0.0", url="b.md")]
    chunks_b = [
        Chunk(id=2, package="beta", version="1.0.0", page_id=2,
              heading_path="Y", summary="Beta content",
              content="Beta package content here",
              source_url="b.md"),
    ]
    _import_pack(db, pack_a, pages_a, chunks_a)
    _import_pack(db, pack_b, pages_b, chunks_b)

    results = search(db, "content", packages=["beta"])
    assert len(results) == 1
    assert results[0].package == "beta"

    results_all = search(db, "content")
    assert len(results_all) == 2


def test_search_summary_mode_excludes_content() -> None:
    db = _make_db()
    pack = Pack(
        name="docs", version="1.0.0",
        lifecycle_state="approved", doc_version_status="stable",
        indexed_at="2026-01-01T00:00:00Z",
    )
    pages = [Page(id=1, package="docs", version="1.0.0", url="index.md")]
    chunks = [
        Chunk(id=1, package="docs", version="1.0.0", page_id=1,
              heading_path="Intro", summary="Welcome",
              content="Some long content text",
              source_url="index.md"),
    ]
    _import_pack(db, pack, pages, chunks)

    results = search(db, "Welcome", detail="summary")
    assert len(results) == 1
    assert results[0].content is None


def test_search_full_mode_includes_content() -> None:
    db = _make_db()
    pack = Pack(
        name="docs", version="1.0.0",
        lifecycle_state="approved", doc_version_status="stable",
        indexed_at="2026-01-01T00:00:00Z",
    )
    pages = [Page(id=1, package="docs", version="1.0.0", url="index.md")]
    chunks = [
        Chunk(id=1, package="docs", version="1.0.0", page_id=1,
              heading_path="Intro", summary="Welcome",
              content="Some long content text",
              source_url="index.md"),
    ]
    _import_pack(db, pack, pages, chunks)

    results = search(db, "Welcome", detail="full")
    assert len(results) == 1
    assert results[0].content == "Some long content text"


def test_search_deprecated_has_warning() -> None:
    db = _make_db()
    pack = Pack(
        name="docs", version="1.0.0",
        lifecycle_state="deprecated", doc_version_status="stable",
        indexed_at="2026-01-01T00:00:00Z",
    )
    pages = [Page(id=1, package="docs", version="1.0.0", url="index.md")]
    chunks = [
        Chunk(id=1, package="docs", version="1.0.0", page_id=1,
              heading_path="Intro", summary="Deprecated docs",
              content="This documentation is deprecated",
              source_url="index.md"),
    ]
    _import_pack(db, pack, pages, chunks)

    results = search(db, "deprecated")
    assert len(results) == 1
    assert results[0].lifecycle_state == "deprecated"
    assert results[0].lifecycle_warning is not None
    assert "deprecated" in results[0].lifecycle_warning.lower()


def test_get_chunks_by_id() -> None:
    db = _make_db()
    pack = Pack(
        name="docs", version="1.0.0",
        lifecycle_state="approved", doc_version_status="stable",
        indexed_at="2026-01-01T00:00:00Z",
    )
    pages = [Page(id=1, package="docs", version="1.0.0", url="index.md")]
    chunks = [
        Chunk(id=1, package="docs", version="1.0.0", page_id=1,
              heading_path="A", summary="First",
              content="Content A",
              source_url="a.md"),
        Chunk(id=2, package="docs", version="1.0.0", page_id=1,
              heading_path="B", summary="Second",
              content="Content B",
              source_url="b.md"),
    ]
    _import_pack(db, pack, pages, chunks)

    results = get_chunks_by_id(db, [1, 2])
    assert len(results) == 2
    assert results[0].chunk_id == 1
    assert results[0].content == "Content A"
    assert results[1].chunk_id == 2
    assert results[1].content == "Content B"


def test_search_empty_index() -> None:
    db = _make_db()
    results = search(db, "anything")
    assert results == []


def test_search_no_match() -> None:
    db = _make_db()
    pack = Pack(
        name="docs", version="1.0.0",
        lifecycle_state="approved", doc_version_status="stable",
        indexed_at="2026-01-01T00:00:00Z",
    )
    pages = [Page(id=1, package="docs", version="1.0.0", url="index.md")]
    chunks = [
        Chunk(id=1, package="docs", version="1.0.0", page_id=1,
              heading_path="Intro", summary="Welcome",
              content="Welcome to docs",
              source_url="index.md"),
    ]
    _import_pack(db, pack, pages, chunks)

    results = search(db, "zzzznonexistent")
    assert results == []


def test_search_best_match_first() -> None:
    db = _make_db()
    pack = Pack(
        name="docs", version="1.0.0",
        lifecycle_state="approved", doc_version_status="stable",
        indexed_at="2026-01-01T00:00:00Z",
    )
    pages = [Page(id=1, package="docs", version="1.0.0", url="index.md")]
    chunks = [
        Chunk(id=1, package="docs", version="1.0.0", page_id=1,
              heading_path="Python Guide", summary="Python programming",
              content="Python is great. Python tutorials. Python examples. Python best practices. Python syntax. Python functions. Python classes.",
              source_url="index.md"),
        Chunk(id=2, package="docs", version="1.0.0", page_id=1,
              heading_path="Languages", summary="Overview",
              content="We support Java Go Rust Ruby and Python among others.",
              source_url="index.md"),
    ]
    _import_pack(db, pack, pages, chunks)

    results = search(db, "python")
    assert len(results) == 2
    assert results[0].chunk_id == 1
