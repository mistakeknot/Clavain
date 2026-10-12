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
# carries a paste-ready /goal LINE (a line that begins with `/goal ` and real
# text, not the template's `<placeholder>`), within a few lines of a "next
# goal" heading. That region is the block. Only assistant lines are considered
# (a user pasting a /goal is not the assistant claiming provenance for it), and
# only assistant lines from THIS turn: a human prompt is a user line with
# string content and no isMeta flag; skill expansions and the Stop hook's own
# feedback are user lines too, but isMeta:true, and must not reset the turn.
#
# The first version of this detector required the literal "OUTCOME:". Only 5
# of 24 minted goals carry it, so from 2026-08-14 to 2026-09-01 every real block
# was invisible to both audits, and the goal-cadence tier demanded a block
# seven times from replies that already ended with one (mk-hxgi).
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

# next_goal_session_key <stdin_session_id>
# The register the WRITER used. scripts/next-goal-candidates.sh and
# scripts/next-goal-verify.sh key receipts on CLAUDE_SESSION_ID, else
# CLAUDE_CODE_SESSION_ID; the Stop hook gets .session_id on stdin. Nothing
# guarantees those strings agree on a live turn, so the reader tries each
# register the writer could have used and settles on the first that has a
# receipt on disk. Falls back to the stdin id, so a missing receipt is still
# reported under the id the hook knows.
next_goal_session_key() {
    local given="${1:-unknown}" cand
    for cand in "$given" "${CLAUDE_SESSION_ID:-${CLAUDE_CODE_SESSION_ID:-}}" "${CLAUDE_CODE_SESSION_ID:-}"; do
        [[ -n "$cand" ]] || continue
        if [[ -f "$(next_goal_receipt_path "$cand")" || -f "${CLAVAIN_VERIFY_DIR:-$HOME/.cache/clavain/next-goal-verify}/${cand}.json" ]]; then
            printf '%s\n' "$cand"
            return 0
        fi
    done
    printf '%s\n' "$given"
}

# next_goal_turn_started_at <transcript_text>
# Timestamp of the most recent human prompt in the window. Empty when the
# window holds none — which callers must treat as "not judged", never as
# "fresh" (see next_goal_receipt_freshness).
next_goal_turn_started_at() {
    printf '%s\n' "${1:-}" | jq -R -r '
        fromjson? | select(.type == "user")
        | select((.message.content | type) == "string")
        | select(.isMeta != true)
        | .timestamp // empty' 2>/dev/null | tail -n 1
}

# next_goal_assistant_text <transcript_text> [turn_start]
# The assistant's text blocks from this turn, one real line per line. Lines
# with no timestamp (older transcripts, fixtures) are kept: a line that cannot
# be placed is not evidence that it is from an earlier turn.
next_goal_assistant_text() {
    local text="${1:-}" start="${2-}"
    printf '%s\n' "$text" | jq -R -r --arg start "$start" '
        fromjson? | select(.type == "assistant")
        | select($start == "" or .timestamp == null or ((.timestamp | tostring) >= $start))
        | .message.content
        | if type == "array" then (.[] | select(.type == "text") | .text)
          elif type == "string" then .
          else empty end' 2>/dev/null
}

# next_goal_block_region <assistant_text>
# The block itself: from the nearest preceding "next goal" line to the
# paste-ready /goal line, inclusive. Anchored on the LAST /goal line so prose
# after a block ("next goal after that") cannot hide it, and bounded to 40
# lines so a "next goal" mention far from a quoted /goal example is not one.
# A /goal line whose text opens with "<" is the template's placeholder, not a
# paste-ready goal.
next_goal_block_region() {
    printf '%s\n' "${1:-}" | awk '
        { line[NR] = $0 }
        tolower($0) ~ /next[ -]goal/ { heading[NR] = 1 }
        $0 ~ /^[[:space:]]*\/goal[[:space:]]+[^[:space:]<]/ { last_goal = NR }
        END {
            if (!last_goal) exit
            for (i = last_goal - 1; i >= 1 && i >= last_goal - 40; i--) {
                if (heading[i]) {
                    for (j = i; j <= last_goal; j++) print line[j]
                    exit
                }
            }
        }' 2>/dev/null
}

# next_goal_block_emitted <transcript_text>
# 0 if the assistant emitted something with the shape of a Next-goal block
# during this turn.
next_goal_block_emitted() {
    local text="${1:-}" start assistant
    start="$(next_goal_turn_started_at "$text")"
    assistant="$(next_goal_assistant_text "$text" "$start")"
    [[ -z "$assistant" ]] && return 1
    [[ -n "$(next_goal_block_region "$assistant")" ]]
}

# next_goal_block_discloses_degradation <transcript_text>
# 0 if the assistant said, in so many words, that no tracker answered.
next_goal_block_discloses_degradation() {
    local text="$1"
    printf '%s\n' "$text" \
        | grep '"type":"assistant"' 2>/dev/null \
        | grep -qi "$CLAVAIN_NO_TRACKER_PHRASE" 2>/dev/null
}

# next_goal_block_stamp <transcript_text>
# Timestamp of the last assistant line in the window: when the block went out.
next_goal_block_stamp() {
    printf '%s\n' "${1:-}" | jq -R -r '
        fromjson? | select(.type == "assistant") | .timestamp // empty' 2>/dev/null | tail -n 1
}

# next_goal_receipt_freshness <receipt_stamp> <transcript_text>
# Echoes fresh | stale | unknown.
#
# A RECEIPT IS A PER-TURN FACT. Sessions live for months and receipts had no
# expiry, so one next-goal run vouched for every block the session emitted
# after it. A receipt is fresh when it was written at or after this turn's
# human prompt. When the window holds no prompt at all (a long, tool-heavy
# turn — exactly the kind likeliest to carry a stale receipt), the block's own
# timestamp minus CLAVAIN_NEXT_GOAL_RECEIPT_BUDGET_MIN (default 30) bounds it
# instead; the fixed 80-line tail must not be a way to fail open. With no
# stamps on either side the answer is unknown, and unknown is not fresh — but
# it is not flagged either, because a transcript with no timestamps is a
# fixture, not a session.
#
# Both stamps are read off the same host clock: Claude Code writes the
# transcript and runs the helper on the same machine, so no skew allowance is
# needed. Comparison is on the first 19 characters (YYYY-MM-DDTHH:MM:SS) of
# UTC stamps; the transcript carries milliseconds and the receipt does not.
next_goal_receipt_freshness() {
    local stamp="${1:-}" text="${2:-}" start block budget
    [[ -z "$stamp" || "$stamp" == "null" ]] && { printf 'unknown\n'; return 0; }
    start="$(next_goal_turn_started_at "$text")"
    if [[ -n "$start" ]]; then
        if [[ "${stamp:0:19}" < "${start:0:19}" ]]; then printf 'stale\n'; else printf 'fresh\n'; fi
        return 0
    fi
    block="$(next_goal_block_stamp "$text")"
    [[ -z "$block" ]] && { printf 'unknown\n'; return 0; }
    budget="${CLAVAIN_NEXT_GOAL_RECEIPT_BUDGET_MIN:-30}"
    [[ "$budget" =~ ^[0-9]+$ ]] || budget=30
    jq -rn --arg s "${stamp:0:19}Z" --arg b "${block:0:19}Z" --argjson m "$budget" '
        try (if ($s | fromdateiso8601) >= (($b | fromdateiso8601) - ($m * 60))
             then "fresh" else "stale" end)
        catch "unknown"' 2>/dev/null || printf 'unknown\n'
}

# next_goal_freshness_anchor <transcript_text>
# The clause a STALE message names as the other side of the comparison.
next_goal_freshness_anchor() {
    local start block
    start="$(next_goal_turn_started_at "${1:-}")"
    if [[ -n "$start" ]]; then
        printf 'this turn began at %s' "$start"
        return 0
    fi
    block="$(next_goal_block_stamp "${1:-}")"
    printf 'the block went out at %s with no prompt in the window, and a receipt more than %s minutes older than the block is not this turn'"'"'s' \
        "$block" "${CLAVAIN_NEXT_GOAL_RECEIPT_BUDGET_MIN:-30}"
}

# next_goal_audit_log <session_id> <kind> [detail]
# One line per emitted warning, so "how often does this fire, and for what"
# has a data source. The plan that shipped these audits gated promotion of
# its warnings on measurement; this is the measurement. Best-effort, never
# fails the caller, nothing written when nothing fired.
next_goal_audit_log() {
    [[ "${CLAVAIN_NEXT_GOAL_AUDIT_LOG_DISABLE:-0}" == "1" ]] && return 0
    command -v jq >/dev/null 2>&1 || return 0
    mkdir -p "$CLAVAIN_PROVENANCE_DIR" 2>/dev/null || return 0
    jq -cn --arg ts "$(date -u +%Y-%m-%dT%H:%M:%SZ)" --arg session "${1:-unknown}" \
        --arg kind "${2:-unknown}" --arg detail "${3:-}" \
        '{ts: $ts, session: $session, kind: $kind, detail: $detail}' \
        >> "$CLAVAIN_PROVENANCE_DIR/audit-log.jsonl" 2>/dev/null || true
    return 0
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

    local state detail stamp
    state="$(next_goal_receipt_state "$session")"
    if [[ "$state" == "reachable" ]]; then
        # A receipt that exists and says reachable still has to be THIS
        # turn's receipt. Fail-open only when there is nothing to compare.
        stamp="$(jq -r '.recorded_at // empty' "$(next_goal_receipt_path "$session")" 2>/dev/null)"
        [[ "$(next_goal_receipt_freshness "$stamp" "$text")" == "stale" ]] || return 0
        next_goal_audit_log "$session" "provenance-stale" "$stamp"
        printf 'Next-goal provenance: STALE receipt. scripts/next-goal-candidates.sh last ran for session %s at %s, but %s — that receipt vouches for an earlier block, not this one, and the backlog it ranked may have moved since. A receipt is a per-turn fact: re-run /clavain:next-goal (or the helper) in this turn and re-derive the candidates.\n' \
            "$session" "$stamp" "$(next_goal_freshness_anchor "$text")"
        return 0
    fi

    detail="$(next_goal_receipt_detail "$session")"
    next_goal_audit_log "$session" "provenance-$state" "$detail"

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

# ---------------------------------------------------------------- verification
#
# THE SECOND CLAIM A BLOCK MAKES, AND THE ONE NOTHING ABOVE CHECKS
#
# Everything above answers "did a tracker answer at all". On 2026-08-14 a block
# passed every one of those checks and was still wrong: it cited `solwend-w46q`,
# a real ID from a reachable tracker, and recommended continuing it. The epic had
# been CLOSED as "all steps complete" for two weeks, and the deliverables it
# proposed building were already on disk.
#
# Provenance asks WHETHER YOU LOOKED. This asks WHETHER WHAT YOU CITED IS STILL
# TRUE. A stale ID and a live one are byte-identical in a block, so the reader
# cannot separate them either — the same argument that put the provenance
# receipt here, applied one level in.
#
# Note the failure is context-RICH, not context-poor: the longer a session runs
# the more confidently it names a bead from memory, and the likelier that memory
# predates the close. So it has to be mechanical. It cannot be delegated to the
# judgement of the thing whose judgement is the problem.
CLAVAIN_VERIFY_DIR="${CLAVAIN_VERIFY_DIR:-$HOME/.cache/clavain/next-goal-verify}"

# next_goal_verify_receipt_state <session_id>
# Echoes one of: missing | unreadable | clean | disqualified | unavailable
#
# `unavailable` (the helper ran but bd/jq were absent) is kept distinct from
# `clean` for the reason the whole file keeps repeating: an unrun check is not a
# passed one. scripts/next-goal-verify.sh writes ok:null for exactly this, and
# folding null into true here would discard the distinction it took care to make.
next_goal_verify_receipt_state() {
    local path="${CLAVAIN_VERIFY_DIR}/${1:-unknown}.json"
    [[ -f "$path" ]] || { printf 'missing\n'; return 0; }
    command -v jq >/dev/null 2>&1 || { printf 'unreadable\n'; return 0; }
    local ok
    ok="$(jq -r '.ok | tostring' "$path" 2>/dev/null)" || { printf 'unreadable\n'; return 0; }
    case "$ok" in
        true)  printf 'clean\n' ;;
        false) printf 'disqualified\n' ;;
        null)  printf 'unavailable\n' ;;
        *)     printf 'unreadable\n' ;;
    esac
}

# next_goal_verify_disqualified <session_id> — comma-joined ids/paths, if any.
next_goal_verify_disqualified() {
    local path="${CLAVAIN_VERIFY_DIR}/${1:-unknown}.json"
    [[ -f "$path" ]] || return 0
    command -v jq >/dev/null 2>&1 || return 0
    jq -r '(.disqualified // []) | join(", ")' "$path" 2>/dev/null || true
}

# ---------------------------------------------------- cited ⊆ verified (W5)
#
# A clean verify receipt says the IDs IT READ BACK are live. It says nothing
# about an ID the block cites that the verifier was never given — and on
# 2026-09-01 the #1 candidate ("Merge PR #26") carried no ID at all, so there
# was nothing to verify and nothing to re-find next session. Known prefixes
# come from the receipts themselves (roots_ok of the provenance receipt, and
# the prefix of every verified bead), because "flux-drive" and "next-goal"
# fit the ID grammar and a registry of trackers does not exist. A token with
# an unknown prefix is therefore never accused of being a bead; but on a
# candidate line that carries no known ID it is NAMED, because "solwend-w46q
# from a tracker the verifier never reached" is the 2026-08-14 failure exactly.

# next_goal_id_tokens <text>
# Every whole token shaped like a bead ID: <prefix>-<slug>[.<n>]*, prefix
# starting with a letter, slug 2-8 lowercase alphanumerics. Whole tokens, so
# "fix/mk-hxgi-next-goal-audit" is not "mk-hxgi" truncated; trailing dots are
# sentence punctuation, not part of the ID.
next_goal_id_tokens() {
    printf '%s\n' "${1:-}" \
        | tr -cs 'A-Za-z0-9_.-' '\n' \
        | sed 's/\.*$//' \
        | grep -E '^[A-Za-z][A-Za-z0-9]*-[a-z0-9]{2,8}(\.[0-9]+)*$' 2>/dev/null \
        | awk '!seen[$0]++'
}

# next_goal_known_prefixes <session_id> — lowercased, one per line.
next_goal_known_prefixes() {
    local ppath vpath
    ppath="$(next_goal_receipt_path "${1:-unknown}")"
    vpath="${CLAVAIN_VERIFY_DIR}/${1:-unknown}.json"
    {
        [[ -f "$ppath" ]] && jq -r '(.roots_ok // [])[] | tostring | select(test("/") | not)' "$ppath" 2>/dev/null
        [[ -f "$vpath" ]] && jq -r '(.beads // [])[] | (.id // "") | select(. != "") | split("-")[0]' "$vpath" 2>/dev/null
        true
    } | tr 'A-Z' 'a-z' | awk 'NF && !seen[$0]++'
}

# next_goal_verified_ids <session_id> — the IDs the verifier read back.
next_goal_verified_ids() {
    local vpath="${CLAVAIN_VERIFY_DIR}/${1:-unknown}.json"
    [[ -f "$vpath" ]] || return 0
    jq -r '(.beads // [])[] | (.id // "") | select(. != "")' "$vpath" 2>/dev/null
    return 0
}

# next_goal_cited_warning <session_id> <transcript_text>
# Echoes a warning when the block cites an ID the verifier never saw, or
# ranks a candidate that carries no verified ID in a block that does not
# disclose degradation. Silent otherwise. Always exits 0.
next_goal_cited_warning() {
    local session="${1:-unknown}" text="${2:-}"
    next_goal_block_discloses_degradation "$text" && return 0
    local start assistant region
    start="$(next_goal_turn_started_at "$text")"
    assistant="$(next_goal_assistant_text "$text" "$start")"
    region="$(next_goal_block_region "$assistant")"
    [[ -z "$region" ]] && return 0

    local known verified
    known="$(next_goal_known_prefixes "$session")"
    verified="$(next_goal_verified_ids "$session")"

    local -a unverified=() idless=()
    local tok prefix
    while IFS= read -r tok; do
        [[ -n "$tok" ]] || continue
        prefix="$(printf '%s' "${tok%%-*}" | tr 'A-Z' 'a-z')"
        grep -qxF -- "$prefix" <<<"$known" 2>/dev/null || continue
        grep -qixF -- "$tok" <<<"$verified" 2>/dev/null || unverified+=("$tok")
    done < <(next_goal_id_tokens "$region")

    local line n=0 has_known hint
    while IFS= read -r line; do
        [[ "$line" =~ ^[[:space:]]*[0-9]+\.[[:space:]] ]] || continue
        n=$((n + 1))
        has_known=0
        hint=""
        while IFS= read -r tok; do
            [[ -n "$tok" ]] || continue
            prefix="$(printf '%s' "${tok%%-*}" | tr 'A-Z' 'a-z')"
            if grep -qxF -- "$prefix" <<<"$known" 2>/dev/null; then
                has_known=1
            else
                hint="${hint:+$hint, }$tok"
            fi
        done < <(next_goal_id_tokens "$line")
        [[ $has_known -eq 1 ]] && continue
        if [[ -n "$hint" ]]; then
            idless+=("candidate $n (it mentions $hint; if that is a bead ID, its tracker was never reached by the verifier)")
        else
            idless+=("candidate $n")
        fi
    done <<<"$region"

    local out="" joined
    if [[ ${#unverified[@]} -gt 0 ]]; then
        joined="$(printf '%s, ' "${unverified[@]}")"; joined="${joined%, }"
        next_goal_audit_log "$session" "verification-cited-unverified" "$joined"
        out+="$(printf 'Next-goal verification: the block cites %s, which the verifier never saw — a receipt vouches only for the IDs it read back, and an ID it did not read back may be closed, deferred, or invented. Re-run scripts/next-goal-verify.sh with every ID the block cites.' "$joined")"
    fi
    if [[ ${#idless[@]} -gt 0 ]]; then
        joined="$(printf '%s; ' "${idless[@]}")"; joined="${joined%; }"
        next_goal_audit_log "$session" "verification-idless-candidate" "$joined"
        [[ -n "$out" ]] && out+=$'\n'
        out+="$(printf 'Next-goal verification: %s carries no tracker ID the verifier reached, in a block that reads as tracker-ranked. A candidate without an ID cannot be verified now or re-found next session: file it and cite the ID, or say in the block that it is improvised ("%s").' "$joined" "$CLAVAIN_NO_TRACKER_PHRASE")"
    fi
    [[ -n "$out" ]] && printf '%s\n' "$out"
    return 0
}

# next_goal_verification_warning <session_id> <transcript_text>
# Echoes a warning when a block cites candidates that were never re-read, or
# that failed the re-read. Silent otherwise. Always exits 0 — a nudge, not a gate.
next_goal_verification_warning() {
    local session="${1:-unknown}" text="${2:-}"

    [[ "${CLAVAIN_PROVENANCE_AUDIT_DISABLE:-0}" == "1" ]] && return 0
    next_goal_block_emitted "$text" || return 0

    local state detail stamp
    state="$(next_goal_verify_receipt_state "$session")"
    if [[ "$state" == "clean" ]]; then
        stamp="$(jq -r '.verified_at // empty' "${CLAVAIN_VERIFY_DIR}/${session}.json" 2>/dev/null)"
        if [[ "$(next_goal_receipt_freshness "$stamp" "$text")" != "stale" ]]; then
            # Fresh and clean for what it read. Now: is what the block cites
            # a subset of what it read?
            next_goal_cited_warning "$session" "$text"
            return 0
        fi
        next_goal_audit_log "$session" "verification-stale" "$stamp"
        printf 'Next-goal verification: STALE receipt. scripts/next-goal-verify.sh last ran for session %s at %s, but %s — the candidates this block cites were re-read for an earlier block, and a bead can close between turns. Re-run the verifier on every ID this block cites before standing behind it.\n' \
            "$session" "$stamp" "$(next_goal_freshness_anchor "$text")"
        return 0
    fi
    detail="$(next_goal_verify_disqualified "$session")"
    next_goal_audit_log "$session" "verification-$state" "$detail"

    case "$state" in
        missing)
            printf 'Next-goal verification: this turn emitted a Next-goal block, but scripts/next-goal-verify.sh never ran in this session, so no cited candidate was re-read at source. A bead that closed since you last saw it looks exactly like one that is still open. Re-run the shortlist through the verifier before standing behind the block.\n'
            ;;
        disqualified)
            printf 'Next-goal verification: the verifier DISQUALIFIED %s, but a Next-goal block went out anyway. A closed, deferred, or nonexistent bead must not be proposed — and a path that already exists must not be proposed as something to build. Drop those candidates and re-derive.\n' \
                "${detail:-one or more candidates}"
            ;;
        unavailable)
            printf 'Next-goal verification: the verifier ran but could not reach bd, so no cited candidate was confirmed to still be open. Unknown is not healthy — say in the block that the candidates are unverified, or re-run once the tracker is reachable.\n'
            ;;
        unreadable)
            printf 'Next-goal verification: a verification receipt exists for session %s but could not be parsed, so whether the cited candidates are live is unknown. Re-run scripts/next-goal-verify.sh.\n' "$session"
            ;;
    esac
    return 0
}
