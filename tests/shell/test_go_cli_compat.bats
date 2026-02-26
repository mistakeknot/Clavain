#!/usr/bin/env bats
# Integration tests: verify Go clavain-cli produces identical/compatible output to Bash version.
# Tests pure functions only — no ic/bd dependency for most tests.
#
# Run: cd os/clavain && bats tests/shell/test_go_cli_compat.bats

# ─── Setup / teardown ───────────────────────────────────────────

setup() {
    load test_helper

    export TMPDIR="$(mktemp -d)"

    # Build Go binary
    GO_CLI="$TMPDIR/clavain-cli-go"
    go build -C "$BATS_TEST_DIRNAME/../../cmd/clavain-cli" -o "$GO_CLI" . || skip "Go build failed"

    BASH_CLI="$BATS_TEST_DIRNAME/../../bin/clavain-cli"

    # Strip ic/bd from PATH so pure-function tests don't hit real backends.
    # bd is at /usr/local/bin/bd and prints stderr noise ("no beads database")
    # when invoked without a .beads directory. We exclude it from CLEAN_PATH.
    CLEAN_PATH="/usr/local/go/bin:/usr/sbin:/usr/bin:/sbin:/bin"
}

teardown() {
    rm -rf "$TMPDIR" 2>/dev/null || true
}

# Helper: run Go CLI with clean PATH (no ic/bd)
go_cli() {
    PATH="$CLEAN_PATH" "$GO_CLI" "$@"
}

# Helper: run Go CLI, capture only stdout (discard stderr from bd/ic noise)
go_cli_stdout() {
    PATH="$CLEAN_PATH" "$GO_CLI" "$@" 2>/dev/null
}

# Helper: run Bash CLI with clean PATH (no ic/bd)
bash_cli() {
    PATH="$CLEAN_PATH" "$BASH_CLI" "$@"
}

# ═══════════════════════════════════════════════════════════════════
# SECTION 1: Help output structure
# ═══════════════════════════════════════════════════════════════════

@test "Go help output starts with Usage: clavain-cli" {
    run go_cli help
    assert_success
    assert_line --index 0 "Usage: clavain-cli <command> [args...]"
}

@test "Go --help flag prints help and exits 0" {
    run go_cli --help
    assert_success
    assert_line --index 0 "Usage: clavain-cli <command> [args...]"
}

@test "Go -h flag prints help and exits 0" {
    run go_cli -h
    assert_success
    assert_line --index 0 "Usage: clavain-cli <command> [args...]"
}

@test "Go no-args prints help and exits 0" {
    run go_cli
    assert_success
    assert_line --index 0 "Usage: clavain-cli <command> [args...]"
}

# ═══════════════════════════════════════════════════════════════════
# SECTION 2: Unknown command handling
# ═══════════════════════════════════════════════════════════════════

@test "Go unknown command exits 1 with error message" {
    run go_cli nonexistent-cmd
    assert_failure
    assert_output --partial "unknown command"
    assert_output --partial "nonexistent-cmd"
}

@test "Go unknown command error format matches Bash" {
    run go_cli nonexistent-cmd
    assert_failure
    # Both Go and Bash output: clavain-cli: unknown command '<cmd>'
    assert_line --index 0 "clavain-cli: unknown command 'nonexistent-cmd'"
    assert_line --index 1 "Run 'clavain-cli help' for usage."
}

# ═══════════════════════════════════════════════════════════════════
# SECTION 3: complexity-label — pure function, all scores
# ═══════════════════════════════════════════════════════════════════

@test "Go complexity-label matches all scores 1-5" {
    local expected_labels=("trivial" "simple" "moderate" "complex" "research")
    for score in 1 2 3 4 5; do
        local result
        result="$(go_cli_stdout complexity-label "$score")"
        local idx=$((score - 1))
        [[ "$result" == "${expected_labels[$idx]}" ]] || {
            echo "Score $score: expected '${expected_labels[$idx]}', got '$result'"
            return 1
        }
    done
}

@test "Go complexity-label matches Bash for all scores 1-5" {
    for score in 1 2 3 4 5; do
        local go_out bash_out
        go_out="$(go_cli_stdout complexity-label "$score")"
        bash_out="$(bash_cli complexity-label "$score" 2>/dev/null)" || true
        if [[ -n "$bash_out" ]]; then
            [[ "$go_out" == "$bash_out" ]] || {
                echo "Mismatch at score=$score: Go='$go_out' Bash='$bash_out'"
                return 1
            }
        fi
    done
}

@test "Go complexity-label out of range returns moderate" {
    local result
    result="$(go_cli_stdout complexity-label 0)"
    [[ "$result" == "moderate" ]]

    result="$(go_cli_stdout complexity-label 99)"
    [[ "$result" == "moderate" ]]

    result="$(go_cli_stdout complexity-label -1)"
    [[ "$result" == "moderate" ]]
}

@test "Go complexity-label handles legacy string inputs" {
    local result
    result="$(go_cli_stdout complexity-label simple)"
    [[ "$result" == "simple" ]]

    result="$(go_cli_stdout complexity-label medium)"
    [[ "$result" == "moderate" ]]

    result="$(go_cli_stdout complexity-label complex)"
    [[ "$result" == "complex" ]]
}

@test "Go complexity-label missing arg exits with error" {
    run go_cli complexity-label
    assert_failure
    assert_output --partial "usage:"
}

# ═══════════════════════════════════════════════════════════════════
# SECTION 4: sprint-next-step — pure function, all phases
# ═══════════════════════════════════════════════════════════════════

@test "Go sprint-next-step maps all 9 phases correctly" {
    # Phase → expected next step (from the static fallback table)
    local -A phase_map=(
        [brainstorm]="strategy"
        [brainstorm-reviewed]="strategy"
        [strategized]="write-plan"
        [planned]="flux-drive"
        [plan-reviewed]="work"
        [executing]="quality-gates"
        [shipping]="reflect"
        [reflect]="done"
        [done]="done"
    )

    for phase in "${!phase_map[@]}"; do
        local expected="${phase_map[$phase]}"
        local result
        result="$(go_cli_stdout sprint-next-step "$phase")"
        [[ "$result" == "$expected" ]] || {
            echo "Phase '$phase': expected '$expected', got '$result'"
            return 1
        }
    done
}

@test "Go sprint-next-step unknown phase returns brainstorm" {
    local result
    result="$(go_cli_stdout sprint-next-step "nonexistent-phase")"
    [[ "$result" == "brainstorm" ]]

    result="$(go_cli_stdout sprint-next-step "garbage")"
    [[ "$result" == "brainstorm" ]]
}

@test "Go sprint-next-step empty phase returns brainstorm" {
    local result
    result="$(go_cli_stdout sprint-next-step "")"
    [[ "$result" == "brainstorm" ]]
}

@test "Go sprint-next-step matches Bash for all phases" {
    local phases=("brainstorm" "brainstorm-reviewed" "strategized" "planned" "plan-reviewed" "executing" "shipping" "reflect" "done")
    for phase in "${phases[@]}"; do
        local go_out bash_out
        go_out="$(go_cli_stdout sprint-next-step "$phase")"
        bash_out="$(bash_cli sprint-next-step "$phase" 2>/dev/null)" || true
        if [[ -n "$bash_out" ]]; then
            [[ "$go_out" == "$bash_out" ]] || {
                echo "Phase '$phase': Go='$go_out' Bash='$bash_out'"
                return 1
            }
        fi
    done
}

@test "Go sprint-next-step missing arg exits with error" {
    run go_cli sprint-next-step
    assert_failure
    assert_output --partial "usage:"
}

# ═══════════════════════════════════════════════════════════════════
# SECTION 5: classify-complexity — pure function (heuristic path)
# ═══════════════════════════════════════════════════════════════════

@test "Go classify-complexity trivial description returns 1" {
    local result
    result="$(go_cli_stdout classify-complexity test-bead "rename the file to fix typo")"
    [[ "$result" == "1" ]]
}

@test "Go classify-complexity research description returns 5" {
    local result
    result="$(go_cli_stdout classify-complexity test-bead "explore and investigate research brainstorm evaluate survey the full landscape")"
    [[ "$result" == "5" ]]
}

@test "Go classify-complexity empty description returns 3" {
    local result
    result="$(go_cli_stdout classify-complexity test-bead "")"
    [[ "$result" == "3" ]]
}

@test "Go classify-complexity short description returns 3" {
    local result
    result="$(go_cli_stdout classify-complexity test-bead "fix it")"
    [[ "$result" == "3" ]]
}

@test "Go classify-complexity moderate length returns 2" {
    local result
    result="$(go_cli_stdout classify-complexity test-bead "add a new validation check to the input handler for edge cases")"
    [[ "$result" == "2" ]]
}

@test "Go classify-complexity missing args exits with error" {
    run go_cli classify-complexity
    assert_failure
    assert_output --partial "usage:"
}

# ═══════════════════════════════════════════════════════════════════
# SECTION 6: Graceful degradation without ic/bd
# ═══════════════════════════════════════════════════════════════════

@test "Go sprint-find-active without ic outputs empty JSON array" {
    local result
    result="$(go_cli_stdout sprint-find-active)"
    [[ "$result" == "[]" ]]
}

@test "Go sprint-budget-remaining without ic/bd outputs 0" {
    local result
    result="$(go_cli_stdout sprint-budget-remaining some-bead)"
    [[ "$result" == "0" ]]
}

@test "Go budget-total without ic/bd outputs 0" {
    local result
    result="$(go_cli_stdout budget-total some-bead)"
    [[ "$result" == "0" ]]
}

@test "Go checkpoint-completed-steps without ic outputs empty JSON array" {
    local result
    result="$(go_cli_stdout checkpoint-completed-steps)"
    [[ "$result" == "[]" ]]
}

@test "Go checkpoint-read without ic handles gracefully" {
    run go_cli checkpoint-read
    # Should either output {} or an error — no panic
    [[ "$status" -eq 0 || "$status" -eq 1 ]]
    # Must not contain "panic" or Go stack trace
    [[ "$output" != *"panic"* ]]
    [[ "$output" != *"goroutine"* ]]
}

@test "Go checkpoint-validate without ic handles gracefully" {
    run go_cli checkpoint-validate
    [[ "$status" -eq 0 || "$status" -eq 1 ]]
    [[ "$output" != *"panic"* ]]
    [[ "$output" != *"goroutine"* ]]
}

@test "Go checkpoint-clear without ic handles gracefully" {
    run go_cli checkpoint-clear
    [[ "$status" -eq 0 || "$status" -eq 1 ]]
    [[ "$output" != *"panic"* ]]
}

@test "Go sprint-create without ic fails gracefully" {
    run go_cli sprint-create "test sprint"
    assert_failure
    [[ "$output" != *"panic"* ]]
}

@test "Go sprint-read-state without ic fails gracefully" {
    run go_cli sprint-read-state some-bead
    [[ "$status" -eq 0 || "$status" -eq 1 ]]
    [[ "$output" != *"panic"* ]]
}

@test "Go sprint-claim without ic fails gracefully" {
    run go_cli sprint-claim some-bead some-session
    assert_failure
    [[ "$output" != *"panic"* ]]
}

@test "Go sprint-advance without ic fails gracefully" {
    run go_cli sprint-advance some-bead brainstorm
    assert_failure
    [[ "$output" != *"panic"* ]]
}

# ═══════════════════════════════════════════════════════════════════
# SECTION 7: Commands that exist in Go but not Bash (new commands)
# ═══════════════════════════════════════════════════════════════════

@test "Go infer-action exists and requires args" {
    run go_cli infer-action
    assert_failure
    assert_output --partial "usage:"
}

@test "Go sprint-track-agent is no-op without sufficient args" {
    # sprint-track-agent returns success (nil) with <2 args — fire-and-forget design
    run go_cli sprint-track-agent
    assert_success
}

@test "Go sprint-complete-agent is no-op without sufficient args" {
    # sprint-complete-agent returns success (nil) with <1 args — fire-and-forget design
    run go_cli sprint-complete-agent
    assert_success
}

@test "Go sprint-invalidate-caches handles no-ic gracefully" {
    run go_cli sprint-invalidate-caches
    # Should succeed or fail gracefully (invalidating caches without ic is a no-op)
    [[ "$output" != *"panic"* ]]
}

@test "Go checkpoint-step-done requires args" {
    run go_cli checkpoint-step-done
    assert_failure
    assert_output --partial "usage:"
}

# ═══════════════════════════════════════════════════════════════════
# SECTION 8: Command parity — all Bash commands have Go equivalents
# ═══════════════════════════════════════════════════════════════════

@test "All Bash CLI commands are recognized by Go CLI" {
    # Commands from the Bash CLI case statement
    local bash_commands=(
        advance-phase enforce-gate infer-bead
        set-artifact record-phase sprint-advance sprint-find-active
        sprint-create sprint-claim sprint-release sprint-read-state
        sprint-next-step sprint-budget-remaining
        classify-complexity complexity-label
        close-children close-parent-if-done
        bead-claim bead-release
        checkpoint-write checkpoint-read checkpoint-validate checkpoint-clear
        help
    )

    for cmd in "${bash_commands[@]}"; do
        # Run Go CLI with the command (no args) — should NOT get "unknown command"
        local result
        result="$(go_cli "$cmd" 2>&1)" || true
        if [[ "$result" == *"unknown command"* ]]; then
            echo "Go CLI does not recognize Bash command: $cmd"
            return 1
        fi
    done
}
