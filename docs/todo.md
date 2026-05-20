# Tank — Known Issues & Gaps

## Bugs

- [ ] **`src/tank/cli/pull.py:39` — hardcoded `doc_version_status`**
  `_import_pack` sets `doc_version_status="imported"` instead of reading the value from the manifest. The manifest carries the real status (`stable`, `prerelease`, etc.) but pull ignores it.

- [ ] **`src/tank/server.py:122` — unused `max_tokens` parameter**
  The `query-docs` MCP tool accepts `max_tokens` but never passes it through or uses it. Either implement token-budget logic or remove the parameter.

- [ ] **`src/tank/storage/db.py:121-126` — page ID foreign key integrity broken on import**
  The `pages` table uses `INTEGER PRIMARY KEY AUTOINCREMENT`, but `import_pack()` omits the `id` column from the INSERT. SQLite generates new IDs that won't match the `page_id` values chunks carry from the `.ctx` pack. After importing a second pack, chunk `page_id` references point to wrong pages or nonexistent rows. Fix: either include `id` in the page INSERT, or remap chunk `page_id` values to the auto-generated IDs during import.

- [ ] **`src/tank/search/fts.py:76` — silent exception swallowing**
  `search()` catches all exceptions and returns `[]`. Malformed queries, database errors, and schema mismatches all silently produce empty results with no logging or error signal.

## Incomplete Implementations

- [ ] **Signature verification is a stub (`src/tank/validator/verify.py`, Step 8)**
  Only checks whether `signatures/manifest.sig` exists in the archive. No actual cryptographic verification (ed25519, Sigstore, etc.) is performed.

- [ ] **No schema migrations (`src/tank/storage/db.py`)**
  Database setup uses `CREATE TABLE IF NOT EXISTS` only. No `PRAGMA user_version` tracking or forward-only migration support. Any future column additions will break existing databases.

## Polish

- [ ] **Stale README**
  `README.md` says "implementation is beginning" but the Phase 1 MVP is code-complete with 141 passing tests.

## Release

- [ ] **No PyPI release**
  Git tag `v0.1.0` exists and the release workflow is configured, but the package has never been published to PyPI. The release workflow creates GitHub Release artifacts (wheel, sdist, `.ctx` packs) but has no `twine upload` or `pypi-publish` step.
