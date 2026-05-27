# Synaptic Drift — Glossary

Definitions of Synaptic Drift-specific terminology. Sorted alphabetically.

---

**`.ctx` pack** — a zip-format archive containing documentation in structured, hash-verifiable form. Contains `manifest.json`, `chunks.jsonl`, `pages.json`, and optionally `signatures/manifest.sig`. The file extension is `.ctx`. Named as `<package>@<version>.ctx`.

**`.synd/` directory** — per-project directory storing Synaptic Drift's local runtime state: `index.db` (the SQLite database) and optionally `policy.toml`. Not committed to version control.

**BM25** — the ranking algorithm used by SQLite FTS5 for full-text search. Produces a relevance score based on term frequency and inverse document frequency. Used by `synd query` and the `search` MCP tool. Column weights: `heading_path` 2.5×, `summary` 1.5×, `content` 1.0×.

**chunk** — a unit of documentation content produced by structural chunking. Each chunk has an ID, belongs to a page, carries a `heading_path`, `summary`, `content`, `token_count`, `source_url`, and `content_hash`. Stored as one line in `chunks.jsonl` and one row in the `chunks` SQLite table.

**chunk ID** — sequential integer assigned during build, starting at 1. Order is determined by lexicographic file sort (then document order within each file). The ID sequence determines `normalized_content_hash` computation.

**chunkana** — third-party Python library (MIT license) currently used for structural Markdown chunking. Splits at `##` heading boundaries while preserving code blocks and tables as atomic units. **Planned for replacement** by a custom `markdown-it-py`-backed chunker (see `docs/spikes.yaml` S7) that splits at all heading levels and builds accurate ancestral `heading_path` values.

**chunks_fts** — the FTS5 virtual table in `index.db`. Columns: `heading_path` (2.5× BM25 weight), `summary` (1.5×), `content` (1.0×). Populated at import time. `rowid` joins to `chunks.id`. All `search` queries run against this table.

**content_hash** — SHA-256 of a single chunk's content after normalization. Used to detect which specific chunks changed between pack versions. Distinct from `normalized_content_hash` (which covers all chunks together).

**doc_version_status** — metadata field indicating the documentation's version state. Values: `stable`, `prerelease`, `archived`, `unknown`. Stored in `manifest.json` and the `packages` table. Used by policy to reject archived documentation.

**fetch** (MCP tool) — retrieves full chunk content by ID. Always called after `search`. Parameters: `chunk_ids` (list of integers from `search` results), `max_tokens` (optional budget). Chunks from revoked packs are silently excluded.

**FTS5** — SQLite's full-text search extension, version 5. Provides an inverted index with BM25 ranking. Synaptic Drift's primary (and only, for MVP) search mechanism. The virtual table is `chunks_fts`.

**heading_path** — hierarchical path describing where a chunk sits in the document structure. Format: `<relative_file_prefix> / <section_heading>`. The file prefix is the path relative to `--source`, minus extension (e.g. `auth/oauth`); the section heading is the first `##`-level heading chunkana found in the chunk. Example: `auth/oauth / Client Credentials`. The current implementation captures one heading level only. The planned custom chunker (S7) will extend this to a full ancestral hierarchy: `auth/oauth / OAuth2 / Client Credentials`.

**index.db** — the SQLite database at `.synd/index.db`. Contains `packages`, `pages`, `chunks`, and `chunks_fts` tables. Source of truth for all imported documentation. One database per project.

**synd.lock** — TOML file at the project root, written by `synd add` and `synd sync` on every import. Records each imported pack's name, version, `pack_digest`, `lifecycle_state`, `indexed_at`, and `source_url`. Commit this file to version-control your documentation dependencies — analogous to `Cargo.lock` or `package-lock.json`. The database (`.synd/index.db`) is the source of truth; `synd.lock` is the human-readable, committable declaration.

**lifecycle_state** — governance field tracking a pack's approval status. Values: `draft` (built, not reviewed), `approved` (reviewed and cleared), `deprecated` (valid but superseded), `revoked` (known-bad, excluded from all queries). Stored in `manifest.json` and the `packages` table. Enforced by policy at both import and query time.

**lifecycle_warning** — field included in `search` and `fetch` results when the queried pack has `lifecycle_state = "deprecated"`. Value: `"This package is deprecated"`. Absent (not null) when the pack is approved. Agents should surface this to the user.

**manifest.json** — the metadata file inside a `.ctx` pack. Contains governance fields (`lifecycle_state`, `owner`, `policy_profile`), integrity fields (`pack_digest`, `normalized_content_hash`), provenance fields (`source_url`, `source_commit`), and pack metadata (`package`, `version`, `chunks`, `pages`).

**MCP** — Model Context Protocol. An open protocol for connecting AI assistants to external tools and data sources. Synaptic Drift exposes its documentation index as an MCP server with two tools (`search` and `fetch`) over stdio transport. See `docs/MCP.md`.

**normalization** — the text transformation applied to chunk content before hashing. Rules: collapse blank line runs, strip HTML boilerplate (MVP: basic tag removal), normalize Unicode whitespace to ASCII, preserve code blocks and tables verbatim. The same code path (`tank.builder.normalizer`) is used at both build and verify time. This is the hash stability guarantee.

**normalized_content_hash** — SHA-256 of all chunk content strings, each normalized, concatenated in ascending chunk ID order with a `\n` separator. Changes only when text content changes (independent of metadata like heading paths or summaries). Stored in `manifest.json`. Verified at import time.

**owner** — optional governance field in `manifest.json` identifying the team or person responsible for the pack (e.g. `"platform-team"`). Not enforced by the policy engine in MVP; informational only.

**pack** — shorthand for a `.ctx` pack. See **`.ctx` pack`**.

**pack_digest** — SHA-256 of the full `.ctx` archive bytes, computed with the `pack_digest` field value in `manifest.json` set to `""`. Detects any tampering of the archive (content or metadata). Verified at import time.

**package** — the name component of a pack's identity, combined with `version` to form the unique identifier `package@version`. Set via `synd build <package>@<version>`. Stored in `manifest.json` and used as the primary lookup key in the `packages` table.

**page** — one source file processed during build. Each file becomes one page entry in `pages.json` with an ID, URL (relative path for local builds), title, and `content_hash`. Chunks reference their parent page via `page_id`.

**pages.json** — file inside a `.ctx` pack listing all pages (source files) with their metadata. Array of objects in page ID order.

**policy.toml** — TOML configuration file controlling what packs are allowed into the index. Specifies `allowed_lifecycle_states`, `require_signatures`, `rejected_doc_version_statuses`. Lookup order: `--policy` flag > `.synd/policy.toml` > `~/.synd/policy.toml` > permissive built-in defaults.

**policy_profile** — optional name in `manifest.json` that associates a pack with a specific policy profile in the consumer's `policy.toml`. For MVP, policies are global (not per-profile). Profile-based policy is a Phase 2 consideration.

**progressive disclosure** — the two-step query pattern. First call `search` to get summaries and chunk IDs (~20–40 tokens each). Then call `fetch` with the selected IDs to retrieve full content. Avoids paying for content the agent won't use.

**search** (MCP tool) — FTS5 full-text search across indexed documentation. Returns `heading_path`, `summary`, `chunk_id`, and provenance fields — **never full content**. Parameters: `query`, `packages` (optional scope), `limit` (default 10), `max_tokens` (optional budget). Use the returned `chunk_id` values to call `fetch`.

**source_commit** — optional provenance field on chunks and packs recording the git commit hash of the source repository at build time. `None` if not provided at `synd build`. Stored in `manifest.json` and the `chunks` table.

**source_url** — provenance field on chunks and pages indicating where the content came from. For local builds: relative path from `--source` root (e.g. `docs/auth/oauth.md`). For Phase 2 web builds: full `https://` URL. Always populated, never null.

**SyndError** — base exception class for all Synaptic Drift-specific errors. CLI commands catch subclasses and map them to exit codes and user-facing messages. Specific subclasses are discovered and added during TDD.

**token_count** — approximate token count per chunk, computed as `len(content) // 4`. Advisory field for agent budget planning. Not exact — documented as a rough estimate.

**WAL mode** — SQLite Write-Ahead Logging mode. Enabled on database creation. Allows concurrent reads while a write is in progress. Combined with a 5000ms busy timeout to handle concurrent access.
