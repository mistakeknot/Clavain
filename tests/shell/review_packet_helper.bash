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

    DISPATCH_ID="dispatch-fixture-1"
    ATTEMPT_ID="attempt-fixture-1"
    cat > "$INPUT_DIR/producer_receipt.json" <<EOF
{
  "dispatch_id": "$DISPATCH_ID",
  "attempt_id": "$ATTEMPT_ID",
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

# Installs a fake `ic` binary on PATH that answers exactly the two subcommands
# the builder is allowed to use: `--json route list --dispatch=<id>` (returns
# one context_json-wrapped attempt record matching the fixture receipt) and
# `--json route identity --model=<model>` (canonical identity lookup). Callers
# may override IC_ROUTE_LIST_JSON / IC_IDENTITY_JSON before invoking the
# builder to simulate a mismatch.
review_packet_fixture_install_fake_ic() {
    IC_BIN_DIR="$FIXTURE_DIR/bin"
    mkdir -p "$IC_BIN_DIR"

    IC_ROUTE_LIST_JSON="$FIXTURE_DIR/ic-route-list.json"
    IC_IDENTITY_JSON="$FIXTURE_DIR/ic-identity.json"

    local context
    context="$(cat "$INPUT_DIR/producer_receipt.json")"
    jq -n --argjson ctx "$context" '[{"context_json": ($ctx | tostring)}]' > "$IC_ROUTE_LIST_JSON"
    printf '{"model_identity":"gpt-6-astra"}\n' > "$IC_IDENTITY_JSON"

    cat > "$IC_BIN_DIR/ic" <<SH
#!/usr/bin/env bash
printf '%s\n' "\$*" >> "$FIXTURE_DIR/ic.log"
if [[ "\$*" == *"route list"* ]]; then
    cat "$IC_ROUTE_LIST_JSON"
elif [[ "\$*" == *"route identity"* ]]; then
    cat "$IC_IDENTITY_JSON"
else
    exit 3
fi
SH
    chmod +x "$IC_BIN_DIR/ic"
    export PATH="$IC_BIN_DIR:$PATH"
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

# --- Step 3 fixtures: a richer diff-scope repo -----------------------------
#
# Builds $DIFF_REPO with a base/head commit pair that exercises: a change
# buried in the middle of a long file (so unchanged distant lines must be
# excluded from bounded excerpts but still fully present in the raw diff),
# a deleted file, an added file, a mode-only change, and a rename
# represented as delete+add (--no-renames). Sets DIFF_REPO, DIFF_BASE_SHA,
# DIFF_HEAD_SHA.
review_packet_fixture_diff_repo() {
    DIFF_REPO="$FIXTURE_DIR/diffrepo"
    mkdir -p "$DIFF_REPO"
    git -C "$DIFF_REPO" init -q
    git -C "$DIFF_REPO" config user.email test@example.com
    git -C "$DIFF_REPO" config user.name test

    # 40-line file; only line 20 (1-indexed) changes at head.
    seq 0 39 | sed 's/^/line /' > "$DIFF_REPO/bigfile.txt"
    printf 'to be deleted\n' > "$DIFF_REPO/to_delete.txt"
    printf '#!/bin/sh\necho old-name\n' > "$DIFF_REPO/rename_old.sh"
    printf 'echo mode-file\n' > "$DIFF_REPO/mode_file.sh"
    chmod 644 "$DIFF_REPO/mode_file.sh"
    git -C "$DIFF_REPO" add -A
    git -C "$DIFF_REPO" commit -qm base
    DIFF_BASE_SHA="$(git -C "$DIFF_REPO" rev-parse HEAD)"

    sed -i '20s/.*/line 19 CHANGED/' "$DIFF_REPO/bigfile.txt"
    git -C "$DIFF_REPO" rm -q to_delete.txt
    git -C "$DIFF_REPO" mv rename_old.sh rename_new.sh
    chmod 755 "$DIFF_REPO/mode_file.sh"
    printf 'brand new file\n' > "$DIFF_REPO/added.txt"
    git -C "$DIFF_REPO" add -A
    git -C "$DIFF_REPO" commit -qam head
    DIFF_HEAD_SHA="$(git -C "$DIFF_REPO" rev-parse HEAD)"
}

# Adds a binary file change (base: absent, head: bytes with a NUL) to an
# existing diff-scope repo/commit pair, returning the new head sha via
# DIFF_HEAD_SHA (rewrites the head commit in place is avoided; instead this
# adds one more commit on top so tests can pick base=DIFF_BASE_SHA,
# head=DIFF_HEAD_SHA for a scope that includes exactly the binary change).
review_packet_fixture_diff_repo_binary() {
    DIFF_REPO="$FIXTURE_DIR/diffrepo-binary"
    mkdir -p "$DIFF_REPO"
    git -C "$DIFF_REPO" init -q
    git -C "$DIFF_REPO" config user.email test@example.com
    git -C "$DIFF_REPO" config user.name test
    printf 'line one\n' > "$DIFF_REPO/text.txt"
    git -C "$DIFF_REPO" add -A
    git -C "$DIFF_REPO" commit -qm base
    DIFF_BASE_SHA="$(git -C "$DIFF_REPO" rev-parse HEAD)"
    printf 'BIN\x00\x01\x02DATA' > "$DIFF_REPO/blob.bin"
    git -C "$DIFF_REPO" add -A
    git -C "$DIFF_REPO" commit -qm head
    DIFF_HEAD_SHA="$(git -C "$DIFF_REPO" rev-parse HEAD)"
}

# Adds a submodule (gitlink) entry between base and head.
review_packet_fixture_diff_repo_submodule() {
    DIFF_REPO="$FIXTURE_DIR/diffrepo-submodule"
    mkdir -p "$DIFF_REPO"
    git -C "$DIFF_REPO" init -q
    git -C "$DIFF_REPO" config user.email test@example.com
    git -C "$DIFF_REPO" config user.name test
    printf 'line one\n' > "$DIFF_REPO/text.txt"
    git -C "$DIFF_REPO" add -A
    git -C "$DIFF_REPO" commit -qm base
    DIFF_BASE_SHA="$(git -C "$DIFF_REPO" rev-parse HEAD)"
    git -C "$DIFF_REPO" update-index --add --cacheinfo \
        160000,0000000000000000000000000000000000000001,vendored-sub
    git -C "$DIFF_REPO" commit -qm head
    DIFF_HEAD_SHA="$(git -C "$DIFF_REPO" rev-parse HEAD)"
}

# Writes $DIFF_INPUT_JSON: a minimal, valid kind:diff INPUT.json reusing the
# already-set-up beads/producer_receipt/ic fixtures, scoped to one repo/base/head.
review_packet_fixture_diff_input() {
    local repo="$1" base="$2" head="$3"
    DIFF_INPUT_JSON="$INPUT_DIR/diff_input.json"
    cat > "$DIFF_INPUT_JSON" <<EOF
{
  "schema_version": 1,
  "kind": "diff",
  "bead_ids": ["fixture-1"],
  "beads_file": "beads.json",
  "producer_receipt": "producer_receipt.json",
  "changes": [{"repo": "$repo", "base": "$base", "head": "$head"}],
  "tests_not_run": "fixture: no tests wired for this diff-scope check"
}
EOF
}
