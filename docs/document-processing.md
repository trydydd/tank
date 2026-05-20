# Tank — Document Processing Pipeline

How `tank build` transforms a local directory of documentation files into a `.ctx` pack.

## Pipeline Overview

```
--source ./docs
     │
     ├─ 1. Source discovery
     ├─ 2. Page construction
     ├─ 3. Chunking
     ├─ 4. Summary generation
     ├─ 5. Content normalization
     ├─ 6. Chunk ID assignment
     ├─ 7. Hash computation
     ├─ 8. Manifest construction
     └─ 9. Archive assembly
           │
           └─ my-lib@1.0.0.ctx
```

## 1. Source Discovery

Starting from the path given to `--source`, the builder discovers documentation files to process.

**Recursion**: subdirectories are walked recursively by default. There is no `--no-recurse` flag in MVP.

**Extension whitelist**: only files matching `.md`, `.html`, or `.htm` are included. All other files are skipped with a debug-level log message (e.g. `DEBUG: skipping docs/diagrams/arch.png — not a supported extension`).

**Walk order**: discovered files are sorted lexicographically by their full relative path (relative to the parent of the `--source` argument). This sort order determines chunk ID assignment and therefore the `normalized_content_hash`. It is a correctness requirement — without deterministic ordering, the same source tree would produce different hashes on different platforms or runs.

Example walk order for `--source ./docs`:

```
docs/api/auth.md
docs/api/billing.md
docs/getting-started.md
docs/guides/deployment.md
docs/guides/monitoring.md
```

Python's `os.listdir` and `pathlib.Path.iterdir()` return entries in filesystem-dependent order. The builder must explicitly sort after discovery, not rely on the iteration order.

## 2. Page Construction

Each file becomes exactly one page entry in `pages.json`.

| Field | Value |
|---|---|
| `id` | Sequential integer, assigned in lexicographic file order starting at 1 |
| `url` | Relative path from the `--source` root, preserving the `--source` directory name. `--source ./docs` + file at `./docs/auth/oauth.md` = `docs/auth/oauth.md`. Only leading `./` is stripped. |
| `title` | Extracted from the first `# heading` in the file, or the filename (without extension) if no heading is found |
| `content_hash` | SHA-256 of the full file content after normalization |

## 3. Chunking

The builder delegates to `chunkana` for structural chunking. Chunkana splits documents at heading boundaries, preserving:

- Code blocks (fenced and indented) as atomic units — never split mid-block
- Tables as atomic units
- Heading hierarchy as metadata (`heading_path`)

**Heading path construction**: the relative file path (minus extension) is used as a prefix, followed by the document's heading hierarchy. The `--source` directory name is stripped from the prefix to avoid redundancy.

| Source file | Heading in file | heading_path |
|---|---|---|
| `docs/auth/oauth.md` | `# Overview` | `auth/oauth / Overview` |
| `docs/auth/oauth.md` | `## Client Credentials` | `auth/oauth / Overview / Client Credentials` |
| `docs/getting-started.md` | `# Installation` | `getting-started / Installation` |

The file path prefix ensures that identically-named headings in different files (e.g. every file has `# Overview`) are disambiguated in search results.

**Chunks per file**: a file with no headings produces a single chunk containing the full file content, with `heading_path` set to the file path prefix only.

## 4. Summary Generation

Each chunk receives a one-line summary, generated heuristically at build time.

**For prose-heavy chunks**: extract the first sentence. A sentence boundary is a period, question mark, or exclamation mark followed by whitespace or end-of-string. If the first sentence exceeds 200 characters, truncate at the last word boundary before 200 characters and append `...`.

**For code-heavy chunks** (more than 50% of content is inside code fences): extract the first function or class signature from the leading code block. If no signature is found, fall back to the first sentence of any prose in the chunk. If the chunk is entirely code with no prose, use the `heading_path` as the summary.

The summary field is present in the schema and the generation strategy can be upgraded in the future without a format change. No LLM dependency is involved.

## 5. Content Normalization

Normalization is applied to chunk content before hashing. The same normalization function (`tank.builder.normalizer`) is used at both build time and verify time — this is the hash stability guarantee.

The normalization rules are defined in `architecture.md` (Token Efficiency > Content normalization):

- Collapse runs of blank lines to a single blank line
- Strip HTML boilerplate, nav, breadcrumbs, footer, version banners
- Remove "Edit this page" links, "See also" sections that are only link lists
- Normalize Unicode whitespace to ASCII
- Preserve code block formatting exactly (indentation matters)
- Preserve table formatting

**What is NOT normalized**: content inside fenced code blocks is preserved verbatim (whitespace, indentation, blank lines). Normalization only applies to prose and markup outside of code fences.

## 6. Chunk ID Assignment

Chunk IDs are sequential integers starting at 1, assigned in the order chunks are produced by the pipeline:

1. Files are processed in lexicographic order (from step 1)
2. Within each file, chunks appear in document order (top to bottom, as produced by chunkana)
3. Each chunk receives the next available ID

This ordering is deterministic: the same source tree always produces the same chunk ID sequence. The `normalized_content_hash` depends on this ordering (chunks are concatenated in ascending ID order before hashing).

## 7. Hash Computation

Three hashes are computed during build:

**Per-chunk `content_hash`**: SHA-256 of the individual chunk's content after normalization. Used for detecting which specific chunks changed between pack versions.

**Per-page `content_hash`**: SHA-256 of the full page content after normalization. Stored in `pages.json`.

**`normalized_content_hash`**: SHA-256 of all chunk content strings, each normalized, concatenated in ascending chunk ID order with a `\n` separator. This hash is independent of metadata (heading paths, summaries, page IDs) and only changes when the actual text content changes.

**`pack_digest`**: computed after archive assembly (step 9). SHA-256 of the full `.ctx` archive bytes, with the `pack_digest` field value in `manifest.json` replaced by an empty string during computation.

## 8. Manifest Construction

The manifest is built from CLI arguments and computed values:

| Field | Source |
|---|---|
| `schema_version` | Hardcoded: `2` |
| `pack_format` | Hardcoded: `"tank-text-v1"` |
| `package` | From CLI argument (`my-lib` in `my-lib@1.0.0`) |
| `version` | From CLI argument (`1.0.0` in `my-lib@1.0.0`) |
| `pack_digest` | Computed after archive assembly |
| `normalized_content_hash` | Computed from step 7 |
| `chunks` | Count of chunks produced |
| `pages` | Count of pages (files) processed |
| `lifecycle_state` | From `--lifecycle` flag (default: `draft`) |
| `policy_profile` | From `--policy-profile` flag (optional) |
| `owner` | From `--owner` flag (optional) |
| `doc_version_status` | Default: `stable` for local builds |
| `source_url` | The `--source` path as provided (normalized: `./` stripped) |
| `created_at` | UTC timestamp at build time |
| `created_by` | `"tank/<version>"` |

Fields not provided via CLI flags are omitted from the manifest (not set to null).

## 9. Archive Assembly

The final `.ctx` file is a zip archive containing:

```
my-lib@1.0.0.ctx
├── manifest.json
├── chunks.jsonl
├── pages.json
└── signatures/
    └── manifest.sig    (empty directory unless signing is configured)
```

Assembly sequence:

1. Write `chunks.jsonl` — one JSON object per line, in chunk ID order
2. Write `pages.json` — array of page objects, in page ID order
3. Write `manifest.json` with `pack_digest` set to empty string
4. Create the zip archive containing all three files (plus empty `signatures/` directory); all ZIP entries use a pinned `date_time` of `(2021, 8, 8, 0, 0, 0)` to ensure the archive is byte-for-byte reproducible across writes
5. Compute `pack_digest` over the archive bytes
6. Rewrite `manifest.json` inside the archive with the real `pack_digest` value
7. Write the final `.ctx` file to the `--output` directory

The output filename is `<package>@<version>.ctx` (e.g. `my-lib@1.0.0.ctx`).

## Example: End-to-End

Given this source tree and command:

```bash
tank build my-lib@1.0.0 --source ./docs --output ./packs
```

```
docs/
├── getting-started.md      # contains: # Installation, ## Prerequisites, ## Quick Start
├── auth/
│   └── oauth.md            # contains: # OAuth2, ## Client Credentials, ## Authorization Code
└── api/
    └── endpoints.md        # contains: # API Reference, ## Users, ## Billing
```

The pipeline produces:

**File processing order** (lexicographic):
1. `docs/api/endpoints.md`
2. `docs/auth/oauth.md`
3. `docs/getting-started.md`

**Pages** (3 entries in `pages.json`):
1. `{ "id": 1, "url": "docs/api/endpoints.md", "title": "API Reference", ... }`
2. `{ "id": 2, "url": "docs/auth/oauth.md", "title": "OAuth2", ... }`
3. `{ "id": 3, "url": "docs/getting-started.md", "title": "Installation", ... }`

**Chunks** (8 entries in `chunks.jsonl`, IDs 1–8):
1. `{ "id": 1, "page_id": 1, "heading_path": "api/endpoints / API Reference", ... }`
2. `{ "id": 2, "page_id": 1, "heading_path": "api/endpoints / API Reference / Users", ... }`
3. `{ "id": 3, "page_id": 1, "heading_path": "api/endpoints / API Reference / Billing", ... }`
4. `{ "id": 4, "page_id": 2, "heading_path": "auth/oauth / OAuth2", ... }`
5. `{ "id": 5, "page_id": 2, "heading_path": "auth/oauth / OAuth2 / Client Credentials", ... }`
6. `{ "id": 6, "page_id": 2, "heading_path": "auth/oauth / OAuth2 / Authorization Code", ... }`
7. `{ "id": 7, "page_id": 3, "heading_path": "getting-started / Installation", ... }`
8. `{ "id": 8, "page_id": 3, "heading_path": "getting-started / Installation / Prerequisites", ... }`

**Output**: `./packs/my-lib@1.0.0.ctx`

## Compatibility with Phase 2 Crawled Builds

Phase 2 will add `tank build --source <URL>` for web-crawled documentation. The processing pipeline is the same from step 3 onward (chunking through archive assembly). The differences are:

- **Source discovery** (step 1): replaced by the crawler, which produces downloaded HTML/Markdown files
- **Page construction** (step 2): `url` is the canonical web URL instead of a file path; `title` is extracted from HTML `<title>` or `<h1>`
- **Ordering**: crawled pages are sorted by canonical URL (lexicographic) before chunk ID assignment, preserving the deterministic hash guarantee
- **source_url on chunks**: full `https://` URLs instead of relative file paths

No MVP schema or format decisions need to change to support this.
