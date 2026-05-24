# Tank — Semver Roadmap

## Current Focus — v0.2.0

v0.1.1 is complete. Active development is on `feature/mcp` targeting v0.2.0.

**Implementation complete (205/206 tests passing):**
- MCP two-tool refactor (`search` / `fetch`)
- `tank serve` CLI command
- FTS5 `heading_path` column with 2.5× BM25 weight
- Full docs refresh (MCP.md, ranking.md, architecture.md, roadmap.md)

**Next up:** PyPI release (blocked on packaging), `schemas/manifest.v2.schema.json`, `tank init`, URL fetch sources.

---

## v0.1.0 — "MVP" ✓

**Theme**: Working end-to-end implementation. Build, verify, pull, query.

**Status**: Tagged. Not on PyPI (blocked — see v0.2.0).

- [x] `tank build` — source tree → `.ctx` pack (Markdown/HTML, lexicographic walk, deterministic chunk IDs)
- [x] `tank verify` — 8-step archive safety validator, policy enforcement, `pack_digest` integrity check
- [x] `tank pull` — verify-before-import, atomic SQLite transaction, WAL mode
- [x] `tank query` — FTS5 BM25 search with source attribution
- [x] MCP server — `query-docs` and `resolve-deps` tools over stdio
- [x] Policy engine — lifecycle state gating (`draft` / `approved` / `deprecated` / `revoked`)
- [x] CI workflow — lint, typecheck, test on push/PR
- [x] Release workflow — builds wheel + `.ctx` packs on `v*` tags, creates GitHub release
- [x] fastmcp@3.3.0 `.ctx` pack — first release artifact (1190 chunks)
- [x] mypy clean — builder type errors resolved

---

## v0.1.1 — "Bug Fixes + Benchmarks"

**Theme**: Fix data integrity bugs found post-tag; ship benchmark infrastructure.

- [x] Polish README — "implementation is beginning" replaced with accurate status
- [x] Expose `limit` parameter on `query-docs` MCP tool and `query_docs()`
- [x] Token overhead benchmark harness — `tests/benchmarks/test_token_overhead.py` with baseline at `tests/benchmarks/results/v0.1.0.json`
- [x] GitHub Actions benchmark workflow — PR delta comparison via `tests/benchmarks/compare.py`
- [x] WebFetch vs Tank benchmark — `tests/benchmarks/test_webfetch_vs_tank.py` with fastmcp fixture
- [x] Extend PR comment bot to include WebFetch vs Tank results alongside token overhead
- [x] Benchmark output cleanup — PR comment redesigned with plain-English headline table and collapsed detail; raw JSON dump replaced with formatted standalone output. Console output unchanged (runs under `-s`, not in reviewers' way).
- [x] Implement or remove unused `max_tokens` parameter in `src/tank/server.py`
- [x] Docs cleanup — consolidate `.work/` artifacts, merge `todo.md` into `roadmap.md`, migrate gotchas to `CLAUDE.md`, absorb `ultraplan` findings into canonical docs
- [ ] Build and ship mcp@2025-11-25 as pack #2 for the v0.1.1 release artifact — `mkdir /tmp/mcp-docs && curl -o /tmp/mcp-docs/mcp.md https://modelcontextprotocol.io/llms-full.txt && tank build mcp@2025-11-25 --source /tmp/mcp-docs --output ./packs`

---

## v0.2.0 — "First Users"

**Theme**: Make it effortless to start. Polish the rough edges that stop adoption.

### Completed

- [x] **MCP two-tool refactor** — replace `query-docs` (single tool with `detail` parameter) with separate `search` (summaries + chunk IDs) and `fetch` (full content by ID) tools. Enforces the two-step agent pattern structurally.
- [x] **`tank serve` CLI command** — `tank serve` launches the MCP stdio server, discoverable from `tank --help`. Replaces the undiscoverable `python -m tank.server` invocation.
- [x] **MCP documentation refresh** — `docs/MCP.md` rewritten with accurate `search`/`fetch` API; all config examples updated to `tank serve`; `README.md` MCP snippet updated with `cwd`.
- [x] **FTS5 heading_path + BM25 weight tuning** — `heading_path` added as first column in `chunks_fts` with 2.5× weight; BM25 tuned to heading 2.5× > summary 1.5× > content 1.0×.

### Foundation — no blockers, start now

- [ ] **`schemas/manifest.v2.schema.json`** — machine-readable JSON Schema as single source of truth for manifest fields; wire verifier to validate against it. Establishes a stable schema contract before PyPI release.
- [ ] **Cross-platform path handling** — normalize to forward slashes, reject backslashes/UNC in validator. Modify `src/tank/validator/verify.py`
- [ ] **Error message polish** — every error path produces an actionable message. Audit all `TankError` subclass usage
- [ ] **Lockfile in git** — document committing `.tank/index.lock` for reproducible team setups

### Chunker quality stream — S7 → chunker → S2 → summary

- [ ] **Custom markdown chunker** — replace chunkana with a `markdown-it-py`-backed chunker that splits at all heading levels (`#` through `######`), keeps code fences atomic, and builds `heading_path` accurately by construction. Removes the `##`-only limitation that produces 900-token multi-section chunks. See `decisions.md` D14.
  - *Requires [S7](docs/spikes.yaml) (custom chunker implementation plan) to be completed before work can begin.*
  - Replace `src/tank/builder/chunking.py`; remove chunkana from dependencies; add `markdown-it-py>=3.0`
- [ ] **Chunk size tuning** — `max_chunk_tokens` / `min_chunk_tokens` in `tank build`. Modify `src/tank/builder/chunking.py`
- [ ] **Heading-aware summary heuristic** — prefix chunk summaries with the leaf heading node (`"STDIO Transport: STDIO is the default transport..."` instead of `"You can now run this server..."`). Eliminates false-positive summaries for chunks that open with transitional sentences or code. See `decisions.md` D13.
  - *Requires [S2](docs/spikes.yaml) (heading-aware summary implementation) to be completed before work can begin. Benefits from the custom chunker landing first — accurate `heading_path` at all levels makes the prefix reliable.*
  - Modify `generate_summary()` in `src/tank/builder/chunking.py`; no schema changes

### URL fetch stream — S6 → llms-full.txt → (S8 in parallel) → llms.txt → packs

- [ ] **`tank build --source <url>/llms-full.txt`** — fetch a `llms-full.txt` URL, preprocess it into per-page documents, chunk and build a `.ctx` pack.
  - *Requires [S6](docs/spikes.yaml) (HTML-to-markdown library selection) to be completed before work can begin.*
  - Modify `src/tank/builder/build.py` to accept URL sources
  - New module: `src/tank/builder/fetch.py` (single-file HTTP fetch, no crawl logic)
  - New module: `src/tank/builder/llms_full.py` — Mintlify-aware preprocessor:
    - Split on `Source: <url>` boundary lines to recover individual pages
    - Strip MDX/JSX tags (e.g. `<FeatureBadge />`, `<Note>`, `<McpClient>`, `<Icon />`, inline `<sup><a ...>`) — keep inner text, discard component wrappers
    - Use each `Source:` URL as the page `source_url`; derive page title from the first `#` heading
    - Feed resulting per-page documents into the existing chunker individually so `heading_path` values are page-relative and meaningful
  - **Note:** `llms-full.txt` from Mintlify-based docs sites (FastMCP, MCP, and many others) is a raw MDX concatenation, not clean markdown. Passing it through the existing pipeline without preprocessing produces garbage heading paths (`llms-full / \`ClassName\` <sup>...</sup>`), polluted summaries (`Source: https://...`), and section collisions (identical heading names from different pages merged). The preprocessor is required for usable pack quality, not optional.
- [ ] **`tank build --source <url>/llms.txt`** — fetch `llms.txt` index, fetch each linked page individually, chunk and build a `.ctx` pack. Higher quality than `llms-full.txt`: each page is fetched as rendered HTML→markdown, giving page-relative heading paths and clean structure. Basic rate limiting + `User-Agent`.
  - *Requires [S6](docs/spikes.yaml) (HTML-to-markdown library selection) and [S8](docs/spikes.yaml) (web page to markdown pipeline research) to be completed before work can begin.*
  - Extend `src/tank/builder/fetch.py` to handle `llms.txt` index parsing and per-page fetching
  - Strip inline MDX/JSX callout tags (`<Tip>`, `<Note>`, `<Warning>`, `<Info>`, etc.) — keep inner text
  - Use the page URL as `source_url`; derive title from first `#` heading
- [ ] **Pre-built packs for top 20 libraries** — built in CI from `llms-full.txt`, published as GitHub Releases (FastAPI, Django, Flask, SQLAlchemy, Pydantic, React, Next.js, Express, Prisma, etc.)

### FTS5 tuning — parallel, no blockers

- [ ] **FTS5 search quality** — two remaining improvements:
  - [ ] Query preprocessing: stopword filtering, term normalization
  - [ ] Synonym expansion: `auth` → `authentication`, `JWT` → `JSON Web Token`, etc.
- [ ] **Query latency benchmark** — measure actual FTS5 query time against a representative index (target: 100K chunks); replace the unbenchmarked sub-10ms claim in `architecture.md` with a measured number. Add to `tests/benchmarks/` alongside the existing token overhead and WebFetch benchmarks.

### Release — after foundation + S5

- [ ] **PyPI release** (`pip install tank`, `pip install tank[build]`) — blocked on resolving the MCP server packaging: either a CLI-only release that excludes the server, or a refactor of the server layer to remove the dependency conflict. Release workflow already produces artifacts; needs a `twine upload` / `pypi-publish` step once unblocked.
  - *Requires [S5](docs/spikes.yaml) (PyPI packaging diagnosis) to be completed before work can begin.*
- [ ] **Validator optimization** — refactor `_read_archive_bytes()` to avoid full in-memory ZIP reconstruction for digest computation. The current implementation reads the entire ZIP into memory, then reconstructs a second in-memory ZIP — decompressing and re-compressing every file — solely to zero out `pack_digest` and hash the result. Near the 500MB archive limit this allocates 500MB+, decompresses everything, and holds it all in memory simultaneously. Fix: hash individual entries in a defined order instead of reconstructing the archive.

### Discovery — after PyPI release + pre-built packs

- [ ] **`tank init`** — scan project deps, download pre-built packs, configure MCP server
  - New module: `src/tank/cli/init.py`
  - Parse `requirements.txt`, `pyproject.toml`, `package.json`, `Cargo.toml`
  - Map package names to `.ctx` pack URLs (static JSON registry on GitHub)
  - Generate MCP config (`.cursor/mcp.json` or Claude Code equivalent)

---

## v0.3.0 — "Growth"

**Theme**: Multi-user, multi-project, CI-integrated. Start looking like infrastructure.

- [ ] **`tank build --source <url>`** — general web crawler: follow links from a docs site root, fetch and chunk all reachable pages. For sites without `llms.txt` or `llms-full.txt`. Rate limiting, `robots.txt` compliance, configurable `User-Agent`. No embeddings or JS rendering — static HTML only.
  - New module: `src/tank/builder/crawler.py`
  - Extend `src/tank/builder/fetch.py` with link extraction and crawl frontier logic
- [ ] **Pack registry (static hosting)** — `tank pull fastapi@0.115.0` resolves against a registry index (JSON manifest on CDN or GitHub Pages). No auth. Read-only.
  - New module: `src/tank/registry/` (client only; server is a static file host)
  - `tank pull` accepts `package@version` in addition to file paths
- [ ] **CI/CD templates** — GitHub Actions, GitLab CI, CircleCI: build packs on release, verify in PRs, publish to static registry
- [ ] **Pre-built packs for top 100 libraries** — scale up pack-building CI pipeline
- [ ] **Token budget intelligence** — `max_tokens` on `search`/`fetch` controls response size, balancing breadth vs. depth within the budget
- [ ] **`index-deps` MCP tool** — scans project deps, reports which have packs available, which are indexed, which are stale
- [ ] **Staleness detection** — compare indexed pack versions against project lockfiles. Surface warnings via `index-deps` MCP tool
- [ ] **Structured logging** — JSON logging at key checkpoints. `python logging` with configurable verbosity

---

## v1.0.0 — "Enterprise-Ready"

**Theme**: Trust, governance, and operational maturity. The version you'd sell to an enterprise security team.

- [ ] **Schema migrations** — `PRAGMA user_version`-based forward-only migrations. Modify `src/tank/storage/db.py`. Must land before any new column additions.
- [ ] **Real signature verification** — Step 8 currently only checks file existence. Implement ed25519 or Sigstore. Modify `src/tank/validator/verify.py`, add `src/tank/signing/`
- [ ] **Observability** — health endpoint for HTTP transport, query latency metrics, import audit trail. Modify `src/tank/server.py`
- [ ] **Multi-project support** — configurable `.tank/` location, monorepo workspace support
- [ ] **Policy profiles** — per-team/per-workspace policy overrides
- [ ] **Audit logging** — who imported what, when, from where. New `audit_log` table in `index.db`
- [ ] **Backup and recovery** — `tank rebuild --from-lockfile`
- [ ] **Comprehensive documentation** — man pages, API reference, enterprise deployment guide

---

## v1.1 — "Smarter Search" *(contingency)*

**Theme**: Hybrid search if FTS5 tuning proves insufficient. Gate on evidence, not schedule.

**Trigger**: Real user feedback shows vocabulary-mismatch failures on semantic queries that tuned FTS5 cannot address.

- [ ] **Import-side embeddings** — BGE-M3 dense + sparse vectors computed at `tank pull` time, stored in `index.db`. Pack format unchanged — no embedding vectors in `.ctx` files.
- [ ] Hybrid search: dense cosine + BGE-M3 sparse + FTS5, fused with Reciprocal Rank Fusion (RRF)
- [ ] `tank[embeddings]` optional dependency group (`pip install tank[embeddings]`)
- [ ] Re-embedding on model change (stored chunk text → new vectors, no re-pull required)
