#!/usr/bin/env bats

# Tripwire for the verdict-grounding invariant (Sylveste-4b5.5, verdict-
# integrity goal 2026-08-24): a "clean" that nothing concrete corroborates
# must surface as NEEDS_VERIFICATION, never advance a phase, and the check
# itself must live where edits to the command doc cannot silently drop it.
# This suite executes the ACTUAL Phase 3a0 grounding block extracted from
# commands/quality-gates.md — if the fence is edited into vacuity, these
# tests fail with it.

setup() {
    load test_helper

    QG_DOC="$BATS_TEST_DIRNAME/../../commands/quality-gates.md"
    TMPDIR_T="$(mktemp -d)"

    # Extract the first bash fence after the "### 3a0" heading.
    GROUNDING="$TMPDIR_T/grounding.sh"
    awk '
        /^### 3a0/ { in_section=1 }
        in_section && /^```bash$/ { in_fence=1; next }
        in_fence && /^```$/ { exit }
        in_fence { print }
    ' "$QG_DOC" > "$GROUNDING"
    [ -s "$GROUNDING" ] || { echo "3a0 grounding block not found in quality-gates.md" >&2; return 1; }

    # Sandbox repo with one commit, so HEAD exists.
    SANDBOX="$TMPDIR_T/repo"
    mkdir -p "$SANDBOX"
    git -C "$SANDBOX" init -q
    git -C "$SANDBOX" -c user.email=t@t -c user.name=t commit -q --allow-empty -m x
    HEAD_SHA="$(git -C "$SANDBOX" rev-parse HEAD)"

    # Fake clavain-cli: get-artifact answers from $TMPDIR_T/artifact, or fails.
    BINDIR="$TMPDIR_T/bin"
    mkdir -p "$BINDIR"
    cat > "$BINDIR/clavain-cli" <<'FAKE'
#!/usr/bin/env bash
if [[ "$1" == "get-artifact" && "$3" == "test-pass-sha" && -f "${FAKE_ARTIFACT_FILE}" ]]; then
    cat "${FAKE_ARTIFACT_FILE}"
    exit 0
fi
exit 1
FAKE
    chmod +x "$BINDIR/clavain-cli"
}

teardown() {
    rm -rf "$TMPDIR_T"
}

# Runs the extracted block inside the sandbox repo and reports:
# "grounded=<value>" plus whether grounding.json exists and its status.
_run_grounding() {
    ( cd "$SANDBOX" &&
      PATH="$BINDIR:$PATH" \
      FAKE_ARTIFACT_FILE="${FAKE_ARTIFACT_FILE:-}" \
      CLAVAIN_BEAD_ID="${CLAVAIN_BEAD_ID:-}" \
      DIFF_PATH="${DIFF_PATH:-/nonexistent}" \
      results_path="${results_path:-}" \
      bash -c '
        source "'"$GROUNDING"'"
        echo "grounded=${GROUNDED}"
        if [[ -f .clavain/verdicts/grounding.json ]]; then
            jq -r '"'"'"status=" + .status + " state=" + .verification_state'"'"' .clavain/verdicts/grounding.json
        else
            echo "no-grounding-verdict"
        fi
      ' )
}

@test "ungrounded clean → NEEDS_VERIFICATION verdict written" {
    export CLAVAIN_BEAD_ID="iv-test"
    run _run_grounding
    [ "$status" -eq 0 ]
    [[ "$output" != *"grounded=test-pass-sha"* && "$output" != *"grounded=criteria-results"* ]]
    [[ "$output" == *"status=NEEDS_VERIFICATION state=UNVERIFIABLE"* ]]
}

@test "test-pass-sha at HEAD → grounded, no downgrade" {
    export CLAVAIN_BEAD_ID="iv-test"
    export FAKE_ARTIFACT_FILE="$TMPDIR_T/artifact"
    printf '%s' "$HEAD_SHA" > "$FAKE_ARTIFACT_FILE"
    run _run_grounding
    [ "$status" -eq 0 ]
    [[ "$output" == *"grounded=test-pass-sha@HEAD"* ]]
    [[ "$output" == *"no-grounding-verdict"* ]]
}

@test "STALE test-pass-sha (predates HEAD) → still NEEDS_VERIFICATION" {
    export CLAVAIN_BEAD_ID="iv-test"
    export FAKE_ARTIFACT_FILE="$TMPDIR_T/artifact"
    printf '%s' "0000000000000000000000000000000000000000" > "$FAKE_ARTIFACT_FILE"
    run _run_grounding
    [ "$status" -eq 0 ]
    [[ "$output" == *"status=NEEDS_VERIFICATION state=UNVERIFIABLE"* ]]
}

@test "fresh CONFORMANCE: PASS grounds the verdict without test-pass-sha" {
    export CLAVAIN_BEAD_ID="iv-test"
    export DIFF_PATH="$TMPDIR_T/diff.txt"
    export results_path="$TMPDIR_T/results.md"
    : > "$DIFF_PATH"
    sleep 0.01
    printf 'criterion | pass | ok\nCONFORMANCE: PASS\n' > "$results_path"
    run _run_grounding
    [ "$status" -eq 0 ]
    [[ "$output" == *"grounded=criteria-results"* ]]
    [[ "$output" == *"no-grounding-verdict"* ]]
}

@test "CONFORMANCE: FAIL does not ground anything" {
    export CLAVAIN_BEAD_ID="iv-test"
    export DIFF_PATH="$TMPDIR_T/diff.txt"
    export results_path="$TMPDIR_T/results.md"
    : > "$DIFF_PATH"
    printf 'criterion | fail | broken\nCONFORMANCE: FAIL\n' > "$results_path"
    run _run_grounding
    [ "$status" -eq 0 ]
    [[ "$output" == *"status=NEEDS_VERIFICATION state=UNVERIFIABLE"* ]]
}

# The tripwire's tripwire: the doc must keep an extractable 3a0 block. If the
# section is renamed or the fence dropped, setup() fails every test above —
# but say it plainly here too.
@test "quality-gates.md still carries the 3a0 grounding fence" {
    grep -q "### 3a0" "$QG_DOC"
    grep -q "NEEDS_VERIFICATION" "$QG_DOC"
    grep -q "test-pass-sha" "$QG_DOC"
}
