# Synaptic Drift — Decision Log

Decisions made during architecture and pre-implementation planning, with reasoning and rejected alternatives. This document exists so that future contributors (human or agent) don't re-open settled questions.

## Format

Each entry records: the decision, the alternatives considered, why we chose what we chose, and when it can be revisited.

---

## D1: Implementation Language — Python

**Decision**: implement Synaptic Drift entirely in Python.

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
- **tiktoken (cl100k_base)**: exact counts for Claude/GPT-4 class models. Rejected because: adds a ~2MB dependency to `synaptic-drift[build]`, and the "right" tokenizer varies by model (cl100k, o200k, etc.). Since `token_count` is advisory — agents use it to estimate "will this fit?" not for exact accounting — the heuristic is good enough.
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

**Decision**: `synd build --source <path>` recurses subdirectories by default. Files are discovered by extension whitelist (`.md`, `.html`, `.htm`), sorted lexicographically by full relative path. This sort order determines chunk ID assignment and `normalized_content_hash`.

**Alternatives considered**:
- **Flat only (no recursion)**: process only top-level files in the source directory. Rejected because: real documentation is almost always nested (`docs/api/`, `docs/guides/`, etc.). Requiring users to flatten their docs first is a poor UX for zero benefit.
- **Configurable recursion (`--no-recurse`, `--include`, `--exclude`)**: full flexibility. Rejected for MVP because: adds CLI complexity without clear demand. Deferred — can be added later without breaking anything.
- **Filesystem iteration order (unsorted)**: rely on `os.listdir` / `pathlib.iterdir()` order. Rejected because: iteration order is filesystem-dependent (arbitrary on Linux, sometimes alphabetical on macOS/Windows). Same source tree would produce different hashes on different platforms, breaking the integrity guarantee.

**Revisit when**: users request `--no-recurse` or glob-based filtering. The architecture accommodates these as additive features.

---

## D9: Error Model — Emergent via TDD

**Decision**: start with a base `SyndError` class. Discover and add specific exception subclasses during TDD as failure modes emerge from writing tests.

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

## D11: FTS5 Configuration — Minimal for MVP, Tuning Partially Implemented (v0.2.0)

**Original MVP decision**: ship with raw query passthrough, uniform BM25 column weights, default tokenizer, and `heading_path` stored in `chunks` but not indexed in FTS5.

**v0.2.0 status**:

- ✅ **`heading_path` added to `chunks_fts`** — `db.py:48-52` creates the FTS5 table with `heading_path` as the first column; both triggers updated to include it. `section_tags[0]` from chunkana provides the `##`-level heading; `###` depth requires D14 (custom chunker).
- ✅ **BM25 column weights tuned** — `fts.py:67` uses `bm25(chunks_fts, 2.5, 1.5, 1.0)` (heading 2.5×, summary 1.5×, content 1.0×). Weight only activates when `heading_path` is non-null; FTS5 treats NULL as empty string for fallback-chunked documents.
- ✅ **Query sanitization (partial)** — `fts.py` strips FTS5 special characters (`.`, `(`, `)`, `"`, `*`, etc.) before passing to `MATCH`, preventing syntax errors on symbol-heavy queries like `mcp.tool`. Stopword filtering and term normalisation remain deferred.
- ⬜ **Synonym expansion** — `auth` → `authentication`, `JWT` → `JSON Web Token`. Still deferred.
- ⬜ **Custom tokenizer** — porter stemmer or unicode61 with diacritics removal. Still deferred; low-priority for technical docs where exact terms dominate.

**Schema commitment note**: indexing `heading_path` in FTS5 means future chunker changes (D14) that alter how `heading_path` is computed will require rebuilding the FTS5 index (or a migration). This is acceptable — the index can be rebuilt from the `chunks` table on schema version bump.

**Remaining work**: query preprocessing and synonym expansion are the next two improvements, ordered by impact. Measure search quality against the fastmcp benchmark before considering embeddings.

---

## D12: MCP Tool Surface — Single Tool vs Split ✓ Implemented (v0.2.0)

**Decision**: ship MVP with a single `query-docs` tool accepting a `detail` parameter (`"summary"` or `"full"`); split into separate `search`/`fetch` tools in v0.2.0.

**The problem with the single-tool surface**: `detail="full"` sounds better than `detail="summary"` to an LLM agent. The parameter name nudged agents toward the expensive single-step path — fetching full content speculatively without a prior relevance pass — which is the footgun the two-step pattern is designed to prevent.

**Resolution (v0.2.0)**:

```
search   query, packages, limit, max_tokens  → always returns summaries + chunk_ids only
fetch    chunk_ids, max_tokens               → always returns full content by ID
```

This enforces the two-step pattern architecturally: `search` cannot return full content; `fetch` cannot do speculative full-content search. Eliminates the footgun without any stateful enforcement. Implemented in `src/tank/server.py`; documented in `docs/MCP.md`.

**`max_tokens` default rationale**: `max_tokens` defaults to `None` (no budget enforcement) by design. A default of e.g. `4000` would silently trade away recall — with BM25 noise, the most relevant chunk can land at position 8 or 12, and a tight budget would exclude it with no signal to the agent. `limit` is the right knob for controlling result count; `max_tokens` is an explicit opt-in for agents with known token constraints.

---

## D13: Summary Heuristic — First Sentence vs Heading-Aware Generation

**Decision**: generate summaries by extracting the first non-trivial sentence from chunk content.

**The problem**: this fails when a chunk opens with a code block or a short bridging sentence rather than a topic-describing sentence. Observed in the fastmcp stdio benchmark:

| Chunk | Summary generated | What the chunk actually covers |
|---|---|---|
| 2 | "You can now run this MCP server by executing `python my_server." | STDIO is the default transport |
| 3 | "STDIO is ideal for: * Local development..." | STDIO transport section |
| 5 | "We recommend using HTTP transport instead of SSE for all new projects." | SSE deprecation + CLI reload |

Chunk 2's summary gives an agent scanning for "stdio configuration" no signal that this chunk is the relevant one. The missed chunk contains the correct answer.

**Proposed fix (deferred)**: prefix the summary with the leaf heading node.

```
summary = "<leaf heading>: <first prose sentence>"
```

For chunk 2 under `### STDIO Transport (Default)`:
```
STDIO Transport (Default): STDIO (Standard Input/Output) is the default transport for FastMCP servers.
```

`heading_path` is already computed before `_generate_summary()` is called in `src/tank/builder/chunking.py`; it just isn't passed through. The change is additive — `summary` remains a plain string, no schema impact.

**Edge cases**: preamble chunks (no heading) fall back to first-sentence behaviour; top-level chunks where heading equals the page title skip the prefix to avoid redundancy; headings over ~60 chars use only the leaf node; chunks opening with a list or code block skip to the next prose sentence.

**Revisit when**: v0.2.0 chunker work begins. Depends on D14 — if chunkana is replaced with a heading-boundary chunker, `heading_path` will be accurate by construction and the prefix heuristic becomes more reliable.

---

## D14: Chunker — chunkana Replacement: Custom Chunker on markdown-it-py

**MVP decision**: use chunkana for MVP structural chunking, accepting its limitations.

**chunkana verdict**: does not support heading-based splitting at arbitrary depth. The `structural` strategy splits only at `##` level, keeping all `###` subsections together. `header_path` is always `[]`; Synaptic Drift works around this by reading `section_tags[0]`, but this is the ceiling of what chunkana can provide. Observed impact: in the fastmcp benchmark, chunk 5 spans six `###` sections (932 tokens) and is matched by FTS5 on incidental keyword overlap rather than relevance.

**Library survey (S1 — done)**: four production-stable (≥1.0.0) candidates evaluated:

- **chunknorris 1.2.2** — meets all requirements (all heading levels, heading_path as ordered list by construction, code fences atomic, paragraph overflow splitting) but ships parsers for PDF, Word, Excel, and Jupyter Notebooks Synaptic Drift will never use. PyMuPDF, pandas, matplotlib in the dependency tree. ~30MB install footprint for a markdown chunker.
- **langchain-text-splitters 1.1.2 `MarkdownHeaderTextSplitter`** — code fences atomic, all heading levels configurable, but heading_path returns as a flat dict (requires reconstruction glue) and no paragraph overflow splitting. Requires `langchain-core`.
- **semantic-text-splitter 0.30.1** — pre-1.0, no heading hierarchy output. Eliminated.
- **chonkie 1.6.7** — delimiter-based, no structural heading tracking. Eliminated.

**Decision**: build a custom chunker using `markdown-it-py` 3.0.0+ as the parsing backend.

**Rationale**: neither off-the-shelf library is a clean drop-in. `markdown-it-py` is MIT-licensed, zero additional dependencies, actively maintained, and is already a widely-used CommonMark parser. The chunknorris markdown chunker is ~250 lines of reference implementation; Synaptic Drift's equivalent with `markdown-it-py` tokens gives full control over heading_path construction, code-fence atomicity, and paragraph overflow with no dependency weight penalty. This aligns with Synaptic Drift's local-first, minimal-dependency philosophy.

**What the custom chunker must do**:
- Split at heading boundaries at all levels (`#`, `##`, `###`, `####`, and deeper) as the primary split point
- Treat fenced code blocks as atomic — never split mid-fence
- Split oversized sections at paragraph boundaries when a section exceeds `max_chunk_tokens`
- Build `heading_path` accurately by construction as a `/`-joined string of ancestor heading texts
- Replace `src/tank/builder/chunking.py` — the `process_file()` function and `generate_summary()` call site

**`semchunk` ruled out earlier**: general-purpose recursive delimiter splitter with no markdown heading awareness. Token-counter-driven rather than structure-driven.

**Implemented in v0.2.0** (`feature/chunker`). See spike S7 (status: done) for implementation notes. The S2 heading-aware summary heuristic (D13) was implemented in the same pass — `generate_summary()` now accepts `heading_path` and prefixes the summary with the leaf heading node.

---

## D15: Pack #2 — mcp@2025-11-25

**Decision**: ship the Model Context Protocol spec (`mcp@2025-11-25`) as the v0.1.1 release artifact alongside fastmcp@3.3.0.

**Rationale**: Synaptic Drift depends on `mcp` directly, and the MCP tool split (D12) is the largest single v0.2.0 work item — agents using the `search`/`fetch` tools will query this pack constantly. `modelcontextprotocol.io` publishes `llms-full.txt`, making it buildable today without a crawler or HTML extraction.

**Alternatives considered**:
- **httpx@0.28.1**: still pre-1.0 (0.x), no API stability commitment. Rejected.
- **requests**: stable (2.x), good candidate for HTTP client docs, but uses RST source and no llms-full.txt — requires S6 HTML extraction work first.
- **click / rich**: Synaptic Drift's other deps, but their docs are sparse and less queried by agents.

**Source**: `modelcontextprotocol.io/llms-full.txt` (spec version 2025-11-25). Build command:
```
synd build mcp@2025-11-25 --source https://modelcontextprotocol.io/llms-full.txt --output ./packs
```

**Revisit when**: never — this is a release artifact decision. Future packs follow the same evaluation process.

---

## D16: Lockfile location — `synd.lock` at project root

**Decision**: The lockfile lives at `synd.lock` in the project root, not `.synd/index.lock`.

**Rationale**: All established package managers (`Cargo.lock`, `package-lock.json`, `poetry.lock`, `Pipfile.lock`) place the lockfile at the project root. A root-level file is immediately visible, committed without gitignore exceptions, and signals its purpose to any developer who opens the repo. `.synd/index.lock` required a `!.synd/index.lock` gitignore negation which silently fails if the parent directory rule uses `/` rather than `/*` — a correctness hazard that tripped us in practice (B1 in the code review).

**Alternatives considered**:
- **`.synd/index.lock`**: Keeps all Synaptic Drift state under one directory but requires gitignore gymnastics and is invisible at the root level. Rejected.

**Revisit when**: Never — this is a UX convention decision. The location is now baked into `add.py`, docs, and `synd.lock` itself.

---

## D17: `pack_source` vs `source_url` — two distinct URL fields

**Decision**: The `packages` table carries two separate URL fields: `source_url` (from the manifest — where the documentation was authored) and `pack_source` (set at import time — where the `.ctx` file was fetched from).

**Lockfile `source_url` population** (refined in D19): the lockfile's `source_url` field prefers the manifest's `source_url` when it is an HTTPS URL (canonical distribution address for official packs), and falls back to `pack_source` (the local import path) otherwise. This ensures `synd sync` can fetch official packs by URL while still recording a usable path for locally-built packs.

**Rationale**: These are fundamentally different things. `source_url` in the manifest is provenance metadata about the documentation content (e.g., `docs/api`). `pack_source` is the local path where the `.ctx` was imported from. For official packs built with a canonical HTTPS `source_url` in their manifest, that URL is what `synd sync` needs to re-fetch the pack. Conflating them caused the lockfile to show the build-time docs directory as the fetch location, making `synd sync` impossible to implement correctly.

**Alternatives considered**:
- **Overwrite `source_url` with the pull path**: Destroys provenance metadata. Rejected.
- **Store pull path only in the lockfile, not the DB**: Loses the data if the lockfile is regenerated. Rejected.
- **Always use `pack_source`**: Would record `/tmp/fastmcp@3.3.0.ctx` in the lockfile, breaking `synd sync` for official packs. Rejected.

**Revisit when**: Phase 2 registry design — `pack_source` may evolve to carry a structured registry reference rather than a raw URL.

---

## D18: Manifest validation — JSON Schema (jsonschema library, draft/2020-12)

**Decision**: `manifest.json` validation in the verifier (step 2) uses a machine-readable JSON Schema file at `src/tank/schemas/manifest.v2.schema.json`, validated via the `jsonschema` Python library. Schema uses draft/2020-12.

**Rationale**: The previous manual field-presence check (`_REQUIRED_MANIFEST_FIELDS` loop) only caught missing keys — it passed manifests with `chunks: "bad"` or `lifecycle_state: "active"`. JSON Schema validates types, enums, patterns, and numeric constraints in one declaration that is also human-readable and tooling-compatible. The schema file becomes the single source of truth for the manifest contract, referenced in docs and validated in CI.

**`additionalProperties` is not set to `false`**: forward-compatible with Phase 2/3 field additions (`embedding_model`, etc.) without a schema version bump.

**Alternatives considered**:
- **Pydantic model**: heavier dependency, more code, harder to publish as a standalone schema artefact. Rejected for MVP.
- **Manual field-by-field checks**: already in place, insufficient. Replaced.

**Revisit when**: schema version 3 (Phase 2 crawl fields) or Phase 3 (embedding fields) — add new optional properties to the schema, keep `additionalProperties` open.

---

## D19: CLI command set — `add`, `sync`, `remove` replace/extend `pull`

**Decision**: Rename `synd pull` → `synd add`; implement `synd sync`; add `synd remove`. Keep `synd pull` as a hidden deprecated alias for one minor version.

**Rationale**:
- `synd pull` was misleading: "pull" implies a remote fetch (`git pull`, `docker pull`), but the command only imports a local file. The misnaming becomes actively harmful once `synd sync` lands and *does* fetch.
- `synd add` is the correct verb: it is consistent with `cargo add`, `uv add`, `npm install <pkg>`, and reads correctly with any input source (local path, HTTPS URL, future registry spec).
- `synd sync` closes the "nothing reads `synd.lock`" gap. It enables `git clone && synd sync` to reproduce the local index on a fresh checkout — the primary missing workflow for teams.
- `synd remove` completes the verb set. Without it, removing a pack requires hand-editing the lockfile, which breaks the invariant that the lockfile is always written by the CLI.

**Command surface after this change (8 commands, two personas)**:

| Persona  | Commands |
|----------|----------|
| Consumer | `add`, `sync`, `remove`, `query`, `serve` |
| Author   | `build`, `verify`, `inspect` |

No individual user touches all 8. Consumer persona needs ~4 in normal use (`sync`, `serve`, `query`, sometimes `add`).

**`add` vs `sync` kept separate** (not collapsed à la `npm install [pkg]`): the operations are genuinely different — ad-hoc acquisition of a new pack vs. reproducing the full index from the lockfile. The uv/Cargo discipline of one-verb-one-thing holds here.

**`tank.toml` deferred**: without a registry there is no resolution step that would distinguish a manifest from a lock. The lockfile continues to serve as both declaration and receipt until the Phase 3 static registry introduces real version ranges. At that point, `tank.toml` + `synd.lock` split cleanly along the Cargo/uv model.

**Alternatives considered**:
- **`tank install [<ref>]` (npm-style unification)**: `npm install` (no args) = from lock; `npm install <pkg>` = add. Familiar but conflates two distinct operations. Broadly considered a design mistake in npm. Rejected in favour of explicit verbs.
- **`tank import`**: accurate but unused by any major package manager. Less discoverable. Rejected.
- **Drop `synd verify` from the top-level**: too useful for CI pipelines ("verify this .ctx before importing"). Kept as standalone; it is also already implicit in `add` and `sync`.

**Revisit when**: Phase 3 static registry lands and `tank.toml` is introduced — at that point `synd add <pkg@range>` becomes the primary declaration verb and `synd sync` becomes the "ensure lockfile is satisfied" executor, matching the Cargo model exactly.

---

## D20: HTML-to-Markdown Conversion — markdownify + BeautifulSoup4

**Decision**: use `markdownify` (MIT) with `BeautifulSoup4` (MIT) for converting rendered HTML documentation pages to markdown for the chunker. Added to the `[serve]` optional extra in `pyproject.toml`.

**Pipeline** (implemented in `src/synd/builder/fetch.py`):
1. Parse with `BeautifulSoup(html, "html.parser")`
2. Decompose boilerplate elements: `nav`, `header`, `footer`, `aside`, `script`, `style`, `noscript`
3. Extract main content: `<main>`, `role="main"`, or `<article>` — fall back to `<body>` if none found
4. Convert with `markdownify.markdownify(target, heading_style="ATX")`
5. Strip pilcrow anchor links (`¶`) left by ReadTheDocs/Sphinx heading anchors
6. Collapse runs of blank lines

**Alternatives evaluated** against `requests.readthedocs.io/en/latest/user/quickstart/`:

- **trafilatura (Apache 2.0)**: good content extraction but inline code spans get fragmented — backtick-enclosed text broken by newlines in output, corrupting prose for FTS and chunking. Rejected.
- **html2text (MIT)**: zero dependencies, but outputs indented (4-space) code blocks rather than fenced ` ``` ` blocks. Incompatible with the chunker's fence detection in `normalizer.py`. Rejected.
- **scripts/llms_full_to_markdown.py (stdlib only)**: handles MDX source (Mintlify `.md` endpoints, `llms-full.txt`) via `strip_mdx()` + `MarkdownExtractor`. Not suitable for rendered browser HTML — no content extraction, nav bleeds through as plain text. Kept in `scripts/` as reference; `strip_mdx()` and `_extract_code_fences()` are candidates for promotion to `src/synd/builder/mdx.py` in S8.

**BeautifulSoup4 is already a `markdownify` transitive dependency** — no additional install cost. `markdownify` is a core dependency (not `[serve]`) because URL fetch is a `synd build` feature, not an MCP server feature.

**Revisit when**: S8 implementation encounters a site type where the BeautifulSoup content-element selector (`<main>`, `<article>`, `role="main"`) produces poor results. Add site-specific selector logic to `html_to_markdown()` at that point.

---

## D21: URL Fetch Pipeline — `urllib.request`, Markdown output, Regex MDX stripping (S8)

**Decision**: the `synd build --source <url>/llms.txt` pipeline uses `urllib.request` (stdlib) for HTTP, produces CommonMark markdown as its output format, and strips MDX/JSX via regex (not a full JSX parser).

**Five sub-decisions and rationale**:

| Question | Decision | Rationale |
|---|---|---|
| Output format | CommonMark markdown | Preserves heading structure (`##`, `###`) that the S7 chunker uses to build `heading_path`. Converting to plain text loses this signal entirely. Same format as local-file pipeline — same chunker handles both paths. |
| HTTP library | `urllib.request` (stdlib) | Zero additional dependency. `httpx` ruled out — still pre-1.0 (same reasoning as D15 which rejected it for Pack #2). Pattern already established in `scripts/llms_full_to_markdown.py`. Async not needed: builder is synchronous; if async/pooling becomes necessary in the v0.3.0 crawler, that's the right time to re-evaluate. |
| Content-type routing | URL ends in `.md` → MDX path; otherwise → HTML path | Mintlify-hosted sites already expose `.md` URLs in their `llms.txt` (confirmed in S8 context). Fetching a `.md` URL returns MDX directly — no HTML-to-markdown step needed. Non-`.md` URLs serve rendered HTML and go through D20's `html_to_markdown()` pipeline. |
| MDX stripping approach | Regex (not full JSX parser) | Covers the confirmed Mintlify tag set (`<Note>`, `<Warning>`, `<Tip>`, `<Tabs>`, `<Tab>`, `<Frame>`, `<Icon />`, `<FeatureBadge />`, etc.) without additional dependencies. A full JSX/XML parser would add complexity for marginal correctness gain on a known, finite tag set. |
| Rate limiting | Configurable `sleep`, default 0.5s between pages | Simple; correct for sequential single-threaded fetches. Token bucket deferred — not needed until the v0.3.0 crawler introduces concurrent fetching. |

**New modules** (implemented as part of S8):
- `src/synd/builder/mdx.py` — `strip_mdx()`, `unwrap_jsx_blocks()`, `clean_heading()`, `process_mdx()`. Functions promoted and extended from `scripts/llms_full_to_markdown.py`.
- `src/synd/builder/llms_full.py` — `LlmsPage`, `parse_llms_txt()`, `fetch_pages()`. Parses the `[label](url)` link format from a `llms.txt` index and orchestrates per-page fetching.
- `src/synd/builder/fetch.py` extended with `fetch_page(url, *, rate_limit_sleep)` — unified entry point that routes on URL extension.

**`pyproject.toml`**: no change — `urllib.request` is stdlib.

**Revisit when**: the v0.3.0 crawler needs concurrent fetching (add connection pooling / async at that point); or a new site type is encountered where `.md` extension detection misfires (extend routing heuristic or add explicit `Content-Type` check).

---

## D23: Minimum-Token Stub Elimination — Internal Chunker Guard

**Decision**: eliminate stub chunks (heading-only content, typically < 10 tokens) by suppressing the emit inside `chunk_content()` when a heading boundary would produce below-threshold content, rather than running a separate post-chunking merge pass.

**The problem**: a heading immediately followed by another heading (no prose between them) produces a stub chunk whose content is just the heading markdown line. These stubs:
- Contribute nothing to BM25 that `heading_path` doesn't already carry.
- Inflate result counts with near-zero-information entries.
- Cannot be surfaced usefully by `fetch` — the content is the heading.

The MCP pack had 249 such stubs across 2,089 chunks.

**Mechanism**: when `heading_open` is encountered, the would-be chunk content (`source_lines[chunk_start_line:heading_line]`) is evaluated against `min_chunk_tokens`. If it is below the threshold, `_emit()` is not called and `chunk_start_line` is not advanced. The `ancestor_stack` is still updated so the heading becomes part of the ancestry. At the next emit, `chunk_start_line` still points to the stub's heading line, so its content is prepended to the absorbing section's content naturally.

**Why internal rather than post-process**: the stub never exists as an intermediate object. The chunker makes the merge decision at the same point it decides where to split — heading boundary detection — which is the semantically correct place. A post-processing pass would need to re-evaluate content that the chunker already visited, and it would require all callers to know to run the pass.

**`heading_path` after absorption**: the absorbing section's (deeper) heading path is used. The stub's heading text appears in the merged chunk's content, so BM25 sees it via content scoring. The ancestor node is also present in the absorbing chunk's `heading_path` as an ancestry entry, so the 2.5× heading weight is preserved.

**Threshold**: `_DEFAULT_MIN_CHUNK_TOKENS = 20`. Pure stubs are almost always < 10 tokens; legitimate one-sentence intros before a code block are 15–30 tokens. 20 absorbs all stubs without risk of merging real introductory content. Configurable via `min_chunk_tokens` parameter on `chunk_content()`.

**Disabling**: pass `min_chunk_tokens=0` to get the original behaviour (all chunks emitted including stubs).

**Alternatives considered**:
- **Post-chunking merge pass (S10 original proposal)**: separate `merge_stubs()` function applied after `chunk_content()` returns. Rejected because: the merge decision belongs at the split point; it adds an external pass that callers must invoke; stubs exist as intermediate `RawChunk` objects even if briefly.
- **Merge backward (absorb into previous chunk)**: when a stub is the last chunk on a page, there is no forward absorber. Backward merging produces worse chunks — the previous section's summary gains the stub heading out of context. Forward absorption with natural carry-forward avoids this entirely for all but the all-stubs-on-page edge case, which is handled by the final `_emit(len(source_lines))`.

**Revisit when**: evidence shows that legitimate short introductory sections (e.g. a 3-sentence overview before a subsection) are being absorbed when they shouldn't be. Lowering `_DEFAULT_MIN_CHUNK_TOKENS` to 10 or making it configurable via CLI are both straightforward changes.

---

## D22: Tab Heading Disambiguation — Title Injection + Heading Depth Shift

**Decision**: when `unwrap_jsx_blocks()` processes a `<Tab title="...">` element, inject the `title` attribute as an ATX heading one level above the shallowest heading in the Tab body, and shift all body headings one level deeper (capped at H6). Tags other than `<Tab>` (i.e. `<Tabs>`, `<Note>`, `<Warning>`, `<Frame>`, etc.) are unaffected — they still receive plain `textwrap.dedent`.

**Problem**: Mintlify wraps multi-language tutorials in `<Tabs><Tab title="Python">…</Tab><Tab title="TypeScript">…</Tab></Tabs>`. Before this fix, `unwrap_jsx_blocks` extracted the inner text and discarded the `title` attribute. The downstream chunker received a flat document where all language tabs concatenated their headings without any language label. Every language produced a chunk for `### Implementing tool execution` and all chunks got the same `heading_path`, making BM25 unable to distinguish "Python / Implementing tool execution" from "TypeScript / Implementing tool execution".

**Algorithm**:
1. Extract `title` from `title="..."` or `title='...'` (via `_TAB_TITLE_RE`). If absent, fall back to plain `textwrap.dedent` — no heading injected.
2. `textwrap.dedent` the body (strips common leading whitespace from Mintlify's 4-space indented Tab content).
3. Scan body lines for ATX headings (`#`–`######`); find the minimum `#` count (shallowest level).
4. Shift every heading one level deeper (`##` → `###`, `#####` → `######`; `######` stays `######`).
5. Prepend `{'#' * (shallowest - 1)} {title}\n\n` to the shifted body. If no headings exist, prepend `### {title}\n\n`.

**Why depth-shift instead of just prepending?** A plain prepend would put the title at the same level as the first heading inside the tab (`## Python\n\n## Setup\n\n...`). The chunker would immediately pop `Python` from the ancestor stack when it hit `## Setup`, so only the first section would carry the language label in its `heading_path`. Depth-shifting ensures the title stays in scope for the entire tab body.

**Alternative considered**: a plain prepend without shifting. Rejected because it breaks the ancestor-stack invariant: the injected heading is immediately shadowed by the first same-level heading inside the tab.

**Edge cases**:
- No `title` attribute → plain dedent (backward compat).
- Body has no headings → inject `### {title}` (default H3).
- Shallowest heading is H6 → shift is a no-op; inject `##### {title}`.
- Title contains special markdown characters (e.g. `C#`) → injected literally; no escaping.
- `<Tabs>` container → plain dedent, no title injection.

**Measured result**: `build-server` page of `mcp@2025-11-25` went from 45 unique `heading_path` values (111 chunks) to 112 unique values. `build-client` achieved 105/105 unique paths.

**Implementation**: `_unwrap_tab_block()` in `src/synd/builder/mdx.py` replaces the inline lambda in `_JSX_UNWRAP_RE.sub()`.

**Revisit when**: a non-Mintlify doc site uses a different multi-tab component name (add to the `_JSX_UNWRAP_RE` tag list and handle in `_unwrap_tab_block` if title injection is appropriate); or heading depth semantics change (unlikely).

---

## D23: Minimum-Token Stub Elimination — Internal Chunker Guard

*(recorded inline above; D23 is `min_chunk_tokens` implementation in S10)*

---

## D24: Chunk Size Gate — Warn-Only Strategy; Default max_chunk_tokens Raised to 800

**Decision**:
1. `_DEFAULT_MAX_CHUNK_TOKENS` raised from 500 → **800** tokens.
2. A new warning system detects chunks that exceed a configurable `warn_chunk_tokens` threshold (default: `2 × max_chunk_tokens = 1,600`) **after** all splits. Warnings are emitted by `cli/build.py`; no changes to `chunk_content()` return type.
3. No automatic splitting of structural token types (`code_block`, `table`, long `fence`). Warn-only.
4. Three new `synd build` CLI params: `--max-chunk-tokens`, `--min-chunk-tokens`, `--warn-chunk-tokens`.

**Why raise the default to 800?** Synaptic Drift's primary target corpus is technical developer documentation (SDK references, API guides, code-heavy tutorials). The original 500-token default was set before real production packs existed. Analysis of the MCP pack (P95 ≈ 423t at 500t max) confirmed that 95% of sections already fit comfortably. However, for developer docs, a prose section of 600–800 tokens typically represents a complete concept explanation that should stay intact for coherent retrieval; splitting it forces the LLM agent to assemble context from two adjacent chunks. Industry tools targeting code-heavy docs commonly use 800–1,024 tokens. The real-data validation script (`scripts/validate_chunk_sizes.py`) confirms the distribution at both defaults.

**Why warn-only (no automatic split for structural tokens)?** Three token types bypass the paragraph-overflow split: `code_block` (4-space indented content, e.g. changelog pages), `table`, and very long `fence` blocks. Automatic line-boundary splitting of these would produce incoherent fragments:
- Indented code block split mid-line: arbitrary cut, no code-structural boundary.
- Table split mid-row: continuation chunks lack the header row, breaking semantic context.
- Fenced code split mid-function: violates the fence-atomicity invariant that is required for correct code-example retrieval.

The URL noise filter (`DEFAULT_NOISE_URL_PATTERNS`) already handles the canonical production case (changelog pages). Warn-only gives pack authors actionable information without risking worse retrieval quality from forced splits.

**`warn_chunk_tokens` formula**: defaults to `2 × max_chunk_tokens` (not a fixed constant). This scales sensibly when authors tune `--max-chunk-tokens` (e.g. `--max-chunk-tokens 300` warns at 600t). The 2× multiplier leaves room for legitimate large fenced code examples (which legitimately bypass the prose split) while still catching true blobs.

**Alternatives considered**:
- Automatic split of `code_block` / `table` at line boundaries — rejected (incoherent fragments, see above).
- Hard cap with fence-breaking split — rejected (breaks fence-atomicity invariant; a code example cut mid-function is worse than one large chunk).
- Keeping `max_chunk_tokens = 500` — rejected (too conservative for code-heavy SDK docs; evidence from MCP/FastMCP production packs).

**Implementation**:
- `src/synd/builder/chunking.py`: `_DEFAULT_MAX_CHUNK_TOKENS = 800`; `chunk_file()` now forwards `max_chunk_tokens` and `min_chunk_tokens` to `chunk_content()`.
- `src/synd/builder/build.py`: `build_pack()` and `build_pack_from_url()` accept all three params; `_finalize_pack()` detects oversized chunks and returns `tuple[Path, list[RawChunk]]`.
- `src/synd/cli/build.py`: three new `@click.option` decorators; `_print_oversized_warnings()` formats the warning output.
- `scripts/validate_chunk_sizes.py`: live validation against MCP and FastMCP `llms-full.txt`.

**Revisit when**: real user feedback shows that oversized structural-token chunks (tables, code blocks) materially degrade search quality in a way that automatic splitting would fix without worse side effects; or when the warning system generates enough data about which structural bypasses are most common to design a targeted mitigation.
