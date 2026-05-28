# Synaptic Drift — Semver Roadmap

## Current Focus — v0.2.0

v0.1.1 is complete. Active development is on `feature/mcp` targeting v0.2.0.

**Implementation complete (205/206 tests passing):**
- MCP two-tool refactor (`search` / `fetch`)
- `synd serve` CLI command
- FTS5 `heading_path` column with 2.5× BM25 weight
- Full docs refresh (MCP.md, ranking.md, architecture.md, roadmap.md)

**Next up:** PyPI release (blocked on packaging), `tank init`, URL fetch sources (S6 done; S7, S8 open).

---

## v0.1.0 — "MVP" ✓

**Theme**: Working end-to-end implementation. Build, verify, pull, query.

**Status**: Tagged. Not on PyPI (blocked — see v0.2.0).

- [x] `synd build` — source tree → `.ctx` pack (Markdown/HTML, lexicographic walk, deterministic chunk IDs)
- [x] `synd verify` — 8-step archive safety validator, policy enforcement, `pack_digest` integrity check
- [x] `synd pull` — verify-before-import, atomic SQLite transaction, WAL mode
- [x] `synd query` — FTS5 BM25 search with source attribution
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
- [x] WebFetch vs Synaptic Drift benchmark — `tests/benchmarks/test_webfetch_vs_tank.py` with fastmcp fixture
- [x] Extend PR comment bot to include WebFetch vs Synaptic Drift results alongside token overhead
- [x] Benchmark output cleanup — PR comment redesigned with plain-English headline table and collapsed detail; raw JSON dump replaced with formatted standalone output. Console output unchanged (runs under `-s`, not in reviewers' way).
- [x] Implement or remove unused `max_tokens` parameter in `src/tank/server.py`
- [x] Docs cleanup — consolidate `.work/` artifacts, merge `todo.md` into `roadmap.md`, migrate gotchas to `CLAUDE.md`, absorb `ultraplan` findings into canonical docs
- [x] Build and ship mcp@2025-11-25 as pack #2 for the v0.1.1 release artifact — `mkdir /tmp/mcp-docs && curl -o /tmp/mcp-docs/mcp.md https://modelcontextprotocol.io/llms-full.txt && synd build mcp@2025-11-25 --source /tmp/mcp-docs --output ./packs`

---

## v0.2.0 — "First Users"

**Theme**: Make it effortless to start. Polish the rough edges that stop adoption.

### Completed

- [x] **MCP two-tool refactor** — replace `query-docs` (single tool with `detail` parameter) with separate `search` (summaries + chunk IDs) and `fetch` (full content by ID) tools. Enforces the two-step agent pattern structurally.
- [x] **`synd serve` CLI command** — `synd serve` launches the MCP stdio server, discoverable from `tank --help`. Replaces the undiscoverable `python -m tank.server` invocation.
- [x] **MCP documentation refresh** — `docs/MCP.md` rewritten with accurate `search`/`fetch` API; all config examples updated to `synd serve`; `README.md` MCP snippet updated with `cwd`.
- [x] **FTS5 heading_path + BM25 weight tuning** — `heading_path` added as first column in `chunks_fts` with 2.5× weight; BM25 tuned to heading 2.5× > summary 1.5× > content 1.0×.

### Foundation — no blockers, start now

- [x] **`schemas/manifest.v2.schema.json`** — machine-readable JSON Schema as single source of truth for manifest fields; wire verifier to validate against it. Establishes a stable schema contract before PyPI release.
- [x] **Cross-platform path handling** — normalize to forward slashes, reject backslashes/UNC in validator. Modify `src/tank/validator/verify.py`
- [x] **Error message polish** — every error path produces an actionable message. Audit all `SyndError` subclass usage
- [x] **Lockfile in git** — `synd.lock` at project root, written by `synd add`; commit to version-control documentation dependencies analogous to `Cargo.lock`
- [x] **`synd add` (renamed from `synd pull`)** — `synd pull` was misleading (implies remote fetch; only imports local files). Renamed to `synd add`, consistent with `cargo add`, `uv add`, `npm install <pkg>`. `synd pull` kept as a hidden deprecated alias. See `decisions.md` D19.
- [x] **`synd sync`** — reads `synd.lock`, skips already-imported packs (idempotent), verifies digest against lockfile before importing (supply-chain check), imports any missing packs. Enables `git clone && synd sync` workflow. HTTPS `source_url` fetch deferred until URL fetcher module lands (exits with actionable `FetchError`). See `src/tank/cli/sync.py`.
- [x] **`synd remove`** — removes a pack from `index.db` and rewrites `synd.lock`. Completes the verb set: without it, removing a pack requires hand-editing the lockfile. See `src/tank/cli/remove.py`.

### Chunker quality stream — S7 → chunker → S2 → summary

- [x] **Custom markdown chunker** — replace chunkana with a `markdown-it-py`-backed chunker that splits at all heading levels (`#` through `######`), keeps code fences atomic, and builds `heading_path` accurately by construction. Removes the `##`-only limitation that produces 900-token multi-section chunks. See `decisions.md` D14.
  - Replace `src/synd/builder/chunking.py`; remove chunkana from dependencies; add `markdown-it-py>=3.0`
- [x] **Heading-aware summary heuristic** — prefix chunk summaries with the leaf heading node (`"STDIO Transport: STDIO is the default transport..."` instead of `"You can now run this server..."`). Eliminates false-positive summaries for chunks that open with transitional sentences or code. See `decisions.md` D13.
  - Modify `generate_summary()` in `src/synd/builder/chunking.py`; no schema changes
- [x] **MDX Tab body de-indentation and pipeline order fix** — three cooperating bugs caused Mintlify tutorial pages (`build-server`, `build-client`) to produce single 15k–22k token chunks instead of per-section splits. See `decisions.md` for details.
  - `strip_mdx` was running before `unwrap_jsx_blocks`, destroying `<Tab>…</Tab>` pairs before they could be processed
  - `unwrap_jsx_blocks` was leaving Tab inner content 4-space indented; `markdown-it-py` parsed headings and prose as `code_block` tokens
  - Fences inside Tab bodies had indented closing `\`\`\`` lines (4+ spaces); CommonMark requires ≤3 spaces on a closing fence, so `markdown-it-py` never closed them and treated the rest of the page as fence content
  - Fixed in `src/synd/builder/mdx.py`: swap pipeline order, `textwrap.dedent()` in `unwrap_jsx_blocks`, `_INDENTED_FENCE_CLOSE_RE` in `_extract_code_fences`
  - Result: `build-server` 22,496t → 111 chunks (max 1,065t); `build-client` 15,172t → 99 chunks (max 651t)
- [ ] **Chunk size tuning** — `max_chunk_tokens` / `min_chunk_tokens` CLI params on `synd build`. See [S9](docs/spikes.yaml).
  - Modify `src/synd/builder/chunking.py` and `src/synd/cli/build.py`
- [ ] **Minimum-token merge** — post-chunking pass that absorbs stub chunks (heading-only, <20 tokens) into their neighbours. The MCP pack has 280 stubs from headings immediately followed by another heading. See [S10](docs/spikes.yaml).
  - Modify `src/synd/builder/chunking.py`
- [ ] **Tab heading disambiguation** — chunks produced by expanding Mintlify `<Tabs>` blocks carry identical `heading_path` values across all language tabs. BM25 cannot distinguish "Python / Implementing tool execution" from "TypeScript / Implementing tool execution" because the tab title is discarded during unwrapping.

  **Reproduction** (requires a built MCP pack):
  ```bash
  synd build mcp@2025-11-25 --source https://modelcontextprotocol.io/llms-full.txt --output /tmp/mcp-pack
  unzip -p /tmp/mcp-pack/mcp@2025-11-25.ctx chunks.jsonl | python3 -c "
  import json, sys
  from collections import Counter
  chunks = [json.loads(l) for l in sys.stdin if l.strip()]
  bs = [c for c in chunks if 'build-server' in c['source_url']]
  paths = Counter(c['heading_path'] for c in bs)
  for path, cnt in paths.most_common(5):
      print(f'x{cnt}  {path}')
  "
  # Output: x15  docs/develop/build-server / Testing your server with Claude for Desktop
  #         x8   docs/develop/build-server / Building your server
  #         x8   docs/develop/build-server / Building your server / Running the server
  # build-server has 111 chunks but only 45 unique heading_paths (7+ language tabs × shared structure)
  ```

  **Root cause**: `unwrap_jsx_blocks` in `src/synd/builder/mdx.py` discards the `title` attribute of `<Tab title="Python">` when extracting the inner content. The chunker receives a flat document with no language context; all 7 language tabs' sections share the same `heading_path`.

  **Recommended solution**: in `unwrap_jsx_blocks`, when handling a `<Tab title="...">` element (not `<Tabs>` or other block tags), extract the `title` attribute and rewrite the Tab body so that all headings inside are shifted one level deeper, then inject the title as a heading at the level of the Tab's shallowest heading. Example:

  ```
  Before (inside <Tab title="Python">):
    ### Importing packages
    ### Implementing tool execution

  After unwrapping with title injection (shallowest was ###, so inject ## Python,
  shift ### → ####):
    ## Python
    #### Importing packages
    #### Implementing tool execution
  ```

  This produces `heading_path = "docs/develop/build-server / Building your server / Python / Implementing tool execution"`, fully disambiguating all language tabs. The depth-shift ensures the tab title stays in scope across all sections within the tab, rather than being immediately popped by a same-level sibling heading.

  Implementation sketch:
  1. Parse `title` from `<Tab title="...">` — add a named group to `_JSX_UNWRAP_RE` or handle `Tab` specially before the generic unwrap loop
  2. Detect the minimum heading level in the Tab body (e.g. H3)
  3. Shift all headings in the body one level deeper (H3 → H4, H4 → H5)
  4. Prepend `## {title}\n\n` (one level above the shifted headings) to the dedented body
  5. Non-`Tab` tags (Note, Warning, Tabs, Frame, etc.) are unaffected — only `Tab` injects a heading

  Modify: `src/synd/builder/mdx.py` (`unwrap_jsx_blocks`); add tests in `tests/test_builder/test_mdx.py` covering single Tab, multi-Tab, and nested Tab > Note.

### URL fetch stream — S6 → llms-full.txt → (S8 in parallel) → llms.txt → packs

- [x] **`synd build --source <url>/llms-full.txt`** — fetch a `llms-full.txt` URL, preprocess it into per-page documents, chunk and build a `.ctx` pack.
  - *[S6](docs/spikes.yaml) done — `html_to_markdown()` in `src/synd/builder/fetch.py`, `markdownify` in core deps.*
  - `src/synd/builder/build.py` accepts URL sources via `build_pack_from_url()`
  - `src/synd/builder/fetch.py` — `fetch_text()` and `fetch_page()` using `urllib.request`; content routing: `.md` → `process_mdx()`, else → `html_to_markdown()`
  - `src/synd/builder/llms_full.py` — Mintlify-aware preprocessor:
    - Split on `Source: <url>` boundary lines to recover individual pages
    - Strip MDX/JSX tags (e.g. `<FeatureBadge />`, `<Note>`, `<McpClient>`, `<Icon />`, inline `<sup><a ...>`) — keep inner text, discard component wrappers
    - Use each `Source:` URL as the page `source_url`; derive page title from the first `#` heading
    - Feed resulting per-page documents into the existing chunker individually so `heading_path` values are page-relative and meaningful
  - `src/synd/builder/mdx.py` — `process_mdx()` pipeline: strip MDX imports/exports, unwrap JSX blocks, clean headings, collapse blank lines. See D21.
- [x] **`synd build --source <url>/llms.txt`** — fetch `llms.txt` index, fetch each linked page individually, chunk and build a `.ctx` pack. Higher quality than `llms-full.txt`: each page is fetched individually, giving page-relative heading paths and clean structure. Basic rate limiting + `User-Agent`.
  - *[S6](docs/spikes.yaml) done. [S8](docs/spikes.yaml) done — see D21.*
  - **Mintlify behaviour**: `llms.txt` on Mintlify sites already contains `.md` URLs (no URL manipulation needed). Fetching them returns MDX directly — no HTML-to-markdown conversion required. JSX components (`<Frame>`, `<Note>`, `<Tabs>`, `<Warning>`, etc.) must still be stripped; inner text kept, wrappers discarded. Images inside `<Frame>` are discarded.
  - For non-Mintlify sites (ReadTheDocs, Docusaurus, etc.): HTML fetch → `html_to_markdown()` via markdownify + BeautifulSoup4
  - Use the page URL as `source_url`; derive title from first `#` heading
- [ ] **Pre-built packs for top 20 libraries** — built in CI from `llms-full.txt`, published as GitHub Releases (FastAPI, Django, Flask, SQLAlchemy, Pydantic, React, Next.js, Express, Prisma, etc.)

### FTS5 tuning — parallel, no blockers

- [ ] **FTS5 search quality** — two remaining improvements:
  - [x] Query sanitization: FTS5 special characters stripped in `fts.py` (prevents crashes on `mcp.tool` style queries)
  - [ ] Query preprocessing: stopword filtering, term normalization
  - [ ] Synonym expansion: `auth` → `authentication`, `JWT` → `JSON Web Token`, etc.
- [ ] **Query latency benchmark** — measure actual FTS5 query time against a representative index (target: 100K chunks); replace the unbenchmarked sub-10ms claim in `architecture.md` with a measured number. Add to `tests/benchmarks/` alongside the existing token overhead and WebFetch benchmarks.

### Release — after foundation + S5

- [ ] **PyPI release** (`pip install synaptic-drift`, `pip install synaptic-drift[build]`) — blocked on resolving the MCP server packaging: either a CLI-only release that excludes the server, or a refactor of the server layer to remove the dependency conflict. Release workflow already produces artifacts; needs a `twine upload` / `pypi-publish` step once unblocked.
  - *[S5](docs/spikes.yaml) resolved — optional `[serve]` extra approach confirmed. Needs `twine upload` / `pypi-publish` step wired into release workflow.*
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

- [ ] **`synd build --source <url>`** — general web crawler: follow links from a docs site root, fetch and chunk all reachable pages. For sites without `llms.txt` or `llms-full.txt`. Rate limiting, `robots.txt` compliance, configurable `User-Agent`. No embeddings or JS rendering — static HTML only.
  - New module: `src/tank/builder/crawler.py`
  - Extend `src/tank/builder/fetch.py` with link extraction and crawl frontier logic
- [ ] **Pack registry (static hosting)** — `synd add fastapi@0.115.0` resolves against a registry index (JSON manifest on CDN or GitHub Pages). No auth. Read-only.
  - New module: `src/tank/registry/` (client only; server is a static file host)
  - `synd add` accepts `package@version` in addition to file paths
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
- [ ] **Multi-project support** — configurable `.synd/` location, monorepo workspace support
- [ ] **Policy profiles** — per-team/per-workspace policy overrides
- [ ] **Audit logging** — who imported what, when, from where. New `audit_log` table in `index.db`
- [ ] **Backup and recovery** — `tank rebuild --from-lockfile`
- [ ] **Comprehensive documentation** — man pages, API reference, enterprise deployment guide

---

## v1.1 — "Smarter Search" *(contingency)*

**Theme**: Hybrid search if FTS5 tuning proves insufficient. Gate on evidence, not schedule.

**Trigger**: Real user feedback shows vocabulary-mismatch failures on semantic queries that tuned FTS5 cannot address.

- [ ] **Import-side embeddings** — BGE-M3 dense + sparse vectors computed at `synd add` time, stored in `index.db`. Pack format unchanged — no embedding vectors in `.ctx` files.
- [ ] Hybrid search: dense cosine + BGE-M3 sparse + FTS5, fused with Reciprocal Rank Fusion (RRF)
- [ ] `synaptic-drift[embeddings]` optional dependency group (`pip install synaptic-drift[embeddings]`)
- [ ] Re-embedding on model change (stored chunk text → new vectors, no re-pull required)
