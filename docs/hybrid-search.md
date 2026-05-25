# Hybrid Search

## Why

Tank's current FTS5/BM25 search is keyword-based. Queries must share vocabulary with the
indexed document or return nothing. The natural language query
`"how do I configure a stdio implementation in fastmcp"` returns 0 results from FTS5
because "configure" and "implementation" do not appear in the source document. An LLM
agent bridges this gap by translating the NL query into FTS5 terms before calling
`search` — but that translation step can fail, and when it does the agent falls back
to WebFetch at full page cost.

Hybrid search (BM25 + vector similarity) eliminates the vocabulary mismatch problem.
Semantic similarity matching would find `"STDIO is the default transport"` and
`"run() with no arguments uses STDIO"` from the NL query directly, without requiring
exact term overlap.

**This is a reliability improvement, not a token efficiency improvement.** When FTS5
finds relevant chunks, an agent reading summaries and selecting the right one already
achieves ~84% token savings vs WebFetch. Better ranking within a working result set
yields marginal gains. The real value of hybrid search is reducing the frequency of
0-result failures — turning misses into hits.

## Architecture

The design constraint is: **no burden to the user beyond `.ctx` file size and a small
query-time SQLite extension.**

This is achieved by moving all model-related work to build time:

1. **Build time** (`tank build`) — the pack publisher generates embeddings for every
   chunk using a local ONNX model. Embeddings are stored inside the `.ctx` archive
   alongside `chunks.jsonl`. The publisher bears the model dependency and the
   (potentially slow) generation cost. This is a one-time cost per pack version.

2. **Pack** (`.ctx`) — the archive bundles pre-computed vectors. No model is required
   to consume the pack. File size increases proportionally to corpus size (see below).

3. **Add time** (`tank add`) — vectors are extracted from the `.ctx` and loaded into
   a `sqlite-vec` virtual table in `index.db`, alongside the existing FTS5 index.
   No model, no generation.

4. **Query time** — `search` runs both FTS5 and a vector ANN search, combines
   scores via Reciprocal Rank Fusion (RRF), and returns the merged ranked list.
   The only runtime dependency is the `sqlite-vec` SQLite extension.

## Dependencies

### Publisher (build time)

- **`fastembed`** — ONNX-based embedding library, no PyTorch. ~50MB runtime plus
  ~80–400MB model download depending on the chosen model. Lightweight by embedding
  library standards.
- A small ONNX model such as `all-MiniLM-L6-v2` (384 dimensions, ~90MB).

Ruled out:
- **`sentence-transformers`** — pulls in PyTorch (~2GB). Too heavy for a CLI tool.
- **API embeddings** — violates the "no outbound network calls at query time" constraint.
  Also couples build correctness to an external service.

### Consumer (query time)

- **`sqlite-vec`** — SQLite extension for vector column type and ANN search. Small
  shared library, no model weights. Keeps the vector index inside the existing
  `index.db` with no separate service required.

## File size

At 384 dimensions (float32), each chunk's embedding is ~1.5KB.

| Corpus size | Embedding overhead |
|---|---|
| 100 chunks | ~150KB |
| 1,000 chunks | ~1.5MB |
| 10,000 chunks | ~15MB |

Whether this is acceptable depends on how packs are distributed. For local builds where
the publisher and consumer are the same person, it is a non-issue. For a future registry
where packs are downloaded, the size increase should be documented alongside the pack.

## Score fusion

BM25 and cosine similarity scores are on different scales and cannot be added directly.
Reciprocal Rank Fusion (RRF) is the standard approach: each result is scored as
`1 / (k + rank)` from each retriever independently, then the scores are summed. This
requires no tuning and is robust to score scale differences.

## Deferred until

Hybrid search is explicitly deferred past MVP. CLAUDE.md states:
`"SQLite FTS5 is the only search backend for MVP. No embedding dependencies."`

Preconditions for revisiting:
- Evidence from a real multi-document corpus that 0-result FTS5 failures are frequent
  enough to justify the added build complexity and `.ctx` size increase.
- The `search-docs` / `fetch-docs` endpoint split (see `docs/decisions.md` D12) is
  the higher-priority search improvement — it enforces the two-step pattern
  architecturally and eliminates the single-step footgun without adding any dependencies.
