# Research Spikes

## MCP Tool API — `query-docs` Design

### Context

During implementation of `max_tokens` on `query-docs`, several design questions came up about how `limit` and `max_tokens` interact, what sane defaults look like, and whether the current single-tool surface is the right architecture.

---

### How `limit` and `max_tokens` compose

`limit` and `max_tokens` operate at different stages of the pipeline:

1. **`limit`** is passed into the SQL `LIMIT ?` clause. The database scores all matching chunks with BM25, sorts descending, and returns at most `limit` rows. Nothing after this point sees the chunks that were cut.

2. **`max_tokens`** is a post-ranking pass applied to whatever `limit` returned. Chunks are accumulated in BM25 rank order; a chunk is included only if its cost doesn't push the running total over the budget. The first chunk that would exceed the budget stops the loop.

`limit` sets the candidate pool size. `max_tokens` trims that pool by budget. Setting `limit=3` and `max_tokens=10000` means the budget can't rescue chunks ranked 4th or lower — they were never fetched.

**Current defaults:** `limit=10`, `max_tokens=None`.

---

### Chunk size and token cost ranges

Chunkana's defaults (used by Tank with no config override):

| Parameter | Default |
|---|---|
| `max_chunk_size` | 4096 chars |
| `min_chunk_size` | 512 chars |
| `overlap_size` | 200 chars |

Using the `len(content) // 4` estimator:

- Per-chunk range: **~128–1024 tokens**
- With `limit=10`, `detail="full"`, no `max_tokens`: up to **~10,240 tokens** worst case

A 65,000-line markdown file (~4.5M chars) produces ~1,100 chunks in the index. At query time only `limit` chunks are returned regardless of source file size — the file size is a build-time concern, not a query-time one.

---

### Efficiency vs accuracy

With BM25 (lexical ranking), the most relevant chunk for a query can easily land at position 8 or 12. Tight limits silently hurt recall with no signal to the agent.

**Summary layer** (`detail="summary"`): optimize for recall. Summaries are 20–40 tokens each, so `limit=20–30` costs only ~400–1200 tokens — negligible. No `max_tokens` needed.

**Full content layer** (`detail="full"`, via `chunk_ids`): optimize for efficiency. The agent has already applied its own relevance judgement from the summary scan. A `max_tokens` guard here is reasonable.

**Single-step full query** (`detail="full"`, no `chunk_ids`): this is the footgun. The agent speculatively fetches full content without a prior relevance pass. With `limit=10` and no `max_tokens` this can return ~10,240 tokens of content the agent may not need.

`max_tokens=4000` (~4 chunks at typical size) was considered as a default for this case but rejected — 4 chunks is too tight to prioritize accuracy over efficiency. With BM25 noise you want headroom. The better bound is `limit` itself: with `limit=10`, full content is already capped at ~10,240 tokens worst case, which is reasonable headroom for any modern context window.

**Conclusion:** `max_tokens` should be an explicit opt-in for agents with specific budget constraints, not a silent default that trades away accuracy. Use `limit` to control result count.

---

### Proposed tool split: `search-docs` + `fetch-docs`

The current `query-docs` single-tool surface with a `detail` parameter is a footgun because "full" sounds better than "summary" to an LLM agent. The parameter name nudges agents toward the expensive path.

**Proposed split:**

```
search-docs   query + packages + limit     → always returns summaries
fetch-docs    chunk_ids + max_tokens       → always returns full content by ID
```

This enforces the two-step pattern architecturally:

- `search-docs` has no `detail` parameter — cannot return full content
- `fetch-docs` has no `query` parameter — cannot do speculative full-content search
- Eliminates the footgun without any stateful enforcement

**Cost:** breaking change to `query-docs`. Agents that already have chunk IDs still only need one call (`fetch-docs`), but the migration affects any existing MCP client configuration.

**Recommendation:** defer to a future release. The immediate fix is ensuring the `query-docs` tool description clearly states that `detail="full"` without `chunk_ids` should be used with an explicit `max_tokens`, and that the summary → chunk_ids workflow is the preferred pattern. The tool split is worth doing once the workflow is proven out.

---

### Recommended usage pattern (current API)

**Step 1 — summary scan:**
```json
{
  "query": "how to configure OAuth2",
  "packages": ["my-lib"],
  "detail": "summary",
  "limit": 20
}
```
Cost: ~400–800 tokens. Agent identifies relevant chunk IDs.

**Step 2 — targeted full fetch:**
```json
{
  "chunk_ids": [4, 5, 12],
  "detail": "full",
  "max_tokens": 8000
}
```
Cost: bounded to ~8000 tokens of only the content the agent decided it needs.

---

### Tank vs WebFetch — token comparison (fastmcp stdio query)

**Query:** "how do I configure a stdio implementation in fastmcp"  
**FTS5 query:** "stdio transport run" — generated by an LLM from the natural language query above, before the document was read. The NL query itself returns 0 FTS5 results; the LLM-derived terms do match, demonstrating the NL→FTS5 translation step.  
**Source:** `https://gofastmcp.com/deployment/running-server` (single page, fetched via WebFetch)  
**Pack:** `fastmcp@3.0.0` built from that page, pulled into local index

**Results:**

| Approach | Tokens | % of WebFetch |
|---|---|---|
| WebFetch full page (HTML comments stripped) | 2,257 | 100% |
| Tank summary scan (3 chunks matched) | 81 | 4% |
| Tank full content (all 3 chunks) | 1,550 | 69% |
| Tank full content (chunk 2 only — STDIO section) | 360 | 16% |

WebFetch baseline strips the three `<!-- -->` comment lines added when the fixture was saved to disk (source URL, fetch date, update note). A real web fetch would not include them.

**Chunk breakdown (full content):**

| Chunk | Heading path | Tokens | Content |
|---|---|---|---|
| 2 | `fastmcp-running-server / STDIO Transport (Default)` | 360 | STDIO section with code example — sufficient to answer the question |
| 3 | `fastmcp-running-server / HTTP Transport (Streamable)` | 258 | Opens with "STDIO is ideal for…" list then transitions to HTTP content |
| 5 | `fastmcp-running-server / Choosing the Right Transport` | 932 | SSE deprecation + CLI flags + reload — noise for this query |

60% of the full-content response (chunk 5, 932 tokens) was irrelevant to the query. BM25 matched it on "transport" and "run" without understanding the question was specifically about stdio.

Chunk 2 contains the complete STDIO answer: the key fact that `run()` with no arguments uses STDIO by default, a working code example, and enough behavioural context (stdin/stdout, client spawns process) to implement. An agent reading the summaries and heading paths would select chunk 2 and skip chunks 3 and 5.

**Token savings vs WebFetch:**

- Agentless full fetch: **707 tokens saved (31% reduction)**
- Selective fetch (chunk 2 only, agent-in-loop): **1,897 tokens saved (84% reduction)**

**⚠️ Agentless benchmark caveat**

This benchmark does not simulate an agent making selective chunk decisions. The summary scan (81 tokens) was computed but not acted on — all three matched chunk IDs were fetched unconditionally:

```python
chunk_ids = [r["chunk_id"] for r in summary_hits]  # [2, 3, 5] — all of them
full_result = query_docs(db, query="", chunk_ids=chunk_ids, detail="full")
```

The 360-token figure (chunk 2 only) is what a real agent would spend after reading the summaries and heading paths, recognising that chunk 2 is the STDIO section and chunks 3 and 5 are not. But no agent was in the loop to make that decision.

The honest agentless result is **1,550 tokens vs 2,257 for WebFetch (69%)**. The selective figure requires an agent reading summaries and choosing — that path is not yet benchmarked.

---

## Summary Heuristic — Heading-Aware Generation

### Problem

The current heuristic extracts the first non-trivial sentence from a chunk's content as its summary. This breaks when the first sentence is a transition or throwaway line rather than a description of what the chunk covers.

Observed in the fastmcp stdio benchmark:

| Chunk | Summary generated | What the chunk actually covers |
|---|---|---|
| 2 | "You can now run this MCP server by executing `python my_server." | The `run()` method intro — STDIO is the default |
| 3 | "STDIO is ideal for: \* Local development..." | STDIO transport section |
| 5 | "We recommend using HTTP transport instead of SSE for all new projects." | SSE deprecation + CLI reload |

Chunk 2's summary is the sentence immediately after a code block (`mcp.run()`). It tells the agent nothing about the chunk's subject. An agent scanning summaries for "how to configure stdio" has no signal from chunk 2 — it looks like a generic "how to run the server" chunk, not an STDIO-specific one.

In practice, the agent would correctly fetch chunk 3 (explicit STDIO signal) and skip chunk 5 (SSE, wrong topic), but would skip chunk 2 despite it containing the STDIO default behaviour (`run()` with no arguments = stdio). That's a missed relevant chunk, not just wasted tokens.

### Root cause

The heuristic is implemented in `src/tank/builder/chunking.py` (`generate_summary()`). It picks the first sentence of the raw content string. For chunks that open with a code block or a short bridging sentence, this produces a summary that describes the transition, not the subject.

**Update:** `heading_path` is now correctly populated — `chunk_file()` was previously reading `header_path` from chunkana metadata (always `[]`); it now reads `section_tags[0]`, giving paths like `"fastmcp-running-server / STDIO Transport (Default)"`. The structural signal is present; it just isn't used by the summary heuristic yet.

### Proposed fix: heading path + first sentence

A chunk's `heading_path` now encodes where in the document the chunk lives (e.g. `"fastmcp-running-server / STDIO Transport (Default)"`). The summary heuristic should incorporate this structural signal:

```
summary = "<leaf heading>: <first prose sentence>"
```

For chunk 2, which sits under `## The run() Method`, this would produce:

```
The run() method: You can now run this MCP server by executing `python my_server.py`.
```

For chunk 2, under `### STDIO Transport (Default)`:

```
STDIO Transport (Default): STDIO (Standard Input/Output) is the default transport for FastMCP servers.
```

The heading provides the subject; the first sentence provides the detail. An agent scanning these for "stdio configuration" would immediately recognize both chunks 2 and 3 as relevant.

### Edge cases to handle

- **No heading path** (preamble chunks): fall back to current first-sentence behaviour.
- **Heading path equals the page/doc title** (top-level chunk): skip the heading prefix to avoid redundancy — it adds no signal.
- **Heading longer than ~60 chars**: truncate or use only the leaf node.
- **First sentence is a list or code block**: skip to the next prose sentence, same as current behaviour.

### Where to implement

`src/tank/builder/chunking.py` — `generate_summary(content: str, heading_path: str | None) -> str`

The `heading_path` field is already computed before `_generate_summary` is called; it just isn't passed through. The change is additive with no schema impact — `summary` is still a plain string, it just has a richer value.

### Acceptance criteria

- Chunk 2 summary includes "run()" or "STDIO" so an agent querying for stdio configuration has a signal.
- Existing summaries that were already informative (chunk 3, chunk 5) are not degraded.
- Preamble chunks (no heading) fall back gracefully.
- No change to the `summary` field schema or storage model.

---

### Related files

- `src/tank/server.py` — `query_docs()`, `_apply_token_budget()`
- `docs/ranking.md` — BM25 ranking strategy and greedy budget enforcement
- `docs/chunking.md` — chunkana defaults, chunk size ranges, token implications
- `docs/architecture.md` — `query-docs` tool surface documentation

---

## Chunker Replacement — Heading-Based Splitting

### Problem

chunkana's size-based splitting produces chunks that span multiple sections. In the
fastmcp benchmark, chunk 5 covers six `###` sections (Choosing the Right Transport,
FastMCP CLI, Dependency Management, Passing Arguments to Servers, Auto-Reload,
Async Usage) in a single 932-token chunk. FTS5 matches it on incidental keyword
overlap ("transport", "run"), not relevance. An agent reading summaries has no way
to know the chunk is mostly off-topic for a stdio configuration query.

The root cause is that chunkana doesn't split at heading boundaries at all heading
levels. Its `structural` strategy splits only at `##` level, keeping all `###`
subsections together — producing coarser chunks than the default, not finer.
`header_path` is always `[]`; section headings are only available after the fact in
`section_tags`, which Tank now reads as a workaround for `heading_path` construction.

### What we need

- Split at heading boundaries (`##`, `###`, and deeper) as the primary split point
- Treat fenced code blocks as atomic — never split mid-fence
- If a section exceeds a size threshold, split at paragraph boundaries within it
- `heading_path` accurate by construction, not inferred from `section_tags[0]`

### chunkana verdict

Does not support heading-based splitting at arbitrary depth. `strategy_override="structural"`
splits at `##` only. No config combination produces one-chunk-per-section behaviour.
The `section_tags` workaround is the ceiling of what chunkana can give us.

### semchunk (isaacus-dev/semchunk) — evaluated and ruled out

semchunk is a general-purpose recursive delimiter splitter. It splits on newlines,
whitespace, and sentence terminators until chunks reach a target token count. There
is no markdown heading awareness — a `###` boundary is not a privileged split point.
It solves a different problem (same-sized chunks for embedding pipelines) and would
reproduce the multi-section chunk problem. Token-counter-driven rather than
structure-driven; requires a tokenizer dependency at build time. Ruled out.

### Custom chunker

A documentation-specific markdown chunker is a small, well-scoped piece of code.
The core logic is:

1. Parse the document line by line, tracking heading level and fenced code block state
2. On each heading line outside a code fence: emit the current chunk, start a new one
3. Within a chunk, if size exceeds threshold: split at the nearest paragraph boundary
4. Build `heading_path` directly from the heading hierarchy during the walk

Estimated scope: ~150 lines. The edge cases are well-defined (preamble before first
heading, sections with only a code block, deeply nested headings, very large sections).

**Payoff**: every chunk maps to exactly one section, `heading_path` is correct by
construction, the summary heuristic improvement (heading prefix + first sentence) works
cleanly, and multi-section chunks like chunk 5 disappear.

### ⚠️ Before building — survey existing markdown chunkers

Before writing a custom chunker, audit available libraries for a production-ready
markdown-structure-aware implementation that fits the problem space. Criteria:

- Splits at heading boundaries at all levels (`##`, `###`, etc.)
- Treats fenced code blocks as atomic
- No heavy dependencies (no PyTorch, no LLM calls at build time)
- Actively maintained
- Handles the edge cases above with existing tests

Known candidates to evaluate: none identified yet. semchunk and chunkana have been
ruled out. Any replacement must be benchmarked against the fastmcp fixture to confirm
it resolves the multi-section chunk problem before adoption.

### Timing

Lower priority than the `search-docs` / `fetch-docs` endpoint split. The chunker
affects build quality; the endpoint split affects agent behaviour and is a breaking
change that should land first. Revisit when the endpoint redesign is complete.

