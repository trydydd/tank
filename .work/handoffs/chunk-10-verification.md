# Verification: chunk-10-mcp-server
Date: 2026-05-19
Verifier: Claude Opus 4.7

## DOD Automated
- [x] pytest tests/test_server.py -v: exit 0 (10 passed, 0 failed)
- [x] mypy src/tank/server.py: exit 0 (success)
- [x] ruff check src/tank/server.py: exit 0 (all checks passed)

## Verification Inputs
- [x] CASE: Output matches architecture.md MCP Tool Surface schema | EXPECTED: {status: 'ok', packs: [{package: 'my-lib', version: '1.0.0', lifecycle_state: 'approved', chunks: 5, ...}]} | ACTUAL: {status: 'ok', packs: [{package: 'my-lib', version: '1.0.0', lifecycle_state: 'approved', chunks: 5, doc_version_status: 'stable', indexed_at: '2026-05-14T10:30:00Z'}]} | PASS
- [x] CASE: Deprecated packs carry lifecycle_warning in MCP output | EXPECTED: Result includes lifecycle_warning field with deprecation message | ACTUAL: lifecycle_warning = "This package is deprecated" | PASS

## Test Coverage
- [x] test_resolve_deps_returns_packs: EXISTS
- [x] test_resolve_deps_empty_index: EXISTS
- [x] test_query_docs_summary_mode: EXISTS
- [x] test_query_docs_full_mode: EXISTS
- [x] test_query_docs_chunk_ids: EXISTS
- [x] test_query_docs_not_indexed_package: EXISTS
- [x] test_query_docs_deprecated_warning: EXISTS
- [x] test_http_does_not_bind_external: EXISTS (NEG)
- [x] test_query_docs_does_not_return_revoked: EXISTS (NEG)
- [x] test_resolve_deps_does_not_omit_deprecated: EXISTS (NEG)
- [x] Negative tests implemented: 3/3

## Review Targets
- [x] resolve-deps returns correct pack count and metadata: assertion matches — test imports 2 packs and verifies count=2 with correct package, version, lifecycle_state, chunks
- [x] query-docs summary mode excludes content: assertion matches — test verifies content is None, heading_path and summary present
- [x] query-docs with chunk_ids returns full content: assertion matches — test verifies content field is present and non-empty for each chunk
- [x] Empty database returns appropriate empty results: assertion matches — test verifies status='ok' and packs=[]

## Manual Checklist
- [x] python -m tank.server starts without error | PASS/FAIL | EVIDENCE: `python -m tank.server` starts cleanly and blocks on stdin (MCP stdio transport) — no import errors, no exceptions before timeout
- [x] Tool output JSON matches the schema in docs/architecture.md | EVIDENCE: resolve-deps output includes status, packs array with package/version/lifecycle_state/doc_version_status/chunks/indexed_at — matches architecture.md lines 50-72. query-docs output includes results array with chunk_id/package/version/lifecycle_state/doc_version_status/heading_path/summary/content/source_url/source_commit/content_hash/indexed_at/score — matches architecture.md lines 98-116.
- [x] HTTP transport binds to 127.0.0.1 only | EVIDENCE: server.py line 22: `_HTTP_HOST = "127.0.0.1"`, line 143: `assert _HTTP_HOST == '127.0.0.1'`, code never uses '0.0.0.0' or ''

## Fixes Applied
None — all checks passed on first attempt.

## Completion Promise
All verification_inputs produce expected output: YES
All interface_contract tests exist and pass: YES
All review_targets assertions hold: YES
All manual_checklist items verified: YES
