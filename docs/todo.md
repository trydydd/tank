# Tank — Known Issues & Gaps

## Bugs

- [x] **`src/tank/cli/pull.py:39` — hardcoded `doc_version_status`** *(fixed)*
  `_import_pack` now reads `doc_version_status` from the manifest instead of hardcoding `"imported"`.

- [ ] **`src/tank/builder/manifest.py:43` — `doc_version_status` hardcoded to `"stable"`**
  `build_manifest()` always writes `"doc_version_status": "stable"` regardless of input. The valid values are `stable`, `prerelease`, `archived`, and `unknown` (per `docs/architecture.md`). The builder should accept `doc_version_status` as a parameter and pass it through to the manifest so packs can accurately reflect their documentation state.

- [ ] **`src/tank/server.py` — `max_tokens` parameter is a stub**
  The `query-docs` MCP tool accepts `max_tokens` but never uses it. Now that `limit` is exposed (see fixed item below), the path is clear: implement token-budget logic that auto-selects `limit` to fit results within the requested token budget, using `len(content) // 4` as the estimator. Design question to settle first: trim from the bottom of the ranked list, or truncate content of the last result? Either implement or remove before v0.1.0 ships.

- [x] **`src/tank/storage/db.py:121-126` — page ID foreign key integrity broken on import** *(fixed)*
  `import_pack()` now builds a `page_id_map` from each page's pack-local ID to its AUTOINCREMENT DB ID, and remaps `chunk.page_id` values through it before inserting chunks.

- [x] **`src/tank/search/fts.py:76` — silent exception swallowing** *(fixed)*
  `search()` now raises `SearchError` (a `TankError` subclass) on `sqlite3.Error` instead of catching all exceptions and returning `[]`.

- [x] **`src/tank/server.py` / `src/tank/search/fts.py:32` — result limit not exposed** *(fixed)*
  `query_docs()` now accepts `limit: int = 10` and passes it through to `search()`. The MCP tool exposes the same parameter. Discovered by the token overhead benchmark when `full_n10 == full_n20`.

## Incomplete Implementations

- [ ] **Signature verification is a stub (`src/tank/validator/verify.py`, Step 8)**
  Only checks whether `signatures/manifest.sig` exists in the archive. No actual cryptographic verification (ed25519, Sigstore, etc.) is performed.

- [ ] **No schema migrations (`src/tank/storage/db.py`)**
  Database setup uses `CREATE TABLE IF NOT EXISTS` only. No `PRAGMA user_version` tracking or forward-only migration support. Any future column additions will break existing databases.

## Polish

- [x] **Stale README** *(fixed)*
  `README.md` now says "Phase 1 / MVP is code-complete with a full test suite" (184 tests, 183 passing).

## Release

- [ ] **No PyPI release**
  Git tag `v0.1.0` exists and the release workflow is configured, but the package has never been published to PyPI. The release workflow creates GitHub Release artifacts (wheel, sdist, `.ctx` packs) but has no `twine upload` or `pypi-publish` step.
