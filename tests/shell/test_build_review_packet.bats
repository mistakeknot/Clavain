#!/usr/bin/env bats
# Step 1 (mk-42j9.34): deterministic review-packet builder interface.
# No model or live tracker calls; every fixture is local files + a scratch
# git repo built in setup().

setup() {
    REPO_ROOT="$(cd "$BATS_TEST_DIRNAME/../.." && pwd)"
    BUILDER="$REPO_ROOT/scripts/build-review-packet.py"
    load "$BATS_TEST_DIRNAME/review_packet_helper.bash"
    review_packet_fixture_setup
    review_packet_fixture_install_fake_ic
}

teardown() {
    review_packet_fixture_teardown
}

build() {
    run python3 "$BUILDER" --input "$INPUT_JSON" --output-dir "$OUTPUT_DIR"
}

@test "packet contains every required section" {
    build
    [ "$status" -eq 0 ]
    packet_path="$output"
    [ -f "$packet_path" ]

    for section in "Review contract" "Acceptance criteria" "Producer receipt" \
        "Scope" "Diff or plan" "Touched-file excerpts" "Test output" \
        "Prior-review disposition" "Focused review asks" "Attached" \
        "Requested output"; do
        grep -qF "## $section" "$packet_path" || {
            echo "missing section: $section" >&2
            false
        }
    done

    # Order matters: contract and criteria are stable and come first.
    contract_line="$(grep -n '^## Review contract' "$packet_path" | cut -d: -f1)"
    criteria_line="$(grep -n '^## Acceptance criteria' "$packet_path" | cut -d: -f1)"
    scope_line="$(grep -n '^## Scope' "$packet_path" | cut -d: -f1)"
    [ "$contract_line" -lt "$criteria_line" ]
    [ "$criteria_line" -lt "$scope_line" ]

    # Real content, not just headings: fixture criteria text and the diff hunk
    # actually appear.
    grep -qF "Fixture criteria must hold." "$packet_path"
    grep -qF "line two CHANGED" "$packet_path"
    grep -qF "fixture-1" "$packet_path"
    # Notes must never be pulled in wholesale.
    ! grep -qF "irrelevant notes that must never be emitted" "$packet_path"

    # A manifest sits alongside the packet with source hashes.
    manifest_path="$(dirname "$packet_path")/manifest.json"
    [ -f "$manifest_path" ]
    jq -e '.packet_sha256 | type == "string" and length == 64' "$manifest_path"
    jq -e '.sources | type == "array" and length > 0' "$manifest_path"
}

@test "plan packet records tests unrun explicitly" {
    review_packet_fixture_patch '. + {tests: null, tests_not_run: "no tests were run against this fixture"}'

    build
    [ "$status" -eq 0 ]
    packet_path="$output"
    grep -qF "UNRUN" "$packet_path"
    grep -qF "no tests were run against this fixture" "$packet_path"
}

@test "missing criteria or producer evidence fails without publishing" {
    # Bead has no acceptance_criteria at all.
    review_packet_fixture_patch '.beads_file = "beads_empty.json"'
    jq '.[0].acceptance_criteria = ""' "$INPUT_DIR/beads.json" > "$INPUT_DIR/beads_empty.json"

    build
    [ "$status" -eq 2 ]
    [ -z "$(find "$OUTPUT_DIR" -mindepth 1 2>/dev/null)" ]

    # Reset, then break the producer receipt instead: not terminal.
    review_packet_fixture_setup
    review_packet_fixture_install_fake_ic
    review_packet_fixture_patch '.producer_receipt = "producer_receipt.json"'
    jq '.terminal = false' "$INPUT_DIR/producer_receipt.json" > "$INPUT_DIR/producer_receipt.json.tmp"
    mv "$INPUT_DIR/producer_receipt.json.tmp" "$INPUT_DIR/producer_receipt.json"

    build
    [ "$status" -eq 2 ]
    [ -z "$(find "$OUTPUT_DIR" -mindepth 1 2>/dev/null)" ]
}

@test "same inputs produce identical bytes" {
    build
    [ "$status" -eq 0 ]
    first_packet="$output"
    first_bytes="$(cat "$first_packet")"
    first_id="$(basename "$(dirname "$first_packet")")"

    out2="$FIXTURE_DIR/output2"
    mkdir -p "$out2"
    run python3 "$BUILDER" --input "$INPUT_JSON" --output-dir "$out2"
    [ "$status" -eq 0 ]
    second_packet="$output"
    second_bytes="$(cat "$second_packet")"
    second_id="$(basename "$(dirname "$second_packet")")"

    [ "$first_id" = "$second_id" ]
    [ "$first_bytes" = "$second_bytes" ]

    # Rebuilding into the same output-dir returns the existing path unchanged.
    run python3 "$BUILDER" --input "$INPUT_JSON" --output-dir "$OUTPUT_DIR"
    [ "$status" -eq 0 ]
    [ "$output" = "$first_packet" ]
}

@test "multiple repositories and beads remain distinguishable" {
    review_packet_fixture_patch '.bead_ids += ["fixture-2"]'
    jq '. + [{"id": "fixture-2", "title": "Second fixture bead", "acceptance_criteria": "Second criteria."}]' \
        "$INPUT_DIR/beads.json" > "$INPUT_DIR/beads.json.tmp"
    mv "$INPUT_DIR/beads.json.tmp" "$INPUT_DIR/beads.json"

    REPO2_DIR="$FIXTURE_DIR/repo2"
    mkdir -p "$REPO2_DIR"
    git -C "$REPO2_DIR" init -q
    git -C "$REPO2_DIR" config user.email test@example.com
    git -C "$REPO2_DIR" config user.name test
    printf 'second repo base\n' > "$REPO2_DIR/other.txt"
    git -C "$REPO2_DIR" add other.txt
    git -C "$REPO2_DIR" commit -qm base2
    BASE2_SHA="$(git -C "$REPO2_DIR" rev-parse HEAD)"
    printf 'second repo CHANGED\n' > "$REPO2_DIR/other.txt"
    git -C "$REPO2_DIR" commit -qam head2
    HEAD2_SHA="$(git -C "$REPO2_DIR" rev-parse HEAD)"

    review_packet_fixture_patch ".changes += [{\"repo\": \"$REPO2_DIR\", \"base\": \"$BASE2_SHA\", \"head\": \"$HEAD2_SHA\"}]"

    build
    [ "$status" -eq 0 ]
    packet_path="$output"
    grep -qF "fixture-1" "$packet_path"
    grep -qF "fixture-2" "$packet_path"
    grep -qF "Second criteria." "$packet_path"
    grep -qF "$REPO_DIR" "$packet_path"
    grep -qF "$REPO2_DIR" "$packet_path"
    grep -qF "second repo CHANGED" "$packet_path"
}

@test "unknown schema version and unknown keys are rejected" {
    review_packet_fixture_patch '.schema_version = 2'
    build
    [ "$status" -eq 2 ]

    review_packet_fixture_setup
    review_packet_fixture_patch '. + {unexpected_field: "nope"}'
    build
    [ "$status" -eq 2 ]
}

@test "duplicate bead IDs are rejected" {
    review_packet_fixture_patch '.bead_ids += ["fixture-1"]'
    build
    [ "$status" -eq 2 ]
}

@test "tests and tests_not_run are mutually exclusive" {
    review_packet_fixture_patch '. + {tests_not_run: "should not coexist with tests"}'
    build
    [ "$status" -eq 2 ]
}

@test "verify validates an existing packet without rebuilding" {
    build
    [ "$status" -eq 0 ]
    packet_path="$output"

    run python3 "$BUILDER" --verify "$packet_path"
    [ "$status" -eq 0 ]
    [ "$output" = "$packet_path" ]
}

@test "verify fails on a tampered packet without a verdict" {
    build
    [ "$status" -eq 0 ]
    packet_path="$output"
    printf '\ntampered\n' >> "$packet_path"

    run python3 "$BUILDER" --verify "$packet_path"
    [ "$status" -ne 0 ]
    ! echo "$output" | grep -qi "verdict"
}

# --- Step 2: producer attribution reuse and transcript-input rejection -----

@test "producer identity follows the executed fallback" {
    # The receipt declares codex/gpt-6-astra; ic route identity agrees; ic
    # route list has a matching terminal attempt. Build must succeed and the
    # rendered packet must show the EXECUTED identity, not a requested one.
    build
    [ "$status" -eq 0 ]
    grep -q '`gpt-6-astra`' "$output"
    grep -q "route list" "$FIXTURE_DIR/ic.log"
    grep -q "route identity" "$FIXTURE_DIR/ic.log"
}

@test "failed or unidentified producer is rejected" {
    # ic route list has no record for this dispatch/attempt at all.
    printf '[]\n' > "$IC_ROUTE_LIST_JSON"
    build
    [ "$status" -eq 2 ]

    # ic route identity disagrees with the receipt's declared model_identity.
    review_packet_fixture_setup
    review_packet_fixture_install_fake_ic
    printf '{"canonical_identity":"claude-opus-5-5"}\n' > "$IC_IDENTITY_JSON"
    build
    [ "$status" -eq 2 ]

    # Receipt is missing attempt_id entirely.
    review_packet_fixture_setup
    review_packet_fixture_install_fake_ic
    review_packet_fixture_patch '.producer_receipt = "producer_receipt.json"'
    jq 'del(.attempt_id)' "$INPUT_DIR/producer_receipt.json" > "$INPUT_DIR/producer_receipt.json.tmp"
    mv "$INPUT_DIR/producer_receipt.json.tmp" "$INPUT_DIR/producer_receipt.json"
    build
    [ "$status" -eq 2 ]
}

@test "receipt event-log pointers are never followed" {
    jq '.execution.event_log = "/should/never/be/read.jsonl"' \
        "$INPUT_DIR/producer_receipt.json" > "$INPUT_DIR/producer_receipt.json.tmp"
    mv "$INPUT_DIR/producer_receipt.json.tmp" "$INPUT_DIR/producer_receipt.json"
    review_packet_fixture_install_fake_ic

    build
    [ "$status" -eq 0 ]
    ! grep -qF "/should/never/be/read.jsonl" "$output"
}

@test "transcript shaped test output is rejected without echoing content" {
    local canary="THE-SECRET-ASSISTANT-REPLY-MUST-NOT-APPEAR"

    # Claude session JSONL.
    printf '{"type":"user","message":{"role":"user","content":"hi"}}\n{"type":"assistant","message":{"role":"assistant","content":"%s"}}\n' \
        "$canary" > "$INPUT_DIR/claude-transcript.jsonl"
    review_packet_fixture_patch '.tests[0].path = "claude-transcript.jsonl"'
    build
    [ "$status" -eq 2 ]
    ! echo "$output" | grep -qF "$canary"
    [ -z "$(find "$OUTPUT_DIR" -mindepth 1 2>/dev/null)" ]

    # Codex response_item JSONL.
    review_packet_fixture_setup
    review_packet_fixture_install_fake_ic
    printf '{"type":"response_item","item":{"type":"reasoning","text":"%s"}}\n{"type":"response_item","item":{"type":"message","role":"assistant","content":"%s"}}\n' \
        "$canary" "$canary" > "$INPUT_DIR/codex-transcript.jsonl"
    review_packet_fixture_patch '.tests[0].path = "codex-transcript.jsonl"'
    build
    [ "$status" -eq 2 ]
    ! echo "$output" | grep -qF "$canary"

    # Messages-array export.
    review_packet_fixture_setup
    review_packet_fixture_install_fake_ic
    jq -n --arg s "$canary" '[{"role":"user","content":"hi"},{"role":"assistant","content":$s}]' \
        > "$INPUT_DIR/messages-export.json"
    review_packet_fixture_patch '.tests[0].path = "messages-export.json"'
    build
    [ "$status" -eq 2 ]
    ! echo "$output" | grep -qF "$canary"

    # Markdown conversation fixture.
    review_packet_fixture_setup
    review_packet_fixture_install_fake_ic
    printf '**Human:** hi\n\n**Assistant:** %s\n' "$canary" > "$INPUT_DIR/conversation.md"
    review_packet_fixture_patch '.tests[0].path = "conversation.md"'
    build
    [ "$status" -eq 2 ]
    ! echo "$output" | grep -qF "$canary"
}

@test "renamed transcript and symlink to a session log are rejected" {
    local canary="ANOTHER-SECRET-THAT-MUST-NOT-LEAK"

    # Renamed: Claude JSONL content under an innocuous .txt name.
    printf '{"type":"assistant","message":{"role":"assistant","content":"%s"}}\n' \
        "$canary" > "$INPUT_DIR/innocuous-name.txt"
    review_packet_fixture_patch '.tests[0].path = "innocuous-name.txt"'
    build
    [ "$status" -eq 2 ]
    ! echo "$output" | grep -qF "$canary"

    # Symlink into a known author-session directory.
    review_packet_fixture_setup
    review_packet_fixture_install_fake_ic
    mkdir -p "$FIXTURE_DIR/.claude/projects/some-project"
    printf 'plain diagnostic text, not a transcript\n' \
        > "$FIXTURE_DIR/.claude/projects/some-project/session.jsonl"
    ln -s "$FIXTURE_DIR/.claude/projects/some-project/session.jsonl" "$INPUT_DIR/linked.jsonl"
    review_packet_fixture_patch '.tests[0].path = "linked.jsonl"'
    build
    [ "$status" -eq 2 ]
}

@test "ordinary test diagnostics mentioning assistant are accepted" {
    printf 'FAIL: the assistant module returned exit code 1\nHuman review recommended.\n' \
        > "$INPUT_DIR/plain-output.txt"
    review_packet_fixture_patch '.tests[0].path = "plain-output.txt"'
    build
    [ "$status" -eq 0 ]
    grep -qF "the assistant module returned exit code 1" "$output"
}
