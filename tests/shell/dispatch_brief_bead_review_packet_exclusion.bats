#!/usr/bin/env bats

# Regression test for mk-42j9.44 cross-lab review finding P1 #9: the
# opt-in review-packet boundary's exclusion list (plan step 4) rejects a
# positional prompt, --prompt-file, --template, --inject-docs and images
# combined with --review-input/--review-packet, but did not reject
# --brief-bead -- a verified review packet is meant to be the *entire*
# prompt (doc: "cannot combine a positional prompt, --prompt-file,
# --template, --inject-docs, images, or backend passthrough"), and a
# prepended role briefing silently violated that boundary.

setup() {
    load test_helper

    DISPATCH_SCRIPT="$BATS_TEST_DIRNAME/../../scripts/dispatch.sh"
    TMPDIR_T="$(mktemp -d)"

    HELPERS="$TMPDIR_T/helpers.sh"
    awk '
        /^_dispatch_prepare_review_packet\(\)[[:space:]]*\{/ { emit=1 }
        emit {
            print
            if ($0 ~ /^}[[:space:]]*$/) { emit=0 }
        }
    ' "$DISPATCH_SCRIPT" > "$HELPERS"
    # Sanity: the extraction actually captured the function body, not an
    # empty file (a rename of the function would otherwise silently pass).
    grep -q "cannot combine" "$HELPERS"
}

teardown() {
    rm -rf "$TMPDIR_T"
}

_load() {
    # shellcheck disable=SC1090
    source "$HELPERS"
}

@test "review-packet boundary rejects --brief-bead combined with --review-input" {
    _load
    ROLE="plan-review"
    REVIEW_INPUT="$TMPDIR_T/input.json"
    REVIEW_PACKET=""
    PLAN_FILE=""
    PROMPT_FILE=""
    TEMPLATE_FILE=""
    INJECT_DOCS=""
    BRIEF_BEAD="mk-42j9.44"
    IMAGES=()
    EXTRA_ARGS=()

    run _dispatch_prepare_review_packet ""
    [ "$status" -ne 0 ]
    [[ "$output" == *"--brief-bead"* ]]
    [[ "$output" == *"cannot combine"* ]]
}

@test "review-packet boundary still rejects the previously-covered cases (no regression)" {
    _load
    ROLE="validation"
    REVIEW_INPUT="$TMPDIR_T/input.json"
    REVIEW_PACKET=""
    PLAN_FILE=""
    PROMPT_FILE="$TMPDIR_T/prompt.txt"
    TEMPLATE_FILE=""
    INJECT_DOCS=""
    BRIEF_BEAD=""
    IMAGES=()
    EXTRA_ARGS=()

    run _dispatch_prepare_review_packet ""
    [ "$status" -ne 0 ]
    [[ "$output" == *"--prompt-file"* ]]
}

@test "review-packet boundary allows a plain review-input dispatch with no briefing, no prompt file" {
    _load
    ROLE="cross-lab-review"
    REVIEW_INPUT=""
    REVIEW_PACKET=""
    PLAN_FILE=""
    PROMPT_FILE=""
    TEMPLATE_FILE=""
    INJECT_DOCS=""
    BRIEF_BEAD=""
    IMAGES=()
    EXTRA_ARGS=()

    run _dispatch_prepare_review_packet ""
    # Reaches past the exclusion checks to "REVIEW_PACKET not found" /
    # verify-step failure (no real packet exists in this unit test) -- what
    # matters here is that it is NOT rejected by the exclusion-list check
    # itself, i.e. it must not mention --brief-bead or --prompt-file etc.
    [[ "$output" != *"cannot combine"* ]]
}
