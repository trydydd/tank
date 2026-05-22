# Tank — Decision Log

Decisions made during architecture and pre-implementation planning, with reasoning and rejected alternatives. This document exists so that future contributors (human or agent) don't re-open settled questions.

## Format

Each entry records: the decision, the alternatives considered, why we chose what we chose, and when it can be revisited.

---

## D1: Implementation Language — Python

**Decision**: implement Tank entirely in Python.

**Alternatives considered**:
- **Rust**: single-binary distribution, memory safety in archive validator, 10-50x faster normalization/hashing. Rejected because: 2-3x slower development velocity, less mature MCP SDK, higher contributor barrier for the target audience (enterprise teams), and `chunkana` is Python-only (would need rewrite or PyO3 bridge defeating single-binary goal).
- **Hybrid (Python + Rust hot paths)**: Python for orchestration, Rust for validator and normalizer via PyO3. Rejected because: premature optimization. Sub-10ms FTS5 queries are achievable in pure Python. Ship MVP, measure, optimize only if performance is actually a problem.
- **Go**: good CLI story, single binary. Rejected because: no MCP SDK, no chunkana equivalent, weaker ecosystem for the specific libraries needed.

**Revisit when**: performance profiling shows Python is the bottleneck for large documentation sets (thousands of pages), or if the Rust MCP SDK matures significantly.

---

## D2: Python Version — 3.11+

**Decision**: require Python 3.11 or later.

**Alternatives considered**:
- **Python 3.10**: would require `tomli` backport for TOML parsing. 3.10 is in security-fix-only mode, EOL October 2026. Adds a dependency for diminishing benefit.
- **Python 3.12+**: too restrictive. 3.11 is widely available in enterprise environments and gives us `tomllib` in stdlib plus `str | None` union syntax.

**Revisit when**: Python 3.11 reaches EOL (October 2027).

---

## D3: Summary Generation — Heuristic

**Decision**: generate one-line summaries heuristically at build time. First sentence for prose chunks, leading function/class signature for code-heavy chunks.

**Alternatives considered**:
- **LLM-generated summaries**: more accurate, better natural language. Rejected because: adds runtime dependency (API key or local model), costs money per build, makes builds non-deterministic (same input → different output), requires network (violates local-first constraint), and increases build time dramatically.
- **No summaries (heading_path only)**: simpler, zero generation logic. Rejected because: the progressive disclosure pattern relies on summaries to help agents decide which chunks to expand. Heading paths alone are often too terse (`API / Users` tells you nothing about what's in the chunk).

**Revisit when**: the `summary` field schema supports upgrading the strategy without a format change. A future `--summarizer llm` flag could opt into LLM generation for users who want it.

---

## D4: source_url Convention — Relative Paths for Local Builds

**Decision**: `source_url` is always populated, never null. Local builds store the relative path from the `--source` argument (e.g. `--source ./docs` + `auth/oauth.md` = `docs/auth/oauth.md`). Only leading `./` is stripped.

**Alternatives considered**:
- **file:// URLs**: absolute paths like `file:///home/user/project/docs/auth/oauth.md`. Rejected because: makes `.ctx` packs completely unportable. The pack would only make sense on the machine where it was built.
- **Paths relative to source root (stripping the source dir)**: `auth/oauth.md` instead of `docs/auth/oauth.md`. Rejected because: loses useful context. If someone sees `auth/oauth.md` they have to guess where that lives in the project. `docs/auth/oauth.md` is unambiguous.
- **Nullable source_url with fallback logic**: allow null, fall back to `packages.source_url` at query time. Rejected because: adds query-time complexity and branching. Always-populated is simpler for both the implementation and consumers.

**Revisit when**: Phase 2 adds web crawling; crawled builds will use full `https://` URLs in the same field. No format change needed.

---

## D5: pack_digest Zeroing — Empty String

**Decision**: when computing `pack_digest`, set the field value to `""` in manifest.json, hash the archive bytes, then write the real digest back.

**Alternatives considered**:
- **Remove the key entirely**: cleaner semantics ("field doesn't exist yet"). Rejected because: removing and re-adding a JSON key introduces key-ordering sensitivity. Different JSON libraries may serialize remaining keys in different orders, breaking the hash. Would require canonical JSON serialization (sorted keys) at both build and verify time — an additional subtle correctness requirement.
- **Sidecar file (`.ctx.sha256`)**: hash the archive directly, store digest externally. Rejected because: two files to track, easy to lose the hash file, breaks the self-contained single-file property of `.ctx` packs.
- **Hash everything except manifest**: `pack_digest` covers only `chunks.jsonl` + `pages.json`. Rejected because: doesn't detect tampering of manifest metadata (someone could change `lifecycle_state` from `draft` to `approved` undetected).
- **Don't store digest inside the archive**: store it only in the lockfile and packages table after import. Rejected because: you can't verify a `.ctx` file in isolation — you need an external source of truth to check against.

**ZIP entry timestamps**: all entries in a `.ctx` archive are written with a fixed `date_time` of `(2021, 8, 8, 0, 0, 0)`. The build writes the archive twice — once with `pack_digest: ""` to compute the digest, then again with the real digest. Without pinned timestamps, the two writes could land in different 2-second DOS timestamp buckets, producing different ZipInfo metadata and making the verifier unable to reproduce the hash. The pinned date is arbitrary and must never change (it is baked into every `.ctx` file ever produced).

**Revisit when**: never. This is a format-level decision that's baked into the verification sequence.

---

## D6: Token Counting — Character Heuristic

**Decision**: `token_count` is computed as `len(content) // 4`. Documented clearly as an approximate estimate for budget planning.

**Alternatives considered**:
- **tiktoken (cl100k_base)**: exact counts for Claude/GPT-4 class models. Rejected because: adds a ~2MB dependency to `tank[build]`, and the "right" tokenizer varies by model (cl100k, o200k, etc.). Since `token_count` is advisory — agents use it to estimate "will this fit?" not for exact accounting — the heuristic is good enough.
- **Multiple tokenizer counts** (generic + Anthropic + OpenAI): maximum accuracy across models. Rejected because: ~30 bytes of bloat per chunk in `chunks.jsonl` for accuracy that doesn't change any decision. An agent with 2000 tokens of budget doesn't care if a chunk is 387 or 412 tokens.

**Revisit when**: agents start making tight budget decisions based on `token_count` and the ~20% error margin causes problems. The field can be recomputed at build time without a format change.

---

## D7: HTML Handling — Markdown-First for MVP

**Decision**: Markdown is the primary supported format. `.html` files are accepted (extension whitelist) but processed via basic tag removal only. Boilerplate stripping (nav, footer, breadcrumbs, sidebar) is deferred to Phase 2.

**Alternatives considered**:
- **Tag-based stripping with element/class matching**: strip `<nav>`, `<footer>`, `<aside>`, elements with class matching `breadcrumb`, `sidebar`, etc. Rejected for MVP because: the primary use case is local documentation which is overwhelmingly Markdown. Building a robust HTML boilerplate detector before we have real crawled HTML to test against is speculative. Phase 2's crawler will produce real HTML that informs the stripping rules.
- **Reject HTML entirely in MVP**: only accept `.md` files. Rejected because: some projects keep docs as HTML (e.g. generated API docs). Basic tag removal is trivial to implement and better than refusing the files.

**Revisit when**: Phase 2 crawler implementation begins and we have real-world HTML documentation to inform stripping rules.

---

## D8: Source Tree Handling — Recursive with Lexicographic Sort

**Decision**: `tank build --source <path>` recurses subdirectories by default. Files are discovered by extension whitelist (`.md`, `.html`, `.htm`), sorted lexicographically by full relative path. This sort order determines chunk ID assignment and `normalized_content_hash`.

**Alternatives considered**:
- **Flat only (no recursion)**: process only top-level files in the source directory. Rejected because: real documentation is almost always nested (`docs/api/`, `docs/guides/`, etc.). Requiring users to flatten their docs first is a poor UX for zero benefit.
- **Configurable recursion (`--no-recurse`, `--include`, `--exclude`)**: full flexibility. Rejected for MVP because: adds CLI complexity without clear demand. Deferred — can be added later without breaking anything.
- **Filesystem iteration order (unsorted)**: rely on `os.listdir` / `pathlib.iterdir()` order. Rejected because: iteration order is filesystem-dependent (arbitrary on Linux, sometimes alphabetical on macOS/Windows). Same source tree would produce different hashes on different platforms, breaking the integrity guarantee.

**Revisit when**: users request `--no-recurse` or glob-based filtering. The architecture accommodates these as additive features.

---

## D9: Error Model — Emergent via TDD

**Decision**: start with a base `TankError` class. Discover and add specific exception subclasses during TDD as failure modes emerge from writing tests.

**Alternatives considered**:
- **Define full exception hierarchy up front**: lay out every exception class and exit code before writing code. Rejected because: speculating about failure modes without implementation experience leads to either over-engineering (exceptions that never get raised) or gaps (real failures that don't fit the pre-defined classes). TDD naturally surfaces the real failure modes.

**Revisit when**: after MVP implementation is complete, review the exception hierarchy for consistency and document the final exit code mapping.

---

## D10: Test Fixtures — Static Archives + Pytest Factories

**Decision**: use static fixtures in `tests/fixtures/` for integration tests (sample source trees, known-good `.ctx` packs, malformed archives) and pytest factory functions for unit tests (individual chunks, normalization cases, policy evaluation).

**Alternatives considered**:
- **Static fixtures only**: committed test data for everything. Rejected because: unit tests for normalization and chunking need many small variations that would bloat the fixtures directory. Factories are more expressive for parameterized tests.
- **Programmatic fixtures only**: build all test data in code. Rejected because: archive validation tests need real `.ctx` files with known byte-level properties (corrupted archives, path traversal entries, bad signatures). These are hard to construct programmatically and easier to inspect as static files.

**Revisit when**: the test suite grows large enough that fixture management becomes a problem.

---

## D11: FTS5 Configuration — Minimal for MVP, Tuning Deferred

**Decision**: ship MVP with a minimal FTS5 configuration: raw query passthrough, uniform BM25 column weights, default tokenizer, and `heading_path` stored in the `chunks` table but not indexed in FTS5.

**What this means in practice**: the MVP implementation uses roughly 30–40% of FTS5's available capability. Specifically:

- `fts.py` passes queries directly to `MATCH` with no preprocessing — stopwords, articles, and filler terms consume BM25 capacity
- BM25 column weights are uniform `(1.0, 1.0, 1.0)` — `summary` and `content` are weighted identically
- Default tokenizer — no stemming, no code-aware tokenization, no prefix matching
- `heading_path` is the strongest relevance signal in documentation search and is not indexed

**Alternatives considered (deferred, not rejected)**:

- **Column weighting** — `bm25(chunks_fts, 2.5, 1.5, 1.0)` with heading > summary > content. Deferred: requires adding `heading_path` to the FTS5 virtual table, which is a schema migration.
- **Query preprocessing** — stopword filtering, term normalisation. Deferred: adds code with no correctness risk but material quality impact; belongs in v0.2.0 where FTS5 tuning is scoped.
- **Prefix queries and synonym expansion** — `auth*` matching `authentication`; a small static dict for common technical abbreviations. Deferred: same scope.
- **Custom tokenizer** — porter stemmer or unicode61 with diacritics removal. Deferred: low-priority for technical documentation where exact terms dominate.

**Revisit when**: v0.2.0 FTS5 tuning work begins. The four improvements are ordered by impact: (1) add `heading_path` to `chunks_fts` with 2.5× weight, (2) tune BM25 column weights, (3) query preprocessing, (4) synonym expansion. Measure search quality before and after before considering embeddings.
