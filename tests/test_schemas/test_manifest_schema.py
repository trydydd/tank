"""Tests for JSON Schema validation of manifest.json (v2)."""

from __future__ import annotations

import pytest

from tank.errors import SchemaValidationError
from tank.schemas import validate_manifest


def _valid_manifest() -> dict[str, object]:
    return {
        "schema_version": 2,
        "pack_format": "tank-text-v1",
        "package": "test-lib",
        "version": "1.0.0",
        "pack_digest": "sha256:" + "a" * 64,
        "normalized_content_hash": "sha256:" + "b" * 64,
        "chunks": 10,
        "pages": 3,
        "lifecycle_state": "approved",
        "doc_version_status": "stable",
        "created_at": 1700000000.0,
        "created_by": "tank/0.1.1",
    }


def test_valid_minimal_manifest_passes() -> None:
    """A minimal valid manifest does not raise."""
    validate_manifest(_valid_manifest())


def test_valid_full_manifest_passes() -> None:
    """A manifest with all optional fields does not raise."""
    manifest = _valid_manifest()
    manifest["owner"] = "team-docs"
    manifest["policy_profile"] = "strict"
    manifest["source_url"] = "docs/api.md"
    manifest["source_commit"] = "abc123"
    validate_manifest(manifest)


@pytest.mark.parametrize(
    "field",
    [
        "schema_version",
        "pack_format",
        "package",
        "version",
        "pack_digest",
        "normalized_content_hash",
        "chunks",
        "pages",
        "lifecycle_state",
        "doc_version_status",
        "created_at",
        "created_by",
    ],
)
def test_missing_required_field_raises(field: str) -> None:
    """Removing any required field raises SchemaValidationError."""
    manifest = _valid_manifest()
    del manifest[field]
    with pytest.raises(SchemaValidationError):
        validate_manifest(manifest)


def test_wrong_type_chunks_as_string() -> None:
    """chunks as a string raises SchemaValidationError."""
    manifest = _valid_manifest()
    manifest["chunks"] = "not-an-int"
    with pytest.raises(SchemaValidationError):
        validate_manifest(manifest)


def test_wrong_type_schema_version_as_string() -> None:
    """schema_version as a string raises SchemaValidationError."""
    manifest = _valid_manifest()
    manifest["schema_version"] = "2"
    with pytest.raises(SchemaValidationError):
        validate_manifest(manifest)


def test_invalid_lifecycle_state() -> None:
    """lifecycle_state 'active' (not in enum) raises SchemaValidationError."""
    manifest = _valid_manifest()
    manifest["lifecycle_state"] = "active"
    with pytest.raises(SchemaValidationError):
        validate_manifest(manifest)


def test_invalid_doc_version_status() -> None:
    """doc_version_status 'latest' (not in enum) raises SchemaValidationError."""
    manifest = _valid_manifest()
    manifest["doc_version_status"] = "latest"
    with pytest.raises(SchemaValidationError):
        validate_manifest(manifest)


def test_wrong_pack_format() -> None:
    """pack_format 'tank-binary-v1' raises SchemaValidationError."""
    manifest = _valid_manifest()
    manifest["pack_format"] = "tank-binary-v1"
    with pytest.raises(SchemaValidationError):
        validate_manifest(manifest)


def test_wrong_schema_version() -> None:
    """schema_version: 1 raises SchemaValidationError."""
    manifest = _valid_manifest()
    manifest["schema_version"] = 1
    with pytest.raises(SchemaValidationError):
        validate_manifest(manifest)


def test_invalid_pack_digest_pattern() -> None:
    """pack_digest 'notahash' raises SchemaValidationError."""
    manifest = _valid_manifest()
    manifest["pack_digest"] = "notahash"
    with pytest.raises(SchemaValidationError):
        validate_manifest(manifest)


def test_negative_chunk_count() -> None:
    """chunks: -1 raises SchemaValidationError."""
    manifest = _valid_manifest()
    manifest["chunks"] = -1
    with pytest.raises(SchemaValidationError):
        validate_manifest(manifest)


def test_extra_fields_allowed() -> None:
    """Unknown extra fields do not raise (forward compatibility)."""
    manifest = _valid_manifest()
    manifest["future_field"] = "value"
    validate_manifest(manifest)
