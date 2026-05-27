from datetime import datetime, timezone

from synd.storage.models import Chunk, Page, Pack


def test_pack_creation() -> None:
    now = datetime.now(timezone.utc).isoformat()
    pack = Pack(
        name="my-lib",
        version="1.0.0",
        lifecycle_state="approved",
        doc_version_status="stable",
        indexed_at=now,
    )
    assert pack.name == "my-lib"
    assert pack.version == "1.0.0"
    assert pack.lifecycle_state == "approved"
    assert pack.doc_version_status == "stable"
    assert pack.indexed_at == now
    assert pack.policy_profile is None
    assert pack.pack_digest is None


def test_chunk_creation() -> None:
    chunk = Chunk(id=1, package="my-lib", version="1.0.0", content="hello")
    assert chunk.id == 1
    assert chunk.page_id is None
    assert chunk.heading_path is None
    assert chunk.summary is None


def test_page_creation() -> None:
    page = Page(id=1, package="my-lib", version="1.0.0", url="docs/readme.md")
    assert page.id == 1
    assert page.title is None
    assert page.content_hash is None


def test_pack_required_fields() -> None:
    """All required fields must be passed; omitted optional fields default to None."""
    now = "2026-05-17T00:00:00Z"
    pack = Pack(
        name="lib",
        version="0.1.0",
        lifecycle_state="draft",
        doc_version_status="unknown",
        indexed_at=now,
    )
    assert pack.policy_profile is None
    assert pack.pack_digest is None
    assert pack.normalized_content_hash is None
    assert pack.source_url is None
    assert pack.source_commit is None
    assert pack.owner is None
