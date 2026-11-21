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
#   ./tests/run-tests.sh --affected BASE  # PR runs only: tests mapped to files changed since BASE;
#                                         # falls back to Tiers 1+2 when anything is unmapped.
#                                         # Never qualification evidence; the full suite stays
#                                         # required on the merge head.

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
FAILED=0

run_structural() {
  echo "=== Tier 1: Structural Tests (pytest) ==="
  # pytest-xdist: the structural suite is parallel-safe (2,822 tests, ~35 s on 16
  # workers vs ~280 s serial). CLAVAIN_TEST_WORKERS=0 forces a serial run;
  # the default is 16 (the count the timing-sensitive tests were validated at).
  cd "$PROJECT_ROOT/tests" && uv run pytest structural/ -v --tb=short -n "${CLAVAIN_TEST_WORKERS:-16}" || FAILED=1
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
  BATS_ARGS=("$PROJECT_ROOT/tests/shell/" --recursive)
  command -v parallel &>/dev/null && BATS_ARGS+=(--jobs 4)
  bats "${BATS_ARGS[@]}" || FAILED=1
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

run_affected() {
  local base="${1:?--affected needs a base ref}" sel mode
  sel="$(python3 -I "$PROJECT_ROOT/scripts/affected-checks.py" --event pull_request --base "$base")"
  mode="$(python3 -I -c 'import json,sys;print(json.load(sys.stdin)["mode"])' <<<"$sel")"
  echo "=== Affected-only selection: $mode ==="
  python3 -I -c 'import json,sys;d=json.load(sys.stdin);print(d["reason"]);print("\n".join(d["pytest"]+d["bats"]))' <<<"$sel"
  if [[ "$mode" == "full" ]]; then
    run_structural
    run_shell
    return
  fi
  mapfile -t py < <(python3 -I -c 'import json,sys;print("\n".join(json.load(sys.stdin)["pytest"]))' <<<"$sel")
  mapfile -t bt < <(python3 -I -c 'import json,sys;print("\n".join(json.load(sys.stdin)["bats"]))' <<<"$sel")
  if [[ -n "${py[*]:-}" ]]; then
    (cd "$PROJECT_ROOT" && uv run --project tests pytest "${py[@]}" -v --tb=short -n 0) || FAILED=1
  fi
  if [[ -n "${bt[*]:-}" ]]; then
    (cd "$PROJECT_ROOT" && bats "${bt[@]}") || FAILED=1
  fi
}

case "${1:-}" in
  --affected)
    run_affected "${2:-}"
    ;;
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
    if [[ "$FAILED" -eq 0 ]]; then
      echo "Tiers 1+2 passed. Run with --smoke for Tier 3 or --all for everything."
    else
      echo "Tiers 1+2 FAILED (exit $FAILED). See failures above."
    fi
    ;;
esac

exit $FAILED
