#!/usr/bin/env bats

# Unit coverage for dispatch.sh's capacity-recheck hygiene fixes (mk-c66x,
# from an adversarial Opus re-check of db2b24e): list-item parsing beyond
# "- " bullets, a "## Re-check by the other lab" section that stops at a
# trailing VERDICT block instead of swallowing it, a receipt that names WHY
# recheck_bead is null instead of leaving every cause indistinguishable, a
# defensive idempotency guard, bd create bounded by a timeout with its
# stderr no longer discarded, and a sidecar write failure that no longer
# still files a bead.
#
# P2 ruling follow-up (review finding 6, superseding mk-c66x's "partial
# success" handling below): a bd call that creates the issue but then exits
# nonzero for an unrelated reason used to have its stdout scanned for an id
# anyway and reported "partial". That is no longer safe in general — a
# failed bd's stdout is unstructured, and guessing an id out of it (an
# unrelated hyphenated word, e.g.) can silently report a fake filing. Only
# bd_rc==0 ever yields a parsed id now; any nonzero exit reports "could not
# file" (bd_failed), even when bd's stdout happens to contain something
# id-shaped.
#
# tests/routing/plan-review-capacity-test.sh drives the equivalent behavior
# end-to-end through the real dispatch.sh CLI with fake codex/claude/bd
# binaries; this file isolates just _dispatch_process_capacity_recheck (and
# the two helpers it calls) the same way dispatch_error_surfacing.bats
# isolates _extract_verdict, so each hygiene fix can be pinned directly
# against the function's own state variables and a controllable fake `bd`,
# without paying for a full plan-review walk per case.

setup() {
    load test_helper

    DISPATCH_SCRIPT="$BATS_TEST_DIRNAME/../../scripts/dispatch.sh"
    TMPDIR_T="$(mktemp -d)"
    OUTPUT="$TMPDIR_T/out.md"
    WORKDIR="$TMPDIR_T/work"
    mkdir -p "$WORKDIR/.beads"
    ROLE="plan-review"
    DISPATCH_ID="dispatch-test-1"
    CAPACITY_SUBSTITUTE_JSON='{"failure_class":"quota_exhausted","producer_lab":"anthropic","reviewer_lab":"anthropic"}'
    CLAVAIN_RECHECK_BEADS_DIR="$WORKDIR"
    unset CLAVAIN_BEAD_ID CLAVAIN_RECHECK_BEADS CLAVAIN_RECHECK_BD_TIMEOUT

    HELPERS="$TMPDIR_T/helpers.sh"
    awk '
        /^_dispatch_capacity_recheck_section\(\)[[:space:]]*\{/ { emit=1 }
        /^_dispatch_recheck_tracker_dir\(\)[[:space:]]*\{/ { emit=1 }
        /^_dispatch_process_capacity_recheck\(\)[[:space:]]*\{/ { emit=1 }
        emit {
            print
            if ($0 ~ /^}[[:space:]]*$/) { emit=0 }
        }
    ' "$DISPATCH_SCRIPT" > "$HELPERS"

    BD_LOG="$TMPDIR_T/bd.log"
    BINDIR="$TMPDIR_T/bin"
    mkdir -p "$BINDIR"
    PATH="$BINDIR:$PATH"
    export PATH BD_LOG
}

teardown() {
    rm -rf "$TMPDIR_T"
}

_load() {
    # shellcheck disable=SC1090
    source "$HELPERS"
}

# FAKE_BD_MODE: success (default) | fail | partial | hang
_fake_bd() {
    cat > "$BINDIR/bd" <<'FAKE_BD'
#!/usr/bin/env bash
for a in "$@"; do
  if [[ "$a" == --help ]]; then
    echo "      --silent    Output only the issue ID (for scripting)"
    exit 0
  fi
done
{ printf '<<<BD-CALL>>>\n'; printf '%s\x1f' "$@"; printf '\n'; } >> "$BD_LOG"
case "${FAKE_BD_MODE:-success}" in
  hang)
    sleep 30
    ;;
  fail)
    echo "fake-bd: simulated failure" >&2
    exit 1
    ;;
  partial)
    # bd created the issue (a real id on stdout) but still exits nonzero,
    # e.g. its --deps attachment was rejected after the issue itself landed.
    echo "fake-bd: --deps target not found" >&2
    echo "fake-42"
    exit 1
    ;;
  *)
    echo "fake-42"
    ;;
esac
FAKE_BD
    chmod +x "$BINDIR/bd"
}

_answer_with_section() {
    printf 'VERDICT: CLEAN\n\n## Re-check by the other lab\n%s\n' "$1" > "$OUTPUT"
}

# --- mk-c66x: '*' and numbered list items are recognized, not dropped -----

@test "recheck: '*' bullet items are recognized, not fabricated (mk-c66x)" {
    _load
    _fake_bd
    _answer_with_section $'* confirmed the migration script runs without executing it\n* unsure whether the fallback order still matches routing.yaml'
    _dispatch_process_capacity_recheck 0
    [[ "$RECHECK_ITEMS" == 2 ]]
    [[ "$RECHECK_SOURCE_JSON" == '"listed"' ]]
    grep -q "confirmed the migration script" "${OUTPUT}.recheck.md"
    grep -q "unsure whether the fallback order" "${OUTPUT}.recheck.md"
}

@test "recheck: numbered '1.'/'2)' items are recognized, not fabricated (mk-c66x)" {
    _load
    _fake_bd
    _answer_with_section $'1. confirmed the migration script runs without executing it\n2) unsure whether the fallback order still matches routing.yaml'
    _dispatch_process_capacity_recheck 0
    [[ "$RECHECK_ITEMS" == 2 ]]
    [[ "$RECHECK_SOURCE_JSON" == '"listed"' ]]
    grep -q "confirmed the migration script" "${OUTPUT}.recheck.md"
    grep -q "unsure whether the fallback order" "${OUTPUT}.recheck.md"
}

@test "recheck: a genuinely missing list still falls back to the fabricated item (control)" {
    _load
    _fake_bd
    printf 'VERDICT: CLEAN\n\n## Re-check by the other lab\nsome unstructured prose, not a list at all\n' > "$OUTPUT"
    _dispatch_process_capacity_recheck 0
    [[ "$RECHECK_ITEMS" == 1 ]]
    [[ "$RECHECK_SOURCE_JSON" == '"missing"' ]]
    grep -q "reviewer did not list re-check items" "${OUTPUT}.recheck.md"
}

# --- mk-c66x: 'None.' followed by a trailing VERDICT block is still 'none' -

@test "recheck: 'None.' followed by a trailing VERDICT block is still recognized as none, not missing (mk-c66x)" {
    _load
    _fake_bd
    printf 'VERDICT: CLEAN\n\n## Re-check by the other lab\nNone.\n\n--- VERDICT ---\nSTATUS: pass\nSUMMARY: ok\n---\n' > "$OUTPUT"
    _dispatch_process_capacity_recheck 0
    [[ "$RECHECK_ITEMS" == 0 ]]
    [[ "$RECHECK_SOURCE_JSON" == '"none"' ]]
    [[ ! -f "${OUTPUT}.recheck.md" ]]
    [[ ! -s "$BD_LOG" ]]
}

# --- mk-c66x: the receipt names WHY recheck_bead is null, not just that it is

@test "recheck: a filed bead reports status 'filed' with tracker dir and sidecar path (mk-c66x)" {
    _load
    _fake_bd
    _answer_with_section '- confirmed nothing was executed'
    _dispatch_process_capacity_recheck 0
    [[ "$RECHECK_BEAD_JSON" == '"fake-42"' ]]
    [[ "$RECHECK_BEAD_STATUS_JSON" == '"filed"' ]]
    [[ "$RECHECK_TRACKER_DIR_JSON" == "$(printf '%s' "$WORKDIR" | jq -Rs 'rtrimstr("\n")')" ]]
    [[ "$RECHECK_SIDECAR_PATH_JSON" == "$(printf '%s' "${OUTPUT}.recheck.md" | jq -Rs 'rtrimstr("\n")')" ]]
}

@test "recheck: CLAVAIN_RECHECK_BEADS=0 reports status 'disabled', not just recheck_bead:null (mk-c66x)" {
    _load
    CLAVAIN_RECHECK_BEADS=0
    _fake_bd
    _answer_with_section '- confirmed nothing was executed'
    _dispatch_process_capacity_recheck 0
    [[ -z "$RECHECK_BEAD_JSON" ]]
    [[ "$RECHECK_BEAD_STATUS_JSON" == '"disabled"' ]]
    [[ ! -s "$BD_LOG" ]]
}

@test "recheck: no tracker resolved reports status 'no_tracker' (mk-c66x)" {
    _load
    CLAVAIN_RECHECK_BEADS_DIR="$TMPDIR_T/not-a-tracker"
    mkdir -p "$CLAVAIN_RECHECK_BEADS_DIR"
    _fake_bd
    _answer_with_section '- confirmed nothing was executed'
    _dispatch_process_capacity_recheck 0
    [[ -z "$RECHECK_BEAD_JSON" ]]
    [[ "$RECHECK_BEAD_STATUS_JSON" == '"no_tracker"' ]]
    [[ ! -s "$BD_LOG" ]]
}

@test "recheck: bd failing outright (no id at all) reports status 'bd_failed' (mk-c66x)" {
    _load
    FAKE_BD_MODE=fail _fake_bd
    _answer_with_section '- confirmed nothing was executed'
    FAKE_BD_MODE=fail run _dispatch_process_capacity_recheck 0
    [[ -z "${RECHECK_BEAD_JSON:-}" ]]
}

@test "recheck: bd creating the issue but exiting nonzero reports bd_failed, not a guessed id (P2 ruling, supersedes mk-c66x partial handling)" {
    _load
    FAKE_BD_MODE=partial _fake_bd
    _answer_with_section '- confirmed nothing was executed'
    FAKE_BD_MODE=partial _dispatch_process_capacity_recheck 0 2>"$TMPDIR_T/stderr.txt"
    [[ -z "${RECHECK_BEAD_JSON:-}" ]]
    [[ "$RECHECK_BEAD_STATUS_JSON" == '"bd_failed"' ]]
    grep -qi "could not file" "$TMPDIR_T/stderr.txt"
}

# --- P2 ruling (review finding 5): a tracker whose bead-id prefix itself
# contains hyphens and digits (e.g. "After-Them-rust") must still parse.

@test "recheck: a hyphenated multi-segment bead-id prefix parses under --silent (P2 ruling, finding 5)" {
    _load
    cat > "$BINDIR/bd" <<'FAKE_BD'
#!/usr/bin/env bash
for a in "$@"; do
  if [[ "$a" == --help ]]; then
    echo "      --silent    Output only the issue ID (for scripting)"
    exit 0
  fi
done
{ printf '<<<BD-CALL>>>\n'; printf '%s\x1f' "$@"; printf '\n'; } >> "$BD_LOG"
echo "After-Them-rust-a1b2"
FAKE_BD
    chmod +x "$BINDIR/bd"
    _answer_with_section '- confirmed nothing was executed'
    _dispatch_process_capacity_recheck 0
    [[ "$RECHECK_BEAD_JSON" == '"After-Them-rust-a1b2"' ]]
    [[ "$RECHECK_BEAD_STATUS_JSON" == '"filed"' ]]
}

# --- mk-c66x: defensive idempotency — one process files at most once -------

@test "recheck: calling the filing pass twice for one OUTPUT files at most once (mk-c66x)" {
    _load
    _fake_bd
    _answer_with_section '- confirmed nothing was executed'
    _dispatch_process_capacity_recheck 0
    first_bead="$RECHECK_BEAD_JSON"
    _dispatch_process_capacity_recheck 0 2>"$TMPDIR_T/stderr2.txt"
    [[ "$(grep -c '<<<BD-CALL>>>' "$BD_LOG")" == 1 ]]
    [[ "$RECHECK_BEAD_JSON" == "$first_bead" ]]
    grep -qi "already processed" "$TMPDIR_T/stderr2.txt"
}

# --- mk-c66x: bd create is bounded by a timeout ----------------------------

@test "recheck: a hung bd create is bounded by a timeout, not left to hang (mk-c66x)" {
    _load
    _fake_bd
    _answer_with_section '- confirmed nothing was executed'
    CLAVAIN_RECHECK_BD_TIMEOUT=1
    t0=$(date +%s)
    FAKE_BD_MODE=hang _dispatch_process_capacity_recheck 0 2>"$TMPDIR_T/stderr.txt"
    t1=$(date +%s)
    [[ $((t1 - t0)) -lt 10 ]]
    [[ -z "${RECHECK_BEAD_JSON:-}" ]]
    grep -qi "timed out" "$TMPDIR_T/stderr.txt"
}

# --- mk-c66x: a sidecar write failure never still files a bead -------------

@test "recheck: a sidecar write failure reports status 'sidecar_write_failed' and files no bead (mk-c66x)" {
    _load
    _fake_bd
    OUTPUT="$TMPDIR_T/readonly/out.md"
    mkdir -p "$(dirname "$OUTPUT")"
    printf 'VERDICT: CLEAN\n\n## Re-check by the other lab\n- confirmed nothing was executed\n' > "$OUTPUT"
    chmod 0500 "$(dirname "$OUTPUT")"
    _dispatch_process_capacity_recheck 0 2>"$TMPDIR_T/stderr.txt"
    chmod 0700 "$(dirname "$OUTPUT")"
    [[ -z "${RECHECK_BEAD_JSON:-}" ]]
    [[ "$RECHECK_BEAD_STATUS_JSON" == '"sidecar_write_failed"' ]]
    [[ ! -s "$BD_LOG" ]]
    grep -qi "could not write the capacity-recheck sidecar" "$TMPDIR_T/stderr.txt"
}
