# Tank — Semver Roadmap

## v0.1.0 — "Ship It"

**Theme**: Get on PyPI. Make it installable. Let people try it.

**Status**: Tagged. PyPI publish pending.

- [x] mypy error in `src/tank/builder/build.py:133`
- [ ] MCP server configuration examples for Claude Code, Cursor, VS Code
- [ ] Tag and release v0.1.0 on PyPI (`pip install tank`, `pip install tank[build]`)

---

## v0.1.1 — "Bug Fixes + Benchmarks"

**Theme**: Fix data integrity bugs found post-tag; ship benchmark infrastructure.

- [x] Polish README — "implementation is beginning" replaced with accurate status
- [x] Expose `limit` parameter on `query-docs` MCP tool and `query_docs()`
- [x] Token overhead benchmark harness — `tests/benchmarks/test_token_overhead.py` with baseline at `tests/benchmarks/results/v0.1.0.json`
- [x] GitHub Actions benchmark workflow — PR delta comparison via `tests/benchmarks/compare.py`
- [x] Fix `src/tank/storage/db.py:121-126` — page ID foreign key integrity on import
- [x] Fix `src/tank/search/fts.py:76` — silent exception swallowing; all search errors return `[]`
- [x] Fix `src/tank/cli/pull.py:39` — hardcoded `doc_version_status="imported"` instead of reading from manifest
- [ ] Fix `src/tank/builder/manifest.py:43` — `doc_version_status` hardcoded to `"stable"`; accept it as a parameter to `build_manifest()`
- [ ] Implement or remove unused `max_tokens` parameter in `src/tank/server.py`

---

## v0.2.0 — "First Users"

**Theme**: Make it effortless to start. Polish the rough edges that stop adoption.

- [ ] **`tank init`** — scan project deps, download pre-built packs, configure MCP server
  - New module: `src/tank/cli/init.py`
  - Parse `requirements.txt`, `pyproject.toml`, `package.json`, `Cargo.toml`
  - Map package names to `.ctx` pack URLs (static JSON registry on GitHub)
  - Generate MCP config (`.cursor/mcp.json` or Claude Code equivalent)
- [ ] **`tank build --source <url>/llms-full.txt`** — fetch a single `llms-full.txt` URL, chunk it, build a `.ctx` pack. No crawler — just HTTP GET + existing build pipeline.
  - Modify `src/tank/builder/build.py` to accept URL sources
  - New module: `src/tank/builder/fetch.py` (single-file HTTP fetch, no crawl logic)
- [ ] **Pre-built packs for top 20 libraries** — built in CI from `llms-full.txt`, published as GitHub Releases (FastAPI, Django, Flask, SQLAlchemy, Pydantic, React, Next.js, Express, Prisma, etc.)
- [ ] **Chunk size tuning** — `max_chunk_tokens` / `min_chunk_tokens` in `tank build`. Modify `src/tank/builder/chunking.py`
- [ ] **Cross-platform path handling** — normalize to forward slashes, reject backslashes/UNC in validator. Modify `src/tank/validator/verify.py`
- [ ] **Error message polish** — every error path produces an actionable message. Audit all `TankError` subclass usage
- [ ] **Lockfile in git** — document committing `.tank/index.lock` for reproducible team setups
- [ ] **FTS5 search quality** — four targeted improvements:
  - Add `heading_path` column to `chunks_fts` with 2.5× weight (`db.py:48`, `fts.py:62`)
  - Tune BM25 weights: heading 2.5× > summary 1.5× > content 1.0×
  - Query preprocessing: stopword filtering, term normalization
  - Synonym expansion: `auth` → `authentication`, `JWT` → `JSON Web Token`, etc.
- [ ] **Validator optimization** — refactor `_read_archive_bytes()` to avoid full in-memory ZIP reconstruction for digest computation. Hash entries in a defined order instead.

---

## v0.3.0 — "Growth"

**Theme**: Multi-user, multi-project, CI-integrated. Start looking like infrastructure.

- [ ] **`tank build --source <url>/llms.txt`** — fetch `llms.txt` index, download each linked doc page, build a `.ctx` pack. Basic rate limiting + `User-Agent`. No general crawler.
  - Extend `src/tank/builder/fetch.py` to handle llms.txt index parsing
- [ ] **Pack registry (static hosting)** — `tank pull fastapi@0.115.0` resolves against a registry index (JSON manifest on CDN or GitHub Pages). No auth. Read-only.
  - New module: `src/tank/registry/` (client only; server is a static file host)
  - `tank pull` accepts `package@version` in addition to file paths
- [ ] **CI/CD templates** — GitHub Actions, GitLab CI, CircleCI: build packs on release, verify in PRs, publish to static registry
- [ ] **Pre-built packs for top 100 libraries** — scale up pack-building CI pipeline
- [ ] **Token budget intelligence** — `max_tokens` on `query-docs` controls response size, balancing breadth vs. depth within the budget
- [ ] **`index-deps` MCP tool** — scans project deps, reports which have packs available, which are indexed, which are stale
- [ ] **Staleness detection** — compare indexed pack versions against project lockfiles. Surface warnings in `resolve-deps`
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
