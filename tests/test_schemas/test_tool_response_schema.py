"""Tests for JSON Schema validation of the MCP tool response (v1)."""

from __future__ import annotations

import pytest

from synd.errors import SchemaValidationError
from synd.schemas import validate_tool_response


def _valid_item() -> dict[str, object]:
    return {
        "chunk_id": 1,
        "package": "my-lib",
        "version": "1.0.0",
        "lifecycle_state": "approved",
        "doc_version_status": "stable",
        "heading_path": "docs / Section",
        "summary": "A summary",
        "content": None,
        "source_url": "docs/x.md",
        "source_commit": None,
        "content_hash": "sha256:" + "c" * 64,
        "indexed_at": "2026-01-01T00:00:00Z",
        "score": 1.5,
    }


def test_empty_results_envelope_passes() -> None:
    validate_tool_response({"results": []})


def test_results_with_item_passes() -> None:
    validate_tool_response({"results": [_valid_item()]})


def test_item_with_lifecycle_warning_passes() -> None:
    item = _valid_item()
    item["lifecycle_state"] = "deprecated"
    item["lifecycle_warning"] = "This pack is deprecated"
    validate_tool_response({"results": [item]})


def test_not_indexed_status_passes() -> None:
    validate_tool_response({"status": "not_indexed"})


def test_both_results_and_status_raises() -> None:
    """oneOf: a payload matching both branches is invalid."""
    with pytest.raises(SchemaValidationError):
        validate_tool_response({"results": [], "status": "not_indexed"})


def test_neither_branch_raises() -> None:
    with pytest.raises(SchemaValidationError):
        validate_tool_response({"foo": "bar"})


def test_wrong_status_value_raises() -> None:
    with pytest.raises(SchemaValidationError):
        validate_tool_response({"status": "indexed"})


@pytest.mark.parametrize(
    "field",
    [
        "chunk_id",
        "package",
        "version",
        "lifecycle_state",
        "doc_version_status",
        "heading_path",
        "summary",
        "content",
        "source_url",
        "source_commit",
        "content_hash",
        "indexed_at",
        "score",
    ],
)
def test_item_missing_required_field_raises(field: str) -> None:
    item = _valid_item()
    del item[field]
    with pytest.raises(SchemaValidationError):
        validate_tool_response({"results": [item]})


def test_invalid_lifecycle_state_raises() -> None:
    item = _valid_item()
    item["lifecycle_state"] = "active"
    with pytest.raises(SchemaValidationError):
        validate_tool_response({"results": [item]})


def test_null_content_allowed() -> None:
    """search returns summary-only items with content == null."""
    item = _valid_item()
    item["content"] = None
    validate_tool_response({"results": [item]})
