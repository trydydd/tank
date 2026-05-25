"""JSON Schema validation for Tank pack artifacts."""

from __future__ import annotations

import json
from importlib.resources import files
from typing import Any

import jsonschema

from tank.errors import SchemaValidationError

_MANIFEST_V2: dict[str, Any] | None = None


def _schema() -> dict[str, Any]:
    global _MANIFEST_V2
    if _MANIFEST_V2 is None:
        text = (
            files("tank.schemas").joinpath("manifest.v2.schema.json").read_text("utf-8")
        )
        _MANIFEST_V2 = json.loads(text)
    return _MANIFEST_V2


def validate_manifest(data: dict[str, Any]) -> None:
    """Validate a manifest dict against the v2 JSON Schema.

    Raises SchemaValidationError with a descriptive message on failure.
    No-ops if the manifest is valid.
    """
    try:
        jsonschema.validate(instance=data, schema=_schema())
    except jsonschema.ValidationError as exc:
        raise SchemaValidationError(exc.message) from exc
