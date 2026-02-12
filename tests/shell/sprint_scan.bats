#!/usr/bin/env bats
# Tests for hooks/sprint-scan.sh scanner library

setup() {
    load test_helper

    # Create isolated temp project directory for each test
    TEST_PROJECT="$(mktemp -d)"
    export SPRINT_PROJECT_DIR="$TEST_PROJECT"

    # Reset the double-source guard so we can re-source in each test
    unset _SPRINT_SCAN_LOADED
    source "$HOOKS_DIR/sprint-scan.sh"
}

teardown() {
    rm -rf "$TEST_PROJECT"
}

# ─── sprint_check_handoff ────────────────────────────────────────────

@test "sprint_check_handoff: returns 1 when HANDOFF.md missing" {
    run sprint_check_handoff
    assert_failure
}

@test "sprint_check_handoff: returns 0 when HANDOFF.md present" {
    touch "$TEST_PROJECT/HANDOFF.md"
    run sprint_check_handoff
    assert_success
    assert_output "$TEST_PROJECT/HANDOFF.md"
}

# ─── sprint_count_orphaned_brainstorms ───────────────────────────────

@test "sprint_count_orphaned_brainstorms: returns 0 with no brainstorms dir" {
    run sprint_count_orphaned_brainstorms
    assert_output "0"
}

@test "sprint_count_orphaned_brainstorms: returns 0 when all matched to plans" {
    mkdir -p "$TEST_PROJECT/docs/brainstorms" "$TEST_PROJECT/docs/plans"
    touch "$TEST_PROJECT/docs/brainstorms/2026-02-10-auth-system-brainstorm.md"
    touch "$TEST_PROJECT/docs/plans/2026-02-10-auth-system.md"
    run sprint_count_orphaned_brainstorms
    assert_output "0"
}

@test "sprint_count_orphaned_brainstorms: counts unmatched brainstorms" {
    mkdir -p "$TEST_PROJECT/docs/brainstorms" "$TEST_PROJECT/docs/plans"
    touch "$TEST_PROJECT/docs/brainstorms/2026-02-10-auth-system-brainstorm.md"
    touch "$TEST_PROJECT/docs/brainstorms/2026-02-10-caching-brainstorm.md"
    touch "$TEST_PROJECT/docs/plans/2026-02-10-auth-system.md"
    run sprint_count_orphaned_brainstorms
    assert_output "1"
}

@test "sprint_count_orphaned_brainstorms: matches against PRDs too" {
    mkdir -p "$TEST_PROJECT/docs/brainstorms" "$TEST_PROJECT/docs/prds"
    touch "$TEST_PROJECT/docs/brainstorms/2026-02-10-auth-system-brainstorm.md"
    touch "$TEST_PROJECT/docs/prds/auth-system-prd.md"
    run sprint_count_orphaned_brainstorms
    assert_output "0"
}

# ─── sprint_find_incomplete_plans ────────────────────────────────────

@test "sprint_find_incomplete_plans: returns 1 with no plans dir" {
    run sprint_find_incomplete_plans
    assert_failure
}

@test "sprint_find_incomplete_plans: shows incomplete plan" {
    mkdir -p "$TEST_PROJECT/docs/plans"
    cat > "$TEST_PROJECT/docs/plans/2026-02-10-test.md" <<'PLAN'
# Test Plan
- [x] Step 1
- [ ] Step 2
- [ ] Step 3
PLAN
    run sprint_find_incomplete_plans
    assert_success
    assert_output "2026-02-10-test.md: 1/3 complete"
}

@test "sprint_find_incomplete_plans: silent when all complete" {
    mkdir -p "$TEST_PROJECT/docs/plans"
    cat > "$TEST_PROJECT/docs/plans/2026-02-10-done.md" <<'PLAN'
# Done Plan
- [x] Step 1
- [x] Step 2
PLAN
    run sprint_find_incomplete_plans
    assert_failure
    assert_output ""
}

# ─── sprint_check_strategy_gap ───────────────────────────────────────

@test "sprint_check_strategy_gap: returns 1 with no brainstorms" {
    run sprint_check_strategy_gap
    assert_failure
}

@test "sprint_check_strategy_gap: returns 0 when brainstorms but no PRDs" {
    mkdir -p "$TEST_PROJECT/docs/brainstorms"
    touch "$TEST_PROJECT/docs/brainstorms/2026-02-10-idea-brainstorm.md"
    run sprint_check_strategy_gap
    assert_success
}

@test "sprint_check_strategy_gap: returns 1 when PRDs exist" {
    mkdir -p "$TEST_PROJECT/docs/brainstorms" "$TEST_PROJECT/docs/prds"
    touch "$TEST_PROJECT/docs/brainstorms/2026-02-10-idea-brainstorm.md"
    touch "$TEST_PROJECT/docs/prds/idea-prd.md"
    run sprint_check_strategy_gap
    assert_failure
}

# ─── sprint_brief_scan ──────────────────────────────────────────────

@test "sprint_brief_scan: empty when clean" {
    run sprint_brief_scan
    assert_success
    assert_output ""
}

@test "sprint_brief_scan: detects HANDOFF.md" {
    touch "$TEST_PROJECT/HANDOFF.md"
    run sprint_brief_scan
    assert_success
    [[ "$output" == *"HANDOFF.md found"* ]]
}

@test "sprint_brief_scan: suppresses single orphaned brainstorm" {
    mkdir -p "$TEST_PROJECT/docs/brainstorms"
    touch "$TEST_PROJECT/docs/brainstorms/2026-02-10-lonely-brainstorm.md"
    run sprint_brief_scan
    # Should NOT mention brainstorms (threshold is ≥2)
    [[ "$output" != *"brainstorms without matching"* ]]
}

@test "sprint_brief_scan: shows multiple orphaned brainstorms" {
    mkdir -p "$TEST_PROJECT/docs/brainstorms"
    touch "$TEST_PROJECT/docs/brainstorms/2026-02-10-idea-one-brainstorm.md"
    touch "$TEST_PROJECT/docs/brainstorms/2026-02-10-idea-two-brainstorm.md"
    run sprint_brief_scan
    [[ "$output" == *"2 brainstorms without matching plans"* ]]
}
