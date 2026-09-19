#!/usr/bin/env bats

# Tripwire for the ship-class shortcut bypass (Sylveste-ymp2 stage A, goal
# 14539da7). commands/quality-gates.md Phase 1 offers a "small change shortcut"
# that runs one fd-quality agent and explicitly skips Phases 2-3 — which is
# where fd-safety is enforced as a MANDATORY reviewer for ship-class surfaces.
# An 8-line edit to a hook script therefore shipped executable platform code
# with no safety review. Found by independent review 2026-09-19 and reproduced.
#
# This suite executes the ACTUAL Phase 1 eligibility block extracted from
# commands/quality-gates.md against real git sandboxes. If that fence is edited
# into vacuity, these tests fail with it.

setup() {
    load test_helper

    ROOT="$BATS_TEST_DIRNAME/../.."
    QG_DOC="$ROOT/commands/quality-gates.md"
    TMPDIR_T="$(mktemp -d)"

    # Extract the fence that carries the eligibility decision — the one whose
    # body mentions the library — rather than "the Nth fence", which silently
    # follows any insertion above it.
    ELIGIBILITY="$TMPDIR_T/eligibility.sh"
    awk '
        /^```bash$/ { collecting=1; buf=""; next }
        collecting && /^```$/ {
            if (buf ~ /lib-ship-class\.sh/ && buf ~ /review_path_decision/) { printf "%s", buf; exit }
            collecting=0; next
        }
        collecting { buf = buf $0 "\n" }
    ' "$QG_DOC" > "$ELIGIBILITY"
    [ -s "$ELIGIBILITY" ] || { echo "Phase 1 eligibility block not found in quality-gates.md" >&2; return 1; }

    SANDBOX="$TMPDIR_T/repo"
    mkdir -p "$SANDBOX"
    git -C "$SANDBOX" init -q --initial-branch=main
    git -C "$SANDBOX" config user.email t@t
    git -C "$SANDBOX" config user.name t
    mkdir -p "$SANDBOX/hooks"
    echo "base" > "$SANDBOX/README.md"
    printf '#!/usr/bin/env bash\necho base\n' > "$SANDBOX/hooks/auto-push.sh"
    git -C "$SANDBOX" add -A
    git -C "$SANDBOX" commit -q -m base

    export CLAVAIN_SOURCE_DIR="$ROOT"
}

teardown() { rm -rf "$TMPDIR_T"; }

# Eight added lines, one file — squarely inside `DIFF_LINES < 20 && CHANGED_FILES == 1`.
small_edit() {
    local target="$1" i
    for i in 1 2 3 4 5 6 7 8; do echo "# line $i" >> "$SANDBOX/$target"; done
}

run_eligibility() { ( cd "$SANDBOX" && bash "$ELIGIBILITY" ); }

@test "an 8-line single-file hook edit is NOT shortcut-eligible" {
    small_edit hooks/auto-push.sh
    run run_eligibility
    [ "$status" -eq 0 ]
    [[ "$output" == *"REVIEW_PATH=full"* ]]
    [[ "$output" == *"ship-class: hooks/auto-push.sh"* ]]
    [[ "$output" != *"shortcut-eligible"* ]]
}

@test "[negative control] an 8-line single-file docs edit IS still shortcut-eligible" {
    small_edit README.md
    run run_eligibility
    [ "$status" -eq 0 ]
    [[ "$output" == *"REVIEW_PATH=shortcut-eligible"* ]]
    [[ "$output" != *"REVIEW_PATH=full"* ]]
}

@test "a staged-only ship-class change is caught too" {
    printf '{"name":"x"}\n' > "$SANDBOX/plugin.json"
    git -C "$SANDBOX" add plugin.json
    run run_eligibility
    [ "$status" -eq 0 ]
    [[ "$output" == *"REVIEW_PATH=full"* ]]
    [[ "$output" == *"ship-class: plugin.json"* ]]
}

@test "an unresolvable library fails closed, it does not shortcut" {
    small_edit README.md
    CLAVAIN_SOURCE_DIR="$TMPDIR_T/nonexistent" \
      run env CLAVAIN_DIR="$TMPDIR_T/nonexistent" CLAUDE_PLUGIN_ROOT="$TMPDIR_T/nonexistent" \
          bash -c "cd '$SANDBOX' && CLAVAIN_SOURCE_DIR='$TMPDIR_T/nonexistent' bash '$ELIGIBILITY'"
    [[ "$output" == *"REVIEW_PATH=full"* ]]
    [[ "$output" == *"failing closed"* ]]
}

@test "every ship-class alternative in the shared regex is still classified" {
    source "$ROOT/scripts/lib-ship-class.sh"
    local p
    for p in plugin.json a/plugin.json mcp-servers.json mcp-tools.yaml mcp-server.ts \
             hooks/x.sh hooks/x.py hooks/x.ts hooks/x.js hooks.json \
             interlock.json authorization.yaml capability.yml .clavain/keys/id \
             pkg/shell-exec.go; do
        run is_ship_class_paths "$p"
        [ "$status" -eq 0 ] || { echo "not classified as ship-class: $p"; return 1; }
    done
    # And a control, so the matcher is not simply always true.
    run is_ship_class_paths README.md
    [ "$status" -ne 0 ]
}

@test "quality-gates.md still carries the eligibility fence and the override rule" {
    grep -q 'review_path_decision' "$QG_DOC"
    grep -q 'REVIEW_PATH=shortcut-eligible' "$QG_DOC"
    grep -q 'overrides the size test' "$QG_DOC"
}
