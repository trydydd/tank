# Ultraplan Review — Accuracy and Realism Audit

Adversarial evaluation of `docs/ultraplan.md`, focused on verifying assumptions, challenging conclusions, and flagging unsupported claims.

---

## 1. Claims That Are Accurate

**Context7 at 55k stars** — Verified. Currently ~55.7k, growing ~800/week. Description is accurate.

**Grounded Docs MCP Server, DevDocs MCP Server** — Both exist and are described accurately.

**Normalizer shared between builder and verifier** — Verified. Both import from `tank.builder.normalizer`.

**WAL mode + 5000ms busy timeout** — Verified at `db.py:75-76`. Exact match.

**Sigstore/SLSA narrative** — Credible. Python 3.14 is moving to Sigstore-only signing (PEP 761). The "documentation supply chain" framing is novel and timely, though adoption is early-to-mid phase.

---

## 2. Claims That Are Inaccurate or Unsupported

**"Sub-10ms queries" (ultraplan line 149)** — There are zero benchmarks anywhere in the codebase. No profiling, no timing tests, no performance assertions. This number appears to be invented. It might be true for a small index, but it's presented as fact without evidence. **Recommendation: add a benchmark test before citing performance numbers.**

**"BM25 is competitive with dense retrieval" (ultraplan line 133)** — This is context-dependent, not a blanket truth. IR research shows BM25 is competitive for exact-match queries (API names, error codes, config keys) but significantly worse for semantic/intent queries where vocabulary mismatch exists ("How do I log in?" vs. docs that say "authentication"). The standard in production retrieval systems is hybrid BM25 + dense + reranking. The document presents this as settled when it's actually a tradeoff the team should make with eyes open. **More critically: the current FTS5 implementation is so naive that claiming "FTS5 is good enough" is premature — you haven't tried a properly configured FTS5 yet.**

**MCP "40-50% of context windows" (ultraplan line 274)** — The document frames this as "research." It's not. It comes from industry benchmarks (Scalekit, Sideko) and anecdotal reports (Merge's Feig in The New Stack). The numbers are real and observed in practice, but calling it "research" is misleading. **Recommendation: say "industry benchmarks" not "research."**

**llms.txt "growing fast" (ultraplan line 41)** — ~784 sites have implemented it, which technically qualifies as "hundreds." But a 300,000-domain study found only ~10% adoption. Growth is concentrated in developer tooling (Cursor, Cline, MCP servers), not broad web adoption. Major AI crawlers (ClaudeBot, Google-Extended) effectively don't prioritize it. The strategy of building on llms.txt is still sound, but the document oversells the adoption trajectory. **Recommendation: temper the framing to "growing among developer tools" not "growing fast" broadly.**

---

## 3. The FTS5 "Good Enough" Dismissal — Wrong Framing

This is the document's most consequential analytical error. The document treats the search quality question as binary: "FTS5 vs. embeddings." The reality is that the current FTS5 implementation uses roughly **30-40% of FTS5's available capability**.

### What the search currently does (`fts.py:60-70`)

- Raw query passthrough to FTS5 MATCH — zero preprocessing
- Uniform BM25 weights `(1.0, 1.0, 1.0)` — summary and content weighted identically
- Default tokenizer — no stemming, no code-aware tokenization
- Silent exception swallowing (`except Exception: return []` at `fts.py:76`)
- `heading_path` is stored but **not indexed in FTS5** — a strong relevance signal is wasted

### What FTS5 supports but Tank doesn't use

- Column weighting (summary should be 2-3x content weight)
- Custom tokenizers (porter stemmer, unicode61)
- Prefix queries (`auth*` matching `authentication`)
- Phrase matching, NEAR queries, boolean operators
- Query preprocessing (stopword removal, synonym expansion)

### The correct conclusion

Not "FTS5 is good enough, skip embeddings." It's: **"We haven't tried a properly tuned FTS5 yet. Tune it first, measure the quality gap, then decide about embeddings."**

### Actionable FTS5 improvements for the roadmap (ordered by impact)

1. **Add `heading_path` to FTS5 index with 2.5x weight** — Schema change to `db.py:48`, weight change in `fts.py:62`. Headings are the strongest relevance signal in documentation search.
2. **Tune BM25 column weights** — Change `bm25(chunks_fts, 1.0, 1.0, 1.0)` to something like `bm25(chunks_fts, 2.5, 1.5, 1.0)` (heading > summary > content).
3. **Add query preprocessing** — Stopword filtering, term normalization. Currently "How do I configure the authentication system?" wastes BM25 capacity on "how", "do", "I", "the".
4. **Synonym/abbreviation expansion** — A small dict mapping `auth` → `authentication`, `JWT` → `JSON Web Token`, etc. Documentation search has predictable vocabulary patterns.

These four changes are v0.2.0-level work, not v1.0.0. They should be in the roadmap before any embeddings discussion.

---

## 4. The Rust/PyO3 Dismissal — Mostly Correct, But Understates the Validator Problem

The document correctly concludes that PyO3 is premature. However, its reasoning is flawed.

**What the document says** (ultraplan line 149): "the validator runs once per pack import" and performance is fine.

**What the code actually does** (`verify.py:240-260`): `_read_archive_bytes()` reads the entire ZIP into memory, then reconstructs the entire archive in a second in-memory ZIP — decompressing and re-compressing every file — just to zero out `pack_digest` in the manifest and compute a hash. For a pack near the 500MB limit (`verify.py:46`), this allocates 500MB+, decompresses everything, re-compresses everything, and holds the result in memory.

This isn't a Rust-vs-Python performance question. It's an **algorithmic design problem**. The fix is to compute the digest differently (e.g., hash individual entries in a defined order rather than reconstructing the whole archive), not to rewrite in Rust. The document's dismissal of Rust is correct, but for the wrong reason — the validator's inefficiency is real, it just doesn't need Rust to fix.

**Recommendation: add a note to v0.2.0 roadmap to optimize `_read_archive_bytes()`. This is a correctness/efficiency issue independent of the Rust question.**

---

## 5. Bug the Document Missed: Page ID Foreign Key Integrity

The exploration found a bug not mentioned in Section VIII.

**The schema** (`db.py:24`): `pages.id` is `INTEGER PRIMARY KEY AUTOINCREMENT`

**Build time** (`build.py:51-69`): Pages get manually assigned IDs (1, 2, 3...) and these IDs are written into `pages.json` in the `.ctx` pack. Chunks reference these page IDs via `page_id`.

**Import time** (`db.py:121-126`): The INSERT into `pages` omits the `id` column:

```python
"INSERT INTO pages (package, version, url, content_hash) VALUES (?, ?, ?, ?)"
```

SQLite AUTOINCREMENT generates new IDs. If this isn't the first pack imported, the auto-generated IDs won't match the `page_id` values that chunks carry. The chunks' `page_id` foreign keys point to the wrong pages (or nonexistent rows).

**This is a data integrity bug that should be added to the v0.1.0 fix list.** Either include `id` in the page INSERT and use the pack's IDs, or remap chunk `page_id` values to the auto-generated IDs during import.

---

## 6. The Embeddings Dismissal — Conditionally Correct

The four arguments against embeddings-in-packs (model coupling, pack size, hash stability, FTS5 sufficiency) are architecturally sound. Baking model-specific vectors into a portable format is genuinely questionable.

**But the alternative recommendation is incomplete.** The document says "invest in better FTS5 tokenization" but doesn't specify what. Given the current implementation's naivety (uniform weights, no tokenizer config, no query preprocessing), there's a substantial quality gap that neither FTS5-as-currently-configured nor embeddings-in-packs addresses.

The document's recommendation to compute embeddings at `tank pull` time (import-side, stored in `index.db`) is correct architecture. But the roadmap pushes this to "maybe never" territory. A more honest framing: **FTS5 tuning is the v0.2.0 priority; import-side embeddings are the v1.1 contingency if tuned FTS5 isn't enough for real users.**

---

## 7. Stale Item in v0.1.0 Checklist

The ultraplan's v0.1.0 checklist (line 166) includes "Fix the one mypy error in `src/tank/builder/build.py:133`." This error has already been fixed — mypy runs clean. This item is stale and should be removed.

---

## 8. Summary of Recommendations for Revised Roadmap

| Item | Target | What to change |
|---|---|---|
| Page ID FK bug | v0.1.0 | Fix `db.py:121-126` page ID integrity on import |
| "Sub-10ms" claim | Remove or benchmark | Either add a performance test or remove the claim |
| FTS5 tuning | v0.2.0 | heading_path indexing, BM25 weight tuning, query preprocessing, synonym expansion |
| Validator optimization | v0.2.0 | Refactor `_read_archive_bytes()` to avoid full ZIP reconstruction |
| llms.txt framing | Section I | Temper "growing fast" to "growing in developer tooling" |
| MCP overhead citation | Section VI | Change "research" to "industry benchmarks" |
| Embeddings position | Section III | Change "maybe never" to "v1.1 contingency, gated on user feedback after FTS5 tuning" |
| Remove mypy error item | v0.1.0 checklist | Already fixed — stale |
| Silent exception swallowing | v0.1.0 or v0.2.0 | `fts.py:76` catches all exceptions and returns `[]` — queries silently fail |

---

## 9. Bottom Line

The document's strategic analysis (competitive positioning, enterprise moat, CI/CD artifact framing) is solid and grounded. The technical claims are where it gets sloppy: unsubstantiated performance numbers, a "good enough" verdict on a barely-configured search engine, and a missed data integrity bug. The dismissals of Rust and embeddings-in-packs are directionally correct but imprecisely reasoned. The biggest gap is that the roadmap has no line item for search quality improvement between "current naive FTS5" and "maybe embeddings someday" — that middle ground is where the most impactful work lives.
