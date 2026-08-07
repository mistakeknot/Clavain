#!/usr/bin/env bash
# shellcheck: sourced library — no set -euo pipefail (would alter caller's error policy)
# lib-next-goal-provenance.sh — did that Next-goal block come from a tracker?
# Used by: auto-stop-actions.sh (Stop hook)
#
# THE GAP THIS CLOSES
#
# scripts/next-goal-candidates.sh made "we could not look" distinguishable from
# "nothing is there", and commands/next-goal.md requires the degraded block to
# say `no tracker reachable`. But that requirement is prose addressed to a
# model. The structural test only asserts the sentence still exists in the
# command file; nothing checks that an emitted block obeys it. A model that
# skips the command entirely and improvises candidates from session context
# produces a block that is indistinguishable, to the reader, from one ranked
# against 40 live beads. That is the original defect — a lookup failure wearing
# the costume of a result — displaced one level up, from the script to the
# prose.
#
# THE PREDICATE
#
# A block that does not disclose degradation is implicitly claiming tracker
# provenance, so it needs a receipt to back the claim:
#
#   flag  <=  block present
#             AND block does not disclose "no tracker reachable"
#             AND NOT (receipt exists for this session AND tracker_reachable)
#
#   receipt reachable, no disclosure  -> ok      (healthy path)
#   receipt unreachable, no disclosure-> FLAG    (contradicts the receipt)
#   receipt unreachable, discloses    -> ok      (honest degradation)
#   no receipt, no disclosure         -> FLAG    (improvised: nothing ever looked)
#   no receipt, discloses             -> ok      (honest, even without the helper)
#
# The two flagged cases get DIFFERENT messages on purpose. "No receipt" and
# "receipt says unreachable" are distinct states, and collapsing them into one
# warning would repeat, inside the fix, the conflation the fix is about.
#
# DETECTING A BLOCK WITHOUT MATCHING THE INSTRUCTION THAT ASKS FOR ONE
#
# auto-stop-actions.sh injects a reason containing the words "Next goal block",
# and that injection is itself written to the transcript. Matching on the
# phrase alone would fire on the hook's own request every time it fired — the
# hook would audit itself and always find a violation. A real block also
# carries paste-ready /goal text, so both markers are required, and only
# assistant lines are considered (a user pasting a /goal is not the assistant
# claiming provenance for it).
#
# KNOWN GAP, STATED RATHER THAN PAPERED OVER
#
# When the goal-cadence tier blocks and the model answers it, that next Stop
# arrives with stop_hook_active=true and auto-stop-actions.sh exits before
# reaching any tier. So a block emitted in direct reply to the injection is not
# audited in that cycle; it is audited on the next ordinary turn, if it is
# still inside the transcript window. The self-initiated blocks — the ones the
# global every-substantive-response rule produces with no hook prompting, and
# so the ones most likely to be improvised — are audited immediately.

[[ -n "${_LIB_NEXT_GOAL_PROVENANCE_LOADED:-}" ]] && return 0
_LIB_NEXT_GOAL_PROVENANCE_LOADED=1

CLAVAIN_PROVENANCE_DIR="${CLAVAIN_PROVENANCE_DIR:-$HOME/.cache/clavain/next-goal-provenance}"

# The exact wording commands/next-goal.md requires of a degraded block. Kept as
# a variable so the command, the helper and this hook can be checked against
# one spelling instead of three drifting copies.
CLAVAIN_NO_TRACKER_PHRASE="no tracker reachable"

# next_goal_block_emitted <transcript_text>
# 0 if the assistant emitted something with the shape of a Next-goal block.
next_goal_block_emitted() {
    local text="$1"
    local assistant
    assistant="$(printf '%s\n' "$text" | grep '"type":"assistant"' 2>/dev/null || true)"
    [[ -z "$assistant" ]] && return 1
    grep -qiE 'next[ -]goal' <<<"$assistant" 2>/dev/null || return 1
    # Paste-ready /goal text: the marker that separates a block from a mention
    # of one. Matches the OUTCOME: line every goal carries per goal-shape.
    grep -q 'OUTCOME:' <<<"$assistant" 2>/dev/null || return 1
    return 0
}

# next_goal_block_discloses_degradation <transcript_text>
# 0 if the assistant said, in so many words, that no tracker answered.
next_goal_block_discloses_degradation() {
    local text="$1"
    printf '%s\n' "$text" \
        | grep '"type":"assistant"' 2>/dev/null \
        | grep -qi "$CLAVAIN_NO_TRACKER_PHRASE" 2>/dev/null
}

# next_goal_receipt_path <session_id>
next_goal_receipt_path() {
    printf '%s/%s.json' "$CLAVAIN_PROVENANCE_DIR" "${1:-unknown}"
}

# next_goal_receipt_state <session_id>
# Echoes one of: missing | unreadable | reachable | unreachable
#
# "unreadable" is deliberately NOT folded into "missing". A receipt that exists
# but cannot be parsed means the helper ran and something went wrong writing
# its result — a different fault from the helper never having run, and one that
# would otherwise be invisible.
next_goal_receipt_state() {
    local path
    path="$(next_goal_receipt_path "$1")"
    [[ -f "$path" ]] || { printf 'missing\n'; return 0; }
    command -v jq >/dev/null 2>&1 || { printf 'unreadable\n'; return 0; }
    local reachable
    # NOT `.tracker_reachable // "absent"`. jq's `//` treats false and null
    # alike as empty, so the alternative form rewrote a legitimate
    # `tracker_reachable: false` into "absent" and reported it as unreadable —
    # silently losing the one state this audit exists to catch. `tostring`
    # keeps false distinct from a missing key.
    reachable="$(jq -r '.tracker_reachable | tostring' "$path" 2>/dev/null)" || {
        printf 'unreadable\n'; return 0; }
    case "$reachable" in
        true)  printf 'reachable\n' ;;
        false) printf 'unreachable\n' ;;
        *)     printf 'unreadable\n' ;;
    esac
}

# next_goal_receipt_detail <session_id>
# Short human-readable summary of the receipt, for naming what vouched (or did
# not) rather than asserting reachability without evidence.
next_goal_receipt_detail() {
    local path
    path="$(next_goal_receipt_path "$1")"
    [[ -f "$path" ]] || return 0
    command -v jq >/dev/null 2>&1 || return 0
    jq -r '
        "recorded " + (.recorded_at // "at an unknown time")
        + ", roots_ok=" + ((.roots_ok // []) | if length == 0 then "none" else join(",") end)
        + ", failures=" + ((.lookup_failures // []) | if length == 0 then "none" else join(",") end)
    ' "$path" 2>/dev/null || true
}

# next_goal_provenance_warning <session_id> <transcript_text>
# Echoes a warning when a block claims provenance it does not have; silent
# otherwise. Always exits 0 — this is a nudge, never a gate.
next_goal_provenance_warning() {
    local session="${1:-unknown}" text="${2:-}"

    [[ "${CLAVAIN_PROVENANCE_AUDIT_DISABLE:-0}" == "1" ]] && return 0
    next_goal_block_emitted "$text" || return 0
    next_goal_block_discloses_degradation "$text" && return 0

    local state detail
    state="$(next_goal_receipt_state "$session")"
    [[ "$state" == "reachable" ]] && return 0

    detail="$(next_goal_receipt_detail "$session")"

    case "$state" in
        missing)
            printf 'Next-goal provenance: this turn emitted a Next-goal block, but scripts/next-goal-candidates.sh never ran in this session — there is no receipt for %s. The candidates were therefore improvised from session context, not ranked against a tracker, and the block does not say so. Either run /clavain:next-goal and re-derive the candidates, or state in the block that the trackers were not consulted. An unchecked backlog is not an empty one.\n' "$session"
            ;;
        unreachable)
            printf 'Next-goal provenance: the candidate lookup ran and reached NO tracker (%s), but the emitted block reads as tracker-ranked — it never says "%s". A block that cannot name a tracker must disclose that, per commands/next-goal.md. Add the disclosure or re-run the lookup.\n' \
                "${detail:-no detail recorded}" "$CLAVAIN_NO_TRACKER_PHRASE"
            ;;
        unreadable)
            printf 'Next-goal provenance: a receipt exists for session %s but could not be parsed, so whether any tracker answered is unknown. Unknown is not healthy — re-run /clavain:next-goal, or say in the block that provenance could not be established.\n' "$session"
            ;;
    esac
    return 0
}
