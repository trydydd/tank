# Synaptic Drift — Chunking

How the custom markdown-it-py chunker splits documentation files into chunks, what controls chunk size, and what the defaults mean for token budgets at query time.

For the broader build pipeline context, see `docs/document-processing.md`.

## How the chunker splits documents

Synaptic Drift uses a custom token-walker built on `markdown-it-py` to split documents at structural boundaries. The chunker processes the markdown-it-py token stream directly, which makes heading-level detection and code-fence atomicity precise by construction:

- **Every heading starts a new chunk** — splits occur at all levels `#` through `######`, not just `##`.
- **Code fences are atomic** — a fenced code block is never split across chunks, even if it exceeds `max_chunk_tokens`. The token stream represents each fence as a single self-contained token, so the atomicity guarantee holds without special-casing.
- **Heading path is built by construction** — the chunker maintains an ancestor stack as it walks tokens. When a heading is encountered, the stack is trimmed to the correct depth and the new heading text is pushed. `heading_path` is `" / ".join(ancestor_stack)` at emission time — never reconstructed after the fact.
- **Preamble content** — content before the first heading is emitted as a chunk with `heading_path` equal to the file prefix only (e.g. `auth/oauth`).
- **No overlap window** — chunks do not duplicate content. Each byte of source appears in exactly one chunk.

## Token budget and overflow splitting

The default maximum chunk size is `_DEFAULT_MAX_CHUNK_TOKENS = 500` tokens (estimated as `len(content) // 4`). Headings are the primary split point. When a single heading section exceeds `max_chunk_tokens`, the chunker splits at the next paragraph boundary — never mid-paragraph and never inside a fence.

| Bound | Tokens (approx) |
|---|---|
| Default `max_chunk_tokens` | 500 |
| Default `min_chunk_tokens` | 20 |

The 500-token default is intentionally conservative. Real-world documentation sections — a `###` subsection with a few paragraphs and one code example — typically land between 100–400 tokens. Sections that run long (API reference tables, large code examples) are split at paragraph breaks so each piece remains coherent.

### Minimum-token threshold

When a heading boundary would produce a chunk below `min_chunk_tokens` (default 20), the emit is skipped and `chunk_start_line` is left in place. The suppressed content carries forward and is absorbed by the next section at its next emit point. This eliminates stub chunks — heading-only chunks produced when a heading is immediately followed by another heading with no prose between them — without a separate post-processing pass.

The absorbed heading text remains in the merged chunk's content, contributing to BM25 scoring, while `heading_path` reflects the absorbing section's (deeper) heading. For example:

```
Source:
  ## Authorization         ← heading only, no prose
  ### Introduction
  OAuth2 requires a client ID and secret.

Before (min_chunk_tokens=0):
  Chunk 1  heading_path: "doc / Authorization"
           content:      "## Authorization"             ← 2-token stub

  Chunk 2  heading_path: "doc / Authorization / Introduction"
           content:      "### Introduction\n\nOAuth2 requires..."

After (default min_chunk_tokens=20):
  Chunk 1  heading_path: "doc / Authorization / Introduction"
           content:      "## Authorization\n\n### Introduction\n\nOAuth2 requires..."
```

`Authorization` is still an ancestor in `heading_path` — its BM25 weight is fully preserved. Pass `min_chunk_tokens=0` to disable the guard and restore the original behaviour.

## Heading path examples

| Source file | Heading in file | `heading_path` |
|---|---|---|
| `docs/auth/oauth.md` | preamble (before any heading) | `auth/oauth` |
| `docs/auth/oauth.md` | `# OAuth2` | `auth/oauth / OAuth2` |
| `docs/auth/oauth.md` | `## Client Credentials` (under `# OAuth2`) | `auth/oauth / OAuth2 / Client Credentials` |
| `docs/auth/oauth.md` | `## Authorization Code` (under `# OAuth2`) | `auth/oauth / OAuth2 / Authorization Code` |
| `docs/guide.md` | `### STDIO Transport` (under `# Running Your Server / ## Transport Protocols`) | `guide / Running Your Server / Transport Protocols / STDIO Transport` |

The file prefix ensures that identically-named headings in different files are always disambiguated.

## What this means for `limit` and `max_tokens`

With the default `limit=10` and no `max_tokens`:

- **Best case** (10 small single-paragraph sections): ~10 × 50 = ~500 tokens
- **Worst case** (10 sections at the overflow limit): ~10 × 500 = ~5,000 tokens
- **Typical** (mixed real-world docs): ~10 × 150–300 tokens = ~1,500–3,000 tokens

`max_tokens` is the mechanism that gives a hard upper bound regardless of what's in the index. For agents with tight context budgets, the recommended pattern is:

```json
{
  "limit": 20,
  "max_tokens": 800
}
```

This fetches up to 20 candidates from SQLite (ensuring good recall), then trims to ~800 tokens of summaries (~20–40 tokens each, so typically 20–40 results fit). The agent then follows up with `chunk_ids` to fetch only the full content it actually needs.

See `docs/ranking.md` for how the greedy budget enforcement works.

## Configuring chunk size

Two parameters on `chunk_content()` in `src/synd/builder/chunking.py` control chunk size:

- `max_chunk_tokens` (default `500`) — upper bound; sections that exceed this are split at the next paragraph boundary.
- `min_chunk_tokens` (default `20`) — lower bound guard; heading boundaries that would produce a below-threshold chunk are skipped and the content is absorbed forward into the next section.

Exposing these as `synd build --max-chunk-tokens` / `--min-chunk-tokens` CLI flags is tracked in `docs/roadmap.md`.

## Summary generation

Each chunk's summary is generated by `generate_summary(content, heading_path)` immediately after chunking. The summary uses a heading-aware prefix heuristic (S2):

- **Prefix with leaf heading**: `"STDIO Transport (Default): STDIO is the default transport..."` rather than the transitional `"You can now run this server..."`.
- **Preamble chunks** (no heading in path): first-sentence only, no prefix.
- **Long headings** (> 60 characters): the heading alone is used as the summary.
- **Prose-heavy chunks**: first sentence of prose (heading lines and list items excluded).
- **Code-heavy chunks** (> 50% of content inside fences): first `def`/`class`/`function`/`export` signature from the leading code block; falls back to first prose sentence.

No LLM is involved. All summary generation is deterministic heuristic logic at build time.
