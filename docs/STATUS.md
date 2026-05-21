# Tank — Project Status

Last updated: 2026-05-20

## Current State: Implementation Complete

Phase 1 / MVP source code is implemented and all tests pass.
Architecture and design documents remain the canonical reference.

## What Exists

### Documentation

| Document | Purpose |
|---|---|
| `architecture.md` | Full system design: MVP scope, .ctx format, SQLite schema, validation sequence, MCP tools, CLI surface, phased roadmap |
| `document-processing.md` | Detailed build pipeline: source discovery through archive assembly, with end-to-end example |
| `decisions.md` | Decision log with reasoning and rejected alternatives for all design choices |
| `recommendations.md` | Architecture review identifying gaps and future-facing recommendations |
| `CLAUDE.md` | Development guide: runtime, code style, constraints, testing mandate |
| `STATUS.md` | This file |
| `glossary.md` | Definitions of all Tank-specific terminology |

### Source Code

| Component | Files |
|---|---|
| `src/tank/` | Core package — 24 Python modules across builder, CLI, errors, policy, search, server, storage, validator |
| `tests/` | 184 tests covering builder, CLI, errors, integration, policy, search, server, storage, validator, benchmark harness |
| `tests/fixtures/` | `malformed_packs/`, `sample_docs/` — static test data |
| `pyproject.toml` | Project config, dependencies, entry points |
| `README.md` | Project overview |

### Test Results

- **183/184 tests passing** (pytest; 1 skipped — FastMCP integration test requires running server)
- **mypy**: 1 minor error in `src/tank/builder/chunking.py:8` (unused `type: ignore` on `chunkana` import)
- **CI/CD**: Benchmark workflow configured (`.github/workflows/benchmark.yml`); release workflow configured; no deploy/publish step yet

### What Is Implemented

All Phase 1 / MVP components:

- [x] Project scaffold (`pyproject.toml`, `src/tank/`, `tests/`)
- [x] Base `TankError` exception class (`tank/errors.py`)
- [x] Content normalizer (`tank.builder.normalizer`)
- [x] Structural chunking integration with chunkana (`tank.builder.chunking`)
- [x] Heuristic summary generator
- [x] Manifest construction and `pack_digest` computation (`tank.builder.manifest`)
- [x] Build orchestrator (`tank.builder.build`)
- [x] Archive safety validator — 8-step sequence (`tank.validator.verify`)
- [x] Policy engine — `policy.toml` loading and lifecycle enforcement (`tank.policy.engine`)
- [x] SQLite storage — schema creation, WAL mode, migrations (`tank.storage.db`)
- [x] Data models — Pack, Chunk, Page dataclasses (`tank.storage.models`)
- [x] FTS5 search with BM25 ranking and attribution (`tank.search.fts`)
- [x] MCP server — `query-docs` (with `limit` parameter) and `resolve-deps` tools (`tank.server`)
- [x] CLI commands — `tank build`, `tank verify`, `tank pull`, `tank query`, `tank inspect`
- [x] Lockfile management (`.tank/index.lock`)

### What Is Deferred

- Phase 2: URL crawling, registry, lifecycle promotion, staleness detection
- Phase 3: BGE-M3 embeddings, hybrid search, RRF fusion

See `architecture.md` > "What Is Deferred" for the complete list.
