# Synaptic Drift — Search Performance Benchmarks

## Summary

FTS5 queries against a 100,427-chunk real documentation index complete in under 21ms P95 across all tested query shapes. The most common agent query — a two-or-three-term technical intersection — runs in 5–6ms P95. Rare or highly specific terms complete in under 0.2ms. The slow end (~20ms P95) only appears when fetching a large result set for a very common word (`configuration`, limit=20).

---

## Corpus

The benchmark index was built from **59 real documentation packs** sourced from [directory.llmstxt.cloud](https://directory.llmstxt.cloud/). All packs were built using `synd build --source <url>/llms-full.txt` against live sites.

| Metric | Value |
|---|---|
| Total chunks | 100,427 |
| Total packs | 59 |
| Sources | Real API and developer documentation (Coinbase, Infisical, Pinecone, Axiom, CrewAI, Bright Data, Speakeasy, and 52 others) |
| Chunk size | 20–800 tokens (project default limits) |
| Index backend | SQLite FTS5, WAL mode, external content table |

This corpus was chosen deliberately over a synthetic one. A synthetic corpus with a small fixed vocabulary gives every term an artificially high document frequency (~44%), making even "rare" queries slow. Real documentation has a long-tail vocabulary distribution: most technical terms appear in a small fraction of chunks, which is the query shape that matters for an AI agent.

The full list of sources and a reproducible setup script are at `scripts/build_benchmark_packs.py`.

---

## Methodology

Each query type is run **2500 times** against the same in-memory-equivalent database (a fresh temp-file DB loaded from the fixture packs at benchmark startup). Timings use `time.perf_counter()` around the `search()` call only — no fixture setup, no result serialisation. True percentiles are computed from all 2500 raw samples per query.

**Metrics reported:**
- **P50** — median latency; what a typical query costs
- **P95** — 95th-percentile latency; the tail users would notice

The benchmark calls the public `search()` API in `src/synd/search/fts.py`, which includes query preprocessing (stopword filtering, special character sanitisation) as well as the FTS5 `MATCH` and BM25 ranking.

Run the benchmark yourself:

```bash
# One-time: fetch and build the 59 packs (~10 min, requires network)
python scripts/build_benchmark_packs.py

# High-precision run (2500 reps/query, results written to latency.json)
python scripts/run_accurate_benchmarks.py

# Quick regression check via pytest (50 reps/query)
pytest tests/benchmarks/test_query_latency.py --benchmark -v -s
```

Results are written to `tests/benchmarks/results/latency.json`.

---

## Results

Measured on a single core, Python 3.12, SQLite 3.x, Linux. 100,427 chunks, 59 packs, 2500 reps/query.

| Query type | Example query | Limit | P50 ms | P95 ms |
|---|---|---|---|---|
| Common single term | `install` | 10 | 9.0 | 9.9 |
| Multi-term intersection | `authentication token` | 10 | 4.9 | 5.3 |
| Technical specific | `webhook endpoint` | 10 | 2.5 | 2.7 |
| Rare / specific term | `sigstore` | 10 | 0.12 | 0.17 |
| High-limit common | `configuration` | 20 | 19.0 | 20.4 |

---

## What Drives Latency

FTS5 BM25 is O(posting-list-size): the time to answer a query is proportional to how many chunks match it. This has two practical implications:

**Term frequency is the dominant factor.** "install" matches thousands of chunks across 59 documentation packs, so BM25 has a long list to score and sort. "sigstore" appears in a handful of chunks, so it returns in microseconds. An AI agent querying for a specific API method name, class, or configuration key will land near the fast end.

**Multi-term queries are faster than single-term.** "authentication token" is faster than "install" alone because the FTS5 inverted index intersects two posting lists before scoring — only chunks that contain both terms are ranked. More terms → smaller intersection → less BM25 work.

**Limit=20 on a common term is the slow path.** The high-limit/common-term case (20ms P95) represents the worst realistic scenario: a very common word with a large result set requested at double the default limit. Still well within an interactive latency budget.

---

## Regression Guard

`tests/benchmarks/test_query_latency.py` asserts `P95 < 100ms` for every query type. This is a safety-net threshold with generous headroom — it would catch a significant FTS5 regression (wrong index, full-table scan, missing `LIMIT`) without triggering on normal environmental variation.

The threshold is not a performance target. The performance target is the table above.
