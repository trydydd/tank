from dataclasses import dataclass


@dataclass
class Pack:
    name: str
    version: str
    lifecycle_state: str
    doc_version_status: str
    indexed_at: str
    policy_profile: str | None = None
    pack_digest: str | None = None
    normalized_content_hash: str | None = None
    source_url: str | None = None
    source_commit: str | None = None
    owner: str | None = None
    pack_source: str | None = None  # path or URL the .ctx file was pulled from


@dataclass
class Page:
    id: int
    package: str
    version: str
    url: str
    title: str | None = None
    content_hash: str | None = None


@dataclass
class Chunk:
    id: int
    package: str
    version: str
    content: str
    page_id: int | None = None
    heading_path: str | None = None
    summary: str | None = None
    token_count: int | None = None
    source_url: str | None = None
    source_commit: str | None = None
    content_hash: str | None = None
