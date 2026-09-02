#!/usr/bin/env bash
#
# next-goal-verify.sh — re-read every candidate a Next-goal block is about to
# cite, at source, immediately before it is emitted.
#
# WHY THIS EXISTS, and why it is NOT the same check as the provenance receipt.
#
# next-goal-candidates.sh answers "did a tracker answer at all", and the Stop
# hook flags a block with no receipt as improvised. That closed the failure
# where a block was written from session context without consulting anything.
#
# It does not close this one. On 2026-08-14 a Next-goal block cited
# `solwend-w46q` — a real bead ID, correctly formed, from a reachable tracker,
# so every provenance signal read clean — and recommended continuing it. The
# epic had been CLOSED as "all steps complete" since 2026-07-31, and the
# deliverables it proposed building were already on disk: eight components, a
# 337-line token sheet, a /plan page. The recommendation was to build what
# existed.
#
# The gap is exact: provenance asks WHETHER YOU LOOKED. Nothing asked WHETHER
# WHAT YOU CITED IS STILL TRUE. A stale ID and a live one are byte-identical in
# a block, so the reader cannot tell them apart either — the same argument that
# put the provenance receipt here in the first place, one level in.
#
# The failure mode is specifically a CONTEXT-RICH one. The longer a session
# runs, the more confidently it can name a bead from memory, and the likelier
# that memory predates the close. So the check has to be mechanical: it must
# not depend on the judgement of the thing whose judgement is compromised.
#
# Usage:
#   next-goal-verify.sh <bead-id> [<bead-id>...]
#   next-goal-verify.sh --path apps/web/components/x/ <bead-id>     # see --path
#
# Exit: 0 = every candidate usable (or verification unavailable — fail-open),
#       3 = at least one candidate DISQUALIFIED. Always prints one JSON object.

set -uo pipefail

SCHEMA_VERSION="clavain.next-goal-verify/v1"
MAX_ROOTS="${CLAVAIN_NEXT_GOAL_MAX_ROOTS:-6}"
BD_TIMEOUT="${CLAVAIN_NEXT_GOAL_BD_TIMEOUT:-20}"

RECEIPT_DIR="${CLAVAIN_VERIFY_DIR:-$HOME/.cache/clavain/next-goal-verify}"
# Same register order as next-goal-candidates.sh, for the same reason: the
# hook reads receipts by session id, and a receipt filed under "unknown"
# vouches for nobody.
RECEIPT_SESSION="${CLAUDE_SESSION_ID:-${CLAUDE_CODE_SESSION_ID:-unknown}}"

IDS=()
PATHS=()
while [[ $# -gt 0 ]]; do
    case "$1" in
        --path) PATHS+=("${2:-}"); shift 2 || shift ;;
        --path=*) PATHS+=("${1#--path=}"); shift ;;
        -h|--help) sed -n '2,40p' "$0"; exit 0 ;;
        *) IDS+=("$1"); shift ;;
    esac
done

emit_and_exit() {
    # $1 = compact JSON payload, $2 = exit code
    record_receipt "$1"
    printf '%s\n' "$1"
    exit "$2"
}

record_receipt() {
    # Mirrors next-goal-candidates.sh's receipt discipline: session-keyed, so a
    # yesterday's verification cannot vouch for today's block, and written via
    # temp+mv so a concurrent hook read never sees a half-written object.
    [[ "${CLAVAIN_PROVENANCE_DISABLE:-0}" == "1" ]] && return 0
    mkdir -p "$RECEIPT_DIR" 2>/dev/null || return 0
    local tmp="${RECEIPT_DIR}/.${RECEIPT_SESSION}.$$.tmp"
    printf '%s\n' "$1" >"$tmp" 2>/dev/null || return 0
    mv -f "$tmp" "${RECEIPT_DIR}/${RECEIPT_SESSION}.json" 2>/dev/null || rm -f "$tmp" 2>/dev/null
    return 0
}

unavailable() {
    # FAIL-OPEN, but never fail-SILENT. `ok` is null rather than true: an
    # unrun check is not a passed one, and the caller is required to say which
    # it got. Same reason the roadmap's `undated` is treated as stale here —
    # unknown is not healthy.
    local payload
    payload="$(printf '{"schema_version":"%s","available":false,"ok":null,"reason":"%s","beads":[],"paths":[],"disqualified":[]}' \
        "$SCHEMA_VERSION" "$1")"
    emit_and_exit "$payload" 0
}

command -v jq >/dev/null 2>&1 || unavailable "jq not installed"
[[ ${#IDS[@]} -gt 0 || ${#PATHS[@]} -gt 0 ]] || unavailable "nothing to verify"

# bd is required only for BEAD IDs. A --path run asks the filesystem whether an
# artifact exists and never touches a tracker, so demanding bd for it made the
# whole run report `available: false` on any host without bd — surrendering the
# half of the check that was still perfectly answerable. Caught on a CI runner
# that has no bd: a paths-only invocation returned no `paths` array at all.
if [[ ${#IDS[@]} -gt 0 ]]; then
    command -v bd >/dev/null 2>&1 || unavailable "bd not installed"
fi

# ---------------------------------------------------------------- root discovery
#
# Deliberately identical to next-goal-candidates.sh: walk up crossing nested-git
# boundaries, because bd resolves from $PWD and stops at the first git root, and
# then add the workspace tracker, which is not an ancestor of every checkout.
# Two different resolution schemes for the same ID space would be a way for the
# gate to disagree with the thing it is gating.
discover_roots() {
    if [[ -n "${CLAVAIN_NEXT_GOAL_ROOTS:-}" ]]; then
        printf '%s\n' "${CLAVAIN_NEXT_GOAL_ROOTS}" | tr ':' '\n'
        return
    fi
    local dir="$PWD" depth=0
    while [[ -n "$dir" && "$dir" != "/" && $depth -lt 12 ]]; do
        [[ -d "$dir/.beads" ]] && printf '%s\n' "$dir"
        dir="$(dirname "$dir")"
        depth=$((depth + 1))
    done
    [[ -d "$HOME/projects/.beads" ]] && printf '%s\n' "$HOME/projects"
}

mapfile -t ROOTS < <(discover_roots | awk 'NF && !seen[$0]++' | head -n "$MAX_ROOTS")
[[ ${#ROOTS[@]} -gt 0 ]] && ROOTS_OK=1 || ROOTS_OK=0

# Reachability is decided AFTER the loop, by whether a tracker actually
# answered — see the ANSWERED check below. Counting roots here would not do it:
# CLAVAIN_NEXT_GOAL_ROOTS is taken on trust, so a configured path with no
# tracker behind it produces a root that cannot answer anything.

bd_show() {
    # $1 = root, $2 = id. Prints the raw JSON, or nothing.
    #
    # `bd show <missing-id> --json` EXITS 0 and prints {"error": ...}. The exit
    # status is not the answer; the payload is. A gate that trusted `$?` here
    # would clear every fabricated ID it was built to catch.
    if command -v timeout >/dev/null 2>&1; then
        (cd "$1" 2>/dev/null && timeout "$BD_TIMEOUT" bd show "$2" --json 2>/dev/null)
    else
        (cd "$1" 2>/dev/null && bd show "$2" --json 2>/dev/null)
    fi
}

BEADS_JSON="[]"
DISQUALIFIED="[]"
ANSWERED=0

for id in ${IDS[@]+"${IDS[@]}"}; do
    found=""
    found_root=""
    for root in ${ROOTS[@]+"${ROOTS[@]}"}; do
        raw="$(bd_show "$root" "$id")"
        [[ -z "$raw" ]] && continue
        # An array means bd resolved it. An object carries {"error": ...}.
        if jq -e 'type == "array" and length > 0' >/dev/null 2>&1 <<<"$raw"; then
            found="$raw"; found_root="$root"; ANSWERED=1; break
        fi
        # A parseable error object is still a TRACKER ANSWERING — it looked and
        # said no. That is the only thing that earns the right to call an id
        # nonexistent below, and it is a different fact from silence.
        if jq -e 'type == "object" and has("error")' >/dev/null 2>&1 <<<"$raw"; then
            ANSWERED=1
        fi
    done

    if [[ -z "$found" ]]; then
        entry="$(jq -cn --arg id "$id" \
            '{id: $id, root: null, status: null, verdict: "disqualified",
              reason: "no such bead in any reachable tracker — do not cite an ID that cannot be read back"}')"
    else
        entry="$(jq -c --arg root "$found_root" '
            .[0]
            | {id, root: $root, status, issue_type, priority,
               title: (.title // ""), closed_at: (.closed_at // null)}
            | . + (
                if   .status == "closed"
                then {verdict: "disqualified",
                      reason: ("already closed" + (if .closed_at then " (" + .closed_at + ")" else "" end)
                               + " — proposing it recommends work that is already done")}
                elif .status == "deferred"
                then {verdict: "disqualified",
                      reason: "deferred — parking it was a decision, and re-proposing it silently reopens that decision"}
                elif .status == "in_progress"
                then {verdict: "warn",
                      reason: "already in progress — usable only if the goal is to finish it, and say so"}
                elif .status == "blocked"
                then {verdict: "warn",
                      reason: "blocked — usable only if the goal is to unblock it, and name what it waits on"}
                else {verdict: "ok", reason: "open"}
                end)
        ' <<<"$found")"
    fi
    BEADS_JSON="$(jq -c --argjson e "$entry" '. + [$e]' <<<"$BEADS_JSON")"
done

# SILENCE IS NOT A VERDICT — and this script shipped its first draft getting
# that wrong, which is precisely the defect it exists to prevent.
#
# If no tracker answered for ANY id, every one of them fell through to the
# not-found branch and the run reported `no such bead in any reachable tracker`
# about beads that were perfectly alive, then exited 3. A gate that says "your
# candidate does not exist" when the truth is "I never reached a tracker" is
# worse than no gate: it is confidently wrong in the direction that drops real
# work, and next-goal-candidates.sh carries ten lines of comment on the same
# distinction one level out. Found by running it on a host missing `awk`.
if [[ ${#IDS[@]} -gt 0 && $ANSWERED -eq 0 ]]; then
    unavailable "no bead root reachable, so a live candidate cannot be told from a closed one"
fi

# ------------------------------------------------------------------ path checks
#
# The second half of the 2026-08-14 failure: the block proposed BUILDING things
# that already existed. A bead status check cannot catch that — the epic could
# have been open and the components still present. So a candidate whose verb is
# "create"/"build"/"add" has to assert the artifact's absence, and asserting is
# a command, not a belief.
for p in ${PATHS[@]+"${PATHS[@]}"}; do
    if [[ -e "$p" ]]; then
        detail="exists"
        [[ -d "$p" ]] && detail="exists, $(find "$p" -maxdepth 1 -type f 2>/dev/null | wc -l | tr -d ' ') file(s)"
        entry="$(jq -cn --arg path "$p" --arg d "$detail" \
            '{path: $path, exists: true, verdict: "disqualified",
              reason: ("already present (" + $d + ") — a goal to build it would rebuild what is there")}')"
    else
        entry="$(jq -cn --arg path "$p" \
            '{path: $path, exists: false, verdict: "ok", reason: "absent, so there is something to build"}')"
    fi
    PATHS_JSON="${PATHS_JSON:-[]}"
    PATHS_JSON="$(jq -c --argjson e "$entry" '. + [$e]' <<<"$PATHS_JSON")"
done
PATHS_JSON="${PATHS_JSON:-[]}"

DISQUALIFIED="$(jq -cn --argjson b "$BEADS_JSON" --argjson p "$PATHS_JSON" \
    '[($b[] | select(.verdict == "disqualified") | .id),
      ($p[] | select(.verdict == "disqualified") | .path)]')"

# `ok: (($disq | length) == 0)` — the OUTER parentheses are load-bearing. jq 1.7
# (Debian, and the CI runner) rejects `key: a == b` inside an object literal
# with "syntax error, unexpected ==", while jq 1.8 accepts it. Written the
# permissive way, this script emitted a compile error instead of JSON on every
# Linux host and parsed fine on the machine it was written on — the third time
# in this change's own history that a platform difference hid a defect, and the
# reason the header insists the environment where a bug cannot appear is not
# evidence it is absent. CI is the guard here; there is no way to pin a jq
# version from inside a test.
PAYLOAD="$(jq -cn \
    --arg schema "$SCHEMA_VERSION" \
    --arg stamp "$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
    --argjson roots_seen "$ROOTS_OK" \
    --argjson beads "$BEADS_JSON" \
    --argjson paths "$PATHS_JSON" \
    --argjson disq "$DISQUALIFIED" \
    '{schema_version: $schema, available: true, verified_at: $stamp,
      roots_discovered: ($roots_seen == 1),
      beads: $beads, paths: $paths, disqualified: $disq,
      warnings: [$beads[] | select(.verdict == "warn") | .id],
      ok: (($disq | length) == 0)}')"

if [[ "$(jq -r '.ok' <<<"$PAYLOAD")" == "true" ]]; then
    emit_and_exit "$PAYLOAD" 0
fi
emit_and_exit "$PAYLOAD" 3
