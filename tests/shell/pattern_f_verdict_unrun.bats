#!/usr/bin/env bats
# --verdict UNRUN in scripts/pattern-f-verdict.sh: a replay the seat could not
# execute is a refusal to rule, recorded as its own verdict value and never a
# pass. Same fresh-register setup as pattern_f_verdict.bats.

setup() {
    REPO_ROOT="$(cd "$BATS_TEST_DIRNAME/../.." && pwd)"
    SCRIPT="$REPO_ROOT/scripts/pattern-f-verdict.sh"
    PROJ="$BATS_TEST_TMPDIR/proj"
    mkdir -p "$PROJ/.clavain/interspect"
    export CLAUDE_PROJECT_DIR="$PROJ"
    export INTERSPECT_QUARANTINE_HOURS=0
    # shellcheck source=/dev/null
    source "$REPO_ROOT/hooks/lib.sh" 2>/dev/null || skip "hooks/lib.sh not sourceable"
    local root
    root=$(_discover_interspect_plugin 2>/dev/null) || root=""
    [[ -n "$root" && -f "$root/hooks/lib-interspect.sh" ]] || skip "interspect library not found"
    export INTERSPECT_ROOT="$root"
    # shellcheck source=/dev/null
    source "$root/hooks/lib-interspect.sh" 2>/dev/null || skip "lib-interspect.sh not sourceable"
    _interspect_ensure_db || skip "_interspect_ensure_db failed"
    DB="$PROJ/.clavain/interspect/interspect.db"
    [[ -f "$DB" ]] || skip "register not created at $DB"
    PLAN="$PROJ/plan-test.md"
}

@test "replay UNRUN row is recorded and listed with its note" {
    run bash "$SCRIPT" --db "$DB" --session sess-u --plan "$PLAN" --commit abc1234 \
        --role validator --kind replay --verdict UNRUN --note "uv run pytest: command denied" --goal g1
    [ "$status" -eq 0 ]
    [[ "$output" == *"recorded validator replay UNRUN"* ]]

    run bash "$SCRIPT" --list --db "$DB" --session sess-u
    [ "$status" -eq 0 ]
    [ "${#lines[@]}" -eq 1 ]
    [[ "${lines[0]}" == *$'\tvalidator\treplay\tUNRUN\t'* ]]
    [[ "${lines[0]}" == *"command denied"* ]]
}

@test "UNRUN with --kind independent exits 2 and writes nothing" {
    run bash "$SCRIPT" --db "$DB" --session sess-u --plan "$PLAN" --commit abc1234 \
        --role validator --kind independent --verdict UNRUN
    [ "$status" -eq 2 ]
    [[ "$output" == *"UNRUN pairs only with --kind replay"* ]]
    run sqlite3 "$DB" "select count(*) from evidence where event='pattern_f_verdict';"
    [ "$output" = "0" ]
}

@test "an executor replay may be UNRUN too" {
    run bash "$SCRIPT" --db "$DB" --session sess-u --plan "$PLAN" --commit none \
        --role executor --kind replay --verdict UNRUN --note "bats not installed"
    [ "$status" -eq 0 ]
    [[ "$output" == *"recorded executor replay UNRUN"* ]]
}

@test "an unknown verdict value still exits 2" {
    run bash "$SCRIPT" --db "$DB" --session sess-u --plan "$PLAN" --commit abc1234 \
        --role executor --kind replay --verdict MAYBE
    [ "$status" -eq 2 ]
    [[ "$output" == *"PASS, FAIL or UNRUN"* ]]
}
