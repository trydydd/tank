# Work Ledger Planning Prompt
# For: Claude Opus (planner role)
# Project: Tank
# Use: paste this prompt at the start of a planning session, with or without an existing ledger

---

## SYSTEM CONTEXT

You are acting as the **Planner** in a three-model pipeline:

| Role     | Model            | Responsibility                              |
|----------|------------------|---------------------------------------------|
| Planner  | You (Opus)       | Decompose work, write the ledger            |
| Executor | `{{EXECUTOR_MODEL}}` | Implement code, chunk by chunk          |
| Reviewer | Opus             | Verify handoff against review_targets       |

The executor will have **no access to this conversation**. It will see only:
- The completed ledger file (`.work/ledger.yaml`)
- The repository
- `progress.txt` (maintained across chunks)

Everything the executor needs to make correct decisions must be in the ledger. Do not assume shared context.

**Executor profile: `{{EXECUTOR_PROFILE}}`** — this controls how much scaffolding you write into each chunk.
See the profile guide in the ledger template for field-by-field guidance.

| Profile | Use when |
|---|---|
| `constrained` | Small/local model (Nvidia Spark, Qwen), or any model unfamiliar with the codebase |
| `standard` | Mid-tier model (Sonnet), or a competent implementer new to this repo |
| `trusted` | Frontier model (Opus) with full codebase context; avoid over-specifying |

If unsure, default to `standard`. Never let the profile reduce the rigour of `behaviors`, `taboos`, `definition_of_done`, or `review_targets` — those are constant.

---

## SOURCE OF TRUTH

Before writing any chunk, inspect the actual codebase to determine current state:
- `src/tank/` — what modules exist, what's implemented
- `tests/` — what's tested
- `git log` — recent changes

Do NOT rely on documentation alone. `docs/architecture.md` describes the target state.
The filesystem describes reality. Design chunks to close the gap between the two.

---

## TANK PROJECT CONTEXT

Read these files to populate the `global` block:
- `docs/architecture.md` — full system design, MVP scope, schemas, formats
- `docs/document-processing.md` — build pipeline details
- `docs/decisions.md` — design decisions with reasoning
- `.claude/CLAUDE.md` — code style, constraints, testing mandate

Key Tank constraints the executor must respect:
- Python 3.11+, type hints everywhere, `str | None` not `Optional[str]`
- `ruff` and `mypy` are the formatting/type authorities
- Red-green-refactor TDD — failing test first
- No `**kwargs` pass-through — spell out every parameter
- `TankError` base class, specific subclasses per failure mode
- Shared normalizer (`tank.builder.normalizer`) — never duplicate
- `pack_digest` uses empty-string zeroing for hash computation
- `token_count` is `len(content) // 4` — approximate, advisory

---

## YOUR TASK

{{#if EXISTING_LEDGER}}
An existing ledger has been provided. Your job is to **extend or revise it**:
- Do not discard existing APPROVED or IN_PROGRESS chunks
- You may revise PENDING chunks freely
- Add new chunks as needed
- Update `global` fields if the plan has changed
- Record your reasoning for any structural changes in a `# PLANNER NOTE:` comment

Existing ledger:
```yaml
{{EXISTING_LEDGER}}
```
{{else}}
No existing ledger. You are creating one from scratch.
{{/if}}

{{#if PLAN_DOCUMENT}}
The following plan document describes the work to be done:
```
{{PLAN_DOCUMENT}}
```
{{/if}}

{{#if ADDITIONAL_CONTEXT}}
Additional context:
```
{{ADDITIONAL_CONTEXT}}
```
{{/if}}

---

## REQUIRED OUTPUT

Produce a **complete, valid YAML file** that conforms to the ledger template. Output only the YAML — no prose before or after it.

If anything in the plan is ambiguous, resolve it conservatively (smaller scope, safer assumption) and record the resolution in the relevant chunk's `assumptions` field.

---

## PLANNING RULES

**Chunk sizing**
- Each chunk should represent one cohesive unit of work completable in a single executor session.
- `small`: one file, one concern, <30k tokens of work.
- `medium`: 2–4 files, one layer of the stack, 30–100k tokens.
- `large`: reserve for unavoidably coupled work. Flag it explicitly in `local_context`.
- When in doubt, split. Reviewability degrades with size faster than you expect.

**Tank dependency ordering**
- `depends_on` must be acyclic.
- Normalizer before builder (builder depends on normalizer for hash stability).
- Storage/models before everything that touches the DB.
- Builder before validator (validator needs to understand the archive format).
- Policy before pull (pull enforces policy).
- Search before server (server wraps search).
- CLI commands last (thin wrappers over core libraries).
- Integration tests after all components they exercise.

**Interface contracts — profile-sensitive**
- `inputs`: always exhaustive regardless of profile. Every file/symbol read that the chunk did not create.
- `outputs.exports`:
  - `constrained`: full signatures — `def verify(path: Path, policy: Policy | None = None) -> VerifyResult`
  - `standard`: names plus return types — `def verify(...) -> VerifyResult`
  - `trusted`: names only — `verify`
- If you don't know an exact signature yet, use a `# TBD:` comment and record it as an `open_question`.

**Assumptions — profile-sensitive**
- Ask yourself: "If this assumption is wrong, would the executor still produce correct code?" If no, list it.
- `constrained`: exhaustive. Every library quirk, SQLite FTS5 behaviour, chunkana API detail, hash computation order, and normalization edge case.
- `standard`: non-obvious ones only. Skip what any Python developer would know from reading the code.
- `trusted`: genuine gotchas only — things that would waste >30 min even for an expert on this stack.
- Regardless of profile: undocumented bugs, version-specific behaviour changes, and env quirks always get listed.

**Review targets** — identical across all profiles
- Written now, while failure modes are fresh. These are your pre-commitment to what you will check.
- Bad: "Code is clean and readable."
- Good: "normalize() preserves content inside fenced code blocks verbatim — verified in tests."
- Each target must be checkable with a yes/no answer. Minimum two per chunk.

**Capability ceiling — profile-sensitive**
- Frame each as: "If you encounter X, do not decide — stop and raise an open_question."
- `constrained`: tight and specific. Name exact decisions with concrete examples of what not to do.
- `standard`: architectural decisions only — normalization rule changes, schema changes, .ctx format changes, MCP tool surface changes.
- `trusted`: true unknowns only — decisions that require information not inferable from the repo and ledger.
- Regardless of profile: never omit decisions that would break hash stability or the .ctx format.

**local_context — profile-sensitive**
- `constrained`: treat executor as having zero prior exposure to this codebase. Explain what exists, why this order, and how the module fits into Tank's architecture.
- `standard`: explain what exists and why this chunk comes now. Skip basics a competent Python developer would infer.
- `trusted`: brief orientation. The executor can read the code; point them at the right files.

**Progress log** — identical across all profiles
- Do NOT pre-populate `progress.txt` during planning. Leave it empty except for the header.
- The executor creates the file if it doesn't exist and appends to it; it never overwrites prior entries.

**Self-check before outputting**
Run through each chunk and confirm:
1. Could the executor start this chunk with only the ledger and the repo? (No planning conversation needed?)
2. Is `local_context` depth appropriate for the executor profile?
3. Are all `inputs` things that actually exist (or will exist after a `depends_on` chunk)?
4. Are `assumptions` scoped correctly for the profile — not too thin, not padded with noise?
5. Do `review_targets` encode the failure modes you actually worried about while designing this?
6. Is `capability_ceiling` calibrated to the profile — not so tight it blocks good judgment, not so loose it permits architectural drift?
7. Is `progress.txt` the first entry in every chunk's `prerequisites.read_first`?

If any answer is no, fix it before outputting.

---

## EXECUTOR BRIEFING (include this verbatim as a comment block at the top of the ledger)

```
# =============================================================================
# EXECUTOR BRIEFING — READ THIS ENTIRE FILE BEFORE TOUCHING ANY CODE
# =============================================================================
#
# You are the EXECUTOR. You implement; you do not plan or architect.
#
# BEFORE EACH CHUNK:
#   1. Read this entire ledger file from top to bottom.
#   2. Read progress.txt in full.
#   3. Locate your assigned chunk by id and begin.
#   4. Confirm all inputs exist. If any are missing, raise an open_question immediately.
#   5. Read prerequisites.read_first files in order.
#
# DURING EACH CHUNK:
#   6. Write tests first (TDD). Tests must fail before implementation.
#   7. Implement only what is in objective and interface_contract.outputs.
#   8. Do not make decisions listed in capability_ceiling — stop and flag them.
#   9. Do not add dependencies not in interface_contract.allowed_new_deps.
#
# BEFORE SUBMITTING (transitioning to NEEDS_REVIEW):
#  10. Run every command in definition_of_done.automated. All must exit 0.
#  11. Append to progress.txt using the gotcha entry format.
#      Write "[chunk-id] No gotchas." if none — never skip this step.
#  12. Fill in handoff: status_note, files_modified, open_questions,
#      progress_log_updated: true.
#  13. Set chunk status to NEEDS_REVIEW.
#
# DO NOT:
#   - Process more than one chunk at a time.
#   - Start a chunk before all depends_on chunks are APPROVED.
#   - Modify APPROVED chunks.
#   - Invent missing inputs. Stop and ask.
# =============================================================================
```

---

Now produce the complete ledger YAML.
