#!/usr/bin/env bats
# Tests for scripts/pattern-f-verdict.sh — the Pattern F verdict register write.
# Every test gets a fresh register that the interspect library itself creates
# (_interspect_ensure_db at $CLAUDE_PROJECT_DIR/.clavain/interspect/interspect.db),
# so the schema under test is the real one, not a hand-written copy.

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

@test "replay PASS row is recorded and listed with role/kind/verdict" {
    run bash "$SCRIPT" --db "$DB" --session sess-a --plan "$PLAN" --commit abc1234 \
        --role executor --kind replay --verdict PASS --goal g1
    [ "$status" -eq 0 ]
    [[ "$output" == *"recorded executor replay PASS"* ]]

    run bash "$SCRIPT" --list --db "$DB"
    [ "$status" -eq 0 ]
    [ "${#lines[@]}" -eq 1 ]
    [[ "${lines[0]}" == *"sess-a"* ]]
    [[ "${lines[0]}" == *$'\texecutor\treplay\tPASS\t'* ]]
    [[ "${lines[0]}" == *"plan-test.md"* ]]
    [[ "${lines[0]}" == *"abc1234"* ]]
}

@test "independent FAIL row with a 300-char note: recorded, note truncated, JSON still valid" {
    local note
    note=$(printf '%0300d' 0 | tr 0 n)
    [ "${#note}" -eq 300 ]

    run bash "$SCRIPT" --db "$DB" --session sess-b --plan "$PLAN" --commit none \
        --role validator --kind independent --verdict FAIL --note "$note"
    [ "$status" -eq 0 ]
    [[ "$output" == *"recorded validator independent FAIL"* ]]

    run sqlite3 "$DB" "select json_valid(context), length(json_extract(context,'\$.note')), json_extract(context,'\$.verdict_kind'), json_extract(context,'\$.verdict') from evidence where event='pattern_f_verdict';"
    [ "$status" -eq 0 ]
    [ "$output" = "1|100|independent|FAIL" ]

    run bash "$SCRIPT" --list --db "$DB" --session sess-b
    [ "$status" -eq 0 ]
    [ "${#lines[@]}" -eq 1 ]
    [[ "${lines[0]}" == *$'\tvalidator\tindependent\tFAIL\t'* ]]
}

@test "missing register exits 3 and names it" {
    run bash "$SCRIPT" --db "$PROJ/nope.db" --session sess-c --plan "$PLAN" --commit none \
        --role executor --kind replay --verdict PASS
    [ "$status" -eq 3 ]
    [[ "$output" == *"register missing"* ]]
    [[ "$output" == *"nope.db"* ]]
}

@test "invalid --kind exits 2 with usage and writes nothing" {
    run bash "$SCRIPT" --db "$DB" --session sess-d --plan "$PLAN" --commit none \
        --role executor --kind bogus --verdict PASS
    [ "$status" -eq 2 ]
    [[ "$output" == *"usage:"* ]]

    run sqlite3 "$DB" "select count(*) from evidence where event='pattern_f_verdict';"
    [ "$status" -eq 0 ]
    [ "$output" = "0" ]
}

@test "--list --session shows only that session's rows" {
    run bash "$SCRIPT" --db "$DB" --session sess-x --plan "$PLAN" --commit none \
        --role executor --kind replay --verdict PASS
    [ "$status" -eq 0 ]
    run bash "$SCRIPT" --db "$DB" --session sess-y --plan "$PLAN" --commit none \
        --role validator --kind replay --verdict FAIL --criterion "bats tests/shell/example.bats"
    [ "$status" -eq 0 ]

    run bash "$SCRIPT" --list --db "$DB"
    [ "$status" -eq 0 ]
    [ "${#lines[@]}" -eq 2 ]

    run bash "$SCRIPT" --list --db "$DB" --session sess-x
    [ "$status" -eq 0 ]
    [ "${#lines[@]}" -eq 1 ]
    [[ "${lines[0]}" == *"sess-x"* ]]
    [[ "$output" != *"sess-y"* ]]
}
