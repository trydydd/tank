# Verification: chunk-09-cli-commands
Date: 2026-05-19
Verifier: Claude Sonnet

## DOD Automated
- [x] `pytest tests/test_cli/ -v`: exit 0 (21 passed)
- [x] `mypy src/tank/cli/`: exit 0 (no issues in 7 files)
- [x] `ruff check src/tank/cli/`: exit 0 (all checks passed)

## Verification Inputs
- [x] CASE: Standard format parsed correctly | EXPECTED: package='my-lib', version='1.0.0' | ACTUAL: package='my-lib', version='1.0.0' | PASS
- [x] CASE: Missing @ detected | EXPECTED: exit_code=1, error message about missing version | ACTUAL: ValueError("Missing '@' in package spec 'my-lib'...") | PASS
- [x] CASE: Multiple @ signs rejected | EXPECTED: exit_code=1, error message about invalid format | ACTUAL: ValueError("Invalid package spec 'my@lib@1.0.0'. Multiple '@' signs detected...") | PASS

## Test Coverage
- [x] test_build_command_success: EXISTS
- [x] test_build_command_missing_source: EXISTS
- [x] test_build_command_bad_package_format: EXISTS
- [x] test_verify_command_pass: EXISTS
- [x] test_verify_command_fail: EXISTS
- [x] test_pull_command_success: EXISTS
- [x] test_pull_command_verify_fails: EXISTS
- [x] test_pull_command_duplicate_rejected: EXISTS
- [x] test_pull_command_force_reimport: EXISTS
- [x] test_pull_does_not_import_on_verify_failure: EXISTS (NEG)
- [x] test_pull_force_does_not_skip_verify: EXISTS (NEG)
- [x] test_query_command_summary: EXISTS
- [x] test_query_command_full: EXISTS
- [x] test_query_does_not_crash_on_empty_db: EXISTS (NEG)
- [x] test_inspect_ctx_file: EXISTS
- [x] test_inspect_index_db: EXISTS
- [x] Negative tests implemented: 3/3

Negative test verification:
- test_pull_does_not_import_on_verify_failure: Queries packages table after failed pull, asserts count == 0. Tests ABSENCE of wrong behavior. PASS
- test_pull_force_does_not_skip_verify: Creates tampered .ctx, runs pull --force, asserts exit_code == 1. Verifies --force does NOT bypass verification. PASS
- test_query_does_not_crash_on_empty_db: Runs query with no imported packs, asserts exit_code == 0 and no traceback. PASS

## Review Targets
- [x] "tank build produces a .ctx file": test_build_command_success assertion (exit_code=0 + .ctx exists + manifest fields) is STRONGER than spec. PASS
- [x] "tank pull rejects when verify fails": test_pull_command_verify_fails asserts exit_code == 1. MATCHES spec. PASS
- [x] "tank pull --force re-imports an existing pack": test_pull_command_force_reimport: first succeeds (0), second without --force fails (1), third with --force succeeds (0). MATCHES spec. PASS
- [x] "tank query returns results with expected text": test_query_command_summary assertion WAS WEAKER (only checked exit_code). STRENGTHENED to assert "getting-started" in output (heading_path from imported data). PASS
- [x] "All commands exit 1 on TankError": test_build_command_missing_source asserts exit_code == 1, error in output, no traceback. MATCHES spec. PASS

## Manual Checklist
- [x] All commands catch TankError and print user-friendly messages | PASS/FAIL | EVIDENCE: All 5 CLI files (build.py, verify.py, pull.py, query.py, inspect.py) contain try/except TankError blocks that print formatted error via rich Console and sys.exit(1)
- [x] Exit codes: 0 for success, 1 for errors | PASS/FAIL | EVIDENCE: grep of sys.exit calls shows exit(1) on all error paths across all 5 commands. Success paths return normally (implicit exit 0)
- [x] tank pull writes/updates .tank/index.lock after import | PASS/FAIL | EVIDENCE: pull.py calls _write_lockfile(db) immediately after _import_pack(ctx_path, policy_obj, db). LOCK_FILE = TANK_DIR / "index.lock" where TANK_DIR = Path(".tank")
- [x] package@version parsing handles edge cases (no @, multiple @) | PASS/FAIL | EVIDENCE: _parse_package_spec in build.py validates: missing @ raises ValueError, multiple @ (len(parts) != 2) raises ValueError, empty name or version raises ValueError. All verified with pytest.

## Fixes Applied
1. tests/test_cli/test_query.py: test_query_command_summary — Added monkeypatch.chdir(build_out) so pull and query resolve the same DB path. Added import pytest. Added assertion "getting-started" in result.output to match review_targets spec (was only checking exit_code == 0).
2. tests/test_cli/test_query.py: test_query_command_full — Added monkeypatch.chdir(build_out) for DB path alignment.

## Completion Promise
All verification_inputs produce expected output: YES
All interface_contract tests exist and pass: YES
All review_targets assertions hold: YES
All manual_checklist items verified: YES
