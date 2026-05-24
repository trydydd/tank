#!/usr/bin/env bash
set -euo pipefail

CHUNK_ID="${1:?Usage: run-chunk.sh <chunk-id> [max-verify-passes]}"
MAX_VERIFY="${2:-3}"
LOGDIR="/workspace/.work/handoffs"
EXECUTOR_LOG="${LOGDIR}/${CHUNK_ID}-executor.log"
VERIFY_LOG="${LOGDIR}/${CHUNK_ID}-verify.log"
EVIDENCE="${LOGDIR}/${CHUNK_ID}-verification.md"
SUMMARY="${LOGDIR}/${CHUNK_ID}-summary.md"

mkdir -p "$LOGDIR"

# Derive unique proxy ports so child detour processes don't collide with
# the parent or with each other when chunks run in parallel.
_port_for() { echo $(( 18000 + $(printf '%s' "$1" | cksum | cut -d' ' -f1) % 1000 )); }
EXEC_PORT=$(_port_for "${CHUNK_ID}_execution")

# ── Phase 1: Executor ────────────────────────────────────────────────────────

echo "=== Phase 1: Executor — ${CHUNK_ID} ===" >&2

EXECUTOR_PROMPT="$(cat <<PROMPT
You are the executor. Implement exactly one chunk.

1. Read /workspace/.work/ledger.yaml — find the chunk with id: "${CHUNK_ID}"
2. Read /workspace/.work/progress.txt
3. Follow the executor briefing at the top of the ledger exactly
4. Read all prerequisites.read_first files listed in the chunk
5. Implement the chunk following TDD (failing test first, then implementation)
6. Implement ALL test functions in interface_contract.outputs — including tests marked with "# NEG:" comments
7. For each verification_inputs case, your test assertions must check the EXACT expected output
8. Run all definition_of_done.automated commands — all must exit 0
9. Append to progress.txt (gotcha format or "No gotchas.")
10. Fill in the handoff section of your chunk in the ledger
11. Set chunk status to NEEDS_REVIEW

Do NOT process more than this one chunk.
Do NOT modify DONE chunks.
If inputs are missing, stop and record an open_question in the handoff.
PROMPT
)"

ANTHROPIC_BASE_URL="http://127.0.0.1:${EXEC_PORT}" \
detour --port "$EXEC_PORT" -- --model red --dangerously-skip-permissions \
  --remote-control "${CHUNK_ID}_execution" \
  -p "$EXECUTOR_PROMPT" --max-turns 100 \
  > "$EXECUTOR_LOG" 2>&1

EXECUTOR_EXIT=$?
echo "Executor finished (exit ${EXECUTOR_EXIT})" >&2

# ── Phase 2: Verification loop ───────────────────────────────────────────────

echo "=== Phase 2: Verification — ${CHUNK_ID} ===" >&2

rm -f "$EVIDENCE"

/workspace/.work/review-chunk.sh "$CHUNK_ID" "$MAX_VERIFY" \
  > "$VERIFY_LOG" 2>&1

VERIFY_EXIT=$?
echo "Verification finished (exit ${VERIFY_EXIT})" >&2

# ── Phase 3: Summary ─────────────────────────────────────────────────────────

cat > "$SUMMARY" <<EOF
# Run Summary: ${CHUNK_ID}
Date: $(date -u +%Y-%m-%dT%H:%M:%SZ)

## Executor
- Exit code: ${EXECUTOR_EXIT}
- Log: ${EXECUTOR_LOG}

## Verification
- Exit code: ${VERIFY_EXIT}
- Log: ${VERIFY_LOG}
- Evidence: ${EVIDENCE}

## Result
EOF

if [ "$VERIFY_EXIT" -eq 0 ]; then
  echo "**PASS** — chunk implemented and verified." >> "$SUMMARY"
  echo "PASS: ${CHUNK_ID} — implemented and verified" >&2
else
  echo "**FAIL** — verification did not pass after ${MAX_VERIFY} attempts." >> "$SUMMARY"
  if [ -f "$EVIDENCE" ]; then
    echo "" >> "$SUMMARY"
    echo "## Completion Promise (last pass)" >> "$SUMMARY"
    grep "^All.*:" "$EVIDENCE" >> "$SUMMARY" 2>/dev/null || true
  fi
  echo "FAIL: ${CHUNK_ID} — see ${SUMMARY}" >&2
fi

# Append evidence inline for easy reading
if [ -f "$EVIDENCE" ]; then
  echo "" >> "$SUMMARY"
  echo "---" >> "$SUMMARY"
  echo "" >> "$SUMMARY"
  cat "$EVIDENCE" >> "$SUMMARY"
fi

exit "$VERIFY_EXIT"
