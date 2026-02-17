#!/usr/bin/env bash
set -euo pipefail

# Clavain Smoke Test Runner
# Dispatches agents via claude CLI to validate they load and respond correctly.
# Uses Max subscription (local), not API credits.
#
# Usage:
#   ./tests/smoke/run-smoke-tests.sh           # Run all smoke tests
#   ./tests/smoke/run-smoke-tests.sh --dry-run  # Just verify agent/command files exist

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$(dirname "$SCRIPT_DIR")")"

# Agent roster — must match smoke-prompt.md (all 17 agents)
AGENTS=(
  # Review (10)
  "agents/review/fd-quality.md"
  "agents/review/fd-architecture.md"
  "agents/review/fd-performance.md"
  "agents/review/fd-safety.md"
  "agents/review/fd-correctness.md"
  "agents/review/fd-user-product.md"
  "agents/review/plan-reviewer.md"
  "agents/review/agent-native-reviewer.md"
  "agents/review/data-migration-expert.md"
  "agents/review/fd-game-design.md"
  # Research (5)
  "agents/research/best-practices-researcher.md"
  "agents/research/framework-docs-researcher.md"
  "agents/research/git-history-analyzer.md"
  "agents/research/learnings-researcher.md"
  "agents/research/repo-research-analyst.md"
  # Workflow (2)
  "agents/workflow/pr-comment-resolver.md"
  "agents/workflow/bug-reproduction-validator.md"
)

# Command roster — must match smoke-prompt.md
COMMANDS=(
  "commands/help.md"
  "commands/doctor.md"
  "commands/changelog.md"
  "commands/brainstorm.md"
  "commands/quality-gates.md"
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

# Pre-check: verify all command files exist
echo "Pre-check: verifying command files..."
for cmd in "${COMMANDS[@]}"; do
  if [[ ! -f "$PROJECT_ROOT/$cmd" ]]; then
    echo "  MISSING: $cmd"
    missing=$((missing + 1))
  fi
done

if [[ $missing -gt 0 ]]; then
  echo "FATAL: $missing file(s) missing. Cannot run smoke tests."
  exit 1
fi
echo "  All ${#COMMANDS[@]} command files present."
echo ""

if [[ "${1:-}" == "--dry-run" ]]; then
  echo "Dry run complete. All ${#AGENTS[@]} agent + ${#COMMANDS[@]} command files verified."
  exit 0
fi

# Check for --include-interserve flag
INCLUDE_INTERSERVE=false
for arg in "$@"; do
  if [[ "$arg" == "--include-interserve" ]]; then
    INCLUDE_INTERSERVE=true
  fi
done

# Check claude CLI is available
if ! command -v claude &>/dev/null; then
  echo "FATAL: claude CLI not found in PATH."
  echo "Install Claude Code or run smoke tests from within a Claude Code session."
  exit 1
fi

# Set up interserve flag if --include-interserve
if [[ "$INCLUDE_INTERSERVE" == true ]]; then
  mkdir -p "$PROJECT_ROOT/.claude"
  date -Iseconds > "$PROJECT_ROOT/.claude/clodex-toggle.flag"
  echo "Interserve behavioral test enabled."
  echo ""
fi

# Run smoke tests via claude CLI
echo "Dispatching ${#AGENTS[@]} agents + ${#COMMANDS[@]} command tests via claude CLI..."
echo "This will take 2-4 minutes."
echo ""

claude --print \
  --plugin-dir "$PROJECT_ROOT" \
  -p "$(cat "$SCRIPT_DIR/smoke-prompt.md")" \
  --max-turns 60

# Cleanup
rm -f "$PROJECT_ROOT"/docs/research/smoke-test-*.md 2>/dev/null || true
if [[ "$INCLUDE_INTERSERVE" == true ]]; then
  rm -f "$PROJECT_ROOT/.claude/clodex-toggle.flag"
  echo ""
  echo "Interserve flag cleaned up."
fi
