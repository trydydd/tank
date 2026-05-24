# Verification Pass — {{CHUNK_ID}}

You are performing a **mechanical verification** of a completed chunk implementation.
You are NOT the implementer. You are a fresh-context verifier with no prior knowledge
of the implementation decisions. Your job is to compare actual behavior against the
ledger specification and report pass/fail with evidence.

## Instructions

### Step 1: Load the spec

Read the chunk definition from `.work/ledger.yaml`. Find the chunk with
`id: "{{CHUNK_ID}}"`. Read the entire chunk definition including all fields:
`objective`, `interface_contract`, `assumptions`, `definition_of_done`,
`review_targets`, `verification_inputs`, and `negative_tests`.

Read every file listed in `handoff.files_modified`.

### Step 2: Run DOD automated checks

Run each command in `definition_of_done.automated`. Record exit codes.
If any fail, fix the issue, re-run, and note the fix.

### Step 3: Execute verification_inputs

For each entry in `verification_inputs`:
- Set up the exact input described
- Call the function or construct the scenario
- Capture the actual output
- Compare against `expected`
- Record: `CASE: <label> | EXPECTED: <expected> | ACTUAL: <actual> | PASS/FAIL`

Do NOT skip any case. Do NOT report PASS without showing the actual output.

### Step 4: Verify test coverage

For each test function listed in `interface_contract.outputs`:
- Confirm the test exists in the correct file
- Confirm the test function name matches exactly
- If any are missing, implement them following the inline description

For tests marked with `# NEG:` comments, verify that the assertion tests for
the ABSENCE of wrong behavior (not just the presence of correct behavior).

### Step 5: Check review_targets

For each `review_targets` entry:
- Read the test named in `verified_by`
- Confirm the test's assertion matches the `assertion` field
- If the test exists but the assertion is weaker than specified, strengthen it

### Step 6: Run manual_checklist

For each item in `definition_of_done.manual_checklist`:
- Verify it by reading the code or running a command
- Record: `CHECK: <item> | PASS/FAIL | EVIDENCE: <what you observed>`

### Step 7: Write completion evidence

Write results to `.work/handoffs/{{CHUNK_ID}}-verification.md` in this format:

```markdown
# Verification: {{CHUNK_ID}}
Date: <today>
Verifier: <model name>

## DOD Automated
- [ ] <cmd>: exit <code>

## Verification Inputs
- [ ] CASE: <label> | EXPECTED: <expected> | ACTUAL: <actual> | PASS/FAIL

## Test Coverage
- [ ] <test_name>: EXISTS / MISSING
- [ ] Negative tests implemented: <count>/<total>

## Review Targets
- [ ] <target>: assertion matches / assertion weaker than spec / test missing

## Manual Checklist
- [ ] <item>: PASS/FAIL | EVIDENCE: <observation>

## Fixes Applied
<list any code changes made during verification, or "None">

## Completion Promise
All verification_inputs produce expected output: YES/NO
All interface_contract tests exist and pass: YES/NO
All review_targets assertions hold: YES/NO
All manual_checklist items verified: YES/NO
```

### Rules

- If you find a discrepancy, FIX IT before reporting. Then re-run the relevant checks.
- After fixing, re-run ALL DOD automated checks to confirm no regressions.
- Do NOT emit "Completion Promise: YES" for any line unless you have shown evidence above.
- If you cannot verify a case (e.g., requires infrastructure you don't have), mark it
  `SKIP: <reason>` — do not mark it PASS.
- Read the actual code. Do not trust your memory of what the code does.
