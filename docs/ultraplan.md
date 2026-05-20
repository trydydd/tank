# Tank Strategy Roadmap: Current State to v1.0.0 and Beyond

## Context

Tank is a local-first documentation pack system for AI coding agents. Its Phase 1 MVP is code-complete: 24 Python modules, 141 passing tests, a working CLI (`build`, `verify`, `pull`, `query`, `inspect`), an MCP server (`query-docs`, `resolve-deps`), SQLite FTS5 search, an 8-step archive validator, and a policy engine. The founders have documented a three-phase plan (MVP → Crawling/Registry → Embeddings) and a 10-item gap analysis. The MVP has never shipped a release to PyPI. No users exist outside the founding team.

This document proposes the fastest credible path to either profitability or acquisition, grounded in the actual codebase and competitive landscape as of May 2026.

---

## I. Competitive Landscape — What Tank Is Up Against

### The field, mapped honestly

| Competitor | What they do | Tank's advantage | Their advantage |
|---|---|---|---|
| **Context7** (Upstash, 55k GitHub stars) | Cloud-hosted MCP server fetching live library docs for AI agents. Two tools: `resolve-library-id`, `get-library-docs`. Free tier. | Tank is local-first (no cloud dependency, works offline, enterprise-safe). Tank supports private/internal docs. Tank has cryptographic integrity verification. | Context7 already has massive adoption, zero-setup UX, covers thousands of public libraries out of the box. |
| **Grounded Docs MCP Server** | Open-source, local-first doc crawler + MCP server (Docker-based). Apache 2.0. | Tank's `.ctx` format is portable and verifiable. Tank has governance (lifecycle states, policy). | Simpler "just crawl and serve" model. Lower barrier to entry. |
| **Cursor built-in context** | Project-aware context from open files, imports, directory structure. MCP plugin system. | Tank provides versioned, attributed, policy-governed documentation — not just "whatever files are open." | Built into the editor. Zero configuration. 5000+ MCP servers in ecosystem. |
| **GitHub Copilot context** | Jaccard-similarity retrieval over open files, import graph, 60-line sliding windows. MCP support added. | Tank provides external documentation context (library docs, API refs), not just project files. Copilot doesn't solve "what does the library I'm using actually do?" | Deepest IDE integration. Largest user base. Microsoft distribution. |
| **Sourcegraph Cody** | RAG over code with embeddings, code graph analysis, multi-repo support. Enterprise-focused. | Tank is purpose-built for documentation (not code). Lighter weight. No cloud infrastructure required. | Vastly more sophisticated retrieval (embeddings + code graph + reranking). Enterprise sales team. |
| **JetBrains AI Assistant** | `/docs` command with RAG. PSI index for project-aware context. | Tank is editor-agnostic. Works with any MCP client. | Deep IDE integration. Built-in RAG over JetBrains' own documentation. |
| **llms.txt** | Convention for websites to expose AI-readable content summaries. | Tank provides structured, versioned, searchable, verifiable documentation — not a flat text file. Tank works offline. | Zero tooling required. Growing adoption as a web standard. Backed by convention, not infrastructure. |
| **DevDocs MCP Server** | Crawl documentation sites, serve via MCP locally (Docker). | Tank adds integrity verification, governance, versioning, and a portable pack format. | Simpler to get started. No build step needed. |

### The uncomfortable truth

**Context7 is Tank's most dangerous competitor, not Copilot or Cursor.** Context7 solves the same core problem (give AI agents accurate library documentation) with a cloud-hosted, zero-config approach that already has 55k GitHub stars. Their model — centrally index public library docs, serve on demand via MCP — is the path of least resistance for individual developers.

Tank's moat against Context7 is **not** "we also serve docs via MCP." It's:
1. **Private/internal documentation** that can never go to a cloud service
2. **Cryptographic integrity** — you can prove docs haven't been tampered with
3. **Policy governance** — enterprises control what enters agent context
4. **Offline operation** — air-gapped environments, regulated industries
5. **Portability** — `.ctx` packs are self-contained artifacts you can store, share, audit

These are enterprise differentiators. Tank will not win the individual developer market against Context7. Tank's path to value is through enterprises and teams that need trust guarantees on the documentation their AI agents consume.

### llms.txt: Tank's crawl on-ramp, not a competitor

llms.txt is a web convention with two files: `llms.txt` (an index of documentation links) and `llms-full.txt` (the entire documentation concatenated into a single Markdown file). Adoption is growing fast — hundreds of libraries already publish one or both.

This is Tank's cheapest path to web-sourced documentation. `llms-full.txt` is a single HTTP GET away from being a `tank build` input — no crawler, no sitemap parsing, no boilerplate stripping. `llms.txt` is a structured list of URLs to fetch. Together they cover the "crawl" use case for the vast majority of public libraries without any of the Crawl4AI complexity.

Don't position against llms.txt; position Tank as **the tool that turns llms.txt into verifiable, versioned, searchable, local documentation packs.** This is a marketing message that writes itself.

---

## II. Strategic Angles the Founders Haven't Considered

### 1. Tank as a CI/CD artifact, not a developer tool

**Confidence: HIGH**

The founders position Tank as a developer CLI. But the highest-leverage use case is Tank as a **build artifact in CI/CD pipelines**. Consider:

- A library maintainer runs `tank build` in CI on every release tag
- The `.ctx` pack is published alongside the PyPI/npm package
- Consumers `tank pull` the pack in their own CI or dev setup
- The AI agent always has verified, version-matched documentation

This reframes Tank from "a tool developers run manually" to "infrastructure that library teams ship as part of their release process." The `.ctx` pack becomes like a `.whl` or `.tgz` — a standard artifact format.

**Why this matters for acquisition**: Every potential acquirer (Cursor, GitHub, JetBrains, Sourcegraph) runs CI/CD. A format that's already embedded in build pipelines is much harder to rip out than a CLI tool.

### 2. Pre-built packs for popular libraries as a growth flywheel

**Confidence: HIGH**

Nobody will adopt Tank if they have to build every pack themselves. The founders should maintain a curated set of pre-built `.ctx` packs for the top 50-100 libraries (React, Django, FastAPI, SQLAlchemy, etc.) and distribute them via a simple registry. This is the "batteries included" strategy that makes Tank immediately useful.

Context7 already does this (they index thousands of libraries). Tank needs an equivalent, but with the local-first, verifiable twist: you download the pack once, verify it, and never need the network again.

### 3. The "documentation supply chain" narrative

**Confidence: MEDIUM**

Software supply chain security (SBOMs, Sigstore, SLSA) is a well-understood enterprise concern. Tank can position `.ctx` packs as **documentation supply chain artifacts** — the documentation equivalent of an SBOM. This gives enterprises a governance story: "We verify the documentation our AI agents consume the same way we verify the packages our software depends on."

This narrative is novel and defensible. No competitor is making this argument. It turns Tank's "over-engineered for a docs tool" verification pipeline into a feature, not a liability.

### 4. `tank init` — zero-config first experience

**Confidence: HIGH**

The current workflow requires manual `tank build` + `tank pull`. For adoption, Tank needs a single command that scans a project, identifies its dependencies, finds documentation sources, builds/downloads packs, and configures the MCP server. Something like:

```bash
tank init
# Scans requirements.txt / package.json / Cargo.toml
# Downloads pre-built packs for recognized libraries
# Creates .tank/ with index.db and MCP config
# Prints: "Tank is ready. Your agent now has docs for: fastapi, sqlalchemy, pydantic"
```

This is the zero-to-value path that competes with Context7's zero-config experience.

### 5. Token budget intelligence as a differentiator

**Confidence: MEDIUM**

The two-step progressive disclosure pattern (summary scan → targeted fetch) is already built. But Tank could go further: expose a `token_budget` parameter on `query-docs` that returns the maximum content within a token budget, automatically balancing breadth (more results at summary level) vs. depth (fewer results with full content). No competitor does this. Agents currently waste context window by over-fetching or under-fetching.

---

## III. Challenging the Planned Direction

### URL crawling (Phase 2): Graduate through llms.txt, not straight to a general crawler.

**Confidence: HIGH**

The founders plan to jump straight to `tank build --source <URL>` with Crawl4AI. That's a massive engineering effort (rate limiting, robots.txt, sitemap parsing, incremental re-crawl with ETags, boilerplate stripping) for a capability that doesn't differentiate Tank. DevDocs MCP Server and Context7 already crawl documentation sites.

**A better sequence exists — follow the emerging llms.txt ecosystem:**

1. **`tank build --source <url>/llms-full.txt`** (v0.2.0) — `llms-full.txt` is a single flat Markdown file that many libraries already publish. It's the entire documentation concatenated. Tank can fetch one file, chunk it with chunkana, and build a `.ctx` pack. Zero crawler needed. This covers a large and growing set of libraries with minimal engineering effort.

2. **`tank build --source <url>/llms.txt`** (v0.3.0) — `llms.txt` is an index file with links to individual doc pages. Tank fetches the index, downloads each linked page, and builds a pack. Still no general crawler — just targeted HTTP fetches of known URLs from a structured manifest. Add basic rate limiting and a `User-Agent` header, but skip sitemap parsing, link discovery, and all the crawler complexity.

3. **General Crawl4AI crawler** (v1.1+ or never) — Only build this if the llms.txt ecosystem doesn't cover enough libraries. By that point you'll have real user data on what's missing. If you do build it, it's a registry-side tool for building public packs in CI, not a user-facing feature.

This sequence is dramatically less engineering effort, aligns Tank with a growing web standard, and produces the same end result (`.ctx` packs built from library documentation). It also gives Tank a marketing angle: "the tool that turns llms.txt into verifiable, searchable, local documentation packs."

### Embeddings inside `.ctx` files (Phase 3): Wrong layer.

**Confidence: HIGH**

The plan to embed BGE-M3 dense/sparse vectors in `.ctx` packs is architecturally questionable:

1. **Model coupling**: Embedding vectors are model-specific. A pack built with BGE-M3 is useless if the consumer uses a different model. The plan acknowledges this ("automated re-embedding from stored chunk text when the local model differs") — but that means the embeddings in the pack are discarded most of the time.
2. **Pack size**: Dense float32 vectors for thousands of chunks add megabytes to every `.ctx` file. This bloats a format whose appeal is portability and inspectability.
3. **Hash stability**: Adding embeddings changes the archive, which changes `pack_digest`. Now you need to decide: are embeddings part of the integrity guarantee, or excluded from it? Either answer creates complexity.
4. **FTS5 is good enough**: For documentation retrieval at Tank's scale (thousands to tens of thousands of chunks per project), BM25 is competitive with dense retrieval. The marginal quality improvement from hybrid search doesn't justify the complexity for the target use case.

**Instead**: If search quality needs to improve, invest in better FTS5 tokenization (code-aware tokenizers, term weighting) and query preprocessing (synonym expansion, query reformulation). These are server-side improvements that don't touch the pack format.

If embeddings are truly needed later, compute them at `tank pull` time (import-side), not at `tank build` time (export-side). Store them in `index.db`, not in the `.ctx` file. This preserves pack portability and lets each consumer use their preferred embedding model.

### The registry: Right idea, wrong priority for v1.0.0.

**Confidence: MEDIUM**

A federated registry (`tank push`, `tank pull <pkg@version>` from a remote) is a significant infrastructure investment. For v1.0.0, a simpler approach works: host pre-built packs as static files (GitHub Releases, S3, or a static CDN) and let `tank pull` accept URLs. A proper registry with auth, signing, search, and governance can come in v1.1 or v1.2, once there's evidence of multi-team adoption.

### PyO3 hybrid: Not yet. Maybe never.

**Confidence: MEDIUM**

`docs/recommendations.md` makes a case for a Rust core via PyO3 in Phase 2. The performance case is weak: FTS5 queries are sub-10ms in Python, the validator runs once per pack import, and normalization is fast enough for any realistic documentation set. The security case (Rust for the archive validator) is theoretically sound but practically irrelevant until Tank is processing untrusted packs from a public registry — which doesn't exist yet.

The engineering cost of maintaining a PyO3 build (cross-platform wheels, CI complexity, contributor barrier) is high for a small team. Revisit only if profiling shows Python is a bottleneck for a real user workload, or when a public registry makes the security argument concrete.

**Evidence that would change my view**: A benchmark showing the validator takes >1s on a realistic `.ctx` pack, or a security audit identifying a Python-specific vulnerability in the archive processing path.

---

## IV. Semver Roadmap

**Assumed time horizon**: 12 months to v1.0.0, 18 months to acquisition-readiness. Team of 2-3 engineers.

### v0.1.0 — "Ship It" (Month 1)

**Theme**: Get on PyPI. Make it installable. Let people try it.

**Checklist**:
- [ ] Fix the one mypy error in `src/tank/builder/build.py:133`
- [ ] Fix `src/tank/cli/pull.py:39` — reads `doc_version_status="imported"` instead of reading from manifest (bug, see Section VIII)
- [ ] Implement or remove unused `max_tokens` parameter in `src/tank/server.py:121` (see Section VIII)
- [ ] Polish README with a 60-second quickstart (build from local docs dir, query via CLI and MCP)
- [ ] MCP server configuration examples for Claude Code, Cursor, VS Code
- [ ] GitHub Actions workflow: `tank build` + `tank verify` as a PR check (demonstrate CI/CD artifact pattern)
- [ ] Tag and release v0.1.0 on PyPI (`pip install tank`, `pip install tank[build]`)

**Why this order**: Nothing else matters until the package is installable. Fix the bugs first so the initial release is clean. The CI/CD workflow demonstrates the "documentation as build artifact" narrative from day one.

**Key files**: `pyproject.toml` (version, classifiers, URLs), `README.md`, `.github/workflows/`, `src/tank/builder/build.py:133`, `src/tank/cli/pull.py`, `src/tank/server.py`

### v0.2.0 — "First Users" (Month 3)

**Theme**: Make it effortless to start. Polish the rough edges that stop adoption.

**Checklist**:
- [ ] **`tank init`** — scan project deps, download pre-built packs, configure MCP server
  - New module: `src/tank/cli/init.py`
  - Parse `requirements.txt`, `pyproject.toml`, `package.json`, `Cargo.toml`
  - Map package names to `.ctx` pack URLs (static JSON registry on GitHub)
  - Generate MCP config (`.cursor/mcp.json` or Claude Code equivalent)
- [ ] **`tank build --source <url>/llms-full.txt`** — fetch a single `llms-full.txt` URL, chunk it with chunkana, build a `.ctx` pack. No crawler needed — just HTTP GET + existing build pipeline. This unlocks any library that publishes `llms-full.txt`.
  - Modify `src/tank/builder/build.py` to accept URL sources
  - New module: `src/tank/builder/fetch.py` (single-file HTTP fetch, no crawl logic)
- [ ] **Pre-built packs for top 20 libraries** — built in CI from `llms-full.txt` or official docs, published as GitHub Releases (FastAPI, Django, Flask, SQLAlchemy, Pydantic, React, Next.js, Express, Prisma, etc.)
- [ ] **Chunk size tuning** — `max_chunk_tokens` / `min_chunk_tokens` in `tank build` (gap #7). Modify `src/tank/builder/chunking.py`
- [ ] **Cross-platform path handling** — normalize to forward slashes, reject backslashes/UNC in validator (gap #6). Modify `src/tank/validator/verify.py`
- [ ] **Error message polish** — every error path produces an actionable message. Audit all `TankError` subclass usage
- [ ] **Lockfile in git** — document committing `.tank/index.lock` for reproducible team setups

**Why this order**: `tank init` is the single most important feature for adoption. `llms-full.txt` support unlocks pack building for hundreds of libraries with minimal code. Pre-built packs make `tank init` actually useful. The other items fix friction that blocks second-time usage.

### v0.3.0 — "Growth" (Month 6)

**Theme**: Multi-user, multi-project, CI-integrated. Start looking like infrastructure.

**Checklist**:
- [ ] **`tank build --source <url>/llms.txt`** — fetch `llms.txt` index, download each linked doc page, build a `.ctx` pack. Basic rate limiting + `User-Agent`. No general crawler — just targeted fetches of URLs from a structured manifest.
  - Extend `src/tank/builder/fetch.py` to handle llms.txt index parsing
- [ ] **Pack registry (static hosting)** — `tank pull fastapi@0.115.0` resolves against a registry index (JSON manifest on CDN or GitHub Pages). No auth. Read-only.
  - New module: `src/tank/registry/` (client only; server is a static file host)
  - `tank pull` accepts `package@version` in addition to file paths
- [ ] **CI/CD templates** — GitHub Actions, GitLab CI, CircleCI: build packs on release, verify in PRs, publish to static registry
- [ ] **Pre-built packs for top 100 libraries** — scale up pack-building CI pipeline
- [ ] **Token budget intelligence** — `max_tokens` on `query-docs` controls response size intelligently, balancing breadth vs. depth within the budget
- [ ] **`index-deps` MCP tool** — scans project deps, reports which have packs available, which are indexed, which are stale. Modify `src/tank/server.py`
- [ ] **Staleness detection** — compare indexed pack versions against project lockfiles. Surface warnings in `resolve-deps`
- [ ] **Structured logging** — JSON logging at key checkpoints (gap #5). `python logging` with configurable verbosity

**Why this order**: `llms.txt` support scales pack building to any library that publishes one. The registry makes Tank useful beyond "build your own packs." CI/CD templates make it sticky in engineering orgs. Token budget intelligence is the MCP-level differentiator that makes agents prefer Tank over raw doc fetching.

### v1.0.0 — "Enterprise-Ready" (Month 10)

**Theme**: Trust, governance, and operational maturity. The version you'd sell to an enterprise security team.

**Checklist**:
- [ ] **Schema migrations** — `PRAGMA user_version`-based forward-only migrations (gap #2). Modify `src/tank/storage/db.py`. Must land before any new column additions.
- [ ] **Real signature verification** — Step 8 of the validator currently only checks file existence. Implement actual cryptographic verification (ed25519 or Sigstore). Modify `src/tank/validator/verify.py`, add `src/tank/signing/`
- [ ] **Observability** — health endpoint for HTTP transport, query latency metrics, import audit trail (gap #5). Modify `src/tank/server.py`
- [ ] **Multi-project support** — configurable `.tank/` location, monorepo workspace support
- [ ] **Policy profiles** — per-team/per-workspace policy overrides (the monorepo merge semantics open question from `architecture.md`)
- [ ] **Audit logging** — who imported what, when, from where. New `audit_log` table in `index.db`
- [ ] **Backup and recovery** — `tank rebuild --from-lockfile` (gap #4)
- [ ] **Comprehensive documentation** — man pages, API reference, enterprise deployment guide

**Why this order**: Schema migrations must land first — they're a prerequisite for every feature that touches the database. Signature verification is the enterprise trust blocker. You can't call it 1.0 if upgrading between versions might break the database or if you can't cryptographically verify pack provenance.

---

## V. Highest-Leverage Bets

### Bet 1: Pre-built pack ecosystem + `tank init` (MUST DO)

**Why**: Tank's biggest obstacle is time-to-value. Context7 gives you docs in seconds with zero setup. If Tank requires building every pack manually, it loses. Pre-built packs + `tank init` is the minimum viable distribution strategy.

**Moat creation**: Once teams commit `.tank/index.lock` and configure their MCP servers, Tank is embedded in the development workflow. Switching costs are real — you'd need to reconfigure every developer's environment.

**Acquisition signal**: A library of 100+ verified documentation packs is a dataset asset. Any acquirer inherits a ready-made documentation infrastructure.

### Bet 2: `.ctx` as a CI/CD artifact standard (HIGH LEVERAGE)

**Why**: If `.ctx` packs become something library maintainers ship alongside their releases (like type stubs or API schemas), Tank becomes infrastructure rather than a tool. This is the difference between "a company that makes a CLI" and "the company that defined the documentation pack format."

**Moat creation**: A format standard is the deepest moat possible. Once packs are published on PyPI, npm, or GitHub Releases, the format outlives any single tool.

**How to execute**: Partner with 3-5 high-profile open-source projects to ship `.ctx` packs in their release pipelines. Publish a "Building Documentation Packs" guide targeting library maintainers. Make the GitHub Actions workflow dead simple.

### Bet 3: Enterprise governance narrative (DIFFERENTIATOR)

**Why**: This is what separates Tank from every competitor. Context7, DevDocs MCP, and Grounded Docs all serve documentation — none of them let you verify provenance, enforce policy, or audit what documentation your agents are consuming. In regulated industries (finance, healthcare, defense), this isn't nice-to-have; it's a procurement requirement.

**Acquisition signal**: Enterprise governance features are exactly what Sourcegraph, GitHub, and JetBrains need to sell AI coding tools to large organizations. Tank's policy engine and verification pipeline fill a gap none of them have addressed.

---

## VI. Open Questions the Founders Must Answer

### Beyond what `architecture.md` already lists:

1. **Pricing model**: Is Tank the product, or is the registry the product? Free CLI + paid hosted registry (like npm/Artifactory) is the obvious model, but it requires building and operating a service. Alternative: consulting/support model around the open-source tool, targeting enterprises. **Must decide before v0.3.0** (registry design depends on this).

2. **Pack authorship and trust**: When a user runs `tank pull react@19.0.0` from the registry, who built that pack? How do they know it was built from the official React docs and not a malicious fork? This is the supply-chain trust question. Sigstore integration is one answer, but the trust model must be designed before the registry ships. **Must decide before v0.3.0.**

3. **Versioning semantics**: If React ships 19.0.1 (a patch), does Tank rebuild the pack? Is `react@19.0.0.ctx` a new file or an update? How does this interact with `pack_digest` (which changes on any content change)? The pack versioning scheme needs to be defined relative to the upstream library's versioning. **Must decide before v0.2.0** (pre-built packs require this).

4. **Community vs. curated packs**: Should anyone be able to publish packs to the registry (like npm), or should it be curated (like Homebrew core)? Curated is safer but doesn't scale. Community is riskier but creates a flywheel. A hybrid (curated "verified" tier + community "unverified" tier) is likely right but adds complexity. **Must decide before v0.3.0.**

5. **MCP token overhead**: Research cited in the competitive analysis says MCP consumes 40-50% of context windows before agents do work. Tank's progressive disclosure pattern mitigates this, but the team should benchmark actual token usage of `query-docs` calls in real agent sessions and publish the numbers. If Tank demonstrably uses less context than alternatives, that's a marketing asset. **Should measure before v0.2.0 launch.**

6. **Target acquirer alignment**: The feature roadmap should be shaped by who might acquire Tank. Sourcegraph values enterprise code intelligence. GitHub values developer ecosystem integration. Cursor values MCP-native tools. JetBrains values IDE-integrated documentation. The team should pick 1-2 target acquirers and align the v0.3.0-v1.0.0 roadmap to their gaps. **Strategic decision needed now.**

---

## VII. What the Documented Gaps Actually Mean for v1.0.0

From the 10 gaps in `recommendations.md`, here's what matters vs. what's noise:

| Gap | Verdict | Rationale |
|---|---|---|
| 1. Concurrency | **Already handled** | WAL mode + busy timeout are implemented in `db.py:75-76`. Document the behavior; don't over-engineer. |
| 2. Schema migrations | **Critical for v1.0.0** | Any column addition (Phase 2/3) breaks existing databases without this. Block on this before adding features. |
| 3. Non-text content | **Noise for now** | Log a warning and skip. Revisit if users ask for diagram support. |
| 4. Backup/recovery | **v1.0.0 item** | `tank rebuild --from-lockfile` is a safety net enterprises expect. |
| 5. Observability | **v1.0.0 item** | Essential for enterprise adoption and debugging in production. |
| 6. Cross-platform paths | **v0.2.0 item** | Windows users will hit this immediately. Fix early. |
| 7. Chunk size tuning | **v0.2.0 item** | Directly affects search quality. Low-effort, high-impact. |
| 8. Query caching | **Noise** | Sub-10ms queries don't need caching. Premature optimization. |
| 9. CI/CD guidance | **v0.1.0 item** | The "docs as artifact" narrative needs a working CI example from day one. |
| 10. Multi-directory handling | **Already implemented** | `discover_files()` in `chunking.py` recursively walks and sorts. The gap is resolved. |

---

## VIII. Contradictions Found Between Prompt and Repository

1. **Prompt says "v0.1.0 is the next tag to ship, not the current capability level."** Repository confirms: `pyproject.toml` says `version = "0.1.0"` but no git tags or PyPI releases exist. Consistent.

2. **`README.md` says "implementation is beginning"** but `STATUS.md` says "Implementation Complete." The README is stale — it should be updated for v0.1.0 release.

3. **`architecture.md` lists `doc_version_status` values as `stable / prerelease / archived / unknown`** but `cli/pull.py:39` hardcodes `doc_version_status="imported"` — a value not in the schema. This is a bug: pull should read `doc_version_status` from the manifest, not invent a value.

4. **`max_tokens` parameter**: `server.py:121` accepts `max_tokens` on `query-docs` but never uses it. The architecture says it's a "budget cap for the response" but the implementation ignores it entirely. This should either be implemented or removed before v0.1.0.

---

## IX. Summary

Tank's path to value is not "a better docs MCP server" — Context7 owns that space with 55k stars and zero-config UX. Tank's path is **documentation supply chain infrastructure for enterprises**: verifiable packs, policy governance, CI/CD integration, and a portable format standard.

The three highest-leverage moves:
1. **Ship pre-built packs + `tank init`** to compete on time-to-value
2. **Push `.ctx` as a CI/CD artifact** to create format-level lock-in
3. **Lean into enterprise governance** to differentiate from every cloud-first competitor

The planned Phase 2 (crawler) and Phase 3 (embeddings-in-packs) should be deprioritized in favor of distribution, adoption, and enterprise features. Build the ecosystem before building more technology.