#!/usr/bin/env bash
set -euo pipefail

# Clavain Test Runner — Tier 1 + Tier 2 (+ optionally Tier 3)
#
# Usage:
#   ./tests/run-tests.sh                  # Run Tiers 1+2
#   ./tests/run-tests.sh --structural     # Tier 1 only (pytest)
#   ./tests/run-tests.sh --shell          # Tier 2 only (bats)
#   ./tests/run-tests.sh --smoke          # Tier 3 only (claude subagents)
#   ./tests/run-tests.sh --all            # All three tiers

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
FAILED=0

run_structural() {
  echo "=== Tier 1: Structural Tests (pytest) ==="
  cd "$PROJECT_ROOT/tests" && uv run pytest structural/ -v --tb=short || FAILED=1
  cd "$PROJECT_ROOT"
}

run_shell() {
  echo ""
  echo "=== Tier 2: Shell Tests (bats) ==="
  if ! command -v bats &>/dev/null; then
    echo "ERROR: bats not found. Install with: sudo apt-get install bats"
    FAILED=1
    return
  fi
  bats "$PROJECT_ROOT/tests/shell/" --recursive || FAILED=1
}

run_smoke() {
  echo ""
  echo "=== Tier 3: Smoke Tests (claude subagents) ==="
  if ! command -v claude &>/dev/null; then
    echo "ERROR: claude CLI not found. Run from within a Claude Code session."
    FAILED=1
    return
  fi
  "$PROJECT_ROOT/tests/smoke/run-smoke-tests.sh" || FAILED=1
}

case "${1:-}" in
  --structural)
    run_structural
    ;;
  --shell)
    run_shell
    ;;
  --smoke)
    run_smoke
    ;;
  --all)
    run_structural
    run_shell
    run_smoke
    ;;
  *)
    run_structural
    run_shell
    echo ""
    echo "Tiers 1+2 passed. Run with --smoke for Tier 3 or --all for everything."
    ;;
esac

exit $FAILED
