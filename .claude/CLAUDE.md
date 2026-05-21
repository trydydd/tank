# Tank — Development Guide

## Source of Truth

- The code is always the source of truth. Never assume something is implemented (or not) just because documentation says so. Check the actual codebase.
- Documentation describes intent and design. The filesystem, tests, and git history describe reality. When they conflict, reality wins — then update the docs.

## Language and Runtime

- Python 3.11+ required. Use `tomllib` from stdlib, no `tomli` backport.
- Prioritize maintainability and readability over cleverness or line count reduction.

## Code Style

- `ruff` and `mypy` are the authority on formatting and type safety. No additional style guide.
- Run all three checks before committing — CI enforces all of them:
  ```
  .venv/bin/ruff check src/ tests/
  .venv/bin/ruff format --check src/ tests/
  .venv/bin/mypy src/
  ```
  To auto-fix formatting: `.venv/bin/ruff format src/ tests/`
- Spell out every parameter explicitly. No `**kwargs` pass-through.
- Prefer dedicated exception classes over generic `ValueError`/`TypeError`. The CLI maps exceptions to specific exit codes and user-facing messages. Start with a base `TankError` class; discover and add specific subclasses during TDD as failure modes emerge.
- Always use type hints. Prefer `str | None` union syntax over `Optional[str]`.

## MVP Design Decisions

- **Summaries**: heuristic generation at build time (first sentence, or leading function/class signature for code-heavy chunks). No LLM dependency. The `summary` field schema supports upgrading the strategy later.
- **source_url**: always populated, never null. Local builds store the path as given to `--source` plus the relative path within it (e.g. `--source ./docs` + `auth/oauth.md` = `docs/auth/oauth.md`). Normalize only `./` off the front. Phase 2 web builds will use full `https://` URLs. No fallback logic needed at query time.

## Build Behavior

- Recurse subdirectories by default. File discovery uses an extension whitelist: `.md`, `.html`, `.htm` for MVP. All other files are skipped with a debug-level log.
- File walk order is lexicographic (sorted by full relative path) to guarantee deterministic chunk ID assignment and reproducible `normalized_content_hash`. This is a correctness requirement, not a preference — any code that assigns chunk IDs must process sources in a defined, sorted order. Phase 2 crawled builds must establish their own deterministic sort (e.g. canonical URL) before assigning IDs.
- `--no-recurse`, `--include`, and `--exclude` are deferred.

## Integrity

- `pack_digest` computation: set `"pack_digest": ""` in manifest.json, assemble the zip, hash the archive bytes, then rewrite the manifest with the real digest. Verification reverses this: replace the value with `""`, hash, compare. The empty-string convention avoids JSON key ordering issues. All ZIP entries use a pinned `date_time` of `(2021, 8, 8, 0, 0, 0)` — the build writes the archive twice and both writes must produce identical ZipInfo metadata for the verifier to reproduce the hash. This date must never change.
- `token_count` is a rough estimate computed as `len(content) // 4`. Document clearly that it is approximate, for budget planning only. No tokenizer dependency.

## Testing

- Red-green-refactor. Write the failing test first, make it pass, then clean up.
- Test error paths and edge cases, not just happy paths. Every public function should have tests for: valid input, invalid input, boundary conditions, and expected failure modes.
- Static fixtures in `tests/fixtures/` for integration-level tests (sample source trees, known-good .ctx packs, malformed archives for validator tests). Pytest factory functions for unit tests (individual chunks, normalization edge cases, policy evaluation).
- **Never bypass the public API in tests or benchmarks.** Call the same functions and entry points that real callers use. Reaching past the public interface to call internal helpers directly (e.g. calling `search()` instead of `query_docs()` to work around a limit) masks bugs rather than surfacing them — if the public API can't do what the test needs, that is the bug to fix.

## Architecture Constraints

- The normalization code path (`tank.builder.normalizer`) is shared between builder and verifier. Never duplicate or reimplement normalization logic — both must use the same function to preserve the hash stability guarantee.
- All data stays local. No outbound network calls at query time.
- SQLite FTS5 is the only search backend for MVP. No embedding dependencies.
- SQLite WAL mode enabled on database creation. Busy timeout set to 5000ms.
- HTML handling: for MVP, `.html` files are converted to text via basic tag removal. Boilerplate stripping (nav, footer, breadcrumbs) is deferred to Phase 2 when the crawler lands. Markdown files are the primary supported format.
