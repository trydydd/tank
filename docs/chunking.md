# Tank — Chunking

How chunkana splits documentation files into chunks, what controls chunk size, and what the defaults mean for token budgets at query time.

For the broader build pipeline context, see `docs/document-processing.md`.

## How chunkana splits documents

Tank passes raw file content to `chunkana.chunk_text()` with no configuration override, so chunkana uses its defaults. Chunkana splits at structural boundaries — headings, code blocks, and tables — rather than at arbitrary character counts. The chunk boundaries are document-aware:

- A new heading always starts a new chunk.
- Code blocks and tables are **atomic** — they are never split mid-block, even if they exceed `max_chunk_size`.
- Content before the first heading is extracted as a preamble chunk.
- Adjacent chunks share an overlap window so that context is not lost at boundaries.

The strategy chunkana selects depends on the document's content mix:

| Document type | Strategy selected |
|---|---|
| >30% code content | `code_aware` |
| ≥3 headings | `structural` |
| >40% list content and ≥5 list blocks | `list_aware` |
| Everything else | `fallback` |

## Default configuration

Tank calls `chunk_text(raw_content)` with no `ChunkConfig` argument. The active defaults are:

| Parameter | Default | Description |
|---|---|---|
| `max_chunk_size` | 4096 chars | Upper bound on chunk size |
| `min_chunk_size` | 512 chars | Lower bound; short sections are merged up to this threshold |
| `overlap_size` | 200 chars | Characters of overlap copied from the end of one chunk to the start of the next |
| `preserve_atomic_blocks` | `True` | Code blocks and tables are never split |
| `extract_preamble` | `True` | Content before the first heading becomes its own chunk |
| `enable_code_context_binding` | `True` | Code blocks are bound to immediately surrounding prose |

## Chunk size in practice

The character limits translate to approximate token counts using the `len(content) // 4` estimator Tank uses everywhere:

| Bound | Characters | Estimated tokens |
|---|---|---|
| Minimum | 512 | ~128 |
| Maximum | 4096 | ~1024 |

These are soft bounds — chunkana will exceed `max_chunk_size` to avoid splitting an atomic block (a large code example or table). In practice, most prose sections from real documentation land between 200–1500 characters (~50–375 tokens).

The 200-character overlap means adjacent chunks share roughly 50 tokens of context. This is written into the stored content, so overlapping tokens are counted in both chunks' `token_count` fields and in any `max_tokens` budget.

## What this means for `limit` and `max_tokens`

With the default `limit=10` and no `max_tokens`:

- **Best case** (10 short chunks at min size): ~10 × 128 = ~1,280 tokens
- **Worst case** (10 large chunks at max size): ~10 × 1,024 = ~10,240 tokens
- **Typical** (mixed real-world docs): ~10 × 200–400 tokens = ~2,000–4,000 tokens

`max_tokens` is the only mechanism that gives a hard upper bound regardless of what's in the index. For agents with tight context budgets, the recommended pattern is:

```json
{
  "detail": "summary",
  "limit": 20,
  "max_tokens": 800
}
```

This fetches up to 20 candidates from SQLite (ensuring good recall), then trims to ~800 tokens of summaries (~20–40 tokens each, so typically 20–40 results fit). The agent then follows up with `chunk_ids` to fetch only the full content it actually needs.

See `docs/ranking.md` for how the greedy budget enforcement works.

## Configuring chunk size

Tank does not currently expose `ChunkConfig` parameters through the CLI. To change chunking behaviour, modify the `_chunk_text(raw_content)` call in `src/tank/builder/chunking.py:54` to pass an explicit config:

```python
from chunkana.config import ChunkConfig

config = ChunkConfig(max_chunk_size=2048, min_chunk_size=256, overlap_size=100)
ana_chunks = _chunk_text(raw_content, config)
```

Chunkana provides several preset configs as class methods on `ChunkConfig`:

| Preset | `max_chunk_size` | `min_chunk_size` | `overlap_size` | Best for |
|---|---|---|---|---|
| `ChunkConfig()` (default) | 4096 | 512 | 200 | General documentation |
| `ChunkConfig.for_code_heavy()` | 8192 | 1024 | 100 | API references, SDK docs |
| `ChunkConfig.for_structured()` | 4096 | 512 | 200 | Structured reference docs |
| `ChunkConfig.minimal()` | 1024 | 256 | 50 | Dense retrieval, small context windows |
| `ChunkConfig.for_changelogs()` | 6144 | 256 | 100 | Changelogs, release notes |

Exposing this via `tank build --chunk-config <preset>` is a candidate for a future release.
