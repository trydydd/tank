"""JSON Schema validation for Synaptic Drift pack artifacts.

The ``*.schema.json`` files in this package are the canonical, language-agnostic
contracts for every artifact that crosses a boundary:

- ``manifest.v2.schema.json``  — the governance/integrity manifest (manifest.json)
- ``chunk.v1.schema.json``     — one chunks.jsonl record
- ``pages.v1.schema.json``     — the pages.json array
- ``tool-response.v1.schema.json`` — the MCP search/fetch response payload

Each ``validate_*`` helper enforces its schema and raises
:class:`~synd.errors.SchemaValidationError` on failure. ``additionalProperties``
is intentionally left open in every schema: unknown fields are permitted so the
format can grow additively without breaking older readers.
"""

from __future__ import annotations

import json
from functools import lru_cache
from importlib.resources import files
from typing import Any, cast

import jsonschema

from synd.errors import SchemaValidationError

_MANIFEST_SCHEMA = "manifest.v2.schema.json"
_CHUNK_SCHEMA = "chunk.v1.schema.json"
_PAGES_SCHEMA = "pages.v1.schema.json"
_TOOL_RESPONSE_SCHEMA = "tool-response.v1.schema.json"


@lru_cache(maxsize=None)
def _load_schema(name: str) -> dict[str, Any]:
    """Load and cache a JSON Schema bundled with this package by file name."""
    text = files("synd.schemas").joinpath(name).read_text("utf-8")
    return cast(dict[str, Any], json.loads(text))


def _validate(data: Any, schema_name: str) -> None:
    """Validate ``data`` against the named schema, raising SchemaValidationError."""
    try:
        jsonschema.validate(instance=data, schema=_load_schema(schema_name))
    except jsonschema.ValidationError as exc:
        raise SchemaValidationError(exc.message) from exc


def validate_manifest(data: dict[str, Any]) -> None:
    """Validate a manifest dict against the v2 JSON Schema.

    Raises SchemaValidationError with a descriptive message on failure.
    No-ops if the manifest is valid.
    """
    _validate(data, _MANIFEST_SCHEMA)


def validate_chunk(record: dict[str, Any]) -> None:
    """Validate a single chunks.jsonl record against the v1 chunk schema.

    Raises SchemaValidationError with a descriptive message on failure.
    """
    _validate(record, _CHUNK_SCHEMA)


def validate_pages(data: list[dict[str, Any]]) -> None:
    """Validate the pages.json array against the v1 pages schema.

    Raises SchemaValidationError with a descriptive message on failure.
    """
    _validate(data, _PAGES_SCHEMA)


def validate_tool_response(data: dict[str, Any]) -> None:
    """Validate an MCP search/fetch response payload against the v1 schema.

    Raises SchemaValidationError with a descriptive message on failure.
    """
    _validate(data, _TOOL_RESPONSE_SCHEMA)


def tool_response_schema() -> dict[str, Any]:
    """Return the MCP tool response JSON Schema (canonical output contract).

    Used to publish the tools' ``outputSchema`` so the validator and the
    advertised contract are guaranteed to be the same document.
    """
    return _load_schema(_TOOL_RESPONSE_SCHEMA)
