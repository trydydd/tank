# Synaptic Drift — API Contracts

This page is the index of every machine-checkable contract in Synaptic Drift:
the `.ctx` pack artifacts, the MCP tool request/response shapes, and the CLI
exit codes. Each contract has a **canonical JSON Schema** (the source of truth)
and an **in-code validator** that enforces it at runtime.

> The code is the source of truth. The schemas live in `src/synd/schemas/` and
> are validated by `src/synd/schemas/__init__.py`. This page describes them; if
> they ever disagree, the schema files win and this page should be updated.

## Where contracts are enforced

```
build  ──emit──▶  validate_manifest / validate_chunk / validate_pages  (fail fast)
   │                                                                    BuildError
   ▼
.ctx pack  ──import──▶  verify (8 steps): manifest@2, chunk@1, pages@1  ─▶ VerifyResult
   │
   ▼
index.db  ──query──▶  search_docs / fetch_docs  ──validate_tool_response──▶  client
                                                  (tool-response.v1 boundary check)
```

A build never emits a pack its own verifier would reject: `build_pack` validates
the manifest, every chunk record, and the pages array before writing the final
archive, raising `BuildError` on any violation.

## 1. Pack artifacts (the `.ctx` format)

A `.ctx` file is a ZIP containing `manifest.json`, `chunks.jsonl`, `pages.json`,
and an (optional) `signatures/` entry. Each data file has a versioned schema:

| Artifact | Schema file | Validator |
|---|---|---|
| `manifest.json` | `manifest.v2.schema.json` | `validate_manifest(data)` |
| `chunks.jsonl` (per record) | `chunk.v1.schema.json` | `validate_chunk(record)` |
| `pages.json` (array) | `pages.v1.schema.json` | `validate_pages(data)` |

Schema file names carry the artifact's version (`manifest` is at v2 because
`schema_version == 2`; chunk/pages are at v1, matching `pack_format`
`synd-text-v1`).

**Forward compatibility.** Every schema leaves `additionalProperties` open:
unknown fields are accepted so the format can grow additively without breaking
older readers. Required fields and value constraints are still enforced.

**Tightened constraints.** Beyond presence/type, the schemas enforce:
`package` matches `^[A-Za-z0-9][A-Za-z0-9._-]*$` (no `@`/whitespace); `version`
matches `^[^@\s/]+$`; digest fields match `^sha256:[a-f0-9]{64}$`; counts and
ids are bounded integers. `source_url`/`url` carry an advisory
`format: uri-reference` annotation (documented, not strictly enforced, so local
filesystem paths remain valid).

See `docs/architecture.md` for the full field-by-field prose description of each
artifact.

## 2. MCP tool contract

The `search` and `fetch` tools (backed by `search_docs`/`fetch_docs`) return a
single response shape, **`tool-response.v1.schema.json`**:

- `{"results": [ <result item>, ... ]}` — zero or more matches, or
- `{"status": "not_indexed"}` — a requested package is not in the local index.

A result item carries `chunk_id`, `package`, `version`, `lifecycle_state`,
`doc_version_status`, `heading_path`, `summary`, `content` (null in summary-only
`search` responses), `source_url`, `source_commit`, `content_hash`,
`indexed_at`, `score`, and an optional `lifecycle_warning` (present only for
deprecated packs).

This contract is enforced two ways:

1. **Boundary validation** — `search_docs`/`fetch_docs` validate every payload
   against the schema before returning (`validate_tool_response`). An
   off-contract payload is a server bug and raises rather than shipping.
2. **Published `outputSchema`** — `create_server()` attaches the *same* schema
   document to each registered tool, so MCP clients discover the response shape
   via `tools/list`. The advertised schema and the validator are the same file.

The tool *input* schemas are derived by FastMCP from the tool function type
hints (the existing mechanism), so request shapes are also discoverable.

## 3. CLI exit codes

`synd` uses a differentiated, stable exit-code taxonomy so CI and scripts can
branch on the *class* of outcome. The mapping lives in `src/synd/cli/exit_codes.py`
(`exit_code_for` / `verify_failure_code`).

| Code | Meaning | Typical trigger |
|---|---|---|
| 0 | success | normal completion |
| 1 | generic/unexpected error | uncaught `SyndError` with no specific mapping; conflicts (e.g. duplicate `add` without `--force`) |
| 2 | usage error | malformed arguments, or a missing/nonexistent input path (Click convention) |
| 3 | policy rejection | `PolicyError`, or `verify` failing at step 3 (policy) |
| 4 | verification / integrity failure | `VerificationError`, schema/manifest errors, or `verify` failing at steps 1–2, 4–8 |
| 5 | not found | `PackNotFoundError` (pack absent from the local index) |
| 6 | build / IO failure | `BuildError`, `FetchError`, `LockfileError` |

Codes are a **stable contract**: future changes are additive (new codes), never
reassigned. A missing or malformed CLI argument (including a path that does not
exist) is a usage error (2) by Click convention; code 6 is reserved for
operations that fail *after* well-formed inputs are accepted.

## Single source of truth (types ↔ schema)

`src/synd/schemas/types.py` holds the in-code expression of these contracts —
`Literal` enum aliases (`LIFECYCLE_STATES`, `DOC_VERSION_STATUSES`) and
`TypedDict` shapes (`ManifestDict`, `ChunkRecord`, `PageRecord`,
`ToolResultItem`, `ToolResponse`) used for `mypy --strict`. The JSON Schemas
remain canonical; `tests/test_schemas/test_schema_consistency.py` fails if the
Python types and the schemas diverge (enum equality, required-field coverage),
so the two never silently disagree.

## Deferred to 1.0.0

Compatibility governance is intentionally out of scope here: a written
compat/deprecation policy, per-artifact self-versioning, and a CI gate that
fails incompatible schema edits (removed required field, dropped enum value,
narrowed type). The versioned filenames (`*.vN.schema.json`) and open
`additionalProperties` shipped now keep that door open.
