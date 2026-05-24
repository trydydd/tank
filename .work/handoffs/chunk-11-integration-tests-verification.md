# Verification: chunk-11-integration-tests
Date: 2026-05-19
Verifier: claude

## DOD Automated
- [x] pytest tests/test_integration.py -v: exit 0 (13 passed)
- [x] mypy tests/test_integration.py: exit 0 (success, no issues found)

## Verification Inputs
- [x] CASE: Golden path end-to-end | EXPECTED: build exits 0, .ctx file created, verify returns passed=True, pull exits 0, query for a known term returns results with attribution | ACTUAL: build exit_code=0, ctx_path exists, verify exit_code=0, pull exit_code=0, query output contains "test-lib" and "getting-started" | PASS
- [x] CASE: Content tampering caught at step 7 specifically | EXPECTED: verify returns VerifyResult(passed=False, step=7) — content hash mismatch, not pack_digest mismatch | ACTUAL: VerifyResult(passed=False, step=7, reason='normalized_content_hash mismatch') | PASS

## Test Coverage
- [x] test_full_pipeline_build_verify_pull_query: EXISTS (line 124)
- [x] test_build_then_verify_passes: EXISTS (line 170)
- [x] test_build_then_tamper_then_verify_fails: EXISTS (line 201)
- [x] test_pull_populates_fts_index: EXISTS (line 235)
- [x] test_query_returns_attributed_results: EXISTS (line 275)
- [x] test_query_progressive_disclosure: EXISTS (line 310)
- [x] test_pull_writes_lockfile: EXISTS (line 367)
- [x] test_pull_duplicate_rejected: EXISTS (line 403)
- [x] test_revoked_pack_excluded_from_query: EXISTS (line 435)
- [x] test_pull_does_not_leave_partial_state_on_failure (NEG): EXISTS (line 488)
- [x] test_revoked_pack_not_in_query_results (NEG): EXISTS (line 531)
- [x] test_build_verify_cycle_is_symmetric (NEG): EXISTS (line 584)
- [x] test_content_tampering_captured_at_step_7 (NEG): EXISTS (line 615)
- Negative tests implemented: 4/4 (3 labeled NEG in interface_contract + 1 additional negative test for step 7 specificity)

## Review Targets
- [x] Full pipeline: assertion matches — test_full_pipeline_build_verify_pull_query asserts build exit_code=0, verify exit_code=0, pull exit_code=0, query output contains package name and source_url
- [x] Tamper detection: assertion matches — test_build_then_tamper_then_verify_fails asserts exit_code!=0 and "step 7" in output
- [x] Progressive disclosure: assertion matches — test_query_progressive_disclosure asserts summary results have content=None, full results have content not None
- [x] Lockfile: assertion matches — test_pull_writes_lockfile asserts lock_file.exists(), pack name in lockfile, version in lockfile

## Manual Checklist
- [x] Full pipeline test covers build -> verify -> pull -> query in sequence | PASS | test_full_pipeline_build_verify_pull_query invokes build, verify, pull, query in sequence, all assertions pass
- [x] No test depends on state from another test (each uses its own tmp_path) | PASS | All 13 tests accept tmp_path fixture; DB paths are tmp_path / ".tank" / "index.db" (unique per test)
- [x] At least one test verifies tamper detection end-to-end | PASS | test_build_then_tamper_then_verify_fails builds, tampers chunk content in .ctx, verifies failure at step 7

## Fixes Applied
1. Created tests/test_integration.py from scratch (chunk was PENDING, file did not exist)
2. Implemented _cli_in_cwd() helper using os.chdir() to handle pull/query commands that use relative Path(".tank") — CliRunner does not support cwd parameter
3. Implemented _tamper_with_valid_digest() helper that rewrites .ctx with modified content but recalculates pack_digest so step 6 passes and only step 7 fails
4. Added type: ignore[import-untyped] for all tank.* imports (project lacks py.typed marker)
5. Added Result import from click.testing and typed _cli_in_cwd return type to satisfy mypy strict mode

## Completion Promise
All verification_inputs produce expected output: YES
All interface_contract tests exist and pass: YES
All review_targets assertions hold: YES
All manual_checklist items verified: YES
