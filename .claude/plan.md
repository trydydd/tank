# Plan: `feature/schemas` — Machine-readable manifest schema + verifier wiring

**Branch:** `feature/schemas` (based on `origin/develop`)  
**Roadmap item:** v0.2.0 Foundation — `schemas/manifest.v2.schema.json`  
**Goal:** Replace manual field-presence checking in `verify.py` step 2 with JSON Schema validation; establish the schema as the single source of truth for the manifest contract before PyPI release.

---

## Context

`verify.py` step 2 (lines 94–105) currently only checks whether required field *names* are present. It does not validate types, enum values, or numeric constraints. A manifest with `lifecycle_state: 12345` or `chunks: "foo"` would pass step 2 today. The JSON Schema becomes the machine-readable contract that catches all of this.

The `jsonschema` library is not yet a dependency. Schemas live inside the package (`src/tank/schemas/`) so they are bundled and importable with `importlib.resources` in both editable installs and wheels.

---

## Execution order (strict TDD — red → green → refactor)

### Step 1 — Add `jsonschema` dependency + package-data config
**File:** `pyproject.toml`  
- Add `"jsonschema>=4.0"` to `[project] dependencies`.  
- Add `[tool.setuptools.package-data]` section: `"tank.schemas" = ["*.json"]` so the schema files are included in the wheel.

### Step 2 — Add `SchemaValidationError` to error hierarchy
**File:** `src/tank/errors.py`  
- Add `class SchemaValidationError(ManifestError)` below the existing `ManifestError`.  
- `ManifestError` already exists as the right parent — no new base needed.

### Step 3 — Write failing tests (RED)
**New files:**
- `tests/test_schemas/__init__.py` (empty)  
- `tests/test_schemas/test_manifest_schema.py`

Tests to write (all should fail before implementation):
1. `test_valid_minimal_manifest_passes` — all required fields with correct types/values
2. `test_valid_full_manifest_passes` — required + all optional fields
3. `test_missing_required_field_raises` — parametrize over each of the 12 required fields
4. `test_wrong_type_integer_field` — `chunks: "not-an-int"` raises
5. `test_wrong_type_string_field` — `schema_version: "2"` (string, not int) raises
6. `test_invalid_lifecycle_state` — enum rejection (`lifecycle_state: "active"`)
7. `test_invalid_doc_version_status` — enum rejection (`doc_version_status: "latest"`)
8. `test_wrong_pack_format` — `pack_format: "tank-binary-v1"` raises
9. `test_wrong_schema_version` — `schema_version: 1` raises
10. `test_invalid_pack_digest_pattern` — digest not starting with `sha256:` raises
11. `test_invalid_nch_pattern` — same for `normalized_content_hash`
12. `test_negative_chunk_count` — `chunks: -1` raises
13. `test_extra_fields_allowed` — unknown fields do NOT raise (forward-compatible)

Update `tests/test_validator/test_verify.py`:
- Add `test_step2_rejects_wrong_type` — pack with `chunks: "bad"` fails at step 2
- Add `test_step2_rejects_bad_lifecycle_enum` — `lifecycle_state: "active"` fails at step 2  
  (These currently fail or behave wrong; confirm they become correct after wiring.)

### Step 4 — Create the JSON Schema (GREEN enabler)
**New file:** `src/tank/schemas/manifest.v2.schema.json`

```
$schema:       https://json-schema.org/draft/2020-12/schema
$id:           https://tank.dev/schemas/manifest.v2.schema.json
title:         Tank manifest.json (schema version 2)
type:          object
additionalProperties: true   ← forward-compatible; future fields not rejected
```

**Required fields** (12):

| Field | Type | Constraint |
|---|---|---|
| `schema_version` | integer | `const: 2` |
| `pack_format` | string | `const: "tank-text-v1"` |
| `package` | string | `minLength: 1` |
| `version` | string | `minLength: 1` |
| `pack_digest` | string | pattern `^sha256:[a-f0-9]{64}$` |
| `normalized_content_hash` | string | pattern `^sha256:[a-f0-9]{64}$` |
| `chunks` | integer | `minimum: 0` |
| `pages` | integer | `minimum: 0` |
| `lifecycle_state` | string | enum `["draft","approved","deprecated","revoked"]` |
| `doc_version_status` | string | enum `["stable","prerelease","archived","unknown"]` |
| `created_at` | number | `minimum: 0` (Unix epoch) |
| `created_by` | string | `minLength: 1` |

**Optional fields** (defined but not required; enables IDE autocomplete and docs):

| Field | Type | Notes |
|---|---|---|
| `owner` | string | team/person responsible |
| `policy_profile` | string | policy profile name |
| `source_url` | string | path or URL |
| `source_commit` | string | git SHA |
| `reviewers` | array of strings | deferred feature |
| `approval_ref` | string | deferred feature |
| `source_tag` | string | deferred feature |

### Step 5 — Implement `src/tank/schemas/__init__.py`
**New file:** `src/tank/schemas/__init__.py`

```python
"""JSON Schema validation for Tank pack artifacts."""

import json
from importlib.resources import files
from typing import Any

import jsonschema

from tank.errors import SchemaValidationError

_MANIFEST_V2_SCHEMA: dict[str, Any] | None = None


def _load_manifest_v2_schema() -> dict[str, Any]:
    global _MANIFEST_V2_SCHEMA
    if _MANIFEST_V2_SCHEMA is None:
        data = files("tank.schemas").joinpath("manifest.v2.schema.json").read_text()
        _MANIFEST_V2_SCHEMA = json.loads(data)
    return _MANIFEST_V2_SCHEMA


def validate_manifest(data: dict[str, Any]) -> None:
    """Validate a manifest dict against the v2 JSON Schema.

    Raises SchemaValidationError with a descriptive message on failure.
    Passes silently if the manifest is valid.
    """
    schema = _load_manifest_v2_schema()
    try:
        jsonschema.validate(instance=data, schema=schema)
    except jsonschema.ValidationError as exc:
        raise SchemaValidationError(exc.message) from exc
```

Design notes:
- Module-level cache avoids re-parsing the JSON on every call.
- `importlib.resources.files()` works in editable installs, wheels, and zipimport.
- `jsonschema.validate()` raises on the first error (fastest path for the verifier).

### Step 6 — Wire `verify.py` step 2
**File:** `src/tank/validator/verify.py`

Replace the current step 2 block (lines ~94–108):
```python
# BEFORE
missing: list[str] = []
for field in _REQUIRED_MANIFEST_FIELDS:
    if field not in manifest:
        missing.append(field)
if missing:
    return VerifyResult(...)
```

With:
```python
# AFTER
from tank.schemas import validate_manifest
from tank.errors import SchemaValidationError

try:
    validate_manifest(manifest)
except SchemaValidationError as exc:
    return VerifyResult(
        passed=False,
        step=2,
        reason=f"Invalid manifest: {exc}",
        manifest=None,
    )
```

Remove the now-unused `_REQUIRED_MANIFEST_FIELDS` constant.

### Step 7 — Run full CI checks (GREEN confirmation)
```
.venv/bin/pytest tests/ -x -q
.venv/bin/ruff check src/ tests/
.venv/bin/ruff format --check src/ tests/
.venv/bin/mypy src/
```

All 206+ tests should pass. Fix any type errors from the new code.

---

## Files touched

| File | Action |
|---|---|
| `pyproject.toml` | modify — add `jsonschema>=4.0` dep + package-data |
| `src/tank/errors.py` | modify — add `SchemaValidationError` |
| `src/tank/schemas/__init__.py` | **create** |
| `src/tank/schemas/manifest.v2.schema.json` | **create** |
| `src/tank/validator/verify.py` | modify — replace step 2 |
| `tests/test_schemas/__init__.py` | **create** |
| `tests/test_schemas/test_manifest_schema.py` | **create** |
| `tests/test_validator/test_verify.py` | modify — add 2 new cases |

---

## Out of scope for this branch

- `schemas/chunks.v1.schema.json` and `schemas/pages.v1.schema.json` — not in the roadmap; deferred.
- SQLite migration system (`PRAGMA user_version`) — separate item.
- Cross-platform path handling in the verifier — separate roadmap item.
