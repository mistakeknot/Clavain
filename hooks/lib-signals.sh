#!/usr/bin/env bash
# shellcheck: sourced library — no set -euo pipefail (would alter caller's error policy)
# Shared signal detection library for Clavain Stop hooks.
#
# Usage:
#   source hooks/lib-signals.sh
#   detect_signals "$TRANSCRIPT_TEXT"
#   echo "Signals: $CLAVAIN_SIGNALS (weight: $CLAVAIN_SIGNAL_WEIGHT)"
#
# After calling detect_signals(), two variables are set:
#   CLAVAIN_SIGNALS       — comma-separated list of detected signal names
#   CLAVAIN_SIGNAL_WEIGHT — integer total weight of all detected signals
#
# Signal definitions:
#   commit          (weight 1) — git commit in transcript
#   resolution      (weight 2) — debugging resolution phrases
#   investigation   (weight 2) — root cause / investigation language
#   bead-closed     (weight 1) — bd close in transcript
#   recovery        (weight 2) — test/build failure followed by pass
#   version-bump    (weight 2) — bump-version.sh or interpub:release
#   goal-completed  (weight 0) — a met /goal (goal_status met:true) or an epic closing.
#                    Weight 0 by design: this is a STRUCTURAL trigger (see the
#                    goal-cadence tier in auto-stop-actions.sh), not meant to
#                    add to the compound/drift weight ladder. Surfaced in
#                    CLAVAIN_SIGNALS for visibility/telemetry only.
#
# Removed: insight (weight 1) — ★ Insight block marker. This is a style artifact
# from explanatory output mode, always present, and inflated signal weight.

# Guard against re-parsing function definitions (performance optimization).
# Note: detect_signals() resets output vars on each call — no persistent state.
[[ -n "${_LIB_SIGNALS_LOADED:-}" ]] && return 0
_LIB_SIGNALS_LOADED=1

# _signals_epic_closed <transcript text>
# True when a Bash tool call in the window ran `bd close` (or `bd done`) on an
# issue the tracker types as an epic, or ran `bd epic close-eligible` for real.
# Reads only the commands of assistant tool_use records, never prose or tool
# output. The tracker is asked only when such a command exists, each lookup is
# capped at 2s and at most 5 are made, and every failure answers "no": a missed
# Next-goal block costs less than a stop blocked for work that did not finish.
_signals_epic_closed() {
    command -v jq >/dev/null 2>&1 || return 1
    local cmds
    cmds=$(printf '%s\n' "$1" | jq -Rc 'fromjson? | select(type == "object" and .type == "assistant")
        | .message.content[]? | select(type == "object" and .type == "tool_use")
        | .input.command? | strings' 2>/dev/null) || true
    [[ -n "$cmds" ]] || return 1
    command -v bd >/dev/null 2>&1 || return 1

    local encoded cmd seg dir id lookups=0
    local -a words
    while IFS= read -r encoded; do
        cmd=$(jq -r . <<<"$encoded" 2>/dev/null) || continue
        # Split on shell separators so each bd call is read with the `cd`
        # that precedes it and without the text of its neighbours.
        dir=""
        while IFS= read -r seg; do
            if [[ "$seg" =~ ^[[:space:]]*cd[[:space:]]+([^[:space:]]+) ]]; then
                dir="${BASH_REMATCH[1]//[\"\']/}"
                dir="${dir/#\~/$HOME}"
            elif [[ "$seg" =~ (^|[[:space:]])bd[[:space:]]+epic[[:space:]]+close-eligible ]]; then
                [[ "$seg" == *--dry-run* ]] || return 0
            elif [[ "$seg" =~ (^|[[:space:]])bd[[:space:]]+(close|done)[[:space:]]+(.*)$ ]]; then
                # IDs come before the flags; a --reason text is not read.
                read -r -a words <<<"${BASH_REMATCH[3]}"
                for id in "${words[@]}"; do
                    [[ "$id" == -* ]] && break
                    [[ "$id" =~ ^[A-Za-z][A-Za-z0-9_]*(-[A-Za-z0-9_]+)*-[a-z0-9]+(\.[0-9]+)*$ ]] || continue
                    (( lookups++ < 5 )) || return 1
                    if (cd "${dir:-.}" 2>/dev/null && timeout 2 bd show "$id" --json 2>/dev/null) \
                        | jq -e '(if type == "array" then .[0] else . end).issue_type == "epic"' >/dev/null 2>&1; then
                        return 0
                    fi
                done
            fi
        done < <(sed -E 's/(&&|\|\||;|\|)/\n/g' <<<"$cmd")
    done <<<"$cmds"
    return 1
}

# Detect signals in transcript text. Sets CLAVAIN_SIGNALS and CLAVAIN_SIGNAL_WEIGHT.
# Args: $1 = transcript text (multi-line string)
# Side effects: Sets global CLAVAIN_SIGNALS and CLAVAIN_SIGNAL_WEIGHT
detect_signals() {
    local text="$1"
    CLAVAIN_SIGNALS=""
    CLAVAIN_SIGNAL_WEIGHT=0

    # 1. Git commit (weight 1)
    if echo "$text" | grep -q '"git commit\|"git add.*&&.*git commit'; then
        CLAVAIN_SIGNALS="${CLAVAIN_SIGNALS}commit,"
        CLAVAIN_SIGNAL_WEIGHT=$((CLAVAIN_SIGNAL_WEIGHT + 1))
    fi

    # 2. Debugging resolution phrases (weight 2)
    if echo "$text" | grep -iq '"that worked\|"it'\''s fixed\|"working now\|"problem solved\|"that did it\|"bug fixed\|"issue resolved'; then
        CLAVAIN_SIGNALS="${CLAVAIN_SIGNALS}resolution,"
        CLAVAIN_SIGNAL_WEIGHT=$((CLAVAIN_SIGNAL_WEIGHT + 2))
    fi

    # 3. Investigation language (weight 2)
    if echo "$text" | grep -iq '"root cause\|"the issue was\|"the problem was\|"turned out\|"the fix is\|"solved by'; then
        CLAVAIN_SIGNALS="${CLAVAIN_SIGNALS}investigation,"
        CLAVAIN_SIGNAL_WEIGHT=$((CLAVAIN_SIGNAL_WEIGHT + 2))
    fi

    # 4. Bead closed (weight 1)
    if echo "$text" | grep -q '"bd close\|"bd update.*completed'; then
        CLAVAIN_SIGNALS="${CLAVAIN_SIGNALS}bead-closed,"
        CLAVAIN_SIGNAL_WEIGHT=$((CLAVAIN_SIGNAL_WEIGHT + 1))
    fi

    # 5. Build/test recovery (weight 2)
    if echo "$text" | grep -iq 'FAIL\|FAILED\|ERROR.*build\|error.*compile\|test.*failed'; then
        if echo "$text" | grep -iq 'passed\|BUILD SUCCESSFUL\|build succeeded\|tests pass\|all.*pass'; then
            CLAVAIN_SIGNALS="${CLAVAIN_SIGNALS}recovery,"
            CLAVAIN_SIGNAL_WEIGHT=$((CLAVAIN_SIGNAL_WEIGHT + 2))
        fi
    fi

    # 6. Version bump (weight 2)
    if echo "$text" | grep -q 'bump-version\|interpub:release'; then
        CLAVAIN_SIGNALS="${CLAVAIN_SIGNALS}version-bump,"
        CLAVAIN_SIGNAL_WEIGHT=$((CLAVAIN_SIGNAL_WEIGHT + 2))
    fi

    # 7. Goal completion (weight 0 — structural trigger, not a weight-ladder
    # contributor; see goal-cadence tier in auto-stop-actions.sh, which fires
    # independently of CLAVAIN_SIGNAL_WEIGHT).
    #
    # Narrowed 2026-09-24 to two events: Claude Code's own record that a /goal
    # was met, and an epic closing. The old pattern also took "goal ...
    # complete", "/goal ... done" (every DONE WHEN line) and "milestone ...
    # landed" anywhere in 80 transcript lines, hook text included, so it fired
    # on ordinary progress and each firing cost a turn.
    #
    # The epic close is read from the tracker, not from prose (2026-09-27).
    # Grep runs per JSONL record, and one record can hold kilobytes of tool
    # input: a `bd create` filed "under the de-slop epic" whose description
    # mentioned "closed registration" read as an epic closing and blocked the
    # stop (jawnomicon, thr_cf7b863d3f). Prose is also where the model says "no
    # epic closed". See _signals_epic_closed.
    if echo "$text" | grep -q '"type":"goal_status","met":true' \
        || _signals_epic_closed "$text"; then
        CLAVAIN_SIGNALS="${CLAVAIN_SIGNALS}goal-completed,"
    fi

    # Remove trailing comma
    CLAVAIN_SIGNALS="${CLAVAIN_SIGNALS%,}"
}
