# Tank — Architecture

A local, enterprise-governed documentation pack system: build versioned `.ctx` packs from documentation sources, verify them against your policy, pull them into a local SQLite index, and serve them to AI coding agents via MCP.

## Goals

- **Local-first**: all data stays on the user's machine; no cloud dependency, no outbound network required at query time
- **Enterprise-governed**: every pack carries `lifecycle_state`, `policy_profile`, `owner`, and `approval_ref`; teams control which documentation enters their AI agents' context
- **Supply-chain integrity**: archive safety validation, hash verification, and optional signature checks at import time prevent tampered or malformed packs from entering the index
- **Source-attributed results**: every query result carries provenance metadata (package, version, `doc_version_status`, `lifecycle_state`, `source_url`, `source_commit`, `chunk_id`, `indexed_at`) so the AI agent can reason about freshness and trust
- **Reproducible**: content hashes at both the pack level (`pack_digest`) and chunk level (`normalized_content_hash`) enable integrity verification and change detection
- **Fast**: sub-10ms queries against pre-indexed content via SQLite FTS5
- **Token-efficient**: layered retrieval (summary scan → targeted full-content fetch) minimises context window usage without sacrificing accuracy

## MVP Definition

The MVP loop is four commands:

```bash
tank build my-lib@1.0.0 --source ./docs --output ./packs
tank verify ./packs/my-lib@1.0.0.ctx --policy ./policy.toml
tank pull ./packs/my-lib@1.0.0.ctx
tank query "How do I configure auth?" --package my-lib
```

Everything in this document that is not required to make this loop work is deferred. See [What Is Deferred](#what-is-deferred) for the explicit list.

### MVP success criteria

1. `tank build` produces a valid text-only `.ctx` archive from a local directory of Markdown or HTML files.
2. `tank verify` rejects packs whose `lifecycle_state` is not in the policy's `allowed_lifecycle_states`, and rejects archives containing path traversal, absolute paths, symlinks, device files, or hash mismatches.
3. `tank pull` only completes after all verify checks pass; it imports chunks into `.tank/index.db` in a single atomic transaction.
4. `tank query` returns BM25-ranked FTS5 results with full source attribution in under 10ms for an index of up to 100,000 chunks.
5. The MCP server exposes `query-docs` and a read-only `resolve-deps` over stdio and includes attribution fields on every result.
6. No outbound network is required.
7. No embedding model is required.
8. The test suite covers archive safety, manifest validation, import, and query attribution.

## MCP Tool Surface

The server exposes two tools to the AI agent. (`index-deps` is deferred to Phase 2.)

### `resolve-deps`

Read-only index health check. Scans `.tank/index.db` and returns the list of imported packs with their current state.

**Input**: optional `project_path` (defaults to cwd, used to locate `.tank/index.db`)

**Output**:
```json
{
  "status": "ok",
  "packs": [
    {
      "package": "my-lib",
      "version": "1.0.0",
      "lifecycle_state": "approved",
      "doc_version_status": "stable",
      "chunks": 412,
      "indexed_at": "2026-05-14T10:30:00Z"
    },
    {
      "package": "other-lib",
      "version": "2.3.0",
      "lifecycle_state": "deprecated",
      "doc_version_status": "archived",
      "chunks": 180,
      "indexed_at": "2026-03-01T08:00:00Z"
    }
  ]
}
```

This tool is effectively free to call (single SQLite read) and should be invoked at the start of every session as a health check. It surfaces deprecated or archived packs so the agent can warn the user before acting on stale documentation.

### `query-docs`

Full-text search across indexed documentation. Fast, read-only, only hits already-imported packs.

**Input**:
```json
{
  "query": "how to configure OAuth2 in my-lib",
  "packages": ["my-lib"],
  "detail": "summary",
  "limit": 10,
  "chunk_ids": []
}
```

- `query`: natural language question (required unless `chunk_ids` is provided)
- `packages`: optional filter scoped to specific package names
- `detail`: `"summary"` (default) returns heading path + one-line summary (~20–40 tokens each); `"full"` returns complete chunk content
- `limit`: maximum number of chunks returned from the FTS5 query (default 10)
- `chunk_ids`: optional list of specific chunk IDs to expand to full content, bypassing search
- `max_tokens`: optional token budget; chunks are accumulated in BM25 rank order and the list is cut before the estimated cost would exceed the budget — whole chunks only, never truncated mid-text (see `docs/ranking.md`)

**Output** (each result includes full provenance):
```json
{
  "results": [
    {
      "chunk_id": 412,
      "package": "my-lib",
      "version": "1.0.0",
      "lifecycle_state": "approved",
      "doc_version_status": "stable",
      "heading_path": "Authentication / Configure OAuth2",
      "summary": "Configure OAuth2 client credentials flow",
      "source_url": "https://my-lib.example.com/auth",
      "source_commit": "abc123def456",
      "content_hash": "sha256:d4e5f6...",
      "indexed_at": "2026-05-14T10:30:00Z",
      "score": 0.847
    }
  ]
}
```

If a queried package is not indexed, the tool returns an explicit `"not_indexed"` status rather than silently returning poor results.

When a result's `lifecycle_state` is `"deprecated"`, the server adds `"lifecycle_warning": "This pack is deprecated; consider updating to a newer version"`. Chunks from `"revoked"` packs are excluded at query time regardless of when they were imported.

**Typical agent workflow**:
1. Call `query-docs` with `detail: "summary"` to scan what's available (~20–40 tokens per result).
2. Pick the relevant chunk IDs from the summary list.
3. Call `query-docs` again with `chunk_ids: [12, 47, 83]` and `detail: "full"` to retrieve only the needed content.

This two-step pattern keeps token usage minimal while preserving access to full content.

## .ctx Pack Format

A `.ctx` pack is a zip-format archive containing documentation in structured, hash-verifiable form.

### MVP archive contents (text-only packs)

```
my-lib@1.0.0.ctx
├── manifest.json           # governance metadata, hashes, provenance
├── chunks.jsonl            # one JSON object per chunk, with attribution fields
├── pages.json              # page-level metadata (URL, content hash)
└── signatures/
    └── manifest.sig        # detached signature (optional unless policy requires it)

# DEFERRED (Phase 3):
# embeddings.bin            # dense float32 vectors (BGE-M3)
# sparse.jsonl              # learned sparse weight vectors per chunk
# overlays.jsonl            # corrections / annotations
# attestations/             # third-party provenance attestations
```

### manifest.json schema

```json
{
  "schema_version": 2,
  "pack_format": "tank-text-v1",

  "package": "my-lib",
  "version": "1.0.0",

  "pack_digest": "sha256:<digest-of-full-archive-with-this-field-zeroed>",
  "normalized_content_hash": "sha256:<hash-of-all-chunk-texts-concatenated-normalized>",
  "chunks": 412,
  "pages": 28,

  "lifecycle_state": "approved",
  "policy_profile": "internal-strict",
  "owner": "platform-team",
  "reviewers": ["alice@example.com", "bob@example.com"],
  "approval_ref": "JIRA-4821",
  "doc_version_status": "stable",

  "source_url": "https://my-lib.example.com/docs",
  "source_commit": "abc123def456",
  "source_tag": "v1.0.0",

  "created_at": "2026-05-14T10:30:00Z",
  "created_by": "tank/0.1.0"
}
```

**Governance fields**:

| Field | Required | Description |
|---|---|---|
| `lifecycle_state` | yes | `draft` / `approved` / `deprecated` / `revoked` |
| `policy_profile` | no | Name matching a profile in the consumer's `policy.toml` |
| `owner` | no | Team or individual responsible for the pack |
| `reviewers` | no | Who approved the pack |
| `approval_ref` | no | External ticket or PR reference |
| `doc_version_status` | yes | `stable` / `prerelease` / `archived` / `unknown` |

**Integrity fields**:

| Field | Description |
|---|---|
| `pack_digest` | SHA-256 of the full archive bytes with the `pack_digest` value zeroed out |
| `normalized_content_hash` | SHA-256 of all chunk `content` fields concatenated in ascending `id` order after normalization |

The normalization applied at build time and at verify time must be identical: strip leading/trailing whitespace per chunk, normalize Unicode whitespace to ASCII, collapse internal whitespace runs (outside code fences) to single spaces.

### chunks.jsonl record schema

Each line is a JSON object:

```json
{
  "id": 412,
  "page_id": 7,
  "heading_path": "docs/auth/oauth / Configure OAuth2",
  "summary": "Configure OAuth2 client credentials flow",
  "content": "To configure the OAuth2 client credentials flow...",
  "token_count": 387,
  "source_url": "docs/auth/oauth.md",
  "source_commit": "abc123def456",
  "content_hash": "sha256:<hash-of-normalized-chunk-content>"
}
```

The `source_url` field is always populated. For local builds, it is the relative path from the `--source` argument (e.g. `--source ./docs` produces `docs/auth/oauth.md`). Phase 2 web builds will use full `https://` URLs. The `source_commit` field is optional for local builds (populated if `--source-commit` is provided).

### pages.json schema

```json
[
  {
    "id": 7,
    "url": "docs/auth/oauth.md",
    "title": "Authentication",
    "content_hash": "sha256:<hash-of-page-content>"
  }
]
```

For local builds, `url` is the relative path from the `--source` root. Each file in the source tree becomes one page entry.

## Archive Safety Validator

Before any extraction, `tank verify` (and `tank pull`'s implicit verify step) runs a manifest-first validation sequence. This sequence is unconditional — it cannot be skipped via a flag.

### Validation sequence

```
tank verify <file.ctx>
  │
  ├─ 1. Open archive, read only manifest.json (no other extraction)
  │       ├─ FAIL → reject: "Cannot read manifest.json"
  │       └─ PASS →
  │
  ├─ 2. Validate manifest JSON schema
  │       Required: schema_version, pack_format, package, version,
  │                 pack_digest, normalized_content_hash, chunks, pages,
  │                 lifecycle_state, doc_version_status, created_at, created_by
  │       ├─ FAIL → reject: "Invalid manifest: missing field X"
  │       └─ PASS →
  │
  ├─ 3. Check lifecycle_state against policy
  │       (uses --policy flag, .tank/policy.toml, ~/.tank/policy.toml, or defaults)
  │       ├─ state not in allowed_lifecycle_states → reject: "lifecycle_state
  │       │   'draft' is not allowed by policy"
  │       └─ ALLOWED →
  │
  ├─ 4. Scan archive file listing (without extracting any file)
  │       Reject immediately if any entry:
  │         - starts with /  (absolute path)
  │         - contains ../  (path traversal)
  │         - is a device file, FIFO, or socket
  │         - is a hard link
  │         - is a symbolic link
  │       ├─ UNSAFE → reject: "Unsafe archive entry: <entry>"
  │       └─ CLEAN →
  │
  ├─ 5. Enforce size and count limits
  │       - max 10,000 archive entries
  │       - max 50 MB uncompressed per file
  │       - max 500 MB uncompressed total
  │       ├─ EXCEEDED → reject: "Archive exceeds size limit"
  │       └─ WITHIN LIMITS →
  │
  ├─ 6. Recompute pack_digest
  │       Hash the full archive bytes with the pack_digest value replaced by
  │       a zero-length placeholder; compare against manifest.pack_digest.
  │       ├─ MISMATCH → reject: "pack_digest mismatch: archive may be tampered"
  │       └─ MATCH →
  │
  ├─ 7. Recompute normalized_content_hash
  │       Extract chunks.jsonl; concatenate all content fields in ascending
  │       id order after normalization; hash; compare.
  │       ├─ MISMATCH → reject: "normalized_content_hash mismatch"
  │       └─ MATCH →
  │
  ├─ 8. Verify signature (only if policy.require_signatures = true)
  │       ├─ signatures/manifest.sig absent → reject: "Signature required by policy"
  │       ├─ Signature invalid → reject: "Signature verification failed"
  │       └─ VALID →
  │
  └─ 9. PASS — all checks succeeded
         (tank pull proceeds to import; tank verify exits 0)
```

Steps 1–8 are entirely read-only. Step 9 in `tank pull` opens the DB. The import is wrapped in a single transaction, so a failure during import leaves the database unchanged.

Documentation text in chunks is treated as untrusted source content. It is stored verbatim and served verbatim; it is never executed or evaluated.

## Lifecycle States and Policy File

### Lifecycle state machine

```
  draft ──────────────────→ approved ──→ deprecated ──→ revoked
                                ↑                           │
                                └─── (re-approve) ──────────┘
                                     (out of scope for MVP)
```

| State | Meaning | Default policy |
|---|---|---|
| `draft` | Built but not reviewed | Rejected in production environments |
| `approved` | Reviewed, hash-verified, policy-cleared | Allowed everywhere |
| `deprecated` | Valid but a newer version exists | Allowed with warning |
| `revoked` | Known-bad: tampered, incorrect, or security issue | Always rejected |

`revoked` is enforced at query time as well as at import time. A pack imported before revocation will have its chunks excluded from all `query-docs` results once `lifecycle_state` is updated to `revoked` in the packages table.

### Policy file (policy.toml)

```toml
# .tank/policy.toml

[policy]
require_signatures = false          # true = reject unsigned packs at verify time
require_attribution = true          # include provenance in query-docs results

allowed_lifecycle_states = [
  "approved",
  "deprecated",                     # allowed with lifecycle_warning on results
]

# Optional: reject packs whose doc_version_status is in this list
rejected_doc_version_statuses = ["archived"]
```

**Policy file lookup order** (first file found wins):
1. `--policy <path>` flag passed to `tank verify` or `tank pull`
2. `.tank/policy.toml` in the current project directory
3. `~/.tank/policy.toml` as user-level default
4. Permissive built-in defaults: all `lifecycle_state` values except `revoked` are allowed; `require_signatures = false`

## Verify-Before-Import Sequence

`tank pull` is shorthand for: verify fully, then import. Nothing is written to the database until all verify steps pass.

```
tank pull <file.ctx> [--policy ./policy.toml]
  │
  ├─ Verify phase (read-only, no DB writes)
  │    Steps 1–8 from Archive Safety Validator above
  │    ├─ ANY FAILURE → print error, exit non-zero, DB unchanged
  │    └─ ALL PASS →
  │
  └─ Import phase (single atomic transaction)
       BEGIN TRANSACTION;
         INSERT INTO packages (name, version, lifecycle_state, policy_profile,
           pack_digest, normalized_content_hash, doc_version_status,
           source_url, source_commit, owner, indexed_at)
         VALUES (...);
         INSERT INTO pages (package, version, url, content_hash)
         VALUES (...) × N;
         INSERT INTO chunks (package, version, page_id, heading_path,
           summary, content, token_count, source_url, source_commit, content_hash)
         VALUES (...) × M;
         -- FTS triggers fire automatically, populating chunks_fts
       COMMIT;
       → Print: "Imported my-lib@1.0.0: 412 chunks, 28 pages"
```

If the pack has already been imported at the same version, `tank pull` rejects with `"Pack my-lib@1.0.0 is already imported. Use --force to re-import."` This prevents accidental overwrites.

## Hash Chain and Content Integrity

The system maintains a hash chain: **pack archive → manifest hashes → chunk content**. Any tampering at any level is detectable.

### Hash semantics

- **`pack_digest`**: SHA-256 of the full `.ctx` archive bytes, computed with the `pack_digest` field value in `manifest.json` replaced by an empty string during computation. This makes the digest deterministic even though `manifest.json` itself declares the digest. All ZIP entries are written with a pinned `date_time` of `(2021, 8, 8, 0, 0, 0)` so that the two archive writes during build (once with empty digest, once with the real digest) produce identical ZipInfo metadata and the verifier can reproduce the hash exactly.
- **`normalized_content_hash`**: SHA-256 of all chunk `content` strings, each normalized (whitespace-normalized, Unicode-normalized to NFC), then concatenated in ascending `id` order with a `\n` separator. This hash is independent of metadata changes (heading paths, summaries, page IDs) and only changes when text content changes.
- **Per-chunk `content_hash`**: SHA-256 of that chunk's normalized content alone. Useful for detecting which specific chunks changed between pack versions.

The normalization function used at `tank build` time and `tank verify` time must be the same code path (`tank.builder.normalizer`). This is the hash stability guarantee.

### Pack-level lockfile (.tank/index.lock)

A TOML record of imported packs, written by `tank pull` and readable by `resolve-deps`:

```toml
[meta]
schema_version = 1
generated_at = "2026-05-14T10:30:00Z"

[packs."my-lib@1.0.0"]
pack_digest = "sha256:a1b2c3..."
lifecycle_state = "approved"
indexed_at = "2026-05-14T10:30:00Z"

[packs."other-lib@2.3.0"]
pack_digest = "sha256:d4e5f6..."
lifecycle_state = "deprecated"
indexed_at = "2026-03-01T08:00:00Z"
```

The database (`index.db`) is the source of truth. The lockfile is a human-readable snapshot useful for git diffs, audits, and offline inspection.

## Storage: SQLite Schema

One database per project at `.tank/index.db`.

```sql
CREATE TABLE packages (
    name                    TEXT NOT NULL,
    version                 TEXT NOT NULL,
    lifecycle_state         TEXT NOT NULL DEFAULT 'draft',
    policy_profile          TEXT,
    pack_digest             TEXT,
    normalized_content_hash TEXT,
    doc_version_status      TEXT,
    source_url              TEXT,
    source_commit           TEXT,
    owner                   TEXT,
    indexed_at              TEXT NOT NULL,
    PRIMARY KEY (name, version)
);

CREATE TABLE pages (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    package       TEXT NOT NULL,
    version       TEXT NOT NULL,
    url           TEXT NOT NULL,
    content_hash  TEXT,
    -- etag, last_modified, fetched_at: deferred to Phase 2 (crawl fields)
    UNIQUE(package, version, url),
    FOREIGN KEY (package, version) REFERENCES packages(name, version)
);

CREATE TABLE chunks (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    package         TEXT NOT NULL,
    version         TEXT NOT NULL,
    page_id         INTEGER REFERENCES pages(id),
    heading_path    TEXT,
    summary         TEXT,
    content         TEXT NOT NULL,
    token_count     INTEGER,
    source_url      TEXT,
    source_commit   TEXT,
    content_hash    TEXT,
    -- DEFERRED (Phase 3): dense_embedding BLOB, sparse_weights TEXT
    FOREIGN KEY (package, version) REFERENCES packages(name, version)
);

-- FTS5 full-text index, BM25 ranking (primary search mechanism for MVP)
CREATE VIRTUAL TABLE chunks_fts USING fts5(
    summary, content,
    content='chunks',
    content_rowid='id'
);

-- Keep FTS5 in sync with chunks
CREATE TRIGGER chunks_ai AFTER INSERT ON chunks BEGIN
    INSERT INTO chunks_fts(rowid, summary, content)
    VALUES (new.id, new.summary, new.content);
END;
CREATE TRIGGER chunks_ad AFTER DELETE ON chunks BEGIN
    INSERT INTO chunks_fts(chunks_fts, rowid, summary, content)
    VALUES ('delete', old.id, old.summary, old.content);
END;
```

## Search: FTS5 with Attribution

MVP search is SQLite FTS5 with BM25 ranking. One retriever, no fusion layer required.

### Query

```sql
SELECT
    c.id              AS chunk_id,
    c.package,
    c.version,
    c.heading_path,
    c.summary,
    c.content,
    c.source_url,
    c.source_commit,
    c.content_hash,
    p.lifecycle_state,
    p.doc_version_status,
    p.indexed_at,
    bm25(chunks_fts)  AS score
FROM chunks_fts
JOIN chunks   c ON chunks_fts.rowid = c.id
JOIN packages p ON c.package = p.name AND c.version = p.version
WHERE chunks_fts MATCH ?
  AND p.lifecycle_state != 'revoked'
ORDER BY score
LIMIT ?
```

Package and version filters are applied as additional `AND c.package = ?` / `AND c.version = ?` clauses.

### Performance target

Under 10ms for queries against up to 100,000 indexed chunks on commodity hardware. FTS5's inverted index makes this straightforwardly achievable without tuning; BM25 is computed during traversal, not post-hoc.

### Progressive disclosure

Results are returned at two detail levels:

1. **Summary** (default): `heading_path`, `summary`, `score`, `source_url`, `lifecycle_state`. ~20–40 tokens per result. The agent uses this to decide which chunks it actually needs.
2. **Full**: all of the above plus `content`. The agent requests specific `chunk_ids` from the first pass.

This two-step pattern is the primary mechanism for staying within the AI agent's token budget.

## Token Efficiency

### Layered retrieval

1. **Summary layer** (returned by default): heading path + one-line summary per matching chunk. Roughly 20–40 tokens per result. The agent scans this to decide what it actually needs.
2. **Full content** (on request): the agent requests specific chunks by ID via `chunk_ids` to get complete text.

### Token budget enforcement (`max_tokens`)

When `max_tokens` is set on `query-docs`, a greedy post-ranking pass enforces a hard budget. After BM25 ranking, chunks are accumulated from highest score to lowest. A chunk is included only if its estimated cost does not push the running total over `max_tokens`. The cut always falls between whole chunks — content is never truncated mid-text.

Token cost estimation: `len(content) // 4` for `detail="full"`, `len(summary) // 4` for `detail="summary"`. This matches the `token_count` estimator written at build time and is intentionally approximate — suitable for budget planning, not byte-exact accounting.

The ranking strategy and the rationale for the greedy approach are documented in `docs/ranking.md`.

### Content normalization (applied at build time)

- Collapse runs of blank lines to a single blank line
- Strip HTML boilerplate, nav, breadcrumbs, footer, version banners
- Remove "Edit this page" links, "See also" sections that are only link lists
- Normalize Unicode whitespace to ASCII
- Preserve code block formatting exactly (indentation matters)
- Preserve table formatting

The same normalization is applied at verify time (to recompute `normalized_content_hash`). Both must use the same code path — `tank.builder.normalizer` — not independent implementations.

### What we explicitly do NOT do

- **Strip all whitespace**: destroys code example readability, confuses models
- **Aggressive abbreviation**: models handle natural language better than compressed shorthand
- **Remove code examples**: these are often the highest-value content in documentation

## CLI Tooling

The `tank` CLI covers everything an AI agent should not be doing. The CLI and MCP server share the same core libraries (`storage`, `search`, `policy`) but can be installed separately.

### Install paths

```bash
# MCP server + query functionality only (minimal install)
pip install tank

# Full toolchain: adds tank build and tank pull
pip install tank[build]

# Everything including optional embedding support (Phase 3)
pip install tank[all]
```

`tank[build]` adds `chunkana` for structural Markdown chunking. It does not add crawler, embeddings, or network-access dependencies — building from a local directory has no network requirements.

### Command surface

```
tank build <package@version> --source <path> [--output ./] [--lifecycle draft]
              [--owner <name>] [--policy-profile <name>]
    Build a .ctx pack from a local directory of Markdown or HTML files.
    --source          Local directory path (required; URL crawling is Phase 2)
    --output          Directory to write the .ctx file (default: current dir)
    --lifecycle       lifecycle_state to set in manifest (default: draft)
    --owner           Owner field in manifest
    --policy-profile  Policy profile name to embed in manifest
    Writes: <output>/<package>@<version>.ctx

    Source tree handling:
    - Recurses subdirectories by default
    - File discovery whitelist: .md, .html, .htm (all others skipped with debug log)
    - Walk order is lexicographic (sorted by full relative path) for deterministic
      chunk ID assignment and reproducible normalized_content_hash
    - Each file becomes one page; heading_path is prefixed with the relative file
      path (e.g. docs/auth/oauth.md heading "# Overview" → "auth/oauth / Overview")
    - source_url is set to the relative path from --source root (e.g. "docs/auth/oauth.md")

    See document-processing.md for the full pipeline description.

tank verify <file.ctx> [--policy ./policy.toml]
    Run the full 8-step archive safety validation sequence.
    Prints a pass/fail summary with the specific check that failed.
    Exits 0 on pass, non-zero on any failure.
    Does NOT write to the database.

tank pull <file.ctx> [--policy ./policy.toml] [--force]
    Verify (full 8-step sequence) then import into .tank/index.db.
    Equivalent to: tank verify <file> && tank import <file>
    Will not import if any verify check fails.
    --force           Re-import even if this package@version is already present

tank query <query> [--package pkg[@version]] [--detail summary|full]
           [--limit N] [--lifecycle approved,deprecated]
    BM25 full-text search against imported packs.
    Returns attribution fields on every result.
    --detail summary  heading_path + summary + score (default)
    --detail full     also includes content
    --lifecycle       filter by lifecycle_state (default: all except revoked)

tank inspect <file.ctx | .tank/index.db>
    Print manifest fields, chunk count, token distribution, page list.
    For index.db: list all imported packs with lifecycle_state, pack_digest,
    indexed_at, and chunk count.
    Useful for debugging pack contents without pulling them into the index.
```

Phase 2 will add `tank publish`, `tank registry`, and `tank promote`. Phase 3 will add `tank index-url` for URL crawling.

### Dependency split

```
tank (base):
  mcp               # Anthropic MCP Python SDK
  sqlite3           # stdlib
  tomllib           # stdlib (Python 3.11+)
  click, rich       # CLI framework and terminal output

tank[build] adds:
  chunkana          # structural Markdown chunking, MIT license

tank[embeddings] adds (Phase 3):
  FlagEmbedding     # BGE-M3 dense + sparse + ColBERT

# Phase 2 additions (deferred):
# crawl4ai          # async crawler + markdown extraction
# pydepsdev         # deps.dev API client
```

## MCP Transport

The server supports two transport modes, configurable at startup.

### stdio (default)

Standard MCP transport over stdin/stdout. Works with all MCP clients (Claude Desktop, Cursor, VS Code, Claude Code, etc.). No network exposure.

```json
{
  "mcpServers": {
    "tank": {
      "command": "python",
      "args": ["-m", "tank.server"]
    }
  }
}
```

### HTTP (local network)

Streamable HTTP transport bound to localhost only. Useful for editors that prefer HTTP-based MCP, for running as a persistent background daemon, or for development and debugging.

```bash
python -m tank.server --http --port 8000 --path /mcp
# Listens on 127.0.0.1:8000/mcp only
```

```json
{
  "mcpServers": {
    "tank": {
      "url": "http://127.0.0.1:8000/mcp"
    }
  }
}
```

**Security**: the HTTP transport binds exclusively to `127.0.0.1`. It does not and will not bind to `0.0.0.0` or any external interface. This is a hard constraint, not a configuration option. For remote access (e.g. a team server), front it with a reverse proxy that handles authentication and TLS.

## Technology Choices

| Component | Choice | Rationale |
|---|---|---|
| Runtime | Python 3.11+ | `tomllib` in stdlib; active support through 2027; `str \| None` syntax |
| MCP server | Python | All dependencies are Python-native; avoids cross-process IPC |
| CLI framework | click + rich | click for composable subcommands; rich for tables and progress bars |
| Chunking | **chunkana** | Preserves code blocks/tables, heading path metadata, structural chunking for RAG, MIT |
| Archive validator | stdlib `zipfile` + `hashlib` | No third-party dependencies for security-critical path |
| Policy engine | stdlib `tomllib` | No third-party dependencies; TOML is human-readable and git-friendly |
| Storage | SQLite + FTS5 | Single file, no infrastructure, portable, fast |
| Pack format | `.ctx` (zip archive) | Self-contained, hashable, portable, inspectable with standard tools |
| Lockfile format | TOML | Human-readable, git-friendly |
| MCP SDK | `mcp` (Python) | Official Anthropic MCP SDK for Python |
| Packaging | single PyPI package with extras | `tank` base + `[build]` extra keeps the MCP server lean |

The project writes custom code only where no good solution exists (archive safety validator, policy engine, SQLite storage layer, FTS5 attribution query). Everything else delegates to well-maintained libraries.

## Project Structure

```
tank/
├── pyproject.toml
├── README.md
├── LICENSE
│
├── src/tank/
│   ├── __init__.py
│   │
│   │── # ── BASE PACKAGE (pip install tank) ─────────────────────
│   │
│   ├── server.py               # MCP server (query-docs, resolve-deps tools)
│   │
│   ├── search/
│   │   ├── __init__.py
│   │   └── fts.py              # BM25 query, package scoping, attribution JOIN
│   │
│   ├── storage/
│   │   ├── __init__.py
│   │   ├── db.py               # Connection management, schema migrations
│   │   └── models.py           # Pack, Chunk, Page dataclasses
│   │
│   ├── policy/
│   │   ├── __init__.py
│   │   └── engine.py           # policy.toml loader, lifecycle_state enforcer
│   │
│   │── # ── BUILD EXTRA (pip install tank[build]) ────────────────
│   │
│   ├── builder/
│   │   ├── __init__.py
│   │   ├── build.py            # Orchestrate: ingest → chunk → manifest → archive
│   │   ├── chunking.py         # chunkana integration
│   │   ├── manifest.py         # Manifest construction and pack_digest computation
│   │   └── normalizer.py       # Shared normalization (used by builder AND verifier)
│   │
│   ├── validator/
│   │   ├── __init__.py
│   │   └── verify.py           # 8-step archive safety validator
│   │
│   ├── cli/
│   │   ├── __init__.py
│   │   ├── main.py             # tank root command (click group)
│   │   ├── build.py            # tank build
│   │   ├── verify.py           # tank verify
│   │   ├── pull.py             # tank pull
│   │   ├── query.py            # tank query
│   │   └── inspect.py          # tank inspect
│   │
│   │── # ── DEFERRED (Phase 2) ───────────────────────────────────
│   │   # crawler/              # Crawl4AI orchestration
│   │   # resolver/             # deps.dev URL resolution
│   │   # registry/             # Remote registry client and signing
│   │
│   └── # ── DEFERRED (Phase 3) ──────────────────────────────────
│       # embeddings/           # BGE-M3 via FlagEmbedding
│       # search/dense.py       # Cosine similarity over dense vectors
│       # search/sparse.py      # Sparse dot product
│       # search/fusion.py      # Reciprocal Rank Fusion
│
└── tests/
    ├── test_builder/
    ├── test_validator/
    ├── test_search/
    ├── test_storage/
    └── test_cli/
```

### pyproject.toml entry points

```toml
[project.scripts]
tank = "tank.cli.main:cli"
# MCP server is invoked directly: python -m tank.server

[project.optional-dependencies]
build = [
    "chunkana>=0.1",
]
embeddings = [
    "FlagEmbedding>=1.2",
]
all = ["tank[build]", "tank[embeddings]", "pytest", "pytest-asyncio"]
```

## Implementation Phases

### Phase 1 — MVP (this document)

- `tank build` from local source directories (Markdown / HTML)
- Archive safety validator (unconditional, 8-step sequence)
- `tank verify` with `policy.toml` enforcement
- `tank pull` (verify-then-import, atomic transaction)
- `tank query` with FTS5/BM25 and full source attribution
- `tank inspect` for debugging pack contents and the local index
- MCP server: `query-docs` and read-only `resolve-deps`
- SQLite schema with governance and attribution columns
- Policy file (`policy.toml`) with lifecycle state and signature enforcement
- `.tank/index.lock` as a human-readable record of imported packs

### Phase 2 — Crawling and Registry

- URL crawling via Crawl4AI with ethical crawling policy, rate limiting, and robots.txt compliance:
  - Per-domain rate limiting (default: 1 request / 2 seconds; respects `Crawl-delay`)
  - Adaptive backoff on 429/403
  - Transparent `User-Agent` identification
  - Sitemap preference over link discovery
  - Scope limiting to doc path prefixes
  - Concurrency model: packages crawled in parallel but per-domain queues remain serial
- deps.dev integration for doc URL resolution (`HOMEPAGE` → `SOURCE_REPO` → well-known patterns → manual overrides)
- `tank build --source <URL>` (URL crawling path, in addition to existing local path)
- Incremental re-crawl using HTTP ETags (`If-None-Match` / `If-Modified-Since`)
- Remote registry: `tank publish`, `tank pull <package@version>` from registry URL
- Lifecycle promotion workflow: `tank promote`, `tank revoke`
- Staleness detection against project lockfiles (`resolve-deps` expanded to scan `requirements.txt`, `package.json`, `Cargo.toml`, etc.)
- Auto-discovery of dependency files in the project directory
- Private and internal packages via `--auth` flag in `tank build`
- Registry governance: signing, content hash verification on upload, reproducibility checks

### Phase 3 — Embeddings

- BGE-M3 embeddings (dense + sparse) as `tank[embeddings]` optional extra
- `dense_embedding BLOB` and `sparse_weights TEXT` columns added to `chunks`
- Hybrid search: dense cosine similarity + BGE-M3 sparse + FTS5, fused with Reciprocal Rank Fusion (RRF)
- ColBERT multi-vector retrieval as opt-in via `config.toml`
- `embeddings.bin` and `sparse.jsonl` in `.ctx` pack format
- `embedding_model` and `embedding_model_hash` fields in manifest for cross-model compatibility
- Automated re-embedding from stored chunk text when the local model differs from the pack's model

## What Is Deferred

The following are explicitly out of scope for Tank v1. No MVP schema or format decision will need to be broken to add them.

### Deferred to Phase 2 (Crawling and Registry)

- URL crawling (`tank build` currently requires `--source <local-path>`)
- deps.dev integration for doc URL resolution
- ReadTheDocs and GitHub version resolution
- Incremental re-crawl with HTTP ETags
- Remote registry: `tank publish`, `tank pull <pkg@version>` from a registry URL
- Community or public registry hosting
- Lifecycle promotion workflows (`tank promote`, `tank revoke`)
- Staleness detection against project lockfiles
- Auto-discovery from `requirements.txt` / `package.json` / `Cargo.toml`
- Private/internal package `--auth` flag
- `index-deps` MCP tool

### Deferred to Phase 3 (Embeddings)

- BGE-M3 embeddings (dense + sparse)
- Hybrid search (dense + sparse + FTS5 with RRF)
- ColBERT multi-vector retrieval
- `embeddings.bin` and `sparse.jsonl` in `.ctx` pack format
- FlagEmbedding as a dependency

### Permanently deferred / out of scope

- `overlays.jsonl` (doc corrections and annotations)
- `attestations/` directory
- Cloud-hosted index (local-first is a hard constraint)

## Resolved Decisions

- **Summary generation approach**: heuristic generation at build time. Extract the first sentence for prose chunks, or the leading function/class signature for code-heavy chunks. No LLM dependency, no network requirement, deterministic output. The `summary` field schema supports upgrading the strategy later without a format change.

- **Chunk-level source_url**: `source_url` is always populated, never null. Local builds store the relative path from the `--source` argument (e.g. `--source ./docs` + file at `docs/auth/oauth.md` = `source_url: "docs/auth/oauth.md"`). Only `./` is stripped from the front. Phase 2 web builds use full `https://` URLs. No fallback logic is needed at query time because the field is never absent.

- **Source tree handling**: `tank build --source <path>` recurses subdirectories by default. Files are discovered by extension whitelist (`.md`, `.html`, `.htm`). Walk order is lexicographic (sorted by full relative path) to guarantee deterministic chunk ID assignment and reproducible `normalized_content_hash`. Phase 2 crawled builds must establish their own deterministic sort (e.g. canonical URL) before assigning IDs.

- **Python version**: 3.11+ required. Uses `tomllib` from stdlib. No backport dependencies.

## Open Questions (Deferred to Phase 2)

- **Policy inheritance in CI**: when a `.ctx` is built in CI with `lifecycle_state: draft` and a human later promotes it to `approved`, should the pack be rebuilt (new `pack_digest`) or should a side-channel approval record update the existing imported entry? Rebuilding is cleaner but requires re-running the pipeline; updating the packages table's `lifecycle_state` in place is pragmatic but means the stored `pack_digest` no longer reflects the approved state. To be resolved when designing the Phase 2 promotion workflow.

- **Policy merge semantics in monorepos**: a monorepo may want a root-level policy and workspace-level overrides. The lookup order (workspace `.tank/policy.toml` > root `.tank/policy.toml` > user default) seems right, but whether workspace policy is additive (can only restrict further) or fully overriding needs to be specified before Phase 2 implementation.
