# Tank — Release Procedure

## Versioning Policy

Tank follows [Semantic Versioning](https://semver.org/).

| Component | When to increment |
|---|---|
| **Major** (x.0.0) | Breaking changes to the `.ctx` pack format, the MCP tool interface, or the CLI contract |
| **Minor** (0.x.0) | New features, new CLI commands, new MCP tools, new pack fields (backward-compatible) |
| **Patch** (0.0.x) | Bug fixes, documentation corrections, dependency updates that don't change behaviour |

Pre-release identifiers: `v0.2.0-alpha.1`, `v0.2.0-rc.1`. Tags without a pre-release
identifier trigger the full release workflow.

---

## Pre-Release Checklist

Work through this list in order. Do not tag until all items are complete.

### 1. Known bugs and gaps

Review `docs/todo.md` and confirm every v{N} item is resolved or explicitly deferred.

The following bugs were open when v0.1.0 was tagged and are deferred to v0.1.1:

- [ ] `src/tank/storage/db.py:121-126` — page ID foreign key integrity on import
- [ ] `src/tank/search/fts.py:76` — silent exception swallowing on search failure
- [ ] `src/tank/cli/pull.py:39` — hardcoded `doc_version_status="imported"`
- [ ] `src/tank/server.py` — `max_tokens` parameter accepted but not implemented

### 2. Tests pass cleanly

```bash
ruff check .
ruff format --check .
mypy src/
pytest tests/
```

All four must exit 0. Do not tag with failures.

### 3. Performance baseline captured

Run the token overhead benchmark and commit the result (see Performance Baselines below):

```bash
pytest tests/benchmarks/ --benchmark -v -s
cp tests/benchmarks/results/latest.json tests/benchmarks/results/v{VERSION}.json
git add tests/benchmarks/results/v{VERSION}.json
git commit -m "chore: capture v{VERSION} benchmark baseline"
```

### 4. Version bumped

Update the version string in two places and confirm they match:

- `pyproject.toml` → `[project] version`
- `src/tank/__init__.py` → `__version__`

### 5. README reflects reality

Confirm the README quickstart works end-to-end with the current code.
The README must not say "implementation is beginning" once any release ships.

### 6. CHANGELOG entry written

Add a section to `CHANGELOG.md` (create it for v0.1.0). Entries should follow
[Keep a Changelog](https://keepachangelog.com/) format.

---

## Release Procedure

```bash
# 1. Ensure main branch is clean and tests pass
git checkout main
git pull origin main
pytest tests/
ruff check . && mypy src/

# 2. Capture performance baseline (see above)

# 3. Bump version
#    Edit pyproject.toml and src/tank/__init__.py

# 4. Commit the version bump and baseline together
git add pyproject.toml src/tank/__init__.py tests/benchmarks/results/v{VERSION}.json
git commit -m "Release v{VERSION}"

# 5. Tag
git tag -a v{VERSION} -m "v{VERSION}"

# 6. Push (tag push triggers the release workflow)
git push origin main
git push origin v{VERSION}

# 7. Verify CI
#    Watch the release workflow at .github/workflows/release.yml.
#    It runs the full test suite, builds wheel + sdist, builds .ctx packs,
#    and creates the GitHub Release with all artifacts attached.

# 8. Publish to PyPI (currently manual — no twine step in CI yet)
pip install build twine
python -m build
twine upload dist/tank-{VERSION}*
```

---

## Release Artifacts

Each GitHub Release contains the following files, attached automatically by
`.github/workflows/release.yml`:

| Artifact | Description |
|---|---|
| `tank-{VERSION}-py3-none-any.whl` | Installable wheel. `pip install tank` or direct URL install. |
| `tank-{VERSION}.tar.gz` | Source distribution. Required for downstream repackaging (Debian, Homebrew, etc.). |
| `fastmcp@{VERSION}.ctx` | Pre-built documentation pack for FastMCP, built from `llms-full.txt` in CI. |

### Adding packs to a release

The `build packs` step in `release.yml` builds one pack per library listed in the
workflow. To add a library for v0.2.0:

1. Confirm the library publishes `llms-full.txt`.
2. Add a `curl` + `tank build` line to the `Build packs` step in `release.yml`.
3. The `.ctx` file is picked up by the `files:` glob automatically.

### Artifact naming convention

`.ctx` packs are named `{name}@{version}.ctx` where `version` is the *library*
version, not the Tank version. Example: `fastmcp@3.3.0.ctx` built by Tank v0.2.0.

---

## Performance Baselines

Token overhead benchmarks are pinned to each release to track regressions and
improvements over time. Results are committed to `tests/benchmarks/results/`.

### Running the benchmark

```bash
pytest tests/benchmarks/ --benchmark -v -s
```

Output is printed to stdout and written to `tests/benchmarks/results/latest.json`.

### What is measured

| Metric | Description |
|---|---|
| Schema tokens | Token cost of `query-docs` + `resolve-deps` tool definitions |
| Schema % of context | Schema tokens as a fraction of 200K and 128K context windows |
| Summary response, N=5/10/20 | Tokens returned by `query-docs` at `detail="summary"` |
| Full response, N=5/10/20 | Tokens returned by `query-docs` at `detail="full"` |
| Progressive disclosure saving | `(naive_full_n20 − two_step_total) / naive_full_n20` |

The two-step pattern (step 1: summary scan → step 2: targeted full fetch of top 3)
is Tank's primary token efficiency claim. The saving % is the headline number.

### Token counter

Benchmarks use `len(str) // 4` — the same approximation used throughout Tank's
codebase. This is ±15% accurate for English prose. For exact cl100k counts,
install `tiktoken` and replace `_count_tokens` in `tests/benchmarks/test_token_overhead.py`.
If you switch counters between releases, note it in the benchmark result's
`token_counter` field.

### Interpreting deltas

Compare `v{N}.json` against `v{N-1}.json` before tagging. Expected behaviour:

| Change | Schema tokens | Summary response | Full response | Progressive saving |
|---|---|---|---|---|
| Add a new MCP tool | Increases | Unchanged | Unchanged | Unchanged |
| Add a field to `_to_dict` | Unchanged | Increases | Increases | May decrease |
| Improve FTS ranking (fewer irrelevant results) | Unchanged | Decreases | Decreases | Increases |
| Increase default `limit` in `search()` | Unchanged | Increases | Increases | Varies |

**Regression thresholds** (guidelines, not hard rules):

- Schema tokens increase by >20% → investigate before shipping; a new tool should
  be justified in the changelog.
- Progressive disclosure saving drops below 40% → review whether `_to_dict` has
  grown or whether FTS result quality has degraded.
- Summary tokens/result increase by >15% → a field has been added to the summary
  response; confirm this was intentional.

### Result file format

```json
{
  "timestamp": "2026-05-20T12:00:00+00:00",
  "git_commit": "abc1234",
  "tank_version": "0.1.0",
  "token_counter": "len_div_4",
  "corpus": {
    "chunks": 20,
    "avg_summary_chars": 112,
    "avg_content_chars": 1640
  },
  "schema": {
    "total_tokens": 245,
    "tools": [
      {"name": "query-docs", "tokens": 170, "chars": 680},
      {"name": "resolve-deps", "tokens": 75, "chars": 301}
    ],
    "pct_of_200k_context": 0.122,
    "pct_of_128k_context": 0.191
  },
  "responses": {
    "summary_n5":  {"tokens": ..., "actual_results": 5,  "tokens_per_result": ...},
    "summary_n10": {"tokens": ..., "actual_results": 10, "tokens_per_result": ...},
    "summary_n20": {"tokens": ..., "actual_results": 20, "tokens_per_result": ...},
    "full_n5":     {"tokens": ..., "actual_results": 5,  "tokens_per_result": ...},
    "full_n10":    {"tokens": ..., "actual_results": 10, "tokens_per_result": ...},
    "full_n20":    {"tokens": ..., "actual_results": 20, "tokens_per_result": ...}
  },
  "progressive_disclosure": {
    "step1_summary_all_tokens": ...,
    "step2_full_top3_tokens": ...,
    "total_tokens": ...,
    "vs_naive_full_n20_tokens": ...,
    "saving_pct": 58.3
  }
}
```

---

## Post-Release Steps

1. **Verify PyPI**: `pip install tank=={VERSION}` in a clean virtualenv. Run
   `tank --version` and confirm it prints the correct version.

2. **Verify GitHub Release**: Check that all expected artifacts are attached —
   wheel, sdist, and all `.ctx` packs.

3. **Update README badge**: If the README has a PyPI version badge, it updates
   automatically. Confirm it shows the new version within ~5 minutes.

4. **Announce** (when applicable): Post to the project's discussion forum,
   Discord, or mailing list. Link the GitHub Release, not the tag.

5. **Open milestone for next version**: Create a GitHub milestone for
   v{NEXT} and move any deferred issues into it.

---

## Hotfix Procedure

For urgent patch releases on an already-shipped version:

```bash
# Branch from the release tag
git checkout -b hotfix/v{VERSION}.{PATCH} v{VERSION}

# Make the fix, run tests
pytest tests/

# Bump patch version in pyproject.toml and __init__.py
# Tag and push
git tag -a v{VERSION}.{PATCH} -m "v{VERSION}.{PATCH}"
git push origin hotfix/v{VERSION}.{PATCH}
git push origin v{VERSION}.{PATCH}

# Open a PR to merge the fix back to main
```

Do not run the performance benchmark for hotfix releases unless the fix
touches search, the MCP server, or response serialisation.
