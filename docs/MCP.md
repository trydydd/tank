# Tank — MCP Server

How to wire the Tank MCP server into Claude Code, Cursor, or VS Code so an AI agent can query your indexed documentation packs.

## Current state

The MCP server is functional via stdio transport with two tools: `search` and `fetch`.

**Known gaps (pre-v0.2.0):**

- HTTP transport code exists (`run_http()` in `src/tank/server.py`) but is not wired to any CLI flag — stdio only for now.

## Prerequisites

1. Tank installed in the environment the MCP harness will use:
   ```bash
   pip install tank        # once on PyPI; until then: pip install -e .
   ```

2. At least one pack imported into the local index:
   ```bash
   tank build my-lib@1.0.0 --source ./docs --output ./packs
   tank add ./packs/my-lib@1.0.0.ctx
   ```
   Or, to reproduce an existing index from a committed `tank.lock`:
   ```bash
   tank sync
   ```
   Both create `.tank/index.db` in the project root.

## Working directory requirement

The server opens `.tank/index.db` relative to its working directory. It must be started from the project root — the same directory that contains `.tank/`. Each MCP config below sets `cwd` explicitly to ensure this.

## Configuration

### Claude Code

Project-scoped config at `.claude/mcp.json` (check it in so all contributors get it automatically):

```json
{
  "mcpServers": {
    "tank": {
      "command": "tank",
      "args": ["serve"],
      "cwd": "${workspaceFolder}"
    }
  }
}
```

Or add to your global `~/.claude/mcp.json` if you prefer not to check it in.

### Cursor

`.cursor/mcp.json` in the project root:

```json
{
  "mcpServers": {
    "tank": {
      "command": "tank",
      "args": ["serve"],
      "cwd": "${workspaceFolder}"
    }
  }
}
```

### VS Code (with an MCP extension)

`.vscode/mcp.json`:

```json
{
  "servers": {
    "tank": {
      "type": "stdio",
      "command": "tank",
      "args": ["serve"],
      "cwd": "${workspaceFolder}"
    }
  }
}
```

### Using a virtualenv

If Tank is installed in a project-local virtualenv rather than the system Python, point directly at the venv binary:

```json
{
  "mcpServers": {
    "tank": {
      "command": "${workspaceFolder}/.venv/bin/tank",
      "args": ["serve"],
      "cwd": "${workspaceFolder}"
    }
  }
}
```

## Tools

### `search`

FTS5 full-text search across indexed documentation. Returns chunk summaries and IDs — **content is not included**. Use the returned `chunk_id` values to fetch full content via the `fetch` tool.

**Parameters:**

| parameter | type | default | description |
|---|---|---|---|
| `query` | string | — | Search terms (required). FTS5 is lexical — use keywords, not natural language sentences. |
| `packages` | string[] | all | Scope results to specific package names. Returns `{"status": "not_indexed"}` if a requested package has no indexed pack. |
| `limit` | integer | `10` | Maximum chunks returned from FTS5 (candidate pool size). |
| `max_tokens` | integer | none | Accumulate chunks in BM25 rank order; stop before estimated token cost exceeds this budget. |

**Result fields per chunk:**

| field | description |
|---|---|
| `chunk_id` | ID to pass to `fetch` |
| `package` | Pack name (e.g. `"my-lib"`) |
| `version` | Pack version (e.g. `"1.0.0"`) |
| `lifecycle_state` | `draft` / `approved` / `deprecated` / `revoked` |
| `doc_version_status` | `stable` / `outdated` / etc. |
| `heading_path` | Section hierarchy (e.g. `"Configuration / Auth / OAuth2"`) |
| `summary` | One-line description of the chunk's content |
| `source_url` | Where this content came from |
| `source_commit` | Git commit recorded at build time (if present) |
| `content_hash` | SHA-256 of the chunk's normalised content |
| `indexed_at` | When this pack was imported |
| `score` | BM25 relevance score (higher = better match) |
| `lifecycle_warning` | Non-null if the pack is deprecated (omitted otherwise) |

**Note on queries:** FTS5 matches on keywords, not meaning. Translate natural-language questions to key terms before calling (`"OAuth2 client credentials"` rather than `"how do I authenticate"`).

---

### `fetch`

Retrieve full chunk content by ID. Always call `search` first to get `chunk_id` values.

**Parameters:**

| parameter | type | default | description |
|---|---|---|---|
| `chunk_ids` | integer[] | — | Chunk IDs to retrieve (required). Obtain from `search` results. |
| `max_tokens` | integer | none | Accumulate chunks in the order provided; stop before estimated token cost exceeds this budget. |

**Result fields per chunk:**

| field | description |
|---|---|
| `chunk_id` | ID of the chunk |
| `package` | Pack name |
| `version` | Pack version |
| `lifecycle_state` | `draft` / `approved` / `deprecated` / `revoked` |
| `doc_version_status` | `stable` / `outdated` / etc. |
| `heading_path` | Section hierarchy |
| `summary` | One-line description |
| `content` | Full chunk content |
| `source_url` | Where this content came from |
| `source_commit` | Git commit recorded at build time (if present) |
| `content_hash` | SHA-256 of the content for integrity checking |
| `indexed_at` | When this pack was imported |
| `score` | BM25 relevance score |
| `lifecycle_warning` | Non-null if the pack is deprecated (omitted otherwise) |

Chunks from `revoked` packs are silently excluded from results.

## Recommended usage pattern

**Step 1 — summary scan** (cheap: ~20–40 tokens per chunk):

```json
{
  "query": "stdio transport run",
  "packages": ["fastmcp"],
  "limit": 15
}
```

Read the `heading_path` and `summary` fields. Identify the `chunk_id` values that look relevant to the task.

**Step 2 — targeted fetch** (pay only for what you need):

```json
{
  "chunk_ids": [2, 3],
  "max_tokens": 8000
}
```

This two-step pattern typically costs 28–84% fewer tokens than fetching a full web page covering the same topic. See `tests/benchmarks/test_webfetch_vs_tank.py` for measured numbers.

## Token cost reference

Based on the fastmcp stdio benchmark (`tests/benchmarks/results/webfetch_vs_tank_latest.json`):

| approach | tokens | vs full page fetch |
|---|---:|---:|
| WebFetch (full page) | 2,257 | — |
| Tank single-step full | 1,550 | −31% |
| Tank two-step, agentless | 1,631 | −28% |
| Tank two-step, agent-selected | ~360 | ~−84% |

The agent-selected figure requires the agent to read summaries and choose only the relevant chunk — the agentless benchmark fetches all matched chunks unconditionally.
