#!/usr/bin/env bash
set -euo pipefail

CHUNK_ID="${1:?Usage: review-chunk.sh <chunk-id>}"
MAX_PASSES="${2:-3}"
TEMPLATE="/workspace/.work/review-prompt-template.md"
EVIDENCE="/workspace/.work/handoffs/${CHUNK_ID}-verification.md"

if [ ! -f "$TEMPLATE" ]; then
  echo "ERROR: Review template not found at $TEMPLATE" >&2
  exit 1
fi

PROMPT="$(sed "s/{{CHUNK_ID}}/${CHUNK_ID}/g" "$TEMPLATE")"

# Derive a unique proxy port to avoid collisions with parent or sibling detour processes
REVIEW_PORT=$(( 18000 + $(printf '%s' "${CHUNK_ID}_validation" | cksum | cut -d' ' -f1) % 1000 ))

for pass in $(seq 1 "$MAX_PASSES"); do
  echo "=== Verification pass ${pass}/${MAX_PASSES} ===" >&2

  ANTHROPIC_BASE_URL="http://127.0.0.1:${REVIEW_PORT}" \
  detour --port "$REVIEW_PORT" -- --model red --dangerously-skip-permissions \
    --remote-control "${CHUNK_ID}_validation" \
    -p "$PROMPT" --max-turns 100

  if [ ! -f "$EVIDENCE" ]; then
    echo "FAIL: verification evidence file not written (pass ${pass})" >&2
    if [ "$pass" -eq "$MAX_PASSES" ]; then
      exit 1
    fi
    continue
  fi

  if ! grep -q "^All.*: NO" "$EVIDENCE"; then
    echo "PASS: all completion promise lines satisfied (pass ${pass})" >&2
    exit 0
  fi

  echo "Issues found on pass ${pass}:" >&2
  grep "^All.*: NO" "$EVIDENCE" >&2

  if [ "$pass" -eq "$MAX_PASSES" ]; then
    echo "FAIL: verification still failing after ${MAX_PASSES} passes — see $EVIDENCE" >&2
    exit 1
  fi

  # Remove stale evidence so next pass starts clean
  rm -f "$EVIDENCE"
done
