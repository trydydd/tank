# Tank — MCP Server

How to wire the Tank MCP server into Claude Code, Cursor, or VS Code so an AI agent can query your indexed documentation packs.

## Current state

The MCP server is functional via stdio transport. Both tools (`query-docs`, `resolve-deps`) work against a local `.tank/index.db`.

**Known gaps (pre-v0.2.0):**

- No `tank serve` CLI subcommand — invocation is `python -m tank.server` (works, just undiscoverable from `tank --help`)
- HTTP transport code exists (`run_http()` in `src/tank/server.py`) but is not wired to any CLI flag — stdio only for now
- `query-docs` does not accept a `project_path` argument; `resolve-deps` does. Both open `.tank/index.db` but only `resolve-deps` lets you override the base directory. Consequence: `query-docs` always resolves relative to the process working directory.

## Prerequisites

1. Tank installed in the environment the MCP harness will use:
   ```bash
   pip install tank        # once on PyPI; until then: pip install -e .
   ```

2. At least one pack built and pulled into the local index:
   ```bash
   tank build my-lib@1.0.0 --source ./docs --output ./packs
   tank pull ./packs/my-lib@1.0.0.ctx
   ```
   This creates `.tank/index.db` in the project root.

## Working directory requirement

The server opens `.tank/index.db` relative to its working directory. It must be started from the project root — the same directory that contains `.tank/`. Each MCP config below sets `cwd` explicitly to ensure this.

## Configuration

### Claude Code

Project-scoped config at `.claude/mcp_servers.json` (checked into the repo so all contributors get it automatically):

```json
{
  "mcpServers": {
    "tank": {
      "command": "python",
      "args": ["-m", "tank.server"],
      "cwd": "${workspaceFolder}"
    }
  }
}
```

Or add to your global `~/.claude/mcp_servers.json` if you prefer not to check it in.

### Cursor

`.cursor/mcp.json` in the project root:

```json
{
  "mcpServers": {
    "tank": {
      "command": "python",
      "args": ["-m", "tank.server"],
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
      "command": "python",
      "args": ["-m", "tank.server"],
      "cwd": "${workspaceFolder}"
    }
  }
}
```

### Using a virtualenv

If Tank is installed in a project-local virtualenv rather than the system Python, point directly at that interpreter:

```json
{
  "mcpServers": {
    "tank": {
      "command": "${workspaceFolder}/.venv/bin/python",
      "args": ["-m", "tank.server"],
      "cwd": "${workspaceFolder}"
    }
  }
}
```

## Tools

### `resolve-deps`

Returns the list of packs currently in the index with their lifecycle state. Cheap to call (single SQLite read). Useful as a session health check.

**Parameters:**

| parameter | type | default | description |
|---|---|---|---|
| `project_path` | string | cwd | Base directory containing `.tank/index.db` |

**Example response:**

```json
{
  "status": "ok",
  "packs": [
    {
      "package": "my-lib",
      "version": "1.0.0",
      "lifecycle_state": "approved",
      "doc_version_status": "stable",
      "chunks": 412,
      "indexed_at": "2026-05-14T10:30:00Z"
    }
  ]
}
```

If `lifecycle_state` is `"deprecated"`, treat results from that pack as potentially stale. Chunks from `"revoked"` packs are excluded from search results entirely.

---

### `query-docs`

FTS5 full-text search across indexed documentation. All results include provenance fields (`source_url`, `content_hash`, `indexed_at`).

**Parameters:**

| parameter | type | default | description |
|---|---|---|---|
| `query` | string | `""` | Search terms (required unless `chunk_ids` is set) |
| `packages` | string[] | all | Scope results to specific package names |
| `detail` | string | `"summary"` | `"summary"` returns heading + one-line summary; `"full"` returns complete chunk content |
| `limit` | integer | `10` | Maximum chunks returned from FTS5 (candidate pool size) |
| `chunk_ids` | integer[] | — | Fetch specific chunks by ID, bypassing search |
| `max_tokens` | integer | none | Accumulate chunks in BM25 rank order; stop before estimated token cost exceeds this budget |

If a package in `packages` is not indexed, the tool returns `{"status": "not_indexed"}` rather than silently returning empty results.

**Note on queries:** FTS5 is lexical — it matches on keywords, not meaning. Natural language questions often return 0 results. Translate the question to key terms before calling (`"OAuth2 client credentials"` rather than `"how do I authenticate"`).

## Recommended usage pattern

**Step 1 — summary scan** (cheap: ~20–40 tokens per result):

```json
{
  "query": "stdio transport run",
  "packages": ["fastmcp"],
  "detail": "summary",
  "limit": 15
}
```

Read the `heading_path` and `summary` fields. Identify the chunk IDs that look relevant.

**Step 2 — targeted fetch** (pay only for what you need):

```json
{
  "chunk_ids": [2, 3],
  "detail": "full",
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
