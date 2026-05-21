# Tank — Ranking Strategy

## Overview

Tank's query pipeline has two stages: **ranking** (which chunks match, and in what order) and **budget enforcement** (how many of those chunks fit within a token limit). Both stages run locally with no network or LLM dependency.

## Stage 1 — BM25 Ranking via SQLite FTS5

All queries use SQLite FTS5's built-in BM25 implementation. BM25 is a lexical ranking function that scores each chunk by term frequency and inverse document frequency, adjusted for document length.

**What it does well:**

- Exact and near-exact keyword matches against both `summary` and `content` fields.
- Fast — FTS5's inverted index makes BM25 sub-10ms for up to 100,000 chunks on commodity hardware.
- Deterministic — the same query against the same index always returns the same ranking.

**What it does not do:**

- Semantic or synonym matching (e.g. "auth" does not automatically match "authentication").
- Cross-chunk relevance reasoning — it ranks each chunk independently.
- Preference for shorter, denser answers over longer ones with more keyword repetitions.

The FTS5 index covers two columns, both weighted equally (`bm25(chunks_fts, 1.0, 1.0, 1.0)`):

| Column | Description |
|---|---|
| `summary` | One-line heuristic summary generated at build time |
| `content` | Full chunk text |

Chunks from `revoked` packs are excluded at query time by a `WHERE p.lifecycle_state != 'revoked'` filter applied before ranking.

## Stage 2 — Greedy Token Budget Enforcement

When the caller specifies `max_tokens`, a post-ranking pass enforces a token budget. The algorithm is strictly greedy:

1. Iterate over BM25-ranked results from highest score to lowest.
2. Estimate the token cost of each chunk using `len(text) // 4` (the same estimator used for the `token_count` field written at build time).
3. Include the chunk if its cost does not push the running total above `max_tokens`.
4. Stop at the first chunk that would exceed the budget.

**Token cost estimation by detail level:**

| `detail` | Text used for estimation |
|---|---|
| `"summary"` | `len(summary) // 4` |
| `"full"` | `len(content) // 4` |

For the `chunk_ids` path (targeted retrieval), full content is always fetched, so `len(content) // 4` is used regardless of the `detail` parameter.

**Properties of the greedy approach:**

- **Whole chunks only.** The boundary always falls between chunks, never mid-text.
- **Prefix of the ranked list.** The returned set is always the highest-BM25-scoring chunks that fit — never a subset that skips a higher-scored chunk to include a lower-scored one.
- **Approximate.** The `len(text) // 4` estimator is a rough proxy for token count — it ignores tokenizer-specific byte counts, punctuation handling, and subword splitting. It is useful for budget planning but not byte-exact.

## What Changes in Later Phases

### Phase 3 — Hybrid Search

Phase 3 adds BGE-M3 dense and sparse embeddings. The ranking stage becomes a three-way fusion:

1. **Dense retrieval** — cosine similarity over BGE-M3 float32 vectors.
2. **Sparse retrieval** — dot product over learned sparse weight vectors.
3. **FTS5 BM25** — same as today.

The three ranked lists are fused with **Reciprocal Rank Fusion (RRF)** before the budget enforcement stage. Budget enforcement remains unchanged — it still operates on the fused ranked list using the same greedy algorithm.

### Future: LLM Reranking

LLM-based reranking selects the semantically best subset within a budget rather than relying on a fixed ranking order. This is qualitatively different from the greedy approach: instead of keeping the top-N prefix that fits, an LLM reranker can pick any subset of candidates. Tank defers this because it introduces latency and a model dependency that conflicts with the local-first, no-LLM-at-query-time constraint for MVP.

The `max_tokens` API parameter is forward-compatible: adding LLM reranking in a later phase does not require callers to change anything.
