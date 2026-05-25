"""JSON Schema validation for Tank pack artifacts."""

from __future__ import annotations

import json
from functools import lru_cache
from importlib.resources import files
from typing import Any, cast

import jsonschema

from tank.errors import SchemaValidationError


@lru_cache(maxsize=None)
def _schema() -> dict[str, Any]:
    text = files("tank.schemas").joinpath("manifest.v2.schema.json").read_text("utf-8")
    return cast(dict[str, Any], json.loads(text))


def validate_manifest(data: dict[str, Any]) -> None:
    """Validate a manifest dict against the v2 JSON Schema.

    Raises SchemaValidationError with a descriptive message on failure.
    No-ops if the manifest is valid.
    """
    try:
        jsonschema.validate(instance=data, schema=_schema())
    except jsonschema.ValidationError as exc:
        raise SchemaValidationError(exc.message) from exc
