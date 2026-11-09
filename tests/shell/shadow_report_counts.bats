#!/usr/bin/env bats
# The two shadow-report scripts count log lines with `grep -c`. When a count is
# zero, grep prints 0 and exits 1; the old `|| echo "0"` then produced "0\n0",
# and the arithmetic that followed aborted the report. These tests feed each
# report lines that leave at least one count at zero. (Sweep bead mk-47vtm.8.)

setup() {
    SCRIPTS_DIR="$BATS_TEST_DIRNAME/../../scripts"
    STUB_BIN="$BATS_TEST_TMPDIR/bin"
    mkdir -p "$STUB_BIN"
    # A stand-in for the session-search tool: prints whatever the test stored.
    cat > "$STUB_BIN/cass" <<'STUB'
#!/usr/bin/env bash
printf '%s\n' "$*" >> "$CASS_ARGS_LOG"
cat "$CASS_OUTPUT"
STUB
    chmod +x "$STUB_BIN/cass"
    export CASS_OUTPUT="$BATS_TEST_TMPDIR/cass-output.txt"
    export CASS_ARGS_LOG="$BATS_TEST_TMPDIR/cass-args.log"
    : > "$CASS_ARGS_LOG"
    export PATH="$STUB_BIN:$PATH"
}

@test "B2 report: no downgrades and no upgrades still reports" {
    printf '%s\n' \
        '[B2-shadow] complexity=C3 inherits model (phase=executing category=review)' \
        '[B2-shadow] complexity=C3 inherits model (phase=planning category=research)' \
        > "$CASS_OUTPUT"
    run bash "$SCRIPTS_DIR/routing-shadow-report.sh"
    [ "$status" -eq 0 ]
    [[ "$output" == *"Total events:  2"* ]]
    [[ "$output" == *"Downgrades:    0 (cost savings)"* ]]
    [[ "$output" == *"Upgrades:      0 (quality boost)"* ]]
    [[ "$output" == *"No change:     2"* ]]
}

@test "B2 report: downgrades are counted once" {
    printf '%s\n' \
        '[B2-shadow] complexity=C2 would change model: sonnet → haiku (phase=executing category=review)' \
        '[B2-shadow] complexity=C3 inherits model (phase=planning category=research)' \
        > "$CASS_OUTPUT"
    run bash "$SCRIPTS_DIR/routing-shadow-report.sh"
    [ "$status" -eq 0 ]
    [[ "$output" == *"Downgrades:    1 (cost savings)"* ]]
    [[ "$output" == *"Upgrades:      0 (quality boost)"* ]]
    [[ "$output" == *"No change:     1"* ]]
}

@test "B2 report: --days N sets the period" {
    : > "$CASS_OUTPUT"
    run bash "$SCRIPTS_DIR/routing-shadow-report.sh" --days 14
    [ "$status" -eq 0 ]
    [[ "$output" == *"Period: last 14 days"* ]]
    grep -q -- '--since 14d' "$CASS_ARGS_LOG"
}

@test "B2 report: a bare number is still the day count" {
    : > "$CASS_OUTPUT"
    run bash "$SCRIPTS_DIR/routing-shadow-report.sh" 3
    [ "$status" -eq 0 ]
    [[ "$output" == *"Period: last 3 days"* ]]
}

@test "B2 report: --days without a number is a usage error" {
    : > "$CASS_OUTPUT"
    run bash "$SCRIPTS_DIR/routing-shadow-report.sh" --days soon
    [ "$status" -eq 2 ]
    [[ "$output" == *"--days needs a whole number"* ]]
}

@test "B5 report: no local routes and no outages still reports" {
    printf '%s\n' \
        '[B5-shadow] complexity=C1 ineligible: fd-safety' \
        '[B5-shadow] complexity=C2 ineligible: fd-correctness' \
        > "$CASS_OUTPUT"
    run bash "$SCRIPTS_DIR/routing-b5-shadow-report.sh"
    [ "$status" -eq 0 ]
    [[ "$output" == *"Total events:      2"* ]]
    [[ "$output" == *"Would route local: 0"* ]]
    [[ "$output" == *"Ineligible:        2 (safety floor agents)"* ]]
    [[ "$output" == *"Unavailable:       0 (interfer down)"* ]]
    [[ "$output" == *"Verdict: NOT READY"* ]]
}

@test "B5 report: --days N sets the period" {
    : > "$CASS_OUTPUT"
    run bash "$SCRIPTS_DIR/routing-b5-shadow-report.sh" --days 30
    [ "$status" -eq 0 ]
    [[ "$output" == *"Period: last 30 days"* ]]
    grep -q -- '--since 30d' "$CASS_ARGS_LOG"
}
