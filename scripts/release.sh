#!/usr/bin/env bash
# Usage: scripts/release.sh [patch|minor|major]
# Runs pre-flight checks, bumps the version, commits, tags, and pushes.
# Pushing the tag triggers the GitHub Actions release workflow.
set -euo pipefail

BUMP="${1:-patch}"
VENV=".venv312"

RED='\033[0;31m'
GREEN='\033[0;32m'
CYAN='\033[0;36m'
RESET='\033[0m'

step() { echo -e "${CYAN}→ $*${RESET}"; }
ok()   { echo -e "${GREEN}✓ $*${RESET}"; }
die()  { echo -e "${RED}✗ $*${RESET}" >&2; exit 1; }

# ── pre-flight ────────────────────────────────────────────────────────────────

if [ ! -d "$VENV" ]; then
    die "Python 3.12 venv not found at $VENV. Run: python3.12 -m venv $VENV && $VENV/bin/pip install -e '.[all]'"
fi

step "Checking for a clean working tree..."
if [ -n "$(git status --porcelain)" ]; then
    die "Working tree is dirty. Commit or stash changes first."
fi
ok "Working tree is clean."

BRANCH=$(git rev-parse --abbrev-ref HEAD)
if [ "$BRANCH" != "main" ]; then
    echo -e "${RED}Warning: not on main (on '$BRANCH').${RESET} Continue? [y/N] "
    read -r REPLY
    [[ $REPLY =~ ^[Yy]$ ]] || exit 1
fi

# ── checks ────────────────────────────────────────────────────────────────────

step "ruff check..."
"$VENV/bin/ruff" check . || die "ruff check failed."
ok "ruff check passed."

step "ruff format --check..."
"$VENV/bin/ruff" format --check . || die "ruff format check failed. Run: $VENV/bin/ruff format ."
ok "ruff format passed."

step "mypy src/..."
"$VENV/bin/mypy" src/ || die "mypy failed."
ok "mypy passed."

step "pytest (unit tests)..."
"$VENV/bin/pytest" tests/ -q || die "Tests failed."
ok "Tests passed."

# ── bump ─────────────────────────────────────────────────────────────────────

CURRENT=$("$VENV/bin/bump-my-version" show current_version)
step "Bumping '$BUMP' version from $CURRENT..."
"$VENV/bin/bump-my-version" bump "$BUMP"
NEW=$("$VENV/bin/bump-my-version" show current_version)
ok "Version bumped: $CURRENT → $NEW"

# ── push ─────────────────────────────────────────────────────────────────────

step "Pushing commit and tag v$NEW..."
git push origin HEAD
git push origin "v$NEW"
ok "Pushed. GitHub Actions will run the release workflow."
echo ""
echo "  https://github.com/trydydd/tank/actions"
echo "  https://github.com/trydydd/tank/releases/tag/v$NEW"
