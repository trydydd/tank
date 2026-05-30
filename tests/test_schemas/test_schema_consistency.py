"""Drift guard: the Python contracts in ``synd.schemas.types`` must agree with
the canonical JSON Schemas. If a schema enum or required field changes without a
matching change to the TypedDicts/Literals (or vice versa), these tests fail.
"""

from __future__ import annotations

import json
from importlib.resources import files
from typing import Any

from synd.schemas.types import (
    DOC_VERSION_STATUSES,
    LIFECYCLE_STATES,
    ChunkRecord,
    ManifestDict,
    PageRecord,
    ToolResultItem,
)


def _schema(name: str) -> dict[str, Any]:
    return json.loads(files("synd.schemas").joinpath(name).read_text("utf-8"))


def _typeddict_keys(td: type) -> set[str]:
    return set(td.__required_keys__) | set(td.__optional_keys__)


# --- Enum single-source-of-truth ---


def test_manifest_lifecycle_enum_matches_code() -> None:
    schema = _schema("manifest.v2.schema.json")
    assert schema["properties"]["lifecycle_state"]["enum"] == list(LIFECYCLE_STATES)


def test_manifest_doc_version_status_enum_matches_code() -> None:
    schema = _schema("manifest.v2.schema.json")
    assert schema["properties"]["doc_version_status"]["enum"] == list(
        DOC_VERSION_STATUSES
    )


def test_tool_response_lifecycle_enum_matches_code() -> None:
    schema = _schema("tool-response.v1.schema.json")
    item = schema["$defs"]["result_item"]
    assert item["properties"]["lifecycle_state"]["enum"] == list(LIFECYCLE_STATES)


# --- Structural agreement: every schema-required field is a non-optional
#     TypedDict field, and every TypedDict field is a known schema property. ---


def test_manifest_typeddict_matches_schema() -> None:
    schema = _schema("manifest.v2.schema.json")
    props = set(schema["properties"])
    assert set(schema["required"]) <= set(ManifestDict.__required_keys__)
    assert _typeddict_keys(ManifestDict) <= props


def test_chunk_typeddict_matches_schema() -> None:
    schema = _schema("chunk.v1.schema.json")
    props = set(schema["properties"])
    assert set(schema["required"]) <= set(ChunkRecord.__required_keys__)
    assert _typeddict_keys(ChunkRecord) <= props


def test_pages_typeddict_matches_schema() -> None:
    schema = _schema("pages.v1.schema.json")
    item = schema["items"]
    props = set(item["properties"])
    assert set(item["required"]) <= set(PageRecord.__required_keys__)
    assert _typeddict_keys(PageRecord) <= props


def test_tool_result_typeddict_matches_schema() -> None:
    schema = _schema("tool-response.v1.schema.json")
    item = schema["$defs"]["result_item"]
    props = set(item["properties"])
    assert set(item["required"]) <= set(ToolResultItem.__required_keys__)
    assert _typeddict_keys(ToolResultItem) <= props
