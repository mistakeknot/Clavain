#!/usr/bin/env bats
# Tests for hooks/lib-gates.sh and hooks/lib-discovery.sh shim behavior.
# Verifies that when interphase is NOT installed, shims provide no-op stubs.
# Verifies that when interphase IS installed, shims delegate correctly.

setup() {
    load test_helper

    # Create isolated temp project directory for each test
    TEST_PROJECT="$(mktemp -d)"
    export HOME="$TEST_PROJECT"
    export GATES_PROJECT_DIR="$TEST_PROJECT"
    export DISCOVERY_PROJECT_DIR="$TEST_PROJECT"

    # Ensure interphase is NOT found (empty plugin cache)
    mkdir -p "$TEST_PROJECT/.claude/plugins/cache"
    export INTERPHASE_ROOT=""

    # Reset the double-source guards so we can re-source in each test
    unset _GATES_LOADED _PHASE_LOADED _DISCOVERY_LOADED
}

teardown() {
    rm -rf "$TEST_PROJECT"
}

# ─── Gates shim: no-op mode ─────────────────────────────────────────

@test "gates shim: sources without errors when interphase absent" {
    run source "$HOOKS_DIR/lib-gates.sh"
    assert_success
}

@test "gates shim: provides CLAVAIN_PHASES array" {
    source "$HOOKS_DIR/lib-gates.sh"
    [[ ${#CLAVAIN_PHASES[@]} -eq 8 ]]
    [[ "${CLAVAIN_PHASES[0]}" == "brainstorm" ]]
    [[ "${CLAVAIN_PHASES[-1]}" == "done" ]]
}

@test "gates shim: is_valid_transition returns failure (no transitions defined)" {
    source "$HOOKS_DIR/lib-gates.sh"
    run is_valid_transition "brainstorm" "brainstorm-reviewed"
    assert_failure
}

@test "gates shim: check_phase_gate returns success (fail-safe)" {
    source "$HOOKS_DIR/lib-gates.sh"
    run check_phase_gate "Test-001" "brainstorm"
    assert_success
}

@test "gates shim: advance_phase returns success (no-op)" {
    source "$HOOKS_DIR/lib-gates.sh"
    run advance_phase "Test-001" "brainstorm" "Test"
    assert_success
}

@test "gates shim: phase_get_with_fallback returns empty" {
    source "$HOOKS_DIR/lib-gates.sh"
    run phase_get_with_fallback "Test-001"
    assert_success
    assert_output ""
}

@test "gates shim: phase_set returns success (no-op)" {
    source "$HOOKS_DIR/lib-gates.sh"
    run phase_set "Test-001" "brainstorm" "Test"
    assert_success
}

@test "gates shim: phase_get returns empty" {
    source "$HOOKS_DIR/lib-gates.sh"
    run phase_get "Test-001"
    assert_success
    assert_output ""
}

@test "gates shim: phase_infer_bead returns empty" {
    source "$HOOKS_DIR/lib-gates.sh"
    run phase_infer_bead "/some/file.md"
    assert_success
    assert_output ""
}

# ─── Discovery shim: no-op mode ─────────────────────────────────────

@test "discovery shim: sources without errors when interphase absent" {
    run source "$HOOKS_DIR/lib-discovery.sh"
    assert_success
}

@test "discovery shim: discovery_scan_beads returns DISCOVERY_UNAVAILABLE" {
    source "$HOOKS_DIR/lib-discovery.sh"
    run discovery_scan_beads
    assert_success
    assert_output "DISCOVERY_UNAVAILABLE"
}

@test "discovery shim: infer_bead_action returns brainstorm" {
    source "$HOOKS_DIR/lib-discovery.sh"
    run infer_bead_action "Test-001" "open"
    assert_success
    assert_output "brainstorm|"
}

@test "discovery shim: discovery_log_selection returns success (no-op)" {
    source "$HOOKS_DIR/lib-discovery.sh"
    run discovery_log_selection "Test-001" "execute" "true"
    assert_success
}

# ─── Gates shim: delegation mode ─────────────────────────────────────

@test "gates shim: delegates when INTERPHASE_ROOT is set" {
    # Point to interphase repo as if it were installed
    export INTERPHASE_ROOT="/root/projects/interphase"
    [[ -d "$INTERPHASE_ROOT/hooks" ]] || skip "interphase not installed"
    unset _GATES_LOADED _PHASE_LOADED
    source "$HOOKS_DIR/lib-gates.sh"

    # Real library provides working is_valid_transition
    run is_valid_transition "brainstorm" "brainstorm-reviewed"
    assert_success
}

@test "gates shim: delegated advance_phase works" {
    export INTERPHASE_ROOT="/root/projects/interphase"
    [[ -d "$INTERPHASE_ROOT/hooks" ]] || skip "interphase not installed"
    unset _GATES_LOADED _PHASE_LOADED

    # Mock bd for the delegated library
    bd() {
        if [[ "$1" == "set-state" ]]; then return 0; fi
        return 0
    }
    export -f bd

    source "$HOOKS_DIR/lib-gates.sh"
    run advance_phase "Test-001" "brainstorm" "Test"
    assert_success
}

@test "gates shim: delegated phase_infer_bead reads env var" {
    export INTERPHASE_ROOT="/root/projects/interphase"
    [[ -d "$INTERPHASE_ROOT/hooks" ]] || skip "interphase not installed"
    export CLAVAIN_BEAD_ID="Test-env-bead"
    unset _GATES_LOADED _PHASE_LOADED
    source "$HOOKS_DIR/lib-gates.sh"

    run phase_infer_bead
    assert_success
    assert_output "Test-env-bead"
    unset CLAVAIN_BEAD_ID
}

# ─── Discovery shim: delegation mode ─────────────────────────────────

@test "discovery shim: delegates when INTERPHASE_ROOT is set" {
    export INTERPHASE_ROOT="/root/projects/interphase"
    [[ -d "$INTERPHASE_ROOT/hooks" ]] || skip "interphase not installed"
    export DISCOVERY_PROJECT_DIR="$TEST_PROJECT"
    mkdir -p "$TEST_PROJECT/.beads"
    unset _DISCOVERY_LOADED

    # Mock bd for the delegated library
    bd() {
        if [[ "$1" == "list" ]]; then echo "[]"; return 0; fi
        return 1
    }
    export -f bd

    source "$HOOKS_DIR/lib-discovery.sh"
    run discovery_scan_beads
    assert_success
    assert_output "[]"
}

@test "discovery shim: delegated infer_bead_action works" {
    export INTERPHASE_ROOT="/root/projects/interphase"
    [[ -d "$INTERPHASE_ROOT/hooks" ]] || skip "interphase not installed"
    export DISCOVERY_PROJECT_DIR="$TEST_PROJECT"
    unset _DISCOVERY_LOADED
    source "$HOOKS_DIR/lib-discovery.sh"

    run infer_bead_action "Test-001" "open"
    assert_success
    assert_output "brainstorm|"
}

# ─── _discover_beads_plugin ──────────────────────────────────────────

@test "_discover_beads_plugin: returns INTERPHASE_ROOT when set" {
    export INTERPHASE_ROOT="/custom/path"
    source "$HOOKS_DIR/lib.sh"
    run _discover_beads_plugin
    assert_success
    assert_output "/custom/path"
    unset INTERPHASE_ROOT
}

@test "_discover_beads_plugin: returns empty when nothing found" {
    export INTERPHASE_ROOT=""
    export HOME="$TEST_PROJECT"
    source "$HOOKS_DIR/lib.sh"
    run _discover_beads_plugin
    assert_success
    assert_output ""
}
