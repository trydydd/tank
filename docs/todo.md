# Tank — Known Issues & Gaps

## Bugs

- [x] **`src/tank/cli/pull.py:39` — hardcoded `doc_version_status`** *(fixed)*
  `_import_pack` now reads `doc_version_status` from the manifest instead of hardcoding `"imported"`.

- [x] **`src/tank/builder/manifest.py:43` — `doc_version_status` hardcoded to `"stable"`** *(fixed)*
  `build_manifest()` now accepts `doc_version_status` as a required parameter. `build_pack()` and `tank build --doc-version-status` pass it through. Valid values: `stable`, `prerelease`, `archived`, `unknown`.

- [x] **`src/tank/server.py` — `max_tokens` parameter is a stub** *(fixed)*
  `query_docs()` now enforces a greedy token budget: chunks are accumulated in BM25 rank order and the list is cut before the estimated cost (`len(content) // 4` for full, `len(summary) // 4` for summary) would exceed `max_tokens`. Whole chunks only — no mid-text truncation. Documented in `docs/ranking.md`.

- [x] **`src/tank/storage/db.py:121-126` — page ID foreign key integrity broken on import** *(fixed)*
  `import_pack()` now builds a `page_id_map` from each page's pack-local ID to its AUTOINCREMENT DB ID, and remaps `chunk.page_id` values through it before inserting chunks.

- [x] **`src/tank/search/fts.py:76` — silent exception swallowing** *(fixed)*
  `search()` now raises `SearchError` (a `TankError` subclass) on `sqlite3.Error` instead of catching all exceptions and returning `[]`.

- [x] **`src/tank/server.py` / `src/tank/search/fts.py:32` — result limit not exposed** *(fixed)*
  `query_docs()` now accepts `limit: int = 10` and passes it through to `search()`. The MCP tool exposes the same parameter. Discovered by the token overhead benchmark when `full_n10 == full_n20`.

## Incomplete Implementations

- [ ] **No machine-readable manifest schema (`schemas/manifest.v2.schema.json`)**
  The `manifest.json` field definitions live in `docs/architecture.md` (prose) and `src/tank/validator/verify.py` (code) and can drift apart. A JSON Schema file at `schemas/manifest.v2.schema.json` would be the single source of truth: the verifier validates against it at runtime, the builder's output is tested against it, and the architecture docs reference it rather than duplicating the field table.

- [ ] **Signature verification is a stub (`src/tank/validator/verify.py`, Step 8)**
  Only checks whether `signatures/manifest.sig` exists in the archive. No actual cryptographic verification (ed25519, Sigstore, etc.) is performed.

- [ ] **No schema migrations (`src/tank/storage/db.py`)**
  Database setup uses `CREATE TABLE IF NOT EXISTS` only. No `PRAGMA user_version` tracking or forward-only migration support. Any future column additions will break existing databases.

## v0.1.1

- [ ] **Benchmark output cleanup + PR comment bot**
  Both `test_token_overhead` and `test_webfetch_vs_tank` produce verbose console output and write results JSON, but results never surface in code review. Two changes needed:

  1. **Output cleanup** — condense each benchmark's console table to the key figures only (schema cost, progressive disclosure saving, WebFetch vs Tank % saved). Current output is noisy enough that reviewers skip it.

  2. **PR comment bot** — add a CI step that runs `pytest --benchmark -s` on every PR targeting `develop` or `main`, then posts the results JSON as a formatted markdown comment on the PR. This makes token regressions visible in review without anyone having to run the benchmarks manually.

  The comment should show: current results, delta vs the baseline in `tests/benchmarks/results/latest.json` (token overhead) and `tests/benchmarks/results/webfetch_vs_tank_latest.json` (WebFetch comparison), and a pass/fail badge if either benchmark regresses beyond a threshold (TBD — suggest ±10%).

## Polish

- [x] **Stale README** *(fixed)*
  `README.md` now says "Phase 1 / MVP is code-complete with a full test suite" (184 tests, 183 passing).

## Release

- [ ] **No PyPI release**
  Git tag `v0.1.0` exists and the release workflow is configured, but the package has never been published to PyPI. The release workflow creates GitHub Release artifacts (wheel, sdist, `.ctx` packs) but has no `twine upload` or `pypi-publish` step.
