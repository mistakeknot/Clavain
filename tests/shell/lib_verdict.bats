#!/usr/bin/env bats
# mk-0qjva, mk-4c909, mk-8m912, mk-0ud4q, mk-n37ml, mk-z770:
# one shared verdict classifier, used by the review receipt and the .verdict sidecar.

bats_require_minimum_version 1.5.0

setup() {
    load test_helper
    T="$(mktemp -d)"
    LIB="$BATS_TEST_DIRNAME/../../scripts/lib-verdict.sh"
    DISPATCH="$BATS_TEST_DIRNAME/../../scripts/dispatch.sh"
    # shellcheck disable=SC1090
    source "$LIB"
    # shellcheck disable=SC1090
    source "$BATS_TEST_DIRNAME/../../scripts/lib-review-receipt.sh"
    OUTPUT="$T/out.md"
    VERDICT_FILE="${OUTPUT}.verdict"
    HELPERS="$T/helpers.sh"
    printf 'source %q\n' "$LIB" > "$HELPERS"
    awk '/^_extract_verdict\(\)[[:space:]]*\{/ { emit=1 }
         emit { print; if ($0 ~ /^}[[:space:]]*$/) { emit=0 } }' "$DISPATCH" >> "$HELPERS"
}
teardown() { rm -rf "$T"; }

@test "word class: PASS, PASS WITH NOTES (space, hyphen, underscore), FAIL and BLOCK" {
    [ "$(verdict_word_class PASS)" = PASS ]
    [ "$(verdict_word_class 'pass.')" = PASS ]
    [ "$(verdict_word_class ' PASS ')" = PASS ]
    for w in 'PASS WITH NOTES' 'pass with notes' 'PASS-WITH-NOTES' 'Pass-With-Notes' 'PASS_WITH_NOTES' 'PASS WITH NOTES.'; do
        [ "$(verdict_word_class "$w")" = PASS_WITH_NOTES ]
    done
    for w in FAIL fail BLOCK block 'FAIL (reason)' 'BLOCK: reason' 'FAIL - reason'; do
        [ "$(verdict_word_class "$w")" = FAIL ]
    done
}

@test "word class: anything else is UNKNOWN, never PASS or FAIL" {
    for w in APPROVE approve CLEAN BLOCKED FAILED PASSING 'PASS WITH' 'PASS WITH CAVEATS' \
        'PASS (explanation)' 'PASS - no, blocked' 'PASS / FAIL' 'PASS or BLOCK' '' 'changes requested'; do
        [ "$(verdict_word_class "$w")" = UNKNOWN ]
    done
}

@test "label word: reads the word after VERDICT, bold wrappers allowed; not a label line returns 1" {
    [ "$(verdict_label_word 'VERDICT: PASS')" = PASS ]
    [ "$(verdict_label_word '**VERDICT: PASS WITH NOTES**')" = 'PASS WITH NOTES' ]
    [ "$(verdict_label_word '**VERDICT:** BLOCK')" = BLOCK ]
    [ "$(verdict_label_word 'verdict: approve')" = approve ]
    run verdict_label_word 'Findings: none'; [ "$status" -eq 1 ]
    run verdict_label_word 'STATUS: pass'; [ "$status" -eq 1 ]
}

# CLEAN is the one deliberate difference: a legacy completion word the sidecar
# still reads for non-review roles, which the cross-lab receipt never accepts.
# Parity: the receipt and the sidecar must classify the same final-line word the
# same way. A receipt pass must be a sidecar pass, a receipt UNKNOWN must not be
# a sidecar pass, and a receipt BLOCK must not be a sidecar pass.
@test "parity: receipt verdict and sidecar status agree for every word" {
    source "$HELPERS"
    while IFS='|' read -r word want_receipt want_status; do
        printf 'Reviewed the change.\n\nVERDICT: %s\n' "$word" > "$OUTPUT"
        rm -f "$VERDICT_FILE"
        got_receipt="$(_review_receipt_verdict "$OUTPUT" 2>/dev/null)"
        _extract_verdict "$OUTPUT" 2>/dev/null
        got_status="$(sed -n 's/^STATUS: //p' "$VERDICT_FILE" | head -1)"
        [ "$got_receipt" = "$want_receipt" ] || { echo "receipt for '$word': $got_receipt != $want_receipt"; false; }
        [ "$got_status" = "$want_status" ] || { echo "sidecar for '$word': $got_status != $want_status"; false; }
    done <<'TABLE'
PASS|PASS|pass
PASS WITH NOTES|PASS WITH NOTES|pass
PASS-WITH-NOTES|PASS WITH NOTES|pass
PASS_WITH_NOTES|PASS WITH NOTES|pass
FAIL|BLOCK|warn
BLOCK|BLOCK|warn
APPROVE|UNKNOWN|warn
CLEAN|UNKNOWN|pass
PASS (but not really)|UNKNOWN|warn
TABLE
}

# --- mk-z770: role verdict-block suffix and the REVIEW field ----------------

@test "role suffix: nothing for cross-lab-review or an empty role" {
    [ -z "$(verdict_role_suffix cross-lab-review '' 'review this')" ]
    [ -z "$(verdict_role_suffix cross-lab-review different-model 'review this')" ]
    [ -z "$(verdict_role_suffix '' '' 'do this')" ]
}

@test "role suffix: nothing when the prompt carries the findings contract" {
    [ -z "$(verdict_role_suffix plan-review '' $'### Findings Index\n- x')" ]
    [ -z "$(verdict_role_suffix plan-review '' $'Findings Index\nVerdict: needs-changes')" ]
    [ -z "$(verdict_role_suffix validation different-model $'x\nVerdict: safe')" ]
}

@test "role suffix: review roles get REVIEW with STATUS: warn, never STATUS: pass" {
    for args in "plan-review ''" "validation ''" "implementation different-model"; do
        eval "out=\"\$(verdict_role_suffix $args 'plain prompt')\""
        [[ "$out" == *"STATUS: warn"* ]]
        [[ "$out" == *"REVIEW: approve"* ]]
        [[ "$out" == *"approve-with-changes"* ]]
        [[ "$out" != *"STATUS: pass"* ]]
    done
}

@test "role suffix: other roles get the completion block without REVIEW" {
    out="$(verdict_role_suffix implementation '' 'plain prompt')"
    [[ "$out" == *"STATUS: pass"* ]]
    [[ "$out" != *"REVIEW:"* ]]
}

@test "REVIEW in the block caps a declared pass at warn, for every value" {
    source "$HELPERS"
    for rv in approve approve-with-changes revise reject nonsense; do
        printf 'Looks fine.\n\n--- VERDICT ---\nSTATUS: pass\nREVIEW: %s\nFILES: 0 changed\nFINDINGS: 0 (P0: 0, P1: 0, P2: 0)\nSUMMARY: ok\n---\n' "$rv" > "$OUTPUT"
        rm -f "$VERDICT_FILE"
        _extract_verdict "$OUTPUT" 2>/dev/null
        [ "$(sed -n 's/^STATUS: //p' "$VERDICT_FILE" | head -1)" = warn ] || { echo "REVIEW: $rv"; cat "$VERDICT_FILE"; false; }
    done
}

@test "REVIEW does not soften a declared fail" {
    source "$HELPERS"
    printf 'Bad.\n\n--- VERDICT ---\nSTATUS: fail\nREVIEW: reject\nFILES: 0 changed\nFINDINGS: 1 (P0: 1, P1: 0, P2: 0)\nSUMMARY: bad\n---\n' > "$OUTPUT"
    _extract_verdict "$OUTPUT" 2>/dev/null
    [ "$(sed -n 's/^STATUS: //p' "$VERDICT_FILE" | head -1)" = fail ]
}

@test "a block without REVIEW still reads STATUS: pass as pass (no behaviour change)" {
    source "$HELPERS"
    printf 'Done.\n\n--- VERDICT ---\nSTATUS: pass\nFILES: 0 changed\nFINDINGS: 0 (P0: 0, P1: 0, P2: 0)\nSUMMARY: ok\n---\n' > "$OUTPUT"
    _extract_verdict "$OUTPUT" 2>/dev/null
    [ "$(sed -n 's/^STATUS: //p' "$VERDICT_FILE" | head -1)" = pass ]
}

@test "sidecar: PASS-WITH-NOTES on the last line and on the first line is a pass" {
    source "$HELPERS"
    for w in PASS-WITH-NOTES PASS_WITH_NOTES; do
        printf 'Notes below.\n\nVERDICT: %s\n' "$w" > "$OUTPUT"
        rm -f "$VERDICT_FILE"; _extract_verdict "$OUTPUT" 2>/dev/null
        [ "$(sed -n 's/^STATUS: //p' "$VERDICT_FILE" | head -1)" = pass ]
        printf 'VERDICT: %s\n\nNotes below.\n' "$w" > "$OUTPUT"
        rm -f "$VERDICT_FILE"; _extract_verdict "$OUTPUT" 2>/dev/null
        [ "$(sed -n 's/^STATUS: //p' "$VERDICT_FILE" | head -1)" = pass ]
    done
}

@test "dispatch.sh sources the shared library before the receipt library" {
    a="$(grep -n 'lib-verdict.sh' "$DISPATCH" | head -1 | cut -d: -f1)"
    b="$(grep -n 'lib-review-receipt.sh' "$DISPATCH" | head -1 | cut -d: -f1)"
    [ -n "$a" ] && [ -n "$b" ] && [ "$a" -lt "$b" ]
}
