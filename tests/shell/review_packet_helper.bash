#!/usr/bin/env bash
# Shared fixtures for tests/shell/test_build_review_packet.bats and
# tests/shell/dispatch_review_packet.bats (Step 4 reuses this helper).
#
# Builds a minimal, valid INPUT.json plus its supporting files (a plan file,
# a git repo with a base/head commit pair, a producer receipt, a beads
# export) in a temp directory, and exposes helpers to mutate one field at a
# time for the negative-path tests.

review_packet_fixture_setup() {
    FIXTURE_DIR="$(mktemp -d)"
    REPO_DIR="$FIXTURE_DIR/repo"
    INPUT_DIR="$FIXTURE_DIR/input"
    OUTPUT_DIR="$FIXTURE_DIR/output"
    mkdir -p "$REPO_DIR" "$INPUT_DIR" "$OUTPUT_DIR"

    git -C "$REPO_DIR" init -q
    git -C "$REPO_DIR" config user.email test@example.com
    git -C "$REPO_DIR" config user.name test
    printf 'line one\nline two\nline three\n' > "$REPO_DIR/touched.txt"
    git -C "$REPO_DIR" add touched.txt
    git -C "$REPO_DIR" commit -qm base
    BASE_SHA="$(git -C "$REPO_DIR" rev-parse HEAD)"
    printf 'line one\nline two CHANGED\nline three\n' > "$REPO_DIR/touched.txt"
    git -C "$REPO_DIR" commit -qam head
    HEAD_SHA="$(git -C "$REPO_DIR" rev-parse HEAD)"

    cat > "$INPUT_DIR/plan.md" <<'EOF'
# Fixture plan

Do the fixture thing.
EOF

    cat > "$INPUT_DIR/producer_receipt.json" <<EOF
{
  "state": "completed",
  "terminal": true,
  "result": {"exit_code": 0},
  "bead_id": "fixture-1",
  "checkout": "$REPO_DIR",
  "resolved_profile": {
    "profile_ref": "planning-astra",
    "profile": {
      "backend": "codex",
      "model": "gpt-6-astra",
      "model_identity": "gpt-6-astra",
      "reasoning_effort": "xhigh"
    }
  },
  "execution": {
    "backend": "codex",
    "model": "gpt-6-astra",
    "reasoning_effort": "xhigh"
  },
  "resolved_route": {
    "policy_hash": "deadbeef",
    "classification_reasons": ["foundational-invariants"],
    "review_requirement": "cross-lab-review",
    "policy_profile": "default"
  }
}
EOF

    cat > "$INPUT_DIR/beads.json" <<'EOF'
[
  {
    "id": "fixture-1",
    "title": "Fixture bead",
    "acceptance_criteria": "Fixture criteria must hold.",
    "notes": "irrelevant notes that must never be emitted"
  }
]
EOF

    cat > "$INPUT_DIR/input.json" <<EOF
{
  "schema_version": 1,
  "kind": "plan",
  "bead_ids": ["fixture-1"],
  "beads_file": "beads.json",
  "producer_receipt": "producer_receipt.json",
  "plan_file": "plan.md",
  "changes": [{"repo": "$REPO_DIR", "base": "$BASE_SHA", "head": "$HEAD_SHA"}],
  "excerpts_not_applicable": "net-new fixture plan, no existing implementation",
  "tests": [
    {"label": "fixture check", "command": "true", "exit_code": 0, "scope": "$HEAD_SHA", "path": "-"}
  ]
}
EOF
    INPUT_JSON="$INPUT_DIR/input.json"
}

review_packet_fixture_teardown() {
    rm -rf "$FIXTURE_DIR"
}

# Rewrite $INPUT_JSON via jq, e.g.:
#   review_packet_fixture_patch '.tests = null | .tests_not_run = "not run"'
review_packet_fixture_patch() {
    local filter="$1"
    local tmp
    tmp="$(mktemp)"
    jq "$filter" "$INPUT_JSON" > "$tmp"
    mv "$tmp" "$INPUT_JSON"
}
