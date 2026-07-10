#!/usr/bin/env bats

setup() {
    REPO_ROOT="$(cd "$BATS_TEST_DIRNAME/../.." && pwd)"
    HOOK="$REPO_ROOT/hooks/gate-calibration-session-end.sh"
    TEST_DIR="$(mktemp -d)"
    PROJECT="$TEST_DIR/project"
    BIN_DIR="$TEST_DIR/bin"
    INTERSPECT_ROOT="$TEST_DIR/interspect"
    IC_LOG="$TEST_DIR/ic.log"
    BD_LOG="$TEST_DIR/bd.log"
    CLI_LOG="$TEST_DIR/clavain-cli.log"
    ROUTING_LOG="$TEST_DIR/routing.log"
    TIMEOUT_LOG="$TEST_DIR/timeout.log"
    RECEIPT_FILE="$TEST_DIR/receipt.json"

    mkdir -p "$PROJECT/.beads" "$PROJECT/.clavain/interspect" \
        "$BIN_DIR" "$INTERSPECT_ROOT/scripts"
    printf '{"backend":"dolt"}\n' > "$PROJECT/.beads/metadata.json"
    printf '{"agents":{"existing":{"recommended_model":"sonnet"}}}\n' \
        > "$PROJECT/.clavain/interspect/routing-calibration.json"
    printf '{"tiers":{"existing":{"weighted_n":4}}}\n' \
        > "$PROJECT/.clavain/gate-tier-calibration.json"
    printf '{"run_count":1,"phases":{"plan":{"runs":1}}}\n' \
        > "$PROJECT/.clavain/phase-cost-calibration.json"

    export PROJECT INTERSPECT_ROOT IC_LOG BD_LOG CLI_LOG ROUTING_LOG TIMEOUT_LOG RECEIPT_FILE
    export TEST_SESSION="session-proof-1" TEST_BEAD="sylveste-proof-1" TEST_RUN="run-proof-1"
    export CURRENT_SESSION="$TEST_SESSION" CURRENT_PROJECT="$PROJECT" CURRENT_PHASE="done"
    export SPRINT_STATE="true" BEAD_RUN_ID="$TEST_RUN" BEAD_STATUS="closed"
    export RUN_STATUS_ID="$TEST_RUN" RUN_STATUS="completed" RUN_PHASE="done"
    export ROUTING_RC="0" ROUTING_WRITE="0"
    export GATE_RC="0" GATE_WRITE="0"
    export PHASE_RC="0" PHASE_WRITE="0" PHASE_TIMEOUT="0" PHASE_SLEEP="0"
    export RECEIPT_RC="0" STATUS_RC="0" STATUS_JSON=""

    cat > "$BIN_DIR/ic" <<'SH'
#!/usr/bin/env bash
printf '%s\n' "$*" >> "$IC_LOG"
[[ "${1:-}" == "--json" ]] && shift
case "${1:-}:${2:-}" in
    session:current)
        printf '{"session_id":"%s","project_dir":"%s","bead_id":"%s","run_id":"%s","phase":"%s"}\n' \
            "$CURRENT_SESSION" "$CURRENT_PROJECT" "$TEST_BEAD" "$TEST_RUN" "$CURRENT_PHASE"
        ;;
    session:end)
        printf '{"session_id":"%s","ended":true}\n' "$TEST_SESSION"
        ;;
    run:status)
        printf '{"id":"%s","project_dir":"%s","status":"%s","phase":"%s"}\n' \
            "$RUN_STATUS_ID" "$PROJECT" "$RUN_STATUS" "$RUN_PHASE"
        ;;
    *) exit 3 ;;
esac
SH

    cat > "$BIN_DIR/bd" <<'SH'
#!/usr/bin/env bash
printf '%s|%s\n' "$PWD" "$*" >> "$BD_LOG"
case "${1:-}:${3:-}" in
    state:sprint) printf '%s\n' "$SPRINT_STATE" ;;
    state:ic_run_id) printf '%s\n' "$BEAD_RUN_ID" ;;
    show:*)
        printf '[{"id":"%s","status":"%s"}]\n' "$TEST_BEAD" "$BEAD_STATUS"
        ;;
    *) exit 3 ;;
esac
SH

    cat > "$BIN_DIR/clavain-cli" <<'SH'
#!/usr/bin/env bash
printf '%s\n' "$*" >> "$CLI_LOG"
case "${1:-}" in
    calibrate-gate-tiers)
        if [[ "$GATE_WRITE" == "1" ]]; then
            root="${SPRINT_LIB_PROJECT_DIR:-$PROJECT}"
            printf '{"tiers":{"a":{"weighted_n":6.8},"b":{"weighted_n":4.5}}}\n' \
                > "$root/.clavain/gate-tier-calibration.json"
        fi
        exit "$GATE_RC"
        ;;
    calibrate-phase-costs)
        if [[ "$PHASE_SLEEP" != "0" ]]; then
            sleep "$PHASE_SLEEP"
        fi
        if [[ "$PHASE_WRITE" == "1" ]]; then
            root="${SPRINT_LIB_PROJECT_DIR:-$PROJECT}"
            printf '{"run_count":7,"phases":{"plan":{"runs":7}}}\n' \
                > "$root/.clavain/phase-cost-calibration.json"
        fi
        exit "$PHASE_RC"
        ;;
    calibration-streak)
        case "${2:-}" in
            status)
                [[ "$STATUS_RC" == "0" ]] || exit "$STATUS_RC"
                if [[ -n "$STATUS_JSON" ]]; then
                    printf '%s\n' "$STATUS_JSON"
                elif [[ -s "$RECEIPT_FILE" ]]; then
                    jq -n --slurpfile receipt "$RECEIPT_FILE" '{schema_version:2,receipts:$receipt}'
                else
                    printf '{"schema_version":2,"receipts":[]}\n'
                fi
                ;;
            record-receipt)
                cat > "$RECEIPT_FILE"
                exit "$RECEIPT_RC"
                ;;
            *) exit 3 ;;
        esac
        ;;
    *) exit 3 ;;
esac
SH

    cat > "$BIN_DIR/timeout" <<'SH'
#!/usr/bin/env bash
seconds="$1"
shift
printf '%s %s\n' "$seconds" "$*" >> "$TIMEOUT_LOG"
if [[ "$PHASE_TIMEOUT" == "1" && "$*" == *"calibrate-phase-costs --auto --strict"* ]]; then
    exit 124
fi
"$@"
SH

    cat > "$INTERSPECT_ROOT/scripts/write-routing-calibration.sh" <<'SH'
#!/usr/bin/env bash
printf 'routing\n' >> "$ROUTING_LOG"
if [[ "$ROUTING_WRITE" == "1" ]]; then
    printf '{"agents":{"quality":{"recommended_model":"sonnet"},"architecture":{"recommended_model":"opus"}}}\n' \
        > "$CLAUDE_PROJECT_DIR/.clavain/interspect/routing-calibration.json"
fi
exit "$ROUTING_RC"
SH

    chmod +x "$BIN_DIR/ic" "$BIN_DIR/bd" "$BIN_DIR/clavain-cli" \
        "$BIN_DIR/timeout" "$INTERSPECT_ROOT/scripts/write-routing-calibration.sh"
    export PATH="$BIN_DIR:$PATH"
}

teardown() {
    rm -rf "$TEST_DIR"
}

run_hook() {
    local input
    if [[ "$#" -gt 0 ]]; then
        input="$1"
    else
        input="$(jq -nc --arg session "$TEST_SESSION" --arg cwd "$PROJECT" \
            '{session_id:$session,cwd:$cwd}')"
    fi
    run bash -c 'printf "%s\n" "$1" | "$2"' _ "$input" "$HOOK"
}

assert_no_calibration_work() {
    [[ ! -s "$ROUTING_LOG" ]]
    ! grep -q 'calibrate-' "$CLI_LOG" 2>/dev/null
    ! grep -q 'calibration-streak record-receipt' "$CLI_LOG" 2>/dev/null
    ! grep -q 'session end' "$IC_LOG" 2>/dev/null
}

reset_authoritative_markers() {
    export CURRENT_SESSION="$TEST_SESSION" CURRENT_PROJECT="$PROJECT" CURRENT_PHASE="done"
    export SPRINT_STATE="true" BEAD_RUN_ID="$TEST_RUN" BEAD_STATUS="closed"
    export RUN_STATUS_ID="$TEST_RUN" RUN_STATUS="completed" RUN_PHASE="done"
}

clear_call_logs() {
    : > "$IC_LOG"
    : > "$BD_LOG"
    : > "$CLI_LOG"
    : > "$ROUTING_LOG"
    : > "$TIMEOUT_LOG"
    rm -f "$RECEIPT_FILE"
}

@test "ineligible SessionEnd never runs calibration or records a receipt" {
    local marker
    for marker in session project phase sprint bead_run bead_status run_id run_status run_phase; do
        reset_authoritative_markers
        clear_call_logs
        case "$marker" in
            session) export CURRENT_SESSION="another-session" ;;
            project) export CURRENT_PROJECT="$TEST_DIR/another-project" ;;
            phase) export CURRENT_PHASE="reflect" ;;
            sprint) export SPRINT_STATE="false" ;;
            bead_run) export BEAD_RUN_ID="another-run" ;;
            bead_status) export BEAD_STATUS="in_progress" ;;
            run_id) export RUN_STATUS_ID="another-run" ;;
            run_status) export RUN_STATUS="active" ;;
            run_phase) export RUN_PHASE="reflect" ;;
        esac

        run_hook
        [[ "$status" -eq 0 ]]
        assert_no_calibration_work
    done
}

@test "eligible SessionEnd records one exact evidence receipt after one run of each loop" {
    export ROUTING_WRITE="1" GATE_WRITE="1" PHASE_WRITE="1"

    run_hook

    [[ "$status" -eq 0 ]]
    [[ -s "$RECEIPT_FILE" ]]
    [[ "$(wc -l < "$ROUTING_LOG" | tr -d ' ')" -eq 1 ]]
    [[ "$(grep -c '^calibrate-gate-tiers --auto$' "$CLI_LOG")" -eq 1 ]]
    [[ "$(grep -c '^calibrate-phase-costs --auto --strict$' "$CLI_LOG")" -eq 1 ]]
    [[ "$(grep -c "^calibration-streak record-receipt --root=$PROJECT$" "$CLI_LOG")" -eq 1 ]]
    [[ "$(grep -c "^--json session end --session=$TEST_SESSION$" "$IC_LOG")" -eq 1 ]]
    [[ "$(wc -l < "$TIMEOUT_LOG" | tr -d ' ')" -eq 3 ]]

    jq -e --arg session "$TEST_SESSION" --arg sprint "$TEST_BEAD" '
        (keys | sort) == (["host","loops","session_id","sprint_id","timestamp"] | sort) and
        .session_id == $session and .sprint_id == $sprint and
        (.host | type == "string" and length > 0) and
        (.timestamp | fromdateiso8601 | type == "number") and
        (.loops | keys | sort) == (["gate_threshold","phase_cost","routing"] | sort) and
        ([.loops[] | keys | sort] | all(. == (["after_hash","before_hash","detail","evidence_count","outcome"] | sort))) and
        .loops.routing.outcome == "updated" and
        .loops.routing.before_hash != .loops.routing.after_hash and
        .loops.routing.evidence_count == 2 and
        .loops.gate_threshold.outcome == "updated" and
        .loops.gate_threshold.before_hash != .loops.gate_threshold.after_hash and
        .loops.gate_threshold.evidence_count == 11 and
        .loops.phase_cost.outcome == "updated" and
        .loops.phase_cost.before_hash != .loops.phase_cost.after_hash and
        .loops.phase_cost.evidence_count == 7 and
        ([.loops[].detail] | all(type == "string" and length > 0))
    ' "$RECEIPT_FILE"
}

@test "failed timeout and rc2 artifact drift are recorded without blocking SessionEnd" {
    export ROUTING_RC="1" ROUTING_WRITE="0"
    export GATE_RC="2" GATE_WRITE="1"
    export PHASE_TIMEOUT="1"

    run_hook

    [[ "$status" -eq 0 ]]
    [[ -s "$RECEIPT_FILE" ]]
    [[ "$(wc -l < "$ROUTING_LOG" | tr -d ' ')" -eq 1 ]]
    [[ "$(grep -c '^calibrate-gate-tiers --auto$' "$CLI_LOG")" -eq 1 ]]
    [[ "$(grep -c 'calibrate-phase-costs --auto --strict' "$TIMEOUT_LOG")" -eq 1 ]]
    jq -e '
        .loops.routing.outcome == "failed" and
        .loops.routing.evidence_count == 1 and
        .loops.gate_threshold.outcome == "failed" and
        .loops.gate_threshold.before_hash != .loops.gate_threshold.after_hash and
        .loops.gate_threshold.evidence_count == 11 and
        .loops.phase_cost.outcome == "timeout" and
        .loops.phase_cost.before_hash == .loops.phase_cost.after_hash and
        .loops.phase_cost.evidence_count == 1
    ' "$RECEIPT_FILE"
}

@test "stable rc0 and rc2 producer contracts are valid no-ops" {
    export ROUTING_RC="2" ROUTING_WRITE="0"
    export GATE_RC="0" GATE_WRITE="0"
    export PHASE_RC="2" PHASE_WRITE="0"

    run_hook

    [[ "$status" -eq 0 ]]
    jq -e '
        .loops.routing.outcome == "valid_noop" and
        .loops.routing.before_hash == .loops.routing.after_hash and
        .loops.gate_threshold.outcome == "valid_noop" and
        .loops.gate_threshold.before_hash == .loops.gate_threshold.after_hash and
        .loops.phase_cost.outcome == "valid_noop" and
        .loops.phase_cost.before_hash == .loops.phase_cost.after_hash
    ' "$RECEIPT_FILE"
}

@test "python fallback enforces the timeout contract without GNU timeout" {
    local jq_bin python_bin
    jq_bin="$(command -v jq)"
    python_bin="$(command -v python3)"
    rm -f "$BIN_DIR/timeout"
    ln -s "$jq_bin" "$BIN_DIR/jq"
    ln -s "$python_bin" "$BIN_DIR/python3"
    export PATH="$BIN_DIR:/usr/bin:/bin"
    export CLAVAIN_CALIBRATION_TIMEOUT_SECONDS="1"
    export PHASE_SLEEP="2"

    run_hook

    [[ "$status" -eq 0 ]]
    jq -e '.loops.phase_cost.outcome == "timeout"' "$RECEIPT_FILE"
}

@test "nested hook cwd records proof and artifacts at the repository root" {
    local nested input
    nested="$PROJECT/src/deep/package"
    mkdir -p "$nested"
    export CURRENT_PROJECT="$nested"
    export ROUTING_WRITE="1" GATE_WRITE="1" PHASE_WRITE="1"
    input="$(jq -nc --arg session "$TEST_SESSION" --arg cwd "$nested" \
        '{session_id:$session,cwd:$cwd}')"

    run_hook "$input"

    [[ "$status" -eq 0 ]]
    grep -q "^--json session current --session=$TEST_SESSION --project=$nested$" "$IC_LOG"
    grep -q "^calibration-streak status --json --root=$PROJECT$" "$CLI_LOG"
    grep -q "^calibration-streak record-receipt --root=$PROJECT$" "$CLI_LOG"
    ! grep -qv "^$PROJECT|" "$BD_LOG"
    jq -e '.loops.routing.evidence_count == 2' "$RECEIPT_FILE"
    jq -e '.tiers.a.weighted_n == 6.8' "$PROJECT/.clavain/gate-tier-calibration.json"
    jq -e '.run_count == 7' "$PROJECT/.clavain/phase-cost-calibration.json"
    [[ ! -e "$nested/.clavain" ]]
}

@test "duplicate SessionEnd delivery does not rerun producers" {
    export ROUTING_WRITE="1" GATE_WRITE="1" PHASE_WRITE="1"

    run_hook
    [[ "$status" -eq 0 ]]
    run_hook
    [[ "$status" -eq 0 ]]

    [[ "$(wc -l < "$ROUTING_LOG" | tr -d ' ')" -eq 1 ]]
    [[ "$(grep -c '^calibrate-gate-tiers --auto$' "$CLI_LOG")" -eq 1 ]]
    [[ "$(grep -c '^calibrate-phase-costs --auto --strict$' "$CLI_LOG")" -eq 1 ]]
    [[ "$(grep -c "^calibration-streak record-receipt --root=$PROJECT$" "$CLI_LOG")" -eq 1 ]]
    [[ "$(grep -c "^calibration-streak status --json --root=$PROJECT$" "$CLI_LOG")" -eq 2 ]]
    [[ "$(grep -c "^--json session end --session=$TEST_SESSION$" "$IC_LOG")" -eq 1 ]]
}

@test "unverified streak status skips producers before artifact mutation" {
    export STATUS_RC="1"
    export ROUTING_WRITE="1" GATE_WRITE="1" PHASE_WRITE="1"

    run_hook

    [[ "$status" -eq 0 ]]
    grep -q "^calibration-streak status --json --root=$PROJECT$" "$CLI_LOG"
    assert_no_calibration_work
}

@test "malformed input and receipt-recorder failure always exit zero" {
    run_hook 'not-json'
    [[ "$status" -eq 0 ]]
    assert_no_calibration_work

    clear_call_logs
    export RECEIPT_RC="1"
    run_hook
    [[ "$status" -eq 0 ]]
    [[ -s "$RECEIPT_FILE" ]]
}
