#!/usr/bin/env bash
set -euo pipefail

# Clavain Smoke Test Runner
# Dispatches agents via claude CLI to validate they load and respond correctly.
# Uses Max subscription (local), not API credits.
#
# Usage:
#   ./tests/smoke/run-smoke-tests.sh           # Run all smoke tests
#   ./tests/smoke/run-smoke-tests.sh --dry-run  # Just verify agent files exist

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$(dirname "$SCRIPT_DIR")")"

# Agent roster — must match smoke-prompt.md
AGENTS=(
  "agents/review/fd-quality.md"
  "agents/review/fd-architecture.md"
  "agents/review/fd-performance.md"
  "agents/review/fd-safety.md"
  "agents/review/plan-reviewer.md"
  "agents/review/agent-native-reviewer.md"
  "agents/research/best-practices-researcher.md"
  "agents/workflow/pr-comment-resolver.md"
)

echo "=== Clavain Smoke Tests ==="
echo "Project root: $PROJECT_ROOT"
echo ""

# Pre-check: verify all agent files exist
echo "Pre-check: verifying agent files..."
missing=0
for agent in "${AGENTS[@]}"; do
  if [[ ! -f "$PROJECT_ROOT/$agent" ]]; then
    echo "  MISSING: $agent"
    missing=$((missing + 1))
  fi
done

if [[ $missing -gt 0 ]]; then
  echo "FATAL: $missing agent file(s) missing. Cannot run smoke tests."
  exit 1
fi
echo "  All ${#AGENTS[@]} agent files present."
echo ""

if [[ "${1:-}" == "--dry-run" ]]; then
  echo "Dry run complete. All agent files verified."
  exit 0
fi

# Check claude CLI is available
if ! command -v claude &>/dev/null; then
  echo "FATAL: claude CLI not found in PATH."
  echo "Install Claude Code or run smoke tests from within a Claude Code session."
  exit 1
fi

# Run smoke tests via claude CLI
echo "Dispatching ${#AGENTS[@]} agents via claude CLI..."
echo "This will take 1-3 minutes."
echo ""

claude --print \
  --plugin-dir "$PROJECT_ROOT" \
  -p "$(cat "$SCRIPT_DIR/smoke-prompt.md")" \
  --max-turns 40

# Cleanup any artifact files agents wrote
rm -f "$PROJECT_ROOT"/docs/research/smoke-test-*.md 2>/dev/null || true
