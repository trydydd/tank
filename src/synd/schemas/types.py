"""Typed, in-code contracts for Synaptic Drift artifacts.

The JSON Schemas in this package are the canonical source of truth. These
``TypedDict`` shapes and ``Literal`` aliases mirror them for static checking at
call sites (``mypy --strict``). The drift-guard test in
``tests/test_schemas/test_schema_consistency.py`` fails if these declarations and
the schemas diverge, so the two never silently disagree.

Enum values live here once and are referenced everywhere (policy, search,
build), rather than being re-typed as bare strings throughout the codebase.
"""

from __future__ import annotations

from typing import Literal, NotRequired, TypedDict

# --- Single-source enumerations (must equal the manifest schema enums) ---

LifecycleState = Literal["draft", "approved", "deprecated", "revoked"]
DocVersionStatus = Literal["stable", "prerelease", "archived", "unknown"]

LIFECYCLE_STATES: tuple[LifecycleState, ...] = (
    "draft",
    "approved",
    "deprecated",
    "revoked",
)
DOC_VERSION_STATUSES: tuple[DocVersionStatus, ...] = (
    "stable",
    "prerelease",
    "archived",
    "unknown",
)


class ManifestDict(TypedDict):
    """Shape of manifest.json (schema version 2).

    Enum *values* for ``lifecycle_state``/``doc_version_status`` are enforced by
    the JSON Schema, not the Python type — the manifest is assembled from
    arbitrary CLI input and only validated at the boundary.
    """

    schema_version: int
    pack_format: str
    package: str
    version: str
    pack_digest: str
    normalized_content_hash: str
    chunks: int
    pages: int
    lifecycle_state: str
    doc_version_status: str
    created_at: float
    created_by: str
    owner: NotRequired[str]
    policy_profile: NotRequired[str]
    source_url: NotRequired[str]
    source_commit: NotRequired[str]
    reviewers: NotRequired[list[str]]
    approval_ref: NotRequired[str]
    source_tag: NotRequired[str]


class ChunkRecord(TypedDict):
    """Shape of one chunks.jsonl record (schema version 1)."""

    id: int
    page_id: int
    heading_path: str
    content: str
    content_hash: str
    summary: str | None
    token_count: int | None
    source_url: str | None
    source_commit: NotRequired[str]


class PageRecord(TypedDict):
    """Shape of one pages.json entry (schema version 1)."""

    id: int
    package: str
    version: str
    url: str
    title: str | None
    content_hash: str | None


class ToolResultItem(TypedDict):
    """One result entry in an MCP search/fetch response (schema version 1)."""

    chunk_id: int
    package: str
    version: str
    lifecycle_state: str
    doc_version_status: str | None
    heading_path: str | None
    summary: str | None
    content: str | None
    source_url: str | None
    source_commit: str | None
    content_hash: str | None
    indexed_at: str
    score: float
    lifecycle_warning: NotRequired[str]


class ToolResultsResponse(TypedDict):
    """Results envelope returned by search/fetch."""

    results: list[ToolResultItem]


class ToolNotIndexedResponse(TypedDict):
    """Signal returned when a requested package is not in the local index."""

    status: Literal["not_indexed"]


ToolResponse = ToolResultsResponse | ToolNotIndexedResponse
