#!/usr/bin/env bash
set -euo pipefail

# Day-1 Workflow Smoke Test — Phase 1-2 (infrastructure + skill presence)
# Tests sprint library functions and verifies skill/command file structure.

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
CLAVAIN_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

pass() { printf '  PASS: %s\n' "$1"; PASSED=$((PASSED + 1)); }
fail() { printf '  FAIL: %s\n' "$1"; FAILED=$((FAILED + 1)); }
PASSED=0
FAILED=0

echo "=== Day-1 Workflow Smoke Test ==="
echo "Clavain root: $CLAVAIN_ROOT"
echo ""

# --- Phase 1: Infrastructure ---
echo "--- Phase 1: Infrastructure ---"

# 1. Sprint library loads
export SPRINT_LIB_PROJECT_DIR="$CLAVAIN_ROOT"
if source "$CLAVAIN_ROOT/hooks/lib-sprint.sh" 2>/dev/null; then
    pass "sprint library loads"
else
    fail "sprint library loads"
fi

# 2. Complexity classification
if command -v sprint_classify_complexity &>/dev/null; then
    # Function exists (may not have beads to test with)
    pass "complexity classification function exists"
else
    fail "complexity classification function missing"
fi

# 3. Sprint CRUD functions exist
missing=""
for fn in sprint_create sprint_read_state sprint_set_artifact sprint_record_phase_completion sprint_claim sprint_release; do
    if ! command -v "$fn" &>/dev/null; then
        missing="$missing $fn"
    fi
done
if [[ -z "$missing" ]]; then
    pass "sprint CRUD functions exist"
else
    fail "sprint CRUD functions missing:$missing"
fi

# 4. Checkpoint functions exist
missing=""
for fn in checkpoint_write checkpoint_read checkpoint_validate checkpoint_clear checkpoint_completed_steps; do
    if ! command -v "$fn" &>/dev/null; then
        missing="$missing $fn"
    fi
done
if [[ -z "$missing" ]]; then
    pass "checkpoint functions exist"
else
    fail "checkpoint functions missing:$missing"
fi

# 5. Gate enforcement function exists
if command -v enforce_gate &>/dev/null; then
    pass "enforce_gate function exists"
else
    fail "enforce_gate function missing"
fi

# 6. Phase advancement — check lib-gates.sh loads
export GATES_PROJECT_DIR="$CLAVAIN_ROOT"
if source "$CLAVAIN_ROOT/hooks/lib-gates.sh" 2>/dev/null && command -v advance_phase &>/dev/null; then
    pass "advance_phase function exists"
else
    fail "advance_phase function missing"
fi

# 7. Sprint advance function exists
if command -v sprint_advance &>/dev/null; then
    pass "sprint_advance function exists"
else
    fail "sprint_advance function missing"
fi

echo ""
echo "--- Phase 2: Skill Presence ---"

# 8. Required skills exist
missing=""
for skill in brainstorming writing-plans executing-plans landing-a-change; do
    skill_path="$CLAVAIN_ROOT/skills/$skill/SKILL.md"
    if [[ ! -f "$skill_path" ]]; then
        missing="$missing $skill"
    fi
done
if [[ -z "$missing" ]]; then
    pass "required skills exist (brainstorming, writing-plans, executing-plans, landing-a-change)"
else
    fail "required skills missing:$missing"
fi

# 9. Required commands exist
missing=""
for cmd in sprint brainstorm write-plan work quality-gates; do
    cmd_path="$CLAVAIN_ROOT/commands/$cmd.md"
    if [[ ! -f "$cmd_path" ]]; then
        missing="$missing $cmd"
    fi
done
if [[ -z "$missing" ]]; then
    pass "required commands exist (sprint, brainstorm, write-plan, work, quality-gates)"
else
    fail "required commands missing:$missing"
fi

# 10. Sprint command references all phases
sprint_cmd="$CLAVAIN_ROOT/commands/sprint.md"
missing=""
for phase in brainstorm strategy write-plan flux-drive work quality-gates; do
    if ! grep -qi "$phase" "$sprint_cmd" 2>/dev/null; then
        missing="$missing $phase"
    fi
done
if [[ -z "$missing" ]]; then
    pass "sprint command references all workflow phases"
else
    fail "sprint command missing phase references:$missing"
fi

echo ""
echo "=== Results ==="
echo "Passed: $PASSED"
echo "Failed: $FAILED"
TOTAL=$((PASSED + FAILED))
echo "Total: $TOTAL"

if [[ $FAILED -gt 0 ]]; then
    echo ""
    echo "SMOKE TEST FAILURE: $FAILED test(s) failed."
    exit 1
fi

echo ""
echo "All Day-1 workflow infrastructure tests passed."
