# Synaptic Drift — Ranking Strategy

## Overview

Synaptic Drift's query pipeline has two stages: **ranking** (which chunks match, and in what order) and **budget enforcement** (how many of those chunks fit within a token limit). Both stages run locally with no network or LLM dependency.

## Stage 1 — BM25 Ranking via SQLite FTS5

All queries use SQLite FTS5's built-in BM25 implementation. BM25 is a lexical ranking function that scores each chunk by term frequency and inverse document frequency, adjusted for document length.

**What it does well:**

- Exact and near-exact keyword matches against both `summary` and `content` fields.
- Fast — FTS5's inverted index makes BM25 O(posting-list-size). Measured against 100,116 real documentation chunks: rare technical terms <1ms P95; common single terms ~11ms P95; multi-term intersections ~6ms P95.
- Deterministic — the same query against the same index always returns the same ranking.

**What it does not do:**

- Semantic or synonym matching (e.g. "auth" does not automatically match "authentication"). Vocabulary-mismatch failures that tuned FTS5 cannot address are the trigger for hybrid search (v1.1 contingency).
- Cross-chunk relevance reasoning — it ranks each chunk independently.
- Preference for shorter, denser answers over longer ones with more keyword repetitions.

**Query preprocessing** — before the FTS5 `MATCH` is issued, common English function words (articles, auxiliary verbs, prepositions) are stripped from the query. FTS5 boolean operators (`AND`, `OR`, `NOT`) and words that appear in section titles (`how`, `what`, `where`) pass through unchanged.

The FTS5 index covers three columns with differentiated BM25 weights (`bm25(chunks_fts, 2.5, 1.5, 1.0)`):

| Column | Weight | Description |
|---|---|---|
| `heading_path` | 2.5× | Section hierarchy (e.g. `"Authentication / Configure OAuth2"`). NULL for fallback-chunked documents; FTS5 treats NULL as empty string so the weight only activates when a heading is populated. |
| `summary` | 1.5× | One-line heuristic summary generated at build time |
| `content` | 1.0× | Full chunk text |

Chunks from `revoked` packs are excluded at query time by a `WHERE p.lifecycle_state != 'revoked'` filter applied before ranking.

## Stage 2 — Greedy Token Budget Enforcement

When the caller specifies `max_tokens`, a post-ranking pass enforces a token budget. The algorithm is strictly greedy:

1. Iterate over BM25-ranked results from highest score to lowest.
2. Estimate the token cost of each chunk using `len(text) // 4` (the same estimator used for the `token_count` field written at build time).
3. Include the chunk if its cost does not push the running total above `max_tokens`.
4. Stop at the first chunk that would exceed the budget.

**Token cost estimation by tool:**

| Tool | Text used for estimation |
|---|---|
| `search` | `len(summary) // 4` — summaries only, content is never included |
| `fetch` | `len(content) // 4` — full content is always returned |

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

LLM-based reranking selects the semantically best subset within a budget rather than relying on a fixed ranking order. This is qualitatively different from the greedy approach: instead of keeping the top-N prefix that fits, an LLM reranker can pick any subset of candidates. Synaptic Drift defers this because it introduces latency and a model dependency that conflicts with the local-first, no-LLM-at-query-time constraint for MVP.

The `max_tokens` API parameter is forward-compatible: adding LLM reranking in a later phase does not require callers to change anything.
