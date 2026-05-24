# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- `auto-release.yml` — triggers on push to `main` when `pyproject.toml` changes; compares the version against the previous commit and, if it bumped, runs the full check+build pipeline and creates the GitHub release via the API (no PAT or branch-protection bypass needed)

### Changed
- `cut-release.yml` — repurposed: now pushes a `release/vX.Y.Z` branch and opens a PR instead of pushing directly to `main`; fixes a latent bug where `GITHUB_TOKEN`-authenticated tag pushes silently failed to trigger `release.yml` due to GitHub's loop-prevention policy

## [0.1.1] - 2026-05-23

### Added
- CI workflow (lint, typecheck, test) on all pushes and pull requests
- Release workflow: runs full test suite (including network tests), builds wheel/sdist, fetches docs source, and publishes a GitHub release with all artifacts
- `cut-release.yml` — manually triggered GitHub Actions workflow (Actions → Cut Release → Run workflow); accepts `patch / minor / major`, runs pre-flight checks, bumps version, commits, and pushes the tag to trigger the Release workflow
- Network integration test for the full FastMCP build + query pipeline
- `bump-my-version` in dev dependencies; `[tool.bumpversion]` config in `pyproject.toml`
- `scripts/release.sh` — local equivalent of Cut Release for dev machines with a 3.12 venv

### Fixed
- `pack_digest` verification: ZIP entry timestamps are now pinned to a fixed epoch (`2021-08-08`) so the archive is reproducible across machines and the digest can be independently verified
- Ruff lint errors (unused imports and variables)
- MyPy errors in builder module

### Changed
- ZIP epoch documented in architecture docs and `CLAUDE.md`
- `ruff` pinned to `0.15.8` to prevent formatting drift across CI runs
- Packs removed from the repository; built and published as release artifacts instead

## [0.1.0] - 2025-01-01

### Added
- Initial MVP: `tank build`, `tank query`, `tank inspect`, `tank verify`, `tank pull`
- SQLite FTS5 search backend with WAL mode
- `.ctx` pack format: deterministic ZIP archive with `manifest.json` and per-chunk files
- `pack_digest` integrity field in manifest
- MCP server (`tank.server`) exposing `query-docs` and `resolve-library-id` tools
- Policy engine for source and chunk filtering
- HTML → text conversion via basic tag removal
- Heuristic chunk summarisation (first sentence / leading signature)
