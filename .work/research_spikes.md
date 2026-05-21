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

### Related files

- `src/tank/server.py` — `query_docs()`, `_apply_token_budget()`
- `docs/ranking.md` — BM25 ranking strategy and greedy budget enforcement
- `docs/chunking.md` — chunkana defaults, chunk size ranges, token implications
- `docs/architecture.md` — `query-docs` tool surface documentation
