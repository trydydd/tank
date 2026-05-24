# Reviewer Findings

Reviewer: claude-opus-4-6
Executor: qwen3.6-35b-a3b-fp8-dflash

## Experiment Design

This review covers an A/B comparison of executor performance across two conditions:

| | Chunks 01–06 (control) | Chunks 07–11 (treatment) |
|---|---|---|
| **Ledger version** | v2.1 — prose review_targets only | v2.2 — assertion-level review_targets, verification_inputs, negative_tests |
| **Context strategy** | Serial, single window (all 6 chunks in one session) | Fresh context per chunk (clean window for each) |
| **Context at completion** | ~106k / 200k tokens (53%) after chunk 06 | Fresh start each chunk (0% carryover) |
| **Executor model** | qwen3.6-35b-a3b-fp8-dflash | qwen3.6-35b-a3b-fp8-dflash (same) |
| **Reviewer** | claude-opus-4-6 | claude-opus-4-6 (same) |

**Hypothesis**: The combination of v2.2 ledger fields (executable test specs instead of prose) and fresh context windows will reduce the number of reviewer-caught bugs in chunks 07–11 compared to 04–06.

**Control baseline** (chunks 01–06): 5 bugs across 4 chunks (0 in 01–02, 1 in 03, 1 in 04, 2 in 05, 1 in 06). Bug rate increased in later chunks, consistent with context fatigue.

**Variables changed simultaneously**: ledger structure AND context strategy. If bug rate drops, we cannot isolate which change caused it. This is a pragmatic tradeoff — running all four combinations (v2.1/serial, v2.1/fresh, v2.2/serial, v2.2/fresh) would require 4× the executor cost. The combined treatment tests whether the overall approach works; decomposition can follow if results are promising.

**What to measure after chunks 07–11**:
- Total bugs found by reviewer (direct comparison to 5-in-4)
- Whether bugs that DO occur are in categories covered by verification_inputs/negative_tests (would indicate the executor ignored them) vs. novel categories (would indicate the fields were well-targeted but incomplete)
- Whether the executor actually implemented the verification_inputs as tests (compliance check)
- Whether the executor actually wrote the negative_tests (compliance check)
- Gotcha log quality (are gotchas from fresh-context chunks more or less detailed?)

## Chunks 1–3 Review Summary

| Chunk | Verdict | Findings |
|-------|---------|----------|
| 01 — Project Scaffold | PASS | Clean. All DOD checks pass. Structure matches architecture.md. |
| 02 — Exceptions and Models | PASS | Clean. All 7 tests pass. Dataclass fields match schema exactly. |
| 03 — Normalizer | PASS (1 fix applied) | Whitespace-only line collapsing was missing. Regex only matched consecutive `\n` characters, not lines containing only spaces/tabs. Fixed by reviewer. |

## Chunks 4–6 Review Summary

| Chunk | Verdict | Findings |
|-------|---------|----------|
| 04 — Storage Layer | PASS (1 fix applied) | Implicit transaction in `import_pack` didn't match the ledger's "explicit BEGIN/COMMIT" requirement. Wrapped in explicit BEGIN/COMMIT with ROLLBACK on failure. |
| 05 — Policy Engine | PASS (2 fixes applied) | `~/.tank/policy.toml` lookup skipped in production (home_dir guard bug). Partial policy files defaulted to empty allowed-states list, blocking everything. |
| 06 — Search Layer | PASS (1 fix applied) | BM25 results ordered worst-first due to `ORDER BY score ASC` on negated scores. |

## Detailed Findings

### Chunk 03: Blank line collapsing missed whitespace-only lines

**What happened**: The `_collapse_blank_lines` regex was `\n{3,}` which only collapses runs of consecutive newline characters. The ledger assumption stated "replace sequences of 2+ consecutive newlines *(possibly with whitespace-only lines between them)*" but the executor implemented only the parenthetical-free reading.

**Fix applied**: Changed regex to `\n([ \t]*\n){2,}` which treats whitespace-only lines as blank lines.

**Root cause**: The assumption text was clear, but the key detail was buried in a parenthetical. The executor likely read "2+ consecutive newlines" and stopped there.

**Hash stability impact**: None — both build and verify share the same code path, so hashes were consistent before and after the fix. The issue was spec conformance, not correctness.

### Chunk 04: Implicit transaction didn't match ledger spec

**What happened**: The ledger manual checklist requires "import_pack uses a single BEGIN/COMMIT transaction for all inserts." The executor relied on Python sqlite3's implicit transaction behavior — calling individual `cursor.execute()` statements followed by `self._conn.commit()`. This was functionally atomic (verified empirically), but didn't match the spec and created a future gotcha: callers trying to compose `delete_pack` + `import_pack` in a larger transaction (e.g. `--force` reimport in chunk-09) would discover that `import_pack` calls `commit()` internally, breaking the outer transaction scope.

**Fix applied**: Wrapped the insert block in explicit `cursor.execute("BEGIN")` / `self._conn.commit()` with `self._conn.rollback()` in the except path. Also moved the `ImportError_` import to the top of the method.

**Root cause**: The executor saw that Python sqlite3 handles transactions implicitly and chose the simpler pattern. The ledger said "BEGIN/COMMIT" but the executor treated it as a behavioral requirement (atomicity) rather than an implementation requirement (explicit SQL statements).

### Chunk 05: Two bugs in Policy.load()

**Bug 1 — `~/.tank/policy.toml` never checked in production.**

**What happened**: The executor added a `home_dir: Path | None = None` parameter for testability. Step 3 was guarded by `if home_dir is not None`, so when `home_dir` is not passed (the default in production), the user-level policy lookup is skipped entirely. The lookup order became: explicit path → project dir → defaults, missing step 3.

**Fix applied**: Changed the guard to `resolved_home = home_dir if home_dir is not None else Path.home()` so that `Path.home()` is used as the fallback.

**Root cause**: The executor correctly identified the testability problem (hardcoded `Path.home()` is hard to mock) and added the parameter. But the guard condition was wrong — `None` should mean "use the real home," not "skip this step." The ledger didn't specify how to handle testability of `Path.home()`, leaving the executor to design it.

**Bug 2 — Partial policy files block everything.**

**What happened**: `_parse_policy` used `policy.get("allowed_lifecycle_states", [])`, defaulting to an empty list when the key is missing. A policy file like `[policy]\nrequire_signatures = true` (without `allowed_lifecycle_states`) would reject ALL packs because no lifecycle state is in the empty allowed list.

**Fix applied**: Changed the default to `list(Policy._DEFAULT_LIFECYCLE)` so missing keys fall back to the permissive defaults.

**Root cause**: The executor followed a standard Python pattern (`dict.get(key, [])`) without considering the domain semantics — an empty allowed list isn't a safe default for a policy engine. The ledger assumptions said "The default policy allows ['draft', 'approved', 'deprecated']" but only in the context of `Policy.default()`, not `_parse_policy`. The executor didn't connect the two.

### Chunk 06: BM25 results ordered worst-first

**What happened**: The search SQL uses `-bm25(chunks_fts, 1.0, 1.0, 1.0) AS score` (negated to make scores positive) with `ORDER BY score ASC`. Since negation flips the ranking (higher = better match), ASC ordering puts the worst match first. Verified empirically: a chunk mentioning "python" 10 times ranked below a chunk mentioning it once.

**Fix applied**: Changed `ORDER BY score ASC` to `ORDER BY score DESC`.

**Root cause**: The executor encountered an FTS5 gotcha (documented in progress.txt): raw `bm25()` returns negative values where "more negative = better." The executor correctly negated the score for positive display values but didn't flip the sort direction to match. The architecture.md reference SQL uses `ORDER BY score` (without negation), which is correct because ASC on raw negative bm25 puts the most-negative (best) first. The executor changed two things (negate + ASC) when only the negation was needed, or the sort should have been DESC.

**Test gap**: No existing test had multiple results with meaningfully different relevance scores, so the ordering bug was invisible. Added `test_search_best_match_first` with chunks of very different relevance.

## Chunk 07 Review Summary

| Chunk | Verdict | Findings |
|-------|---------|----------|
| 07 — Builder | PASS (1 fix applied, 3 tests added) | Per-chunk source_url and page url stripped source directory name, violating D4. All three ledger-specified negative tests were missing. |

### Chunk 07: source_url missing source directory name prefix

**What happened**: `build_pack()` computed per-chunk `source_url` as `os.path.relpath(file_path, source)`, which produces `auth/oauth.md` for a file at `docs/auth/oauth.md` with `--source ./docs`. Per decisions.md D4 and document-processing.md section 2, the source directory name must be preserved: the correct value is `docs/auth/oauth.md`. The same bug affected `Page.url` in pages.json.

**Fix applied**: Changed `os.path.relpath(file_path, source)` to `os.path.relpath(file_path, source.parent)` in build.py line 51. This makes the relative path start from the parent of the source directory, preserving the source directory name as D4 requires.

**Root cause**: The executor used `source` as the relpath base instead of `source.parent`. This is the same category of error seen in earlier chunks — the executor read "relative path from the `--source` root" as "relative to the source directory" when the spec means "the path as given to `--source` plus the relative path within it." The ledger's verification_inputs section specified the exact expected output (`docs/auth/oauth.md`), but the executor's test only asserted `not url.startswith("./")`, which is a much weaker check.

**Test gap**: The existing `test_build_source_url_relative_paths` tested with an absolute fixture path and only checked the `./` prefix, which couldn't catch this bug. The ledger's negative test `test_source_url_does_not_strip_source_dir_name` was NOT implemented. Added three missing negative tests:
1. `test_source_url_does_not_strip_source_dir_name` — verifies no chunk's source_url starts with `auth/` when `--source` is `./docs`
2. `test_discover_files_does_not_include_non_whitelisted` — verifies .png, .txt, .py files are excluded (fixture had no non-whitelisted files to test against)
3. `test_chunk_ids_not_filesystem_dependent` — verifies files created in non-alphabetical order are still discovered in sorted order

Also strengthened `test_build_source_url_relative_paths` to assert source_url starts with `docs/` and page url starts with `docs/`.

### Chunk 07: Minor observations (not fixed)

1. **`generate_summary` code-heavy threshold mismatch**: The ledger verification input for code-heavy content (one code block with 2 lines + 1 prose line) is only 40% code by line count, below the >50% threshold. The executor's test uses a different input with 67% code lines. The function returns `"Some prose here."` instead of the expected signature for the ledger's exact input. Not fixed because: (a) the algorithm is correct per its own definition, (b) the ambiguity is in "50% of content" — lines vs. characters — and the executor's interpretation (lines) is reasonable, (c) summary generation is build-time only, not security-critical.

2. **Dead `hasattr` check**: `if not hasattr(rc, "summary") or not rc.summary:` in build.py:97 — `hasattr` is always True since `summary` is a dataclass field with a default. Harmless but unnecessary.

3. **`discover_files` sort key conditional**: `source_parent = source.parent if str(source).startswith("./") else source` — per document-processing.md, the sort should always be relative to `source.parent`. The conditional doesn't cause incorrect ordering (constant prefix), but is inconsistent with the spec.

## Observations for Improving Executor Performance

### What the executor did well

**Chunks 1–3:**

1. **Followed the ledger precisely.** File paths, export signatures, and test names all matched the interface_contract. Zero spec drift across three chunks.
2. **Tests are well-structured.** Each test function is focused and tests one behavior. No test depends on another.
3. **Clean mypy and ruff on first pass.** No type errors, no lint issues. The executor respected `str | None` syntax throughout.
4. **Idempotency was tested.** The executor added `test_deterministic_output` which verifies `normalize(normalize(x)) == normalize(x)` — a critical property not always obvious to smaller models.
5. **Progress log maintained.** Both gotcha entries (chunk-01) and no-gotcha entries (chunks 02–03) were recorded as required.
6. **Reasonable judgment calls.** Using `click.Group()` directly instead of `@click.group()` decorator, adding `test_placeholder.py` for pytest exit-0, and adding the `conftest.py` were all pragmatic decisions.

**Chunks 4–6:**

7. **SQL schema is exact.** The CREATE TABLE statements in db.py match docs/architecture.md character-for-character, including FTS5 triggers. No drift.
8. **Good gotcha logging.** The FTS5 comma-style join and bm25 weight-factor gotchas (chunk-06) are genuine 15+ minute traps. Well-documented with repro and workaround.
9. **TYPE_CHECKING guard for circular imports.** The executor correctly identified and solved the circular import between `search.fts` and `storage.db` using the standard `TYPE_CHECKING` pattern.
10. **Policy engine structure is clean.** The `PolicyResult` dataclass, lookup chain, and `evaluate()` method are all well-organized and readable. The `_parse_policy` helper keeps TOML parsing separate from the class.
11. **Search handles edge cases.** Empty queries return `[]`, malformed FTS5 queries are caught via broad exception handler, empty chunk_ids list short-circuits. These weren't all explicit in the ledger.

### What could be improved

**Recurring pattern — behavioral equivalence treated as spec compliance:**

1. The executor consistently meets the *behavioral intent* of the spec but misses *implementation-level requirements*. Implicit transactions satisfy "atomic import" but not "explicit BEGIN/COMMIT." `dict.get(key, [])` satisfies "has a default" but not "uses the permissive defaults." This pattern appeared in 2 of 3 chunks reviewed (04 and 05).

2. **Semantic defaults not inferred from domain context.** When the ledger says "default policy allows X" in one place and the executor writes `dict.get(key, [])` in another, the connection isn't made. Small models treat each function as local — they don't propagate domain invariants across implementation boundaries.

3. **Sort direction not re-evaluated after algebraic transformation.** The executor negated the bm25 score (correct) but didn't re-derive the sort direction (incorrect). When a transformation changes the sign of a value, the ordering must flip. This is an algebraic reasoning step that small models skip.

4. **Guard conditions inverted for optional parameters with production defaults.** `if home_dir is not None` was the natural guard for a nullable parameter, but the correct semantics were "None means use the real default, not skip the step." This is a common trap when adding testability parameters.

**New from chunk 07 (first treatment-group chunk):**

5. **`relpath` base confusion.** The executor computed `os.path.relpath(file_path, source)` when the spec requires the path relative to `source.parent`. The phrase "relative path from the --source root" is ambiguous — does "from" mean "starting at" or "computed against"? The document-processing.md examples are unambiguous (`docs/auth/oauth.md` clearly includes the source dir name), but the executor didn't cross-reference the example in section 2 against the implementation in build.py.

6. **Negative tests not implemented despite being specified in the ledger.** All three `negative_tests` entries were ignored. The executor focused entirely on the `interface_contract` test list and appears not to have read the `negative_tests` section. This is a compliance issue — the v2.2 ledger fields were designed to reduce bugs, but only if the executor actually reads them.

7. **Test assertions weaker than verification_inputs.** The executor's `test_build_source_url_relative_paths` asserted `not url.startswith("./")` — a weaker check than the verification_inputs section's expected output `docs/auth/oauth.md`. The verification_inputs were available but not used to calibrate the assertion.

### Recommendations for the ledger / planner

**Carried forward from chunks 1–3:**

1. **Promote critical qualifiers out of parentheticals.** Small models parse top-level statements more reliably than nested clauses. Use definition-then-rule structure.

2. **Add edge-case test inputs to review_targets when hash stability matters.** Concrete expected-output assertions catch bugs that behavioral descriptions miss.

3. **Pin regex patterns in the ledger for security/integrity-critical functions.** Eliminates interpretation errors for constrained models.

4. **The gotcha bar is well-calibrated.** No adjustment needed.

**New from chunks 4–6:**

5. **Distinguish behavioral requirements from implementation requirements in the manual checklist.** When the checklist says "uses a single BEGIN/COMMIT transaction," make it explicit whether this means "the operation is atomic" (behavioral) or "the code must contain literal BEGIN and COMMIT SQL statements" (implementation). For small models, the safest approach is: if you mean explicit SQL, write the SQL in the assumptions section:
   > "import_pack must execute `cursor.execute('BEGIN')` before inserts and `self._conn.commit()` after. On failure, call `self._conn.rollback()`."

6. **Specify default-fallback behavior for partial config files.** When a config parser has optional keys, state what the default is for EACH key independently, not just for the "no file found" case. Instead of:
   > "The default policy allows ['draft', 'approved', 'deprecated']"

   Write:
   > "The default policy allows ['draft', 'approved', 'deprecated']. When loading a policy file, any missing key falls back to the same defaults — a partial file is merged with defaults, not treated as a complete override."

   This prevents the "empty list as default" trap.

7. **When the executor must transform a value before sorting, state the expected sort direction with the transformed value.** The ledger assumption said "bm25 returns NEGATIVE scores (lower is better). Sort ORDER BY score ASC, or negate it for display." This gave two options but didn't connect them: if you negate, you must also flip the sort. Better:
   > "bm25() returns negative scores. Two correct patterns: (a) `bm25(chunks_fts) AS score ORDER BY score ASC` or (b) `-bm25(chunks_fts) AS score ORDER BY score DESC`. Do not mix negation with ASC."

8. **For parameters added for testability, specify the production-default behavior.** When the interface_contract doesn't include a parameter but the executor needs one for testing, the ledger should anticipate this. Add to assumptions:
   > "Policy.load may accept additional parameters for testability (e.g. home_dir). When such parameters are None, the production default must be used (e.g. Path.home()), not skipped."

   Alternatively, the interface_contract could include the testability parameter upfront.

9. **Add multi-result ordering tests to the interface_contract for any ranked-output function.** The chunk-06 test list included `test_search_returns_ranked_results` but that test only had one result. Add:
   > "test_search_best_match_first() — import chunks with very different term frequencies for the query term, verify the most relevant chunk is returned first"

   Single-result tests cannot catch ordering bugs.

**New from chunk 07:**

10. **Disambiguate `relpath` base in path-construction assumptions.** When the spec says "relative path from --source," explicitly state whether the base is `source` or `source.parent`. Include the Python expression:
    > "Per-chunk source_url: `os.path.relpath(file_path, source.parent)` — this preserves the source directory name. Do NOT use `os.path.relpath(file_path, source)` which strips it."

11. **Mark `negative_tests` as mandatory in the executor prompt.** The executor implemented all `interface_contract` tests but ignored all `negative_tests`. The executor prompt should state: "The `negative_tests` section is mandatory — implement each test listed there in addition to the interface_contract tests."

12. **Require test assertions to match `verification_inputs` precision.** When the ledger provides exact expected outputs (e.g. `source_url='docs/auth/oauth.md'`), the executor's test assertions should check for that exact value, not a weaker property (e.g. `not url.startswith('./')`). Add to the executor prompt:
    > "When the `verification_inputs` section provides expected output for a function, your test assertions must verify that exact output, not a weaker property."

## Chunk 08 Review Summary

| Chunk | Verdict | Findings |
|-------|---------|----------|
| 08 — Validator | PASS (2 fixes applied via executor) | ZipFile handle leak on every return path. `_compute_normalized_content_hash_from_archive` could raise on corrupted archives, violating the "verify() never raises" contract. |

### Chunk 08: ZipFile handle leak

**What happened**: `verify()` opened the archive at line 58 with `zf = zipfile.ZipFile(ctx_path, "r")` — a bare open, not a context manager. Every early return (14 return statements across steps 1–8) leaked the file handle. On the success path and on every failure path, `zf.close()` was never called.

**Fix applied**: Wrapped the entire post-open body in `with zf:` (line 67). All return paths now close the handle via the context manager.

**Root cause**: The executor needed the `zf` variable available before entering the context manager (to handle the `BadZipFile`/`OSError` case separately), and chose a bare open. The obvious pattern is try/except for the open, then `with zf:` for the body — but the executor didn't connect the two. This is a resource lifecycle issue that requires reasoning across all return paths, not just local correctness.

**How it was found**: Manual reviewer inspection. The automated verification pipeline (v2.3) did not catch this — the completion promise was all-YES on the first pass. The "verify() never raises" contract was tested, but no test checked whether file handles were leaked.

**Executor fix attempts**: The executor was prompted 3 times to fix this. Attempts 1–2 produced descriptions of the issue but no code changes — the executor correctly identified resource concerns but claimed the cleanup already existed ("the with at line 58 does clean up" — there was no `with`). Attempt 3 successfully applied the fix.

### Chunk 08: Step 7 can raise on corrupted archives

**What happened**: `_compute_normalized_content_hash_from_archive()` calls `zf.read("chunks.jsonl")`, `json.loads()`, and accesses chunk fields — all of which can raise on a corrupted/malicious archive. The call at line 196 had no try/except, so exceptions propagated out of `verify()`, violating the "verify() never raises for expected failures" contract.

**Fix applied**: Wrapped the call in `try/except (KeyError, json.JSONDecodeError, UnicodeDecodeError)` returning `VerifyResult(passed=False, step=7, reason=...)`.

**Root cause**: The executor treated `chunks.jsonl` as trusted builder output, but the verifier handles untrusted archives. Defensive error handling was needed at the boundary.

**How it was found**: Executor self-reported (Bug 1 in a 4-bug list). Validated by reviewer — 1 of 4 reported bugs was real.

### Chunk 08: Executor self-reported bugs — accuracy

The executor produced a 4-bug report when prompted to find issues. Reviewer evaluation:

| Bug | Claim | Verdict |
|-----|-------|---------|
| 1 — Step 7 can raise | `_compute_normalized_content_hash_from_archive` propagates exceptions | **VALID** — real contract violation |
| 2 — Silent `.get()` defaults | Malformed chunk records silently ignored | **INVALID** — hash mismatch catches corruption; SHA-256 collision infeasible |
| 3 — Wrong size field | `file_size` is uncompressed, should check decompressed | **INVALID** — `file_size` IS the uncompressed/decompressed size; executor contradicted itself |
| 4 — Expensive archive rebuild | `_read_archive_bytes` is needlessly expensive | **INVALID** — zip rebuild is required by zeroing convention; "hash without rebuild" doesn't work because zip entry headers change |

**Pattern**: The executor finds surface-level issues well (Bug 1) but confuses itself on domain-specific reasoning (Bugs 3–4) and generates false positives from over-application of defensive coding patterns (Bug 2).

### Chunk 08: Minor observations (not fixed)

1. **`VerificationError` imported but unused in tests**: `from tank.errors import VerificationError` is dead code — `verify()` returns `VerifyResult` by design.
2. **`hashlib` imported inside functions**: `_compute_pack_digest_from_bytes` and `_compute_normalized_content_hash_from_archive` import hashlib locally instead of at module level. Functional, just non-standard.
3. **`malformed_packs/` fixture directory is empty**: The ledger spec lists it as an output, but all tests construct bad archives inline. The inline approach is actually better for test readability.

### Chunk 08: Pipeline performance

This was the first chunk processed end-to-end by the automated executor→verifier pipeline (run-chunk.sh). The pipeline reported all-green on the first verification pass. Both bugs were missed by the automated verifier — the ZipFile leak because no test checks handle lifecycle, and the step 7 raise because no test supplies a corrupted chunks.jsonl to a pack that passes steps 1–6.

**Implication for verifier design**: The v2.3 review prompt template is effective for spec-compliance checking (all 4 completion promise lines correctly evaluated) but does not cover resource management or defensive error handling at internal boundaries. These categories require either:
- Explicit review targets in the ledger (e.g. "verify all opened resources are closed on every return path")
- A separate review pass focused on resource/error handling patterns

## A/B Experiment — Results After Chunk 08

**Treatment group (v2.3 ledger + fresh context + automated pipeline): 2 bugs in 2 chunks.**

| Metric | Control (01–06, v2.1, serial) | Treatment (07–08, v2.2→2.3, fresh) |
|--------|-------------------------------|--------------------------------------|
| Chunks reviewed | 6 | 2 |
| Bugs found by reviewer | 5 | 3 (1 in chunk 07, 2 in chunk 08) |
| Bug rate | 0.83/chunk | 1.5/chunk |
| Bugs self-reported by executor | N/A | 1 valid of 4 reported (chunk 08) |
| Negative tests implemented | N/A (not in v2.1) | 0/3 (chunk 07), 3/3 (chunk 08) |
| Verification inputs used | N/A (not in v2.1) | No (chunk 07), Yes (chunk 08) |
| Automated verifier caught | N/A | 0 of 3 bugs |

**Observations after 2 treatment chunks**:
- v2.3 negative test inlining worked — chunk 08 implemented all 3 NEG tests (vs. 0/3 in chunk 07 with separate section). Confirms the attention-proximity hypothesis.
- Verification inputs compliance improved in chunk 08 — exact expected outputs were checked.
- Bug categories shifted: chunk 07 bugs were spec-compliance (covered by verification_inputs). Chunk 08 bugs were resource management and defensive error handling — categories NOT covered by current ledger fields.
- The automated verifier pipeline (review-chunk.sh) has not caught any bugs independently. It validates spec compliance well but misses implementation-quality issues.
- Executor self-reporting has a 25% accuracy rate (1/4) — generates false positives from confused reasoning but can find genuine contract violations.

**Conclusion after 2 treatment chunks**: The v2.3 ledger changes fixed executor compliance (negative tests now implemented, verification inputs now used). The remaining bug surface is in categories the ledger doesn't cover: resource lifecycle, defensive error handling at internal boundaries. Next steps: add resource-management review targets to chunks 09–11, or add a dedicated review pass for these patterns.
