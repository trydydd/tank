"""Tests for JSON Schema validation of chunks.jsonl records (v1)."""

from __future__ import annotations

import pytest

from synd.errors import SchemaValidationError
from synd.schemas import validate_chunk


def _valid_chunk() -> dict[str, object]:
    return {
        "id": 1,
        "page_id": 1,
        "heading_path": "docs/auth / OAuth2",
        "content": "To configure OAuth2 ...",
        "content_hash": "sha256:" + "a" * 64,
        "summary": "Configure OAuth2",
        "token_count": 42,
        "source_url": "docs/auth/oauth.md",
    }


def test_valid_minimal_chunk_passes() -> None:
    """Only the required fields, with optionals omitted, validates."""
    validate_chunk(
        {
            "id": 1,
            "page_id": 1,
            "heading_path": "h",
            "content": "c",
            "content_hash": "sha256:" + "f" * 64,
        }
    )


def test_valid_full_chunk_passes() -> None:
    chunk = _valid_chunk()
    chunk["source_commit"] = "abc123"
    validate_chunk(chunk)


def test_nullable_optionals_accept_null() -> None:
    chunk = _valid_chunk()
    chunk["summary"] = None
    chunk["token_count"] = None
    chunk["source_url"] = None
    validate_chunk(chunk)


@pytest.mark.parametrize(
    "field",
    ["id", "page_id", "heading_path", "content", "content_hash"],
)
def test_missing_required_field_raises(field: str) -> None:
    chunk = _valid_chunk()
    del chunk[field]
    with pytest.raises(SchemaValidationError):
        validate_chunk(chunk)


def test_zero_id_raises() -> None:
    """Chunk ids are 1-based; 0 must fail."""
    chunk = _valid_chunk()
    chunk["id"] = 0
    with pytest.raises(SchemaValidationError):
        validate_chunk(chunk)


def test_id_as_string_raises() -> None:
    chunk = _valid_chunk()
    chunk["id"] = "1"
    with pytest.raises(SchemaValidationError):
        validate_chunk(chunk)


def test_negative_token_count_raises() -> None:
    chunk = _valid_chunk()
    chunk["token_count"] = -1
    with pytest.raises(SchemaValidationError):
        validate_chunk(chunk)


def test_bad_content_hash_pattern_raises() -> None:
    chunk = _valid_chunk()
    chunk["content_hash"] = "notahash"
    with pytest.raises(SchemaValidationError):
        validate_chunk(chunk)


def test_uppercase_content_hash_raises() -> None:
    chunk = _valid_chunk()
    chunk["content_hash"] = "sha256:" + "A" * 64
    with pytest.raises(SchemaValidationError):
        validate_chunk(chunk)


def test_extra_field_allowed() -> None:
    """Unknown fields are permitted (additive forward-compat)."""
    chunk = _valid_chunk()
    chunk["future_field"] = "value"
    validate_chunk(chunk)
