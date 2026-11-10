#!/usr/bin/env bats
# --help on these scripts prints the header comment. Each one used a fixed line
# range that had drifted from the header, so help either leaked code or stopped
# before the Usage block and the exit codes.

setup() {
    SCRIPTS="$BATS_TEST_DIRNAME/../../scripts"
}

# Every line of help output is a comment line: no code leaked past the header.
assert_only_comments() {
    local line
    while IFS= read -r line; do
        [[ "$line" == "#"* ]] || { echo "not a comment line: $line"; return 1; }
    done <<< "$output"
}

@test "nested-repo-freshness --help prints the header and no code" {
    run bash "$SCRIPTS/nested-repo-freshness.sh" --help
    [ "$status" -eq 0 ]
    assert_only_comments
    [[ "$output" == *"--root DIR"* ]]
    [[ "$output" == *"Exit code:"* ]]
}

@test "nested-repo-freshness --root without a value is a usage error, not a hang" {
    run timeout 10 bash "$SCRIPTS/nested-repo-freshness.sh" --root
    [ "$status" -eq 2 ]
    [[ "$output" == *"--root needs a directory"* ]]
}

@test "next-goal-verify --help reaches the Usage block and the exit codes" {
    run bash "$SCRIPTS/next-goal-verify.sh" --help
    [ "$status" -eq 0 ]
    assert_only_comments
    [[ "$output" == *"Usage:"* ]]
    [[ "$output" == *"--recommend"* ]]
    [[ "$output" == *"Exit: 0"* ]]
}

@test "review-round --help lists every flag the parser accepts and the exit codes" {
    run bash "$SCRIPTS/review-round.sh" --help
    [ "$status" -eq 0 ]
    assert_only_comments
    [[ "$output" == *"Exit: 0 receipt"* ]]
    [[ "$output" == *"12 --prior-head is not an"* ]]
    local usage flag
    usage=$(sed -n '/^# Usage:/,/^#$/p' <<< "$output")
    while IFS= read -r flag; do
        [[ "$usage" == *"$flag"* ]] || { echo "Usage omits $flag"; return 1; }
    done < <(grep -oE '^    --[a-z-]+\)' "$SCRIPTS/review-round.sh" | tr -d ' )')
}
