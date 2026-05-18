# Tank — Project Status

Last updated: 2026-05-17

## Current State: Pre-Implementation

Architecture and design are complete. No source code exists yet.

## What Exists

| Document | Purpose |
|---|---|
| `architecture.md` | Full system design: MVP scope, .ctx format, SQLite schema, validation sequence, MCP tools, CLI surface, phased roadmap |
| `document-processing.md` | Detailed build pipeline: source discovery through archive assembly, with end-to-end example |
| `decisions.md` | Decision log with reasoning and rejected alternatives for all design choices |
| `recommendations.md` | Architecture review identifying gaps and future-facing recommendations |
| `CLAUDE.md` | Development guide: runtime, code style, constraints, testing mandate |
| `STATUS.md` | This file |
| `glossary.md` | Definitions of all Tank-specific terminology |

## What Does Not Exist

- `pyproject.toml` and project scaffold
- Any Python source code (`src/tank/`)
- Test suite (`tests/`)
- Test fixtures (`tests/fixtures/`)
- CI/CD configuration
- README.md (planned — content and tone under discussion)

## What Is Fully Specified (Ready to Build)

All of Phase 1 / MVP:

- [ ] Project scaffold (`pyproject.toml`, `src/tank/`, `tests/`)
- [ ] Base `TankError` exception class
- [ ] Content normalizer (`tank.builder.normalizer`)
- [ ] Structural chunking integration with chunkana (`tank.builder.chunking`)
- [ ] Heuristic summary generator
- [ ] Manifest construction and `pack_digest` computation (`tank.builder.manifest`)
- [ ] Build orchestrator (`tank.builder.build`)
- [ ] Archive safety validator — 8-step sequence (`tank.validator.verify`)
- [ ] Policy engine — `policy.toml` loading and lifecycle enforcement (`tank.policy.engine`)
- [ ] SQLite storage — schema creation, WAL mode, migrations (`tank.storage.db`)
- [ ] Data models — Pack, Chunk, Page dataclasses (`tank.storage.models`)
- [ ] FTS5 search with BM25 ranking and attribution (`tank.search.fts`)
- [ ] MCP server — `query-docs` and `resolve-deps` tools (`tank.server`)
- [ ] CLI commands — `tank build`, `tank verify`, `tank pull`, `tank query`, `tank inspect`
- [ ] Lockfile management (`.tank/index.lock`)

## Implementation Order (Suggested)

Build from the inside out — core libraries first, then CLI and server as thin wrappers:

1. **Normalizer** — everything depends on this; it's the hash stability guarantee
2. **Storage layer** — schema, models, connection management
3. **Builder** — chunking, summary generation, manifest, archive assembly
4. **Validator** — 8-step verification sequence
5. **Policy engine** — TOML loading, lifecycle enforcement
6. **Search** — FTS5 query with attribution
7. **CLI** — thin wrappers over core libraries
8. **MCP server** — expose search and resolve-deps as tools

Each component is developed TDD: write failing tests first, implement to pass, refactor.

## What Is Deferred

- Phase 2: URL crawling, registry, lifecycle promotion, staleness detection
- Phase 3: BGE-M3 embeddings, hybrid search, RRF fusion

See `architecture.md` > "What Is Deferred" for the complete list.
