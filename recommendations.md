# Tank — Architecture Review & Future-Facing Recommendations

## Identified Gaps

### 1. Concurrency and Multi-Agent Access

The architecture assumes a single writer at a time but does not specify behavior when multiple MCP server instances, CLI invocations, or AI agents access `index.db` concurrently. SQLite supports concurrent reads but serializes writes; without explicit WAL mode enablement and busy-timeout configuration, concurrent `tank pull` invocations will fail with `SQLITE_BUSY` errors. The HTTP transport compounds this — a persistent daemon could receive overlapping requests.

**Recommendation**: Enable WAL mode on database creation, set a busy timeout (e.g. 5000ms), and document that `tank pull` acquires an exclusive lock for the duration of its transaction. Consider advisory file locking on `index.lock` writes.

### 2. SQLite Schema Migration Strategy

`storage/db.py` is listed as handling "schema migrations" but no migration strategy is documented. Phase 2 adds columns to `pages` (etag, last_modified, fetched_at); Phase 3 adds columns to `chunks` (dense_embedding, sparse_weights). Without a defined migration mechanism, users upgrading between phases will face broken indexes or data loss.

**Recommendation**: Adopt a `user_version` pragma-based migration system. Store the current schema version in `PRAGMA user_version`, and on database open, run any pending migration scripts sequentially. Document that migrations are forward-only and non-destructive (ADD COLUMN, never DROP).

### 3. Non-Text Content Handling

The `.ctx` pack format and chunking pipeline are entirely text-oriented. Documentation frequently includes diagrams (SVG, PNG), screenshots, and embedded media. The architecture does not address how these are handled — silently dropped at build time, stored as binary blobs, or referenced as external URLs.

**Recommendation**: Define explicit behavior for non-text content at build time. For MVP, strip non-text assets and log a warning. For Phase 2, consider storing image references as metadata in `chunks.jsonl` (a `media_refs` array) so the agent can surface "this section includes a diagram at <url>" without embedding binary data.

### 4. Backup and Recovery

There is no documented strategy for backing up or recovering `index.db`. A corrupted or accidentally deleted database means re-pulling all packs. The lockfile (`index.lock`) partially mitigates this by recording what was imported, but it doesn't carry the chunk data needed to rebuild without the original `.ctx` files.

**Recommendation**: Document a recovery workflow: `tank rebuild --from-lockfile` that re-pulls all packs listed in `index.lock` from a local `.ctx` cache directory. Recommend users keep `.ctx` files in a known location or version-control the lockfile.

### 5. Observability and Error Reporting

No logging, metrics, or structured error reporting strategy is defined. When `tank query` returns poor results or `tank pull` fails in CI, there is no audit trail beyond exit codes. The MCP server is a long-running process with no health endpoint beyond `resolve-deps`.

**Recommendation**: Add structured logging (Python `logging` module with JSON formatter option) at key checkpoints: verify step results, import timing, query latency, FTS5 match counts. For the HTTP transport, add a `/health` endpoint returning server uptime, database size, and pack count.

### 6. Cross-Platform Path Handling

The archive safety validator rejects absolute paths and `../` traversal, but the validation rules are written in terms of Unix path separators. On Windows, backslash paths and UNC paths (`\\server\share`) are additional attack vectors. The `.tank/` directory convention also assumes Unix-style hidden directories.

**Recommendation**: Normalize all archive entry paths to forward slashes before validation. Add Windows-specific checks: reject entries containing backslashes, UNC prefixes, or drive letters (e.g. `C:\`). Document that `.tank/` is the canonical directory name on all platforms.

### 7. Chunk Size Tuning and Diagnostics

The architecture relies on `chunkana` for structural chunking but provides no guidance on target chunk sizes, maximum token counts, or what happens when a single section exceeds a reasonable token budget. `tank inspect` shows token distribution, but there's no mechanism to flag outlier chunks at build time.

**Recommendation**: Add configurable `max_chunk_tokens` (default: 2000) and `min_chunk_tokens` (default: 50) to `tank build`. Chunks exceeding the max should be split at paragraph boundaries; chunks below the min should be merged with adjacent siblings. Emit warnings for chunks that resist splitting (e.g. a single enormous code block).

### 8. Query Result Caching

Every `query-docs` call executes a fresh FTS5 query against SQLite. For MCP server sessions where the agent makes repeated similar queries (e.g. refining search terms), there is no caching layer. While individual queries are fast (<10ms), the cumulative overhead adds up in long sessions.

**Recommendation**: Add an optional LRU cache keyed on `(query, packages, detail, lifecycle_filter)` with a short TTL (e.g. 60 seconds) or invalidation on `tank pull`. This is low-priority given the sub-10ms target but becomes relevant at scale.

### 9. CI/CD Integration Guidance

The build-verify-pull pipeline maps naturally to CI but the architecture doesn't document how. Questions like "should CI build with `--lifecycle draft` and a human promote later?" and "how do you verify a .ctx artifact in a PR gate?" are left open.

**Recommendation**: Add a CI/CD section documenting: (a) build `.ctx` in CI with `--lifecycle draft`, (b) run `tank verify` as a PR check, (c) promote to `approved` post-merge via Phase 2's `tank promote`, (d) publish to registry. This also resolves the first open question about policy inheritance in CI.

### 10. Multi-Directory Source Tree Handling

`tank build --source <path>` accepts a single directory but the architecture does not specify how subdirectory trees are processed. Real documentation sets are almost always organized into nested directories (e.g. `docs/serving/`, `docs/deployment/`, `docs/api/`), each containing multiple Markdown files. The architecture is silent on:

- **Recursion behavior**: whether `--source ./docs` walks subdirectories or only reads top-level files. This must be explicitly defined — implicit recursion that varies by platform or `chunkana` version would break reproducibility.
- **Directory-to-metadata mapping**: whether the subdirectory path contributes to `heading_path` in `chunks.jsonl`. A file at `docs/serving/tls.md` with an `# Overview` heading could produce `heading_path: "Overview"` (file-scoped) or `heading_path: "serving / TLS / Overview"` (tree-scoped). The choice significantly affects search result quality and the agent's ability to disambiguate similarly-named sections across subdirectories.
- **Page identity in `pages.json`**: whether each file becomes a page entry, each directory becomes a page, or the mapping is configurable. This affects `page_id` references in chunks and the `content_hash` per page.
- **File ordering and chunk ID determinism**: `normalized_content_hash` is computed by concatenating chunk content in ascending `id` order. If chunk IDs are assigned by insertion order during build, then the directory walk order determines the hash. An unspecified walk order (e.g. `os.listdir` on Linux returns arbitrary order) means the same source tree produces different `normalized_content_hash` values on different machines or runs, breaking the integrity guarantee.
- **File filtering**: whether non-documentation files (images, config files, dotfiles) in the source tree are silently skipped, cause warnings, or cause build failures.

**Recommendation**: Define and document the following build behaviors:

1. `--source` recurses all subdirectories by default. Add `--no-recurse` for flat-only builds.
2. Files are discovered by extension whitelist: `.md`, `.html`, `.htm` for MVP. All other files are skipped with a debug-level log message.
3. Directory walk order is lexicographic (sorted by full relative path) to guarantee deterministic chunk ID assignment and reproducible `normalized_content_hash` across platforms and runs.
4. The relative path from `--source` root to each file is preserved as a `source_path` field in `pages.json` and used as a prefix in `heading_path` (e.g. `serving/tls.md` + `# Overview` produces `heading_path: "serving / TLS / Overview"`). This makes subdirectory structure searchable and aids disambiguation.
5. Add `--include` and `--exclude` glob patterns for fine-grained control over which files enter the build (e.g. `--exclude "**/internal/**"` to skip private docs).

---

## Language Recommendations

The architecture currently specifies Python exclusively. Below are three alternative language strategies with trade-offs, plus an assessment of the current Python choice.

---

### Option 1: Rust (core library + CLI + MCP server)

Rewrite the core in Rust, exposing both a native CLI and the MCP server as a single compiled binary. Use `rusqlite` for SQLite, `zip` crate for archive handling, and the Rust MCP SDK for server transport.

**Pros**:
- **Single-binary distribution**: no Python runtime, no virtualenv, no dependency conflicts. Users run `tank` immediately. This is a significant UX win for a tool that must integrate into diverse developer environments.
- **Memory safety without GC**: the archive safety validator is the security-critical hot path. Rust eliminates an entire class of memory bugs (buffer overflows, use-after-free) in the code that processes untrusted zip archives. This is not theoretical — zip parsers are a well-known attack surface.
- **Performance headroom**: sub-10ms FTS5 queries are achievable in Python, but Rust's zero-cost abstractions mean the normalization pipeline, hash computation, and archive validation will be 10-50x faster. This matters when building large documentation sets (thousands of pages) or re-indexing.
- **Cross-compilation**: Rust cross-compiles to Linux, macOS (ARM + x86), and Windows from a single CI pipeline. No platform-specific Python packaging issues.
- **Strong type system**: the manifest schema, lifecycle state machine, and policy engine all benefit from exhaustive enum matching and compile-time guarantees.

**Cons**:
- **Development velocity**: Rust's compile times and borrow checker increase iteration time, especially for the MCP server's request handling and the policy engine's config parsing. Expect 2-3x longer initial development compared to Python.
- **Ecosystem maturity for MCP**: the Rust MCP SDK is less mature than the official Python SDK. You may need to contribute upstream or maintain a fork for missing features.
- **Contributor barrier**: the target audience (enterprise teams managing AI agent documentation) is more likely to have Python expertise than Rust expertise. This limits external contributions and internal maintenance if the original authors move on.
- **`chunkana` integration**: `chunkana` is a Python library. You would need to either rewrite the chunking logic in Rust, use PyO3 to call into Python (defeating the single-binary goal), or find a Rust-native Markdown structural chunker.
- **Prototyping friction**: for a project still in Phase 1 with multiple open questions, Rust's rigidity penalizes design exploration. Changing the manifest schema or policy engine behavior requires more code changes than in a dynamic language.

---

### Option 2: TypeScript (MCP server) + Python (CLI and build tooling)

Split the system: write the MCP server in TypeScript (using the official TypeScript MCP SDK) and keep the CLI (`tank build`, `tank verify`, `tank pull`) in Python.

**Pros**:
- **MCP ecosystem alignment**: the MCP specification and reference implementations are TypeScript-first. The TypeScript SDK receives features and fixes before the Python SDK. Writing the server in TypeScript means fewer compatibility surprises and faster adoption of new MCP protocol features.
- **Deployment matches the consumer**: MCP clients (Claude Code, VS Code extensions, Cursor) are Electron/Node.js applications. A TypeScript MCP server can be distributed as an npm package and invoked via `npx`, which is already in every developer's PATH. No Python environment required on the client machine.
- **`better-sqlite3` performance**: the `better-sqlite3` Node.js binding is a synchronous, native SQLite wrapper that benchmarks comparably to `rusqlite`. FTS5 query performance will meet the sub-10ms target.
- **Async I/O model**: Node.js's event loop naturally handles the MCP server's concurrent read workload (multiple `query-docs` calls from an agent session) without threading complexity.
- **Keeps Python for build**: the build pipeline (`chunkana`, `hashlib`, `zipfile`) stays in Python where the dependencies exist and the code is already designed. No rewrite needed for the offline toolchain.

**Cons**:
- **Two-language codebase**: developers must context-switch between Python and TypeScript. Shared logic (normalization, manifest parsing, policy evaluation) must be implemented twice or extracted into a shared format (e.g. JSON schema for validation, WASM module for normalization). This is the biggest ongoing maintenance cost.
- **Normalization divergence risk**: the architecture explicitly requires that `tank.builder.normalizer` is the single code path for normalization at both build and verify time. A TypeScript MCP server that also verifies at query time (e.g. checking `content_hash` on cached results) would need a second normalization implementation, creating a hash stability risk.
- **Two package ecosystems**: publishing to both PyPI (`tank[build]`) and npm (`@tank/mcp-server`) doubles the release pipeline, versioning discipline, and user documentation. Enterprise users managing both `pip` and `npm` in locked-down environments may find this burdensome.
- **SQLite write contention**: `better-sqlite3` is synchronous. If the TypeScript server ever needs to write (Phase 2's `index-deps` tool), it will block the event loop during transactions. This constrains future server-side mutations.
- **Type safety gaps**: TypeScript's type system is structural and unsound in places (e.g. `any` escape hatch, no exhaustive enum matching without extra patterns). The policy engine and lifecycle state machine would be more robustly modeled in Python's `dataclasses` + `enum` or Rust's enums.

---

### Option 3: Go (CLI + MCP server, single binary)

Write both the CLI and MCP server in Go. Use `modernc.org/sqlite` (pure-Go SQLite) or `mattn/go-sqlite3` (CGo binding) for storage, and the Go MCP SDK for server transport.

**Pros**:
- **Single static binary**: like Rust, Go produces a self-contained binary with no runtime dependencies. `go build` produces cross-platform executables trivially. Distribution is a single file download or `go install`.
- **Concurrency model**: Go's goroutines and channels are a natural fit for the HTTP MCP transport's concurrent request handling. The `tank pull` pipeline (verify steps running in sequence, with parallel chunk insertion) maps cleanly to goroutine orchestration.
- **Fast compilation**: Go compiles in seconds, not minutes. This keeps the development feedback loop tight during Phase 1's iterative design period.
- **Mature SQLite bindings**: `mattn/go-sqlite3` is battle-tested in production systems handling millions of queries. WAL mode, busy timeouts, and concurrent read/write patterns are well-documented.
- **Enterprise adoption**: Go is the dominant language for infrastructure tooling in enterprise environments (Kubernetes, Terraform, Docker). Teams already running Tank in enterprise contexts are likely to have Go expertise and CI pipelines configured for Go builds.
- **Strong standard library**: `archive/zip`, `crypto/sha256`, `encoding/json`, and `net/http` cover the archive validator, hash chain, manifest parsing, and HTTP transport without third-party dependencies.

**Cons**:
- **No `chunkana` equivalent**: Go lacks a structural Markdown chunker comparable to `chunkana`. You would need to write one (significant effort) or shell out to a Python subprocess at build time (adds a Python dependency for build, partially defeating the single-binary advantage).
- **Error handling verbosity**: Go's explicit `if err != nil` pattern adds significant boilerplate to the 8-step validation sequence and the manifest parsing logic. The verify pipeline alone would be substantially more code than the Python equivalent.
- **MCP SDK maturity**: the Go MCP SDK is community-maintained and less complete than the official Python and TypeScript SDKs. Missing features (e.g. streamable HTTP transport, tool annotations) may require upstream contributions.
- **Weaker type expressiveness**: Go lacks sum types, pattern matching, and generics maturity. The lifecycle state machine (`draft → approved → deprecated → revoked`) cannot be modeled as a compile-time-exhaustive enum the way it can in Rust. Invalid state transitions would be caught at runtime, not compile time.
- **Module/package overhead**: Go's module system requires explicit package boundaries that may feel heavy for a project of this size. The `src/tank/` Python package structure with its `__init__.py` files is more compact.
- **FTS5 tokenizer customization**: if you later need custom tokenizers for FTS5 (e.g. code-aware tokenization), Go's CGo boundary makes this harder to implement than Python's C extension or Rust's FFI.

---

### Option 4: Stay with Python (current choice, with targeted hardening)

Keep the entire stack in Python as designed. Address the gaps above within the Python ecosystem.

**Pros**:
- **Zero rewrite cost**: the architecture is already designed for Python. All dependencies (`chunkana`, `mcp`, `click`, `rich`) are Python-native. Development can start immediately.
- **Fastest time to MVP**: Python's dynamic typing and REPL-driven development allow rapid iteration on the open questions (summary generation, policy merge semantics, CI promotion workflow) without fighting a compiler.
- **Unified normalization**: the `tank.builder.normalizer` single-code-path guarantee is trivially maintained when everything is Python. No cross-language hash divergence risk.
- **`chunkana` is Python**: the chosen structural chunker is a Python library. No FFI bridge, no subprocess overhead, no rewrite.
- **PyPI distribution is sufficient**: `pip install tank` and `pip install tank[build]` cover the two deployment profiles. Enterprise Python environments (conda, poetry, uv) handle this well.

**Cons**:
- **Runtime dependency**: users must have Python 3.11+ installed. In enterprise environments with locked-down system images, getting the right Python version can be a blocker. Virtual environments add friction compared to a single binary.
- **Startup latency**: Python's import time means the MCP server takes 200-500ms to cold-start. For stdio transport (spawned per session), this is noticeable. For HTTP transport (persistent daemon), it's a one-time cost.
- **Archive validator in Python**: the security-critical archive validation path runs in an interpreted language. While Python's `zipfile` module delegates to C for decompression, the path traversal checks, hash computation, and size enforcement are pure Python. A maliciously crafted archive could exploit Python-level slowness for denial-of-service during `tank verify`.
- **GIL limitations**: the HTTP transport serving concurrent `query-docs` requests is constrained by Python's GIL. While SQLite FTS5 queries release the GIL during C-level execution, the Python-level result serialization and attribution JOIN processing do not. Under high concurrency (unlikely for local-first, but possible in team-server scenarios), this becomes a bottleneck.
- **No compile-time safety net**: manifest schema changes, policy engine logic errors, and lifecycle state machine bugs are caught at test time rather than compile time. The architecture acknowledges this implicitly by requiring "the test suite covers archive safety, manifest validation, import, and query attribution."

---

## Summary Matrix

| Criterion | Rust | TypeScript + Python | Go | Python (current) |
|---|---|---|---|---|
| Time to MVP | Slow | Medium | Medium | **Fast** |
| Distribution simplicity | **Single binary** | Two ecosystems | **Single binary** | Requires Python runtime |
| MCP SDK maturity | Low | **High** | Low | **High** |
| Security-critical code safety | **Strongest** | Moderate | Strong | Moderate |
| `chunkana` integration | Difficult | Easy (Python side) | Difficult | **Native** |
| Enterprise deployment | Strong | Mixed | **Strong** | Moderate |
| Normalization consistency | Needs reimpl | **Risk of divergence** | Needs reimpl | **Guaranteed** |
| Long-term maintainability | High | Medium (two langs) | High | Medium |
| Contributor accessibility | Low | High | Medium | **High** |

## Recommendation

For Phase 1 (MVP), stay with Python. The open questions, rapid iteration needs, and `chunkana` dependency all favor it. The architecture is well-designed for Python and the gaps identified above are addressable within the Python ecosystem.

For Phase 2+, evaluate a Rust rewrite of the core library (archive validator, normalizer, hash chain, SQLite storage) exposed as a Python extension via PyO3. This gives you Rust's safety guarantees on the security-critical path while keeping the Python MCP server and CLI as thin wrappers. The `tank` PyPI package would ship a native wheel — no Rust toolchain required for users, no Python runtime required for the compiled core. This hybrid approach avoids the "rewrite everything" risk while hardening the components that matter most.
