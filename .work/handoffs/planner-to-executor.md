# Handoff: Planner → Executor

**Date:** 2026-05-18
**Planner:** claude-opus-4-6
**Executor:** qwen3.6-35b-a3b-fp8-dflash
**Profile:** constrained

## What to do

1. Read `.work/ledger.yaml` from top to bottom.
2. Read `.work/progress.txt`.
3. Start with `chunk-01-project-scaffold` (it has no dependencies).
4. Follow the executor briefing at the top of the ledger exactly.

## State of the repo

- **No code exists yet.** The `src/` and `tests/` directories do not exist.
- Documentation is complete: `docs/architecture.md`, `docs/document-processing.md`, `docs/decisions.md`, `docs/glossary.md`, `docs/STATUS.md`.
- `.claude/CLAUDE.md` has all code style rules and design decisions.
- The ledger has 11 chunks. Start at chunk-01, work in dependency order.

## Chunk dependency order (what can run when)

```
chunk-01  (no deps — start here)
  └─ chunk-02  (after 01)
       ├─ chunk-03  (after 02)
       ├─ chunk-04  (after 02)
       └─ chunk-05  (after 02)
            chunk-06  (after 04)
            chunk-07  (after 02, 03)
            chunk-08  (after 03, 05)
            chunk-09  (after 04, 05, 06, 07, 08)
            chunk-10  (after 04, 06)
            chunk-11  (after 09, 10)
```

## Key files

| File | Purpose |
|------|---------|
| `.work/ledger.yaml` | The work plan — read this first |
| `.work/progress.txt` | Append gotchas here after each chunk |
| `.claude/CLAUDE.md` | Code style and design decisions |
| `docs/architecture.md` | Full system design (target state) |
| `docs/document-processing.md` | Build pipeline details |
| `docs/decisions.md` | Design decisions with reasoning |

## Rules reminder

- TDD: write failing test first, then implement.
- One chunk at a time. Do not skip ahead.
- Run all `definition_of_done.automated` commands before marking NEEDS_REVIEW.
- Append to `progress.txt` after every chunk, even if no gotchas.
- If something is unclear or missing, stop and flag it as an `open_question`.
