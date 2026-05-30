"""Tests for JSON Schema validation of pages.json (v1)."""

from __future__ import annotations

import pytest

from synd.errors import SchemaValidationError
from synd.schemas import validate_pages


def _valid_page() -> dict[str, object]:
    return {
        "id": 1,
        "package": "my-lib",
        "version": "1.0.0",
        "url": "docs/auth/oauth.md",
        "title": "Authentication",
        "content_hash": "sha256:" + "b" * 64,
    }


def test_empty_array_passes() -> None:
    validate_pages([])


def test_valid_pages_pass() -> None:
    validate_pages([_valid_page()])


def test_nullable_optionals_accept_null() -> None:
    page = _valid_page()
    page["title"] = None
    page["content_hash"] = None
    validate_pages([page])


def test_not_an_array_raises() -> None:
    with pytest.raises(SchemaValidationError):
        validate_pages(_valid_page())  # type: ignore[arg-type]


@pytest.mark.parametrize("field", ["id", "package", "version", "url"])
def test_missing_required_field_raises(field: str) -> None:
    page = _valid_page()
    del page[field]
    with pytest.raises(SchemaValidationError):
        validate_pages([page])


def test_package_with_at_sign_raises() -> None:
    page = _valid_page()
    page["package"] = "my@lib"
    with pytest.raises(SchemaValidationError):
        validate_pages([page])


def test_version_with_whitespace_raises() -> None:
    page = _valid_page()
    page["version"] = "1.0 .0"
    with pytest.raises(SchemaValidationError):
        validate_pages([page])


def test_bad_content_hash_raises() -> None:
    page = _valid_page()
    page["content_hash"] = "deadbeef"
    with pytest.raises(SchemaValidationError):
        validate_pages([page])


def test_extra_field_allowed() -> None:
    page = _valid_page()
    page["future_field"] = "value"
    validate_pages([page])
