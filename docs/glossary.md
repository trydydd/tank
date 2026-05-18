# Tank — Glossary

Definitions of Tank-specific terminology. Sorted alphabetically.

---

**`.ctx` pack** — a zip-format archive containing documentation in structured, hash-verifiable form. Contains `manifest.json`, `chunks.jsonl`, `pages.json`, and optionally `signatures/manifest.sig`. The file extension is `.ctx`. Named as `<package>@<version>.ctx`.

**`.tank/` directory** — per-project directory storing Tank's local state: `index.db` (the SQLite database), `index.lock` (the lockfile), and optionally `policy.toml`.

**BM25** — the ranking algorithm used by SQLite FTS5 for full-text search. Produces a relevance score based on term frequency and inverse document frequency. Used by `tank query` and `query-docs`.

**chunk** — a unit of documentation content produced by structural chunking. Each chunk has an ID, belongs to a page, carries a `heading_path`, `summary`, `content`, `token_count`, `source_url`, and `content_hash`. Stored as one line in `chunks.jsonl` and one row in the `chunks` SQLite table.

**chunk ID** — sequential integer assigned during build, starting at 1. Order is determined by lexicographic file sort (then document order within each file). The ID sequence determines `normalized_content_hash` computation.

**chunkana** — third-party Python library (MIT license) used for structural Markdown chunking. Splits at heading boundaries while preserving code blocks and tables as atomic units. Provides `heading_path` metadata.

**content_hash** — SHA-256 of a single chunk's content after normalization. Used to detect which specific chunks changed between pack versions. Distinct from `normalized_content_hash` (which covers all chunks together).

**doc_version_status** — metadata field indicating the documentation's version state. Values: `stable`, `prerelease`, `archived`, `unknown`. Stored in `manifest.json` and the `packages` table. Used by policy to reject archived documentation.

**FTS5** — SQLite's full-text search extension, version 5. Provides an inverted index with BM25 ranking. Tank's primary (and only, for MVP) search mechanism.

**heading_path** — hierarchical path describing where a chunk sits in the document structure. Constructed as the file path prefix (minus extension, minus the `--source` directory name) joined with the heading hierarchy from the document. Example: file `docs/auth/oauth.md` with heading `## Client Credentials` produces `auth/oauth / OAuth2 / Client Credentials`.

**index.db** — the SQLite database at `.tank/index.db`. Contains `packages`, `pages`, `chunks`, and `chunks_fts` tables. Source of truth for all imported documentation. One database per project.

**index.lock** — TOML file at `.tank/index.lock`. Human-readable snapshot of imported packs (package, version, `pack_digest`, `lifecycle_state`, `indexed_at`). Useful for git diffs and audits. The database is the source of truth; the lockfile is informational.

**lifecycle_state** — governance field tracking a pack's approval status. Values: `draft` (built, not reviewed), `approved` (reviewed and cleared), `deprecated` (valid but superseded), `revoked` (known-bad, excluded from all queries). Stored in `manifest.json` and the `packages` table. Enforced by policy at both import and query time.

**manifest.json** — the metadata file inside a `.ctx` pack. Contains governance fields (`lifecycle_state`, `owner`, `policy_profile`), integrity fields (`pack_digest`, `normalized_content_hash`), provenance fields (`source_url`, `source_commit`), and pack metadata (`package`, `version`, `chunks`, `pages`).

**normalization** — the text transformation applied to chunk content before hashing. Rules: collapse blank line runs, strip HTML boilerplate (MVP: basic tag removal), normalize Unicode whitespace to ASCII, preserve code blocks and tables verbatim. The same code path (`tank.builder.normalizer`) is used at both build and verify time. This is the hash stability guarantee.

**normalized_content_hash** — SHA-256 of all chunk content strings, each normalized, concatenated in ascending chunk ID order with a `\n` separator. Changes only when text content changes (independent of metadata like heading paths or summaries). Stored in `manifest.json`. Verified at import time.

**pack_digest** — SHA-256 of the full `.ctx` archive bytes, computed with the `pack_digest` field value in `manifest.json` set to `""`. Detects any tampering of the archive (content or metadata). Verified at import time.

**page** — one source file processed during build. Each file becomes one page entry in `pages.json` with an ID, URL (relative path for local builds), title, and `content_hash`. Chunks reference their parent page via `page_id`.

**pages.json** — file inside a `.ctx` pack listing all pages (source files) with their metadata. Array of objects in page ID order.

**policy.toml** — TOML configuration file controlling what packs are allowed into the index. Specifies `allowed_lifecycle_states`, `require_signatures`, `rejected_doc_version_statuses`. Lookup order: `--policy` flag > `.tank/policy.toml` > `~/.tank/policy.toml` > permissive built-in defaults.

**policy_profile** — optional name in `manifest.json` that associates a pack with a specific policy profile in the consumer's `policy.toml`. For MVP, policies are global (not per-profile). Profile-based policy is a Phase 2 consideration.

**progressive disclosure** — the two-step query pattern. First call returns summaries (~20-40 tokens each) so the agent can decide what it needs. Second call retrieves full content for specific chunk IDs. Primary mechanism for token efficiency.

**source_url** — provenance field on chunks and pages indicating where the content came from. For local builds: relative path from `--source` root (e.g. `docs/auth/oauth.md`). For Phase 2 web builds: full `https://` URL. Always populated, never null.

**TankError** — base exception class for all Tank-specific errors. CLI commands catch subclasses and map them to exit codes and user-facing messages. Specific subclasses are discovered and added during TDD.

**token_count** — approximate token count per chunk, computed as `len(content) // 4`. Advisory field for agent budget planning. Not exact — documented as a rough estimate.

**WAL mode** — SQLite Write-Ahead Logging mode. Enabled on database creation. Allows concurrent reads while a write is in progress. Combined with a 5000ms busy timeout to handle concurrent access.
