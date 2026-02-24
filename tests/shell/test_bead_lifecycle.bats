#!/usr/bin/env bats
# Tests for bead lifecycle reliability — bead_claim, bead_release,
# sprint_close_parent_if_done. Mocks bd to avoid real beads DB.

setup() {
    load test_helper

    TEST_PROJECT="$(mktemp -d)"
    mkdir -p "$TEST_PROJECT/.beads"
    export SPRINT_LIB_PROJECT_DIR="$TEST_PROJECT"
    export HOME="$TEST_PROJECT"

    mkdir -p "$TEST_PROJECT/.claude/plugins/cache"
    export INTERPHASE_ROOT=""
    export INTERLOCK_ROOT=""

    unset _SPRINT_LOADED _GATES_LOADED _PHASE_LOADED _DISCOVERY_LOADED _LIB_LOADED

    BD_CALL_LOG="$TEST_PROJECT/bd_calls.log"
    export BD_CALL_LOG

    # State store for mock bd set-state / bd state
    BD_STATE_DIR="$TEST_PROJECT/bd_state"
    mkdir -p "$BD_STATE_DIR"
    export BD_STATE_DIR
}

teardown() {
    rm -rf "$TEST_PROJECT" 2>/dev/null || true
    unset -f bd 2>/dev/null || true
}

_source_sprint_lib() {
    unset _SPRINT_LOADED _GATES_LOADED _PHASE_LOADED _DISCOVERY_LOADED _LIB_LOADED
    source "$HOOKS_DIR/lib-sprint.sh"
}

# ═══════════════════════════════════════════════════════════════════
# Mock bd that tracks calls and simulates set-state / state
# ═══════════════════════════════════════════════════════════════════

_mock_bd_with_state() {
    bd() {
        echo "bd $*" >> "$BD_CALL_LOG"
        case "$1" in
            set-state)
                local bead_id="$2"
                local kv="$3"
                local key="${kv%%=*}"
                local val="${kv#*=}"
                mkdir -p "$BD_STATE_DIR/$bead_id"
                echo "$val" > "$BD_STATE_DIR/$bead_id/$key"
                ;;
            state)
                local bead_id="$2"
                local key="$3"
                if [[ -f "$BD_STATE_DIR/$bead_id/$key" ]]; then
                    cat "$BD_STATE_DIR/$bead_id/$key"
                else
                    echo "(no ${key} state set)"
                fi
                ;;
            close)
                echo "closed $2" >> "$BD_CALL_LOG"
                ;;
            show)
                # Override per-test via BD_SHOW_OUTPUT
                if [[ -n "${BD_SHOW_OUTPUT:-}" ]]; then
                    echo "$BD_SHOW_OUTPUT"
                fi
                ;;
        esac
        return 0
    }
    export -f bd
}

# ═══════════════════════════════════════════════════════════════════
# bead_claim tests
# ═══════════════════════════════════════════════════════════════════

@test "bead_claim: first claim succeeds" {
    _mock_bd_with_state
    _source_sprint_lib

    run bead_claim "iv-test1" "session-abc"
    assert_success

    # Verify state was set
    [[ "$(cat "$BD_STATE_DIR/iv-test1/claimed_by")" == "session-abc" ]]
    [[ -n "$(cat "$BD_STATE_DIR/iv-test1/claimed_at")" ]]
}

@test "bead_claim: same session re-claim is idempotent" {
    _mock_bd_with_state
    _source_sprint_lib

    bead_claim "iv-test2" "session-abc"
    run bead_claim "iv-test2" "session-abc"
    assert_success
}

@test "bead_claim: different session gets conflict" {
    _mock_bd_with_state
    _source_sprint_lib

    bead_claim "iv-test3" "session-abc"

    # Set claimed_at to now (fresh claim)
    echo "$(date +%s)" > "$BD_STATE_DIR/iv-test3/claimed_at"

    run bead_claim "iv-test3" "session-xyz"
    assert_failure
    assert_output --partial "claimed by session"
}

@test "bead_claim: stale claim (>2h) gets overridden" {
    _mock_bd_with_state
    _source_sprint_lib

    bead_claim "iv-test4" "session-old"

    # Set claimed_at to 3 hours ago
    local three_hours_ago=$(( $(date +%s) - 10800 ))
    echo "$three_hours_ago" > "$BD_STATE_DIR/iv-test4/claimed_at"

    run bead_claim "iv-test4" "session-new"
    assert_success

    # Verify new session owns the claim
    [[ "$(cat "$BD_STATE_DIR/iv-test4/claimed_by")" == "session-new" ]]
}

# ═══════════════════════════════════════════════════════════════════
# bead_release tests
# ═══════════════════════════════════════════════════════════════════

@test "bead_release: clears claim state" {
    _mock_bd_with_state
    _source_sprint_lib

    bead_claim "iv-test5" "session-abc"
    bead_release "iv-test5"

    # Verify state was cleared (empty string)
    [[ "$(cat "$BD_STATE_DIR/iv-test5/claimed_by")" == "" ]]
    [[ "$(cat "$BD_STATE_DIR/iv-test5/claimed_at")" == "" ]]
}

# ═══════════════════════════════════════════════════════════════════
# sprint_close_parent_if_done tests
# ═══════════════════════════════════════════════════════════════════

@test "sprint_close_parent_if_done: closes parent when all children done" {
    _source_sprint_lib

    # Mock bd show to return parent + all-closed children
    bd() {
        echo "bd $*" >> "$BD_CALL_LOG"
        case "$1" in
            show)
                if [[ "$2" == "iv-child" ]]; then
                    cat <<'SHOWEOF'
iv-child: Child bead (OPEN, P2)
PARENT
  ↑ ✓ iv-parent: Parent epic
CHILDREN
SHOWEOF
                elif [[ "$2" == "iv-parent" ]]; then
                    cat <<'SHOWEOF'
iv-parent: Parent epic (OPEN, P1)
CHILDREN
  ↳ ✓ iv-child: Child bead
  ↳ ✓ iv-other: Other child
SHOWEOF
                fi
                ;;
            close)
                echo "closed $2" >> "$BD_CALL_LOG"
                ;;
        esac
        return 0
    }
    export -f bd

    run sprint_close_parent_if_done "iv-child"
    assert_success
    assert_output "iv-parent"

    # Verify bd close was called on parent
    grep -q "closed iv-parent" "$BD_CALL_LOG"
}

@test "sprint_close_parent_if_done: keeps parent open when children remain" {
    _source_sprint_lib

    bd() {
        echo "bd $*" >> "$BD_CALL_LOG"
        case "$1" in
            show)
                if [[ "$2" == "iv-child" ]]; then
                    cat <<'SHOWEOF'
iv-child: Child bead (OPEN, P2)
PARENT
  ↑ ✓ iv-parent: Parent epic
SHOWEOF
                elif [[ "$2" == "iv-parent" ]]; then
                    # One open child (○ = open)
                    cat <<'SHOWEOF'
iv-parent: Parent epic (OPEN, P1)
CHILDREN
  ↳ ✓ iv-child: Child bead
  ↳ ○ iv-other: Still open child
SHOWEOF
                fi
                ;;
            close)
                echo "closed $2" >> "$BD_CALL_LOG"
                ;;
        esac
        return 0
    }
    export -f bd

    run sprint_close_parent_if_done "iv-child"
    assert_success
    assert_output ""

    # Verify bd close was NOT called
    ! grep -q "closed iv-parent" "$BD_CALL_LOG" 2>/dev/null
}

@test "sprint_close_parent_if_done: no-op when bead has no parent" {
    _source_sprint_lib

    bd() {
        echo "bd $*" >> "$BD_CALL_LOG"
        case "$1" in
            show)
                # No PARENT section
                cat <<'SHOWEOF'
iv-orphan: Orphan bead (OPEN, P2)
DESCRIPTION
  Some description
SHOWEOF
                ;;
        esac
        return 0
    }
    export -f bd

    run sprint_close_parent_if_done "iv-orphan"
    assert_success
    assert_output ""
}

@test "sprint_close_parent_if_done: skips already-closed parent" {
    _source_sprint_lib

    bd() {
        echo "bd $*" >> "$BD_CALL_LOG"
        case "$1" in
            show)
                if [[ "$2" == "iv-child" ]]; then
                    cat <<'SHOWEOF'
iv-child: Child bead (OPEN, P2)
PARENT
  ↑ ✓ iv-parent: Parent epic
SHOWEOF
                elif [[ "$2" == "iv-parent" ]]; then
                    # Parent already CLOSED
                    cat <<'SHOWEOF'
iv-parent: Parent epic (CLOSED, P1)
CHILDREN
  ↳ ✓ iv-child: Child bead
SHOWEOF
                fi
                ;;
            close)
                echo "closed $2" >> "$BD_CALL_LOG"
                ;;
        esac
        return 0
    }
    export -f bd

    run sprint_close_parent_if_done "iv-child"
    assert_success
    assert_output ""

    ! grep -q "closed iv-parent" "$BD_CALL_LOG" 2>/dev/null
}
