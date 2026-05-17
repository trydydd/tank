# LocalContext — Architecture

An open-source, local-first MCP server that automatically detects project dependencies, crawls their documentation, indexes it with hybrid search, and serves it to AI coding agents with minimal token overhead.

## Goals

- **Zero-config discovery**: detect dependencies from lockfiles and manifest files automatically
- **Local-first**: all data stays on the user's machine, no cloud dependency
- **Token-efficient**: layered retrieval that minimizes context window usage without sacrificing accuracy
- **Reproducible**: a `docs.lock` file with content hashes enables team sharing, staleness detection, and integrity verification
- **Fast**: sub-10ms queries against pre-indexed content via SQLite
- **Ethical**: crawl responsibly with rate limiting, robots.txt compliance, and transparent identification

## MCP Tool Surface

The server exposes three tools to the AI agent.

### `resolve-deps`

Read-only health check. Scans the project for dependency files, hashes them, and compares against `docs.lock`.

**Input**: optional `project_path` (defaults to cwd)

**Output**:
```json
{
  "status": "stale",
  "dep_files": [
    { "path": "requirements.txt", "hash": "sha256:f7a8...", "locked_hash": "sha256:c3d4...", "match": false }
  ],
  "packages": {
    "indexed": ["fastapi@0.115.0", "pydantic@2.11.0"],
    "missing": ["httpx@0.28.0"],
    "version_changed": [{ "name": "uvicorn", "locked": "0.30.0", "current": "0.32.0" }],
    "removed": ["flask@3.0.0"]
  }
}
```

This tool is effectively free to call (microsecond hash comparison) and should be invoked at the start of every session as a health check.

### `index-deps`

Explicit crawl trigger. Fetches, chunks, embeds, and indexes documentation for the specified packages (or all missing/stale packages by default).

**Input**:
```json
{
  "packages": ["httpx@0.28.0", "uvicorn@0.32.0"],
  "force": false
}
```

- `packages`: optional, defaults to everything `resolve-deps` reported as missing or changed
- `force`: re-crawl even if content hash matches (for when docs update without a version bump)

**Output**: updated manifest entries with new hashes and chunk counts.

This is the only slow tool. The agent knows upfront that it may take seconds to minutes depending on the number of packages.

**Graceful degradation**: if the base-only package is installed (no `[cli]` extra), `index-deps` cannot crawl or embed locally. It will attempt to pull pre-built packages from the community registry instead. If the requested package isn't available there, it returns a clear error directing the user to install `localcontext[cli]`.

### `query-docs`

Hybrid search across indexed documentation. Fast, read-only, only hits already-indexed content.

**Input**:
```json
{
  "query": "how to define a dependency injection in FastAPI",
  "packages": ["fastapi"],
  "max_tokens": 2000,
  "detail": "summary",
  "chunk_ids": []
}
```

- `query`: natural language question (required unless `chunk_ids` is provided)
- `packages`: optional filter to scope search to specific libraries
- `max_tokens`: budget cap for the response
- `detail`: `"summary"` (default) returns heading path + one-line summary per chunk (~20-40 tokens each); `"full"` returns complete chunk content
- `chunk_ids`: optional list of specific chunk IDs to expand to full content, bypassing search entirely

If a queried package is not indexed, the tool returns an explicit `"not_indexed"` status rather than silently returning poor results.

**Typical agent workflow**:
1. Call `query-docs` with `detail: "summary"` to scan what's available
2. Pick the relevant chunks from the summary list
3. Call `query-docs` again with `chunk_ids: [12, 47, 83]` and `detail: "full"` to pull only what's needed

This two-step pattern keeps token usage minimal while preserving access to full content.

## Hash Chain and `docs.lock`

The system maintains a hash chain: **dependency file → docs.lock → indexed chunks**. Any change at the top propagates detection downward.

### Lockfile Format

```toml
[meta]
schema_version = 1
generated_at = "2026-05-16T14:00:00Z"

[[meta.dep_files]]
path = "requirements.txt"
hash = "sha256:f7a8b9..."

[[meta.dep_files]]
path = "pyproject.toml"
hash = "sha256:e1d2c3..."

[packages.fastapi]
version = "0.115.0"
source = "https://fastapi.tiangolo.com"
content_hash = "sha256:a1b2c3..."
chunks = 412
indexed_at = "2026-05-14T10:30:00Z"

[packages.pydantic]
version = "2.11.0"
source = "https://docs.pydantic.dev/2.11"
content_hash = "sha256:d4e5f6..."
chunks = 638
indexed_at = "2026-05-12T08:15:00Z"
```

### Hash Semantics

- `dep_file.hash`: SHA-256 of the raw dependency file bytes. Changing any dependency triggers a diff.
- `content_hash`: SHA-256 of all chunk texts concatenated in order after normalization. Computed over post-processed output, not raw HTML, so cosmetic upstream changes don't cause unnecessary re-indexing.

### Staleness Detection Flow

```
resolve-deps called
  ├─ hash(requirements.txt) == docs.lock meta.dep_files[0].hash ?
  │   ├─ YES → all good, return "current" status
  │   └─ NO  → diff old vs new dep list
  │            ├─ new packages      → status: "missing"
  │            ├─ removed packages  → status: "removed"
  │            └─ version changes   → status: "version_changed"
  └─ for each indexed package, verify SQLite DB exists and is readable
```

### Multi-File and Monorepo Support

The `meta.dep_files` array supports multiple dependency files. Each is tracked with an independent hash. The lockfile represents the union of all discovered dependencies. In a monorepo, each workspace can have its own `docs.lock`, or a root-level one can aggregate.

## Dependency File Parsers

Supported manifest/lockfile formats:

| Ecosystem  | Files                                          |
|------------|-------------------------------------------------|
| Python     | `requirements.txt`, `pyproject.toml`, `Pipfile`, `setup.cfg` |
| Node       | `package.json`, `package-lock.json`, `yarn.lock`, `pnpm-lock.yaml` |
| Rust       | `Cargo.toml`, `Cargo.lock`                     |
| Go         | `go.mod`, `go.sum`                              |
| Ruby       | `Gemfile`, `Gemfile.lock`                       |
| PHP        | `composer.json`, `composer.lock`                |
| Java/Kotlin| `build.gradle`, `build.gradle.kts`, `pom.xml`  |
| .NET       | `*.csproj`, `packages.config`, `Directory.Packages.props` |

Each parser extracts: package name, version (or constraint), and optionally whether it's a dev dependency.

## Doc Source Resolution

Not every package has docs in the same place. The resolver uses a tiered strategy with deps.dev as the primary lookup.

### deps.dev API (primary)

Google's deps.dev API is the first hop for resolving doc URLs. It aggregates metadata across npm, PyPI, Cargo, Maven, Go, NuGet, and RubyGems — covering the vast majority of open-source packages. For each package version, it provides `HOMEPAGE`, `SOURCE_REPO`, and `ISSUE_TRACKER` links.

```python
from pydepsdev.api import DepsdevAPI

async with DepsdevAPI() as api:
    version_info = await api.get_version("pypi", "fastapi", "0.115.0")
    # version_info.links → [
    #   {"label": "HOMEPAGE", "url": "https://fastapi.tiangolo.com"},
    #   {"label": "SOURCE_REPO", "url": "https://github.com/tiangolo/fastapi"},
    # ]
```

The resolver prefers `HOMEPAGE` (usually the doc site) over `SOURCE_REPO` (usually the GitHub repo). If `HOMEPAGE` is missing, it falls back to `SOURCE_REPO` and looks for a `/docs` folder or README.

### Fallback tiers

If deps.dev doesn't have the package or doesn't provide a useful link:

1. **Well-known patterns**: `https://docs.{name}.dev`, `https://{name}.readthedocs.io`, GitHub repo `/docs` folder
2. **GitHub repo README + `/docs`**: fallback when no dedicated doc site exists
3. **Manual overrides**: a `.context/sources.toml` file where users can pin a doc URL for any package

```toml
# .context/sources.toml
[overrides.my-internal-lib]
source = "https://internal-docs.company.com/my-lib"
auth = "header:Authorization=Bearer ${INTERNAL_DOCS_TOKEN}"

[overrides.fastapi]
source = "https://fastapi.tiangolo.com"
```

deps.dev is a free API with no authentication required. It's rate-limited but generous enough for our use case (we only query it during `index-deps`, not on every `query-docs`). Package metadata is cached locally so repeat builds don't re-query.

## Crawl Pipeline

```
URL resolved
  → check community registry for pre-built package (skip crawl if found + hash matches)
  → scheduler assigns domain queue with rate limiter
  → Crawl4AI deep crawl (BFS, respects robots.txt, outputs clean markdown)
      → configured with: excluded_tags, remove_overlay_elements,
        exclude_external_links, word_count_threshold
      → CacheMode.ENABLED for incremental re-crawls
  → for each page markdown:
      → compute per-page content hash (for incremental re-indexing)
      → chunkana structural chunking (preserves code blocks, tables, heading paths)
      → for each chunk:
          → generate summary line (function/class signature + one-line description)
          → compute BGE-M3 embeddings via FlagEmbedding (dense + sparse in one call)
          → store in SQLite
  → compute content_hash over all normalized chunk texts
  → update docs.lock
```

### Crawl4AI Integration

Crawl4AI is the crawl and content extraction engine. It handles page fetching, JavaScript rendering (via Playwright/Chromium), robots.txt compliance, HTML→markdown conversion, and caching. We configure it but don't reimplement what it already does well.

```python
from crawl4ai import AsyncWebCrawler
from crawl4ai.async_configs import BrowserConfig, CrawlerRunConfig, CacheMode

browser_config = BrowserConfig(
    user_agent="LocalContext/0.1.0 (+https://github.com/org/localcontext)",
    verbose=False,
)

run_config = CrawlerRunConfig(
    word_count_threshold=10,
    exclude_external_links=True,
    remove_overlay_elements=True,
    excluded_tags=["nav", "footer", "header"],
    cache_mode=CacheMode.ENABLED,
)
```

**What Crawl4AI handles for us**: robots.txt parsing, JavaScript rendering for doc sites that need it (e.g. some SPA-based docs), HTML→clean markdown conversion, link discovery for deep crawling, and HTTP caching.

**What we still build on top**: the per-domain rate-limiting scheduler (Crawl4AI doesn't enforce shared domain queues across packages), adaptive backoff on 429/403, scope limiting to doc path prefixes, and the concurrency model described below.

### Chunking with chunkana

chunkana handles the markdown→chunks step. It's purpose-built for RAG over documentation: it never breaks code blocks, tables, or LaTeX formulas, preserves heading hierarchy as navigable paths, and provides rich metadata per chunk.

```python
from chunkana import chunk_markdown, ChunkConfig

config = ChunkConfig(
    max_chunk_size=1500,    # ~1500 tokens
    min_chunk_size=200,
    overlap_size=100,
)

chunks = chunk_markdown(page_markdown, config=config)

for chunk in chunks:
    # chunk.content       → the text
    # chunk.metadata["header_path"]  → "/Reference/Router/add_api_route"
    # chunk.metadata["has_code"]     → True
    # chunk.start_line, chunk.end_line → source location
```

### Ethical Crawling Policy

The crawler is designed to be a good citizen of the web. All of the following are enforced by default, not opt-in.

**Identification**: every request includes a descriptive `User-Agent` header with the project name, version, and a URL pointing to the project's GitHub page where site owners can learn what LocalContext is and file concerns. Example: `LocalContext/0.1.0 (+https://github.com/org/localcontext; documentation indexer for AI coding agents)`.

**robots.txt compliance**: before crawling any domain, the crawler fetches and parses `robots.txt`. Disallowed paths are never requested. If `robots.txt` is unreachable (network error, not 404), the crawler assumes restrictive defaults and proceeds cautiously.

**Rate limiting**: the crawler enforces a per-domain rate limit. The strategy is layered:

1. If `robots.txt` specifies a `Crawl-delay`, that value is used as the minimum delay between requests to that domain.
2. If no `Crawl-delay` is specified, the default is **1 request per 2 seconds** for documentation sites (these are typically small/medium infrastructure).
3. **Adaptive backoff**: if server response time exceeds 2 seconds, the delay is increased by 50%. If a `429 Too Many Requests` is received, the crawler backs off exponentially (2s → 4s → 8s → 16s, max 60s) and retries up to 3 times before marking the page as failed.
4. If a `403 Forbidden` is received on 3 consecutive pages, the crawler stops that domain entirely and reports the failure.

**Concurrency model**: packages are crawled concurrently (default: 4 packages in parallel), but each domain gets its own serial queue with its own rate limiter. Two packages hosted on the same domain (e.g. two libraries both documented on `readthedocs.io`) share a single rate-limited queue for that domain. This prevents the common mistake of multiplying request rates across parallel workers hitting the same server.

```
index-deps called with [pkg-a, pkg-b, pkg-c, pkg-d, pkg-e]
  │
  ├─ domain resolver:
  │    pkg-a → docs.pkg-a.dev     (own queue)
  │    pkg-b → readthedocs.io     (shared queue)
  │    pkg-c → readthedocs.io     (shared queue)
  │    pkg-d → github.com         (shared queue)
  │    pkg-e → docs.pkg-e.com     (own queue)
  │
  ├─ worker pool (4 concurrent workers):
  │    worker 1 → pulls from docs.pkg-a.dev queue
  │    worker 2 → pulls from readthedocs.io queue (pkg-b and pkg-c interleaved)
  │    worker 3 → pulls from github.com queue
  │    worker 4 → pulls from docs.pkg-e.com queue
  │
  └─ each queue enforces its own rate limit independently
```

**Sitemap preference**: if a site publishes `sitemap.xml`, the crawler uses it to discover pages rather than following links. This is more efficient and more predictable for the site operator.

**Scope limiting**: the crawler only follows links within the doc site's path prefix. If the entry point is `https://fastapi.tiangolo.com/reference/`, it won't crawl `https://fastapi.tiangolo.com/blog/`. Maximum depth is configurable (default: 5 levels). Maximum pages per package is capped (default: 500) to prevent runaway crawls on massive doc sites.

**Caching**: HTTP `ETag` and `Last-Modified` headers are stored per page. On re-crawl, conditional requests (`If-None-Match`, `If-Modified-Since`) are used so unchanged pages return `304 Not Modified` with no body transfer. This dramatically reduces bandwidth on incremental re-indexes.

## Incremental Re-Indexing

Full re-crawls are wasteful when only a few pages in a doc site have changed. The system supports incremental updates at two granularities.

### Page-Level Hashing

Each crawled page is stored with its own content hash and HTTP caching headers:

```sql
CREATE TABLE pages (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    package       TEXT NOT NULL,
    version       TEXT NOT NULL,
    url           TEXT NOT NULL,
    content_hash  TEXT,
    etag          TEXT,
    last_modified TEXT,
    fetched_at    TEXT,
    UNIQUE(package, version, url)
);
```

### Incremental Flow

```
index-deps called with force=false for an already-indexed package
  │
  ├─ for each known page URL:
  │    → send conditional request (If-None-Match / If-Modified-Since)
  │    ├─ 304 Not Modified → skip, page hasn't changed
  │    └─ 200 OK → re-process page
  │         → compute new page content_hash
  │         ├─ hash unchanged → skip (cosmetic HTML change only)
  │         └─ hash changed → re-chunk, re-embed, replace chunks in DB
  │
  ├─ check for new pages (via sitemap diff or link discovery)
  │    → process and insert new chunks
  │
  ├─ check for removed pages (in DB but not in sitemap/crawl)
  │    → delete orphaned chunks
  │
  └─ recompute package-level content_hash from all page hashes
     → update docs.lock if changed
```

This means a re-index of a 400-page doc site where 3 pages changed only re-fetches and re-embeds those 3 pages. The package-level `content_hash` in `docs.lock` still changes, so downstream consumers know the index was updated.

## Community Registry (Pre-Built Doc Packages)

To avoid redundant crawling, the project supports a community registry where users can publish and pull pre-built documentation packages.

### Package Format

A doc package is a compressed archive containing:

```
react@19.1.0.ctx
├── manifest.json        # metadata, hashes, source URL, chunk count
├── chunks.jsonl         # one JSON object per chunk (content, summary, heading_path)
├── embeddings.bin       # dense embeddings as contiguous float32 array
├── sparse.jsonl         # sparse (lexical) weight vectors per chunk
└── pages.json           # page-level metadata for incremental re-indexing
```

### Manifest Schema

```json
{
  "schema_version": 1,
  "package": "react",
  "version": "19.1.0",
  "source_url": "https://react.dev/reference",
  "content_hash": "sha256:a1b2c3...",
  "embedding_model": "BAAI/bge-m3",
  "embedding_model_hash": "sha256:...",
  "chunks": 847,
  "created_at": "2026-05-14T10:30:00Z",
  "created_by": "github:username",
  "pages": 142
}
```

### Integrity Verification

When pulling a package from the registry:

1. Verify `content_hash` matches the SHA-256 of the chunk content (recomputed locally).
2. Verify `embedding_model_hash` matches the locally installed BGE-M3 model. If the model differs (e.g. a future fine-tuned variant), the embeddings are re-generated locally from the chunk text. The text content is still trusted if its hash matches.
3. Packages are signed by the publishing user's GPG key or a registry-managed signing key. Unsigned packages trigger a warning.

### Pull vs Crawl Decision

```
index-deps called for react@19.1.0
  │
  ├─ check registry: does react@19.1.0.ctx exist?
  │   ├─ YES → download, verify content_hash
  │   │        ├─ hash valid → import chunks + embeddings, skip crawl
  │   │        └─ hash invalid → discard, fall through to crawl
  │   └─ NO → crawl from source
  │
  └─ after successful crawl, optionally publish to registry
      (requires user opt-in and authentication)
```

### Registry Hosting

The registry is a simple static file store (S3-compatible, GitHub Releases, or a dedicated server). The index is a JSON manifest listing available packages with their versions and content hashes. No complex API surface — `GET /index.json`, `GET /packages/react/19.1.0.ctx`. The registry protocol is designed so anyone can host a mirror or a private registry for internal packages.

### Registry Governance

The community registry starts as a closed, maintainer-only registry. Only project maintainers can publish packages. This keeps the package corpus small, trusted, and high-quality while the automated governance tooling is developed.

**Phase 1 (launch)**: maintainers publish packages for the most common libraries. All packages are signed with a project key. The registry index is a git repo so every addition is auditable.

**Phase 2 (automated governance)**: once the tooling matures, open publishing to the community with automated checks:
- Content hash verification on upload (server recomputes from chunk text, rejects mismatches)
- Automated diff against the previous version of the same package (flag suspicious changes like chunk count dropping by 90%)
- Rate limiting on publishes per account
- Reproducibility checks: the registry can independently crawl the declared `source_url` and verify the content hash matches what the publisher submitted

**Phase 3 (federated)**: anyone can host a registry. Users configure multiple registry URLs with priority order. Private registries for internal packages sit alongside the community registry.

## Package Size Limits

Size limits differ depending on whether a package is local (built by the developer for their own project) or published (distributed via the community registry).

### Local Packages

Local packages are built by the developer on their own machine and stored in `.context/index.db`. The limits here are generous — the developer is paying the storage and crawl cost themselves, and large doc sites (AWS SDK, Android docs, Kubernetes) are legitimate use cases.

| Limit                | Default  | Override                     |
|----------------------|----------|------------------------------|
| Max pages per package| 2000     | `lctx index --max-pages N`   |
| Max crawl depth      | 5 levels | `lctx index --max-depth N`   |
| Max chunk size       | 1500 tokens | `.context/config.toml`    |
| No total index cap   | —        | Disk space is the constraint |

If a crawl hits the page limit, it stops and reports how many pages were skipped. The developer can raise the limit if they know what they're doing.

### Published Packages

Published packages are distributed to other users, so size matters for download time, registry storage, and import speed. The limits are tighter and enforced by the registry on upload.

| Limit                        | Default   | Rationale                                            |
|------------------------------|-----------|------------------------------------------------------|
| Max pages per package        | 500       | Keeps download size reasonable (~50MB compressed)    |
| Max compressed archive size  | 100MB     | Hard limit on registry upload                        |
| Max chunks per package       | 5000      | Prevents bloated indexes from slowing down search    |
| ColBERT vectors              | Excluded  | Too large for distribution; re-generated locally if needed |

For genuinely massive doc sites (AWS SDK has 10,000+ pages), the recommendation is to split into scoped packages: `aws-sdk-s3@2.x.ctx`, `aws-sdk-ec2@2.x.ctx`, etc. This also improves search relevance since agents typically query one service at a time.

Developers who need the full unscoped index can build it locally with `lctx index` where the higher local limits apply.

## Storage: SQLite Schema

One database per project at `.context/index.db`.

```sql
CREATE TABLE packages (
    name         TEXT NOT NULL,
    version      TEXT NOT NULL,
    source_url   TEXT,
    content_hash TEXT,
    indexed_at   TEXT,
    PRIMARY KEY (name, version)
);

CREATE TABLE pages (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    package       TEXT NOT NULL,
    version       TEXT NOT NULL,
    url           TEXT NOT NULL,
    content_hash  TEXT,
    etag          TEXT,
    last_modified TEXT,
    fetched_at    TEXT,
    UNIQUE(package, version, url)
);

CREATE TABLE chunks (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    package         TEXT NOT NULL,
    version         TEXT NOT NULL,
    page_id         INTEGER REFERENCES pages(id),
    heading_path    TEXT,             -- "Reference > Router > add_api_route"
    summary         TEXT,             -- one-line signature/description
    content         TEXT NOT NULL,    -- full chunk text
    dense_embedding BLOB,            -- BGE-M3 dense: 1024-dim float32
    sparse_weights  TEXT,            -- BGE-M3 sparse: JSON {token_id: weight}
    token_count     INTEGER,
    FOREIGN KEY (package, version) REFERENCES packages(name, version)
);

-- FTS5 full-text index (supplementary to BGE-M3 sparse retrieval)
CREATE VIRTUAL TABLE chunks_fts USING fts5(
    summary, content,
    content='chunks',
    content_rowid='id'
);

-- Keep FTS in sync
CREATE TRIGGER chunks_ai AFTER INSERT ON chunks BEGIN
    INSERT INTO chunks_fts(rowid, summary, content)
    VALUES (new.id, new.summary, new.content);
END;
CREATE TRIGGER chunks_ad AFTER DELETE ON chunks BEGIN
    INSERT INTO chunks_fts(chunks_fts, rowid, summary, content)
    VALUES ('delete', old.id, old.summary, old.content);
END;
```

## Embedding Model: BGE-M3

BGE-M3 (BAAI) is the embedding model for v1. It was chosen because it produces dense, sparse (lexical), and ColBERT embeddings in a single forward pass, which gives us hybrid retrieval from one model without maintaining separate pipelines.

**Key properties**:

| Property          | Value                                 |
|-------------------|---------------------------------------|
| Architecture      | XLM-RoBERTa                          |
| Dense dimensions  | 1024                                  |
| Sparse output     | Learned token weights (like SPLADE)  |
| Max input tokens  | 8192                                  |
| Languages         | 100+                                  |
| License           | MIT                                   |
| ONNX available    | Yes (CPU and CUDA)                   |

**Why BGE-M3 over alternatives**:

- vs. MiniLM-L6: BGE-M3 is significantly more accurate on retrieval benchmarks, handles 8192 tokens vs 512, and its native sparse output eliminates the need for a separate BM25 index.
- vs. Voyage/OpenAI: BGE-M3 is fully local, no API dependency, no per-query cost, no rate limits. Aligns with the local-first goal.
- vs. Qwen3-Embedding: comparable quality but BGE-M3 has more mature ONNX tooling and a smaller model size for CPU inference.

**Runtime via FlagEmbedding**: we use the official `FlagEmbedding` Python library from BAAI, which provides the `BGEM3FlagModel` class. This gives us all three embedding types in a single call with no custom model code.

```python
from FlagEmbedding import BGEM3FlagModel

model = BGEM3FlagModel("BAAI/bge-m3", use_fp16=True)

# Encode documents (returns dense + sparse + colbert in one call)
output = model.encode(
    ["FastAPI dependency injection uses Depends()..."],
    return_dense=True,
    return_sparse=True,
    return_colbert_vecs=False,  # enable when ColBERT retrieval is turned on
)

dense_vectors = output["dense_vecs"]      # numpy array, 1024-dim per doc
sparse_weights = output["lexical_weights"] # list of {token_id: weight} dicts
```

Model weights are downloaded on first run from HuggingFace and cached at `~/.cache/huggingface/`. For future optimization, ONNX exports are available (`aapot/bge-m3-onnx`) that reduce the dependency footprint by dropping PyTorch entirely.

**Swappable models** (future): the architecture stores the `embedding_model` and `embedding_model_hash` in the registry manifest, so a future version can support alternative models. If the local model doesn't match the package's embeddings, the system re-embeds from the stored chunk text.

## Hybrid Search

BGE-M3's multi-output architecture gives us three retrieval signals from a single embedding pass on the query:

### Three-Way Retrieval

1. **Dense retrieval**: cosine similarity between the query's 1024-dim dense vector and each chunk's dense vector. Captures semantic meaning ("how do I handle errors" matches "exception handling" even without keyword overlap).

2. **Sparse retrieval (learned lexical)**: dot product between the query's sparse token weight vector and each chunk's sparse weights. This is BGE-M3's built-in learned sparse representation — similar to SPLADE, it assigns importance weights to tokens based on context, not just term frequency. More accurate than raw BM25 because the weights are learned, not statistical.

3. **FTS5 fallback**: SQLite full-text search as a safety net for exact matches that neither dense nor sparse retrieval might catch (e.g. searching for a very specific error code like `ERR_HTTP2_INADEQUATE_TRANSPORT_SECURITY`). This is cheap to maintain and costs nothing at query time if not needed.

### Fusion

Results from all three retrievers are combined using **Reciprocal Rank Fusion (RRF)**:

```
score(chunk) = Σ  1 / (k + rank_in_retriever)
               for each retriever where chunk appears in top-N
```

Default `k = 60`. The top results after fusion are returned.

In practice, dense + sparse from BGE-M3 will handle the vast majority of queries well. FTS5 acts as a long-tail safety net and adds negligible overhead.

### Package Scoping

When `packages` is specified in the query, all three retrievers are filtered to only those packages before ranking. This avoids polluting results with irrelevant libraries.

### ColBERT Retrieval (Optional)

BGE-M3 produces ColBERT (multi-vector) embeddings alongside dense and sparse outputs. ColBERT represents each token in a passage as its own vector, then scores a query-document pair by finding the best-matching document token for each query token (MaxSim). This enables fine-grained, token-level matching that dense single-vector retrieval cannot capture.

ColBERT retrieval is **disabled by default** and can be enabled per-query or globally via configuration. When enabled, it participates in RRF fusion alongside dense, sparse, and FTS5.

**Pros**:

- Highest retrieval accuracy of all four methods, especially for long documents where a single dense vector can't capture all the nuances. A query about "authentication middleware" will find a chunk that discusses auth in one paragraph and middleware patterns in another, even if neither paragraph alone is a strong dense match.
- Token-level interaction means partial matches are scored more granularly. "How do I configure rate limiting in Express" can match a chunk about Express middleware configuration that mentions rate limiting as one of several examples — dense retrieval might rank this lower because the overall embedding is diluted across topics.
- Complements dense retrieval rather than duplicating it. Dense captures the overall topic; ColBERT captures whether specific query terms are actually addressed in the text.

**Cons**:

- Storage cost is significantly higher. Dense embeddings are 1 vector per chunk (1024 × 4 bytes = 4KB). ColBERT stores 1 vector per token, so a 500-token chunk requires ~500 × 128-dim × 4 bytes = 256KB. For a project with 10,000 chunks, that's ~2.5GB for ColBERT vs ~40MB for dense. This makes ColBERT impractical for the community registry (`.ctx` packages would be 50-100x larger).
- Query latency is higher. MaxSim requires comparing every query token against every document token in the candidate set. Even with pre-filtering to top-100 candidates from dense/sparse, this adds measurable overhead (10-50ms depending on chunk count and hardware).
- Complexity. ColBERT vectors need their own storage format, their own similarity computation, and careful memory management to avoid loading all multi-vectors into RAM. This is the most complex retrieval path to implement and maintain.

**Recommendation**: implement ColBERT as a v2 feature behind a flag. Store ColBERT vectors in a separate SQLite table (or a separate file) so they can be omitted from `.ctx` packages without affecting the core package format. Users who want maximum accuracy opt in; everyone else gets dense + sparse + FTS5 which is already very strong.

```sql
-- Separate table, only populated when ColBERT is enabled
CREATE TABLE colbert_vectors (
    chunk_id    INTEGER REFERENCES chunks(id),
    token_pos   INTEGER,          -- position in the chunk
    vector      BLOB,             -- 128-dim float32
    PRIMARY KEY (chunk_id, token_pos)
);
```

**Configuration**:
```toml
# .context/config.toml or ~/.localcontext/config.toml
[search]
colbert = false      # set to true to enable ColBERT retrieval
```

## Token Efficiency

The system uses a **progressive disclosure** strategy rather than aggressive compression.

### Layered Retrieval

1. **Summary layer** (returned by default): heading path + one-line summary per matching chunk. Roughly 20-40 tokens per result. The agent scans this to decide what it actually needs.
2. **Full content** (on request): the agent requests specific chunks by ID via the `chunk_ids` parameter to get complete text.

### Content Normalization (applied at index time)

- Collapse runs of blank lines to a single blank line
- Strip HTML boilerplate, nav, breadcrumbs, footer, version banners
- Remove "Edit this page" links, "See also" sections that are just link lists
- Normalize Unicode whitespace to ASCII
- Preserve code block formatting exactly (indentation matters)
- Preserve table formatting

### What We Explicitly Do NOT Do

- **Strip all whitespace**: destroys code example readability, confuses LLMs
- **Aggressive abbreviation**: models handle natural language better than compressed shorthand
- **Remove code examples**: these are often the highest-value content

## CLI Tooling

The project includes a full command-line interface for building, inspecting, and publishing doc packages outside of the MCP ecosystem. The CLI and MCP server share the same core libraries (crawler, embeddings, storage, registry client) but are installable separately so that the MCP server stays lean and the CLI doesn't pollute the agent's tool schema.

### Install Paths

```bash
# MCP server only — minimal install for AI agent usage
pip install localcontext

# CLI tools — for package maintainers, CI pipelines, and manual management
pip install localcontext[cli]

# Everything
pip install localcontext[all]
```

The base `localcontext` package installs the MCP server with search and storage dependencies. The `[cli]` extra adds the crawler, embedding model, and the `lctx` command-line entry point. This means the MCP server can be installed on a machine that will only consume pre-built packages from the registry without pulling in ONNX Runtime, trafilatura, or httpx.

When the MCP server's `index-deps` tool is called, it checks whether the crawl/embed dependencies are available. If they're not (base-only install), it attempts to pull from the community registry instead, and returns a clear error if the package isn't available there either: `"Crawl dependencies not installed. Run pip install localcontext[cli] or pull a pre-built package from the registry."`

### Dependency Split

```
localcontext (base):
  mcp, sqlite3 (stdlib), tomli/tomllib, numpy

localcontext[cli] adds:
  crawl4ai              # async crawler + markdown extraction
  chunkana              # structural markdown chunking
  FlagEmbedding         # BGE-M3 model (dense + sparse + ColBERT)
  pydepsdev             # deps.dev API client
  click, rich           # CLI framework
```

### Command Surface

The CLI is invoked via `lctx` (short, fast to type) and covers everything an agent shouldn't be doing.

```
lctx resolve [--project-path .]
    Scan dependency files, diff against docs.lock, print status table.
    Same logic as the MCP resolve-deps tool, but with human-readable output.

lctx index [packages...] [--force] [--workers 4] [--no-registry]
    Crawl and index documentation for specified packages (or all stale/missing).
    --force         Re-crawl even if content hash matches
    --workers N     Max concurrent packages (default: 4)
    --no-registry   Skip registry lookup, always crawl from source

lctx search <query> [--packages pkg1,pkg2] [--detail summary|full] [--limit 10]
    Run a hybrid search query against the local index. Useful for testing
    and verifying that indexing produced good results.

lctx build <package@version> [--source URL|PATH] [--output ./] [--auth HEADER]
    Build a .ctx doc package from a URL or local file path without adding
    it to any project index. Produces a standalone archive suitable for
    publishing or local use.
    --source        URL or local directory path (e.g. ./docs, /path/to/docs)
    --output        Directory to write the .ctx file (default: current dir)
    --auth          Auth header for private doc sites (e.g. "Authorization=Bearer $TOKEN")
    This is the primary tool for package maintainers, CI pipelines, and
    building packages from private/internal documentation.

lctx verify <file.ctx>
    Verify a .ctx package's integrity: check content hash, validate manifest
    schema, report embedding model compatibility.

lctx publish <file.ctx> [--registry URL] [--sign]
    Publish a .ctx package to a community or private registry.
    --sign          GPG-sign the package before upload
    --registry URL  Target registry (default: official community registry)

lctx pull <package@version> [--registry URL]
    Download a .ctx package from the registry without adding it to a project.
    Useful for inspecting packages or pre-populating a cache.

lctx inspect <file.ctx | .context/index.db>
    Print detailed information about a .ctx package or a local index:
    chunk count, token distribution, embedding model, page list, etc.

lctx config [--global | --project]
    View or edit configuration (registry URLs, default workers, model path).
    Global config at ~/.localcontext/config.toml, project config at
    .context/config.toml.

lctx doctor
    Diagnostic tool. Checks: ONNX Runtime installed and working, BGE-M3
    model downloaded, SQLite FTS5 available, registry reachable, disk usage
    for model cache and indexes.
```

### CI/CD Integration

The `lctx build` and `lctx publish` commands are designed for CI pipelines. A library maintainer can add a workflow that rebuilds the doc package on every docs change:

```yaml
# .github/workflows/docs-package.yml
on:
  push:
    paths: ['docs/**']

jobs:
  build-ctx:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - run: pip install localcontext[cli]
      - run: lctx build mylib@${{ github.ref_name }} --source ./docs --output ./
      - run: lctx publish mylib@${{ github.ref_name }}.ctx --sign
        env:
          LOCALCONTEXT_REGISTRY_TOKEN: ${{ secrets.REGISTRY_TOKEN }}
```

This keeps the community registry populated with fresh, maintainer-published packages rather than relying solely on user-initiated crawls.

### Private and Internal Packages

Private package documentation is handled entirely through the CLI — it is deliberately excluded from the MCP tool surface. The MCP server should never need credentials for internal doc sites; instead, a developer or CI pipeline builds the `.ctx` package offline and imports it into the project index.

**Workflow for private packages**:

```bash
# Build from a private doc site with auth
lctx build internal-api@3.2.0 \
  --source https://internal-docs.company.com/api \
  --auth "Authorization=Bearer $DOCS_TOKEN" \
  --output ./packages/

# Or build from a local docs directory (no network needed)
lctx build internal-api@3.2.0 \
  --source ./libs/internal-api/docs \
  --output ./packages/

# Import into the project index
lctx pull ./packages/internal-api@3.2.0.ctx

# Optionally publish to a private registry
lctx publish ./packages/internal-api@3.2.0.ctx \
  --registry https://ctx.internal.company.com
```

This keeps sensitive credentials out of the MCP server's runtime, supports arbitrary auth mechanisms (the developer handles auth however they need to when running `lctx build`), and allows building from local file paths for docs that aren't hosted anywhere. The resulting `.ctx` file can be checked into the repo, shared via a private registry, or distributed through any file transfer mechanism.

## MCP Transport

The server supports two transport modes, configurable at startup.

### stdio (default)

Standard MCP transport over stdin/stdout. Works with all MCP clients (Claude Desktop, Cursor, VS Code, Claude Code, etc.). No network exposure.

```bash
# In MCP client config (e.g. claude_desktop_config.json)
{
  "mcpServers": {
    "localcontext": {
      "command": "localcontext",
      "args": ["serve", "--stdio"]
    }
  }
}
```

### HTTP (local network)

Streamable HTTP transport bound to localhost only. Useful for editors or tools that prefer HTTP-based MCP, for running the server as a persistent background daemon, or for development/debugging.

```bash
# Start as a local HTTP server
localcontext serve --http --port 8000 --path /mcp

# Listens on 127.0.0.1:8000/mcp (loopback only, never exposed to network)
```

**Security**: the HTTP transport binds exclusively to `127.0.0.1`. It does not and will not bind to `0.0.0.0` or any external interface. This is a hard constraint, not a configuration option. If users need remote access (e.g. for a team server), they should front it with a reverse proxy that handles authentication and TLS.

```bash
# MCP client config for HTTP mode
{
  "mcpServers": {
    "localcontext": {
      "url": "http://127.0.0.1:8000/mcp"
    }
  }
}
```

## Technology Choices

| Component          | Choice                          | Rationale                                           |
|---------------------|---------------------------------|-----------------------------------------------------|
| MCP server          | Python                         | All dependencies are Python-native, avoids cross-process IPC |
| CLI framework       | click + rich                   | click for composable subcommands, rich for tables/progress bars in terminal |
| Crawler             | **Crawl4AI**                   | Async, outputs clean markdown, BFS/DFS strategies, robots.txt, JS rendering, Apache 2.0 |
| Content extraction  | Crawl4AI (built-in)            | Crawl4AI's markdown generator handles boilerplate stripping and content cleaning |
| Chunking            | **chunkana**                   | Preserves code blocks/tables, heading path metadata, structural chunking for RAG, MIT |
| Doc source resolver | **deps.dev API** + pydepsdev   | Google's cross-ecosystem package metadata API; covers npm, PyPI, Cargo, Maven, Go, NuGet, RubyGems |
| Embeddings          | **FlagEmbedding** (BGEM3FlagModel) | Official BAAI library; dense + sparse + ColBERT in one call, MIT license |
| Storage             | SQLite + FTS5                   | Single file, no infra, portable, fast               |
| Lockfile format     | TOML                            | Human-readable, git-friendly, standard in Rust/Python |
| Package format      | `.ctx` (compressed archive)    | Self-contained, hashable, portable                  |
| MCP SDK             | mcp (Python)                   | Official Anthropic MCP SDK for Python               |
| Packaging           | single PyPI package with extras | `localcontext` base + `[cli]` extra avoids two packages while keeping MCP server lean |

The project leans heavily on proven external libraries for the hard parts (crawling, chunking, embeddings, package metadata) and only writes custom code where no good solution exists (dependency file parsers, hybrid search fusion, SQLite storage layer, registry protocol). This keeps the codebase small and focused on orchestration rather than reimplementation.

## Project Structure

```
localcontext/
├── pyproject.toml
├── README.md
├── LICENSE                      # MIT
│
├── src/localcontext/
│   ├── __init__.py
│   │
│   │── # ── BASE PACKAGE (pip install localcontext) ──────────
│   │
│   ├── server.py                # MCP server (tool definitions, transport setup)
│   │
│   ├── deps/                    # Dependency file parsers (custom, stdlib only)
│   │   ├── __init__.py
│   │   ├── python.py            # requirements.txt, pyproject.toml, Pipfile
│   │   ├── node.py              # package.json, yarn.lock, pnpm-lock.yaml
│   │   ├── rust.py              # Cargo.toml, Cargo.lock
│   │   ├── go.py                # go.mod
│   │   ├── ruby.py              # Gemfile, Gemfile.lock
│   │   ├── php.py               # composer.json, composer.lock
│   │   ├── jvm.py               # build.gradle, pom.xml
│   │   └── dotnet.py            # *.csproj, packages.config
│   │
│   ├── search/                  # Hybrid search engine (custom, query-time only)
│   │   ├── __init__.py
│   │   ├── dense.py             # Cosine similarity over dense vectors (numpy)
│   │   ├── sparse.py            # Dot product over sparse weight vectors
│   │   ├── fts.py               # SQLite FTS5 queries
│   │   └── fusion.py            # Reciprocal Rank Fusion
│   │
│   ├── storage/                 # SQLite database layer (custom)
│   │   ├── __init__.py
│   │   ├── db.py                # Connection management, schema migrations
│   │   └── lockfile.py          # docs.lock read/write/diff
│   │
│   │── # ── CLI EXTRA (pip install localcontext[cli]) ────────
│   │
│   ├── cli/                     # CLI entry point and subcommands
│   │   ├── __init__.py
│   │   ├── main.py              # lctx root command (click group)
│   │   ├── resolve.py           # lctx resolve
│   │   ├── index.py             # lctx index
│   │   ├── search_cmd.py        # lctx search
│   │   ├── build.py             # lctx build
│   │   ├── verify.py            # lctx verify
│   │   ├── publish.py           # lctx publish
│   │   ├── pull.py              # lctx pull
│   │   ├── inspect_cmd.py       # lctx inspect
│   │   ├── config.py            # lctx config
│   │   └── doctor.py            # lctx doctor
│   │
│   ├── resolver/                # Doc source URL resolution
│   │   ├── __init__.py
│   │   ├── depsdev.py           # deps.dev API via pydepsdev (primary resolver)
│   │   ├── patterns.py          # Well-known URL pattern fallbacks
│   │   └── overrides.py         # .context/sources.toml
│   │
│   ├── crawler/                 # Crawl4AI orchestration
│   │   ├── __init__.py
│   │   ├── crawler.py           # Crawl4AI configuration and page crawling
│   │   ├── chunking.py          # chunkana integration and chunk post-processing
│   │   └── scheduler.py         # Per-domain queue, concurrency, rate limiting
│   │
│   ├── embeddings/              # BGE-M3 via FlagEmbedding
│   │   ├── __init__.py
│   │   └── model.py             # BGEM3FlagModel wrapper (encode, batch, config)
│   │
│   │── # ── SHARED (used by both base and cli) ──────────────
│   │
│   └── registry/                # Community registry client (custom)
│       ├── __init__.py
│       ├── client.py            # Pull/push .ctx packages
│       ├── package.py           # .ctx archive create/extract/verify
│       └── signing.py           # Package signature verification
│
└── tests/
    ├── test_deps/
    ├── test_crawler/
    ├── test_search/
    ├── test_registry/
    └── test_cli/
```

### pyproject.toml Entry Points

```toml
[project.scripts]
# No default entry point for base install — MCP clients invoke
# the server directly via "python -m localcontext.server"

[project.optional-dependencies]
cli = [
    "crawl4ai>=0.4",
    "chunkana>=0.1",
    "FlagEmbedding>=1.2",
    "pydepsdev>=0.1",
    "click>=8.0",
    "rich>=13.0",
]
all = ["localcontext[cli]", "pytest", "pytest-asyncio"]

[project.entry-points."console_scripts"]
lctx = "localcontext.cli.main:cli"
```

Note on entry point conditionality: `pip install localcontext` will install the `lctx` console script, but invoking it without the `[cli]` extra will immediately fail with a clear import error message pointing the user to `pip install localcontext[cli]`. This is the standard Python packaging pattern — the alternative (a separate `localcontext-cli` package) adds distribution complexity without meaningful benefit.

## Open Questions

- **Crawl data retention vs re-crawl**: should the system store the full cleaned markdown per page (pre-chunking) alongside the chunks? Storing it enables re-chunking with better strategies and re-embedding with future models without hitting the source again. Not storing it keeps the index ~50% smaller and treats source sites as the source of truth. The model upgrade story depends on this decision, and it'll become clearer once we can measure real storage costs.
- **FTS5 vs sparse redundancy**: BGE-M3's learned sparse weights may make FTS5 entirely redundant for most queries. Worth benchmarking once the search pipeline is built — if sparse consistently subsumes FTS5 results, we can drop FTS5 to simplify the schema. Until then, keep it as a zero-cost safety net.
- **Registry reproducibility verification**: in Phase 2 governance, the registry can independently crawl a source URL and verify the publisher's content hash. But doc sites change between publish and verification. Need a time-window policy, or verify against a pinned snapshot, or skip content verification and rely solely on signing.
- **Monorepo dependency deduplication**: in a monorepo with 10 workspaces that all depend on `react@19.1.0`, should there be 10 copies of the React index or a shared one? Shared is more efficient but requires a different lockfile structure (workspace-level dep files pointing to a shared package store).
- **Summary generation quality**: the one-line summaries per chunk are critical for the progressive disclosure flow. Generating them with heuristics (extract first sentence, parse function signatures) is fast but brittle. Generating them with an LLM is accurate but adds a dependency and significant indexing time. Need to decide the approach and whether LLM-generated summaries are worth the cost.
- **Versioned doc URLs**: many doc sites don't include version numbers in their URL structure, or use "latest" as the default. When a user has `fastapi@0.115.0` pinned but the doc site only serves current docs, the crawled content may not match their installed version. How aggressively should we try to find version-specific docs (ReadTheDocs versioning, GitHub tagged releases, Wayback Machine)?
