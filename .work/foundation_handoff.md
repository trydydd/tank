# Foundation Work Handoff — feature/schemas

**Session date**: 2026-05-25  
**Branch**: `feature/schemas` (based on `origin/develop`)  
**Tests**: 251 passed, 3 skipped. ruff + mypy clean.

---

## What was completed

All four original Foundation roadmap items are done. The branch also extended the lockfile significantly beyond the original spec.

### Commits (oldest → newest)

| Commit | Summary |
|---|---|
| `28bdaf9` | docs: lockfile-in-git — initial .gitignore exception + team setup docs |
| `05a5d12` | fix: error message polish — BuildError, ImportError_, SearchError, verify step 1 |
| `3ae0d79` | feat(schemas): manifest.v2.schema.json + SchemaValidationError + wire verify step 2 |
| `ce8f586` | fix(paths): normalize to forward slashes in builder; strengthen verifier step 4 |
| `4a5d15f` | fix: code-review findings — gitignore B1, docs B2, flaky test B3, dead code, narrow catch, schema tests |
| `d5fd628` | feat(lockfile): add source_url to lockfile (schema v2) + tank sync roadmap item |
| `a37bc18` | docs: mark mcp@2025-11-25 pack complete in v0.1.1 roadmap |
| `fd37860` | feat: add tank.lock with v0.1.1 release packs |
| `b2118b1` | refactor(lockfile): consolidate to tank.lock at project root |
| `ed7c3f9` | fix(lockfile): pack_source field + ISO indexed_at + correct source_url in lockfile |
| *(this commit)* | docs: decisions D16-D18 + foundation handoff |

### Substantive changes

**Schemas** (`src/tank/schemas/`)
- `manifest.v2.schema.json` — JSON Schema (draft/2020-12) for all 12 required manifest fields with types, enums, patterns. `additionalProperties` not restricted (forward-compat).
- `__init__.py` — `validate_manifest()` using `importlib.resources` + `@lru_cache`. Raises `SchemaValidationError(ManifestError)`.
- `verify.py` step 2 now calls `validate_manifest()`. `_REQUIRED_MANIFEST_FIELDS` removed.
- `jsonschema>=4.0` added to `pyproject.toml` dependencies.

**Cross-platform paths** (`src/tank/builder/`)
- `build.py`: `Path(source).as_posix()` for manifest `source_url`; `Path(relpath(...)).as_posix()` for per-file `source_url`.
- `chunking.py`: `discover_files` sort key uses `.as_posix()` (deterministic across platforms); `chunk_file` stores posix `source_url`. Dead `startswith("./")` branch removed.
- `verify.py` step 4: rejects Windows drive letters (`C:/`) and UNC paths (`//`) after backslash normalisation.

**Lockfile** (major rework)
- Location: `tank.lock` at project root (was `.tank/index.lock`). See D16.
- Schema v2: adds `source_url` per pack (the `.ctx` fetch location, not the docs source).
- `pull.py`: `indexed_at` is now import timestamp (ISO 8601), not build timestamp float.
- `pack_source` column added to `packages` table (soft ALTER migration in `create_schema`). See D17.
- `tank.lock` committed with both v0.1.1 release packs pointing at GitHub Release URLs.

**Error polish**
- `cli/build.py`: `ValueError` → `BuildError` in `_parse_package_spec`.
- `storage/db.py`: `RuntimeError` → `ImportError_` for null `lastrowid`.
- `cli/pull.py`: bare `except Exception: pass` removed; catch broadened to `BadZipFile | JSONDecodeError | OSError`.
- `search/fts.py`: `SearchError` message includes operation context.
- `verify.py` step 1: three error messages made more specific.

---

## One open question: rename `tank pull`

`tank pull` is a misnomer — it accepts only local file paths (`click.Path(exists=True)`), never fetches from a remote. The name implies remote fetch, which is what `tank sync` will do.

**Candidates**: `tank import`, `tank load`, `tank add`.  
**Recommendation**: `tank import` — unambiguous, consistent with the verb used in the codebase (`import_pack`, `_import_pack`).  
**When to decide**: before PyPI release — renaming after public release is a breaking change.  
**Decision not made this session** — left for the next contributor.

---

## Next Foundation item: `tank sync`

**Spec** (in `docs/roadmap.md`):
- New command: `src/tank/cli/sync.py`
- Reads `tank.lock` using `tomllib`
- For each `[packs.*]` entry: skip if `pack_digest` already in DB; fetch `source_url` (local path or `https://`); verify `pack_digest` matches lockfile entry before importing
- Writes updated `tank.lock` after all imports

**Blocked on**: pre-built packs having stable `source_url` values (GitHub Releases for v0.1.1 already satisfy this — `tank sync` could be implemented now against the two committed packs).

**Not blocked**: the `tank.lock` format, `pack_source` DB column, and `_import_pack` internal API are all ready.

---

## New decisions recorded

- **D16**: `tank.lock` at project root (see `docs/decisions.md`)
- **D17**: `pack_source` vs `source_url` — two distinct URL fields
- **D18**: Manifest validation via JSON Schema (jsonschema, draft/2020-12)

---

## Environment notes

- Python 3.12 venv at `.venv312/` — use this, not `.venv/` (3.11)
- `.tank/index.db` exists locally with fastmcp@3.3.0 and mcp@2025-11-25 imported
- `tank.lock` committed with GitHub Release URLs; local DB has local pull paths (normal — they diverge)
