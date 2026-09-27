#!/usr/bin/env bash
# shellcheck: sourced library — no set -euo pipefail (would alter caller's error policy)
# Shared signal detection library for Clavain Stop hooks.
#
# Usage:
#   source hooks/lib-signals.sh
#   detect_signals "$TRANSCRIPT_TEXT"
#   echo "Signals: $CLAVAIN_SIGNALS (weight: $CLAVAIN_SIGNAL_WEIGHT)"
#
# After calling detect_signals(), three variables are set:
#   CLAVAIN_SIGNALS       — comma-separated list of detected signal names
#   CLAVAIN_SIGNAL_WEIGHT — integer total weight of all detected signals
#   CLAVAIN_GOAL_COMPLETED_LINE — line of the last goal-completed event, or 0
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

# _signals_deadline <seconds> <command...>
# Runs a command and kills it after <seconds>. Written in bash because macOS
# has no timeout(1) unless coreutils is installed. Output goes through a file:
# a child the kill does not reach (a wrapper script's own children) would
# otherwise hold the caller's pipe open past the deadline.
_signals_deadline() {
    local secs=$1 pid watchdog out rc=0
    shift
    out=$(mktemp 2>/dev/null) || return 1
    "$@" >"$out" &
    pid=$!
    ( sleep "$secs"; kill "$pid" 2>/dev/null ) >/dev/null 2>&1 &
    watchdog=$!
    wait "$pid" || rc=$?
    kill "$watchdog" 2>/dev/null
    (( rc == 0 )) && cat "$out"
    rm -f "$out"
    return "$rc"
}

# _signals_bd_segment <segment>
# If a shell segment runs bd as its command, print "<dir>^_<verb>^_<args>"
# (unit separator, since a tab in IFS would swallow an empty dir):
# verb is close (args are its IDs) or eligible (a real `bd epic close-eligible`).
# `echo bd close x`, help and dry runs print nothing.
_signals_bd_segment() {
    local -a w
    read -r -a w <<<"$1" || true
    local i=0 n=${#w[@]} dir=""
    # Assignments and wrappers that still run bd as the command.
    while (( i < n )); do
        case "${w[i]}" in
            *=*) [[ "${w[i]}" =~ ^[A-Za-z_][A-Za-z0-9_]*= ]] || break; i=$((i + 1)) ;;
            env|command|exec) i=$((i + 1)) ;;
            timeout) i=$((i + 1)); while (( i < n )) && [[ "${w[i]}" == -* ]]; do i=$((i + 1)); done; i=$((i + 1)) ;;
            *) break ;;
        esac
    done
    [[ "${w[i]:-}" == bd || "${w[i]:-}" == */bd ]] || return 0
    i=$((i + 1))
    while (( i < n )) && [[ "${w[i]}" == -* ]]; do
        case "${w[i]}" in
            -h|--help) return 0 ;;
            -C|--directory) dir="${w[i+1]:-}"; i=$((i + 2)) ;;
            --directory=*) dir="${w[i]#--directory=}"; i=$((i + 1)) ;;
            --actor|--db|--dolt-auto-commit) i=$((i + 2)) ;;
            *) i=$((i + 1)) ;;
        esac
    done
    local verb="${w[i]:-}" sub="${w[i+1]:-}" a args="" eligible=0
    case "$verb" in
        close|done) i=$((i + 1)) ;;
        epic) [[ "$sub" == close-eligible ]] || return 0; i=$((i + 2)); eligible=1 ;;
        *) return 0 ;;
    esac
    for (( ; i < n; i++ )); do
        a="${w[i]}"
        case "$a" in
            -h|--help|--dry-run) return 0 ;;
            -*) (( eligible )) || break ;;
            *) (( eligible )) || args+="${a//[\"\']/} " ;;
        esac
    done
    dir="${dir//[\"\']/}"
    if (( eligible )); then printf '%s\037eligible\037\n' "$dir"
    elif [[ -n "$args" ]]; then printf '%s\037close\037%s\n' "$dir" "$args"
    fi
}

# jq: an ISO-8601 time ("2026-09-27T11:46:17.195Z", "...+02:00") as epoch
# seconds, or -1 when absent or unreadable.
_SIGNALS_JQ_EPOCH='def epoch: (if type == "string" then
    (capture("^(?<b>[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2})(\\.[0-9]+)?(?<z>Z|[+-][0-9]{2}:?[0-9]{2})$")? // null)
    else null end) as $m
  | if $m == null then -1 else
      (($m.b + "Z") | fromdateiso8601)
      - (if $m.z == "Z" then 0 else ($m.z | gsub(":"; "")) as $o
            | ($o[1:3] | tonumber) * 3600 + ($o[3:5] | tonumber) * 60
            | if $o[0:1] == "-" then -. else . end end)
    end; '

# _signals_epic_closed <transcript text>
# Prints the transcript line of the last Bash tool call that closed an epic:
# `bd close`/`bd done` on an ID, or a real `bd epic close-eligible` (its IDs
# read from the call's own tool_result). An ID counts only if the tracker now
# reports it as an epic, closed, with a closed_at no earlier than the call:
# so a failed close, a close of an epic that was already closed, and
# `false && bd close` do not count. Reads only Bash tool_use commands, never
# prose or tool output text.
#
# Budget: the Stop hook has 5s. The tracker is asked only when a close ran,
# once per directory with every ID batched, 1s each, at most 2 directories and
# the newest 20 IDs. Every failure answers "no": a missed Next-goal block
# costs less than a stop blocked for work that did not finish.
#
# Known miss: words are split on whitespace, so `bd -C "/my repo" close x` is
# not read.
_signals_epic_closed() {
    command -v jq >/dev/null 2>&1 || return 1
    local calls
    calls=$(printf '%s\n' "$1" | jq -Rc "${_SIGNALS_JQ_EPOCH}"'input_line_number as $n | fromjson?
        | select(type == "object" and .type == "assistant")
        | (.timestamp | epoch) as $t
        | .message.content[]? | select(type == "object" and .type == "tool_use" and .name == "Bash")
        | select((.input.command? | strings | test("\\bbd\\b")))
        | [$n, (.id // ""), .input.command, $t]' 2>/dev/null) || true
    [[ -n "$calls" ]] || return 1
    command -v bd >/dev/null 2>&1 || return 1
    # Candidate records: "<line>\t<dir>\t<id>\t<call epoch>".
    local rec n tid cmd ts seg dir cd_dir hit verb ids id out cands=""
    while IFS= read -r rec; do
        n=$(jq -r '.[0]' <<<"$rec") tid=$(jq -r '.[1]' <<<"$rec") cmd=$(jq -r '.[2]' <<<"$rec") ts=$(jq -r '.[3]' <<<"$rec")
        cd_dir=""
        while IFS= read -r seg; do
            if [[ "$seg" =~ ^[[:space:]]*cd[[:space:]]+([^[:space:]]+) ]]; then
                cd_dir="${BASH_REMATCH[1]//[\"\']/}"
                continue
            fi
            hit=$(_signals_bd_segment "$seg")
            [[ -n "$hit" ]] || continue
            IFS=$'\037' read -r dir verb ids <<<"$hit"
            [[ -n "$dir" ]] || dir="$cd_dir"
            dir="${dir/#\~/$HOME}"
            if [[ "$verb" == eligible ]]; then
                [[ -n "$tid" ]] || continue
                # close-eligible lists what it closed as "  - <id>: <title>".
                out=$(printf '%s\n' "$1" | jq -Rr --arg t "$tid" 'fromjson?
                    | select(type == "object" and .type == "user")
                    | .message.content[]? | select(type == "object" and .type == "tool_result" and .tool_use_id == $t)
                    | .content | if type == "array" then (map(.text? // empty) | join("\n")) else tostring end' 2>/dev/null) || true
                ids=$(sed -nE 's/^[[:space:]]*-[[:space:]]+([A-Za-z][A-Za-z0-9_.-]*):.*/\1/p' <<<"$out" | tr '\n' ' ')
            fi
            for id in $ids; do
                [[ "$id" =~ ^[A-Za-z][A-Za-z0-9_]*(-[A-Za-z0-9_]+)*-[a-z0-9]+(\.[0-9]+)*$ ]] || continue
                cands+="$n"$'\t'"$dir"$'\t'"$id"$'\t'"$ts"$'\n'
            done
        done < <(sed -E 's/(&&|\|\||;|\|)/\n/g' <<<"$cmd")
    done <<<"$calls"
    [[ -n "$cands" ]] || return 1
    cands=$(printf '%s' "$cands" | tail -n 20)

    local dirs closed best=0 lookups=0 line at
    dirs=$(cut -f2 <<<"$cands" | sort -u)
    while IFS= read -r dir; do
        (( lookups++ < 2 )) || break
        ids=$(awk -F'\t' -v d="$dir" '$2 == d { print $3 }' <<<"$cands" | sort -u | tr '\n' ' ')
        # shellcheck disable=SC2086  # IDs are validated tokens, split on purpose
        closed=$( (cd "${dir:-.}" 2>/dev/null && _signals_deadline 1 bd show $ids --json 2>/dev/null) \
            | jq -r "${_SIGNALS_JQ_EPOCH}"'(if type == "array" then .[] else . end)
                | select(.issue_type == "epic" and .status == "closed")
                | "\(.id)=\(.closed_at | epoch)"' 2>/dev/null) || true
        for rec in $closed; do
            id=${rec%%=*} at=${rec#*=}
            # 5s of slack: the call is stamped when written, before it runs,
            # and the tracker may keep another clock.
            line=$(awk -F'\t' -v d="$dir" -v i="$id" -v at="$at" \
                '$2 == d && $3 == i && $4 >= 0 && at >= $4 - 5 { l = $1 } END { print l + 0 }' <<<"$cands")
            (( line > best )) && best=$line
        done
    done <<<"$dirs"
    (( best > 0 )) || return 1
    printf '%s\n' "$best"
}

# Detect signals in transcript text. Sets CLAVAIN_SIGNALS and CLAVAIN_SIGNAL_WEIGHT.
# Args: $1 = transcript text (multi-line string)
# Side effects: Sets global CLAVAIN_SIGNALS and CLAVAIN_SIGNAL_WEIGHT
detect_signals() {
    local text="$1"
    CLAVAIN_SIGNALS=""
    CLAVAIN_SIGNAL_WEIGHT=0
    CLAVAIN_GOAL_COMPLETED_LINE=0

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
    #
    # CLAVAIN_GOAL_COMPLETED_LINE is the transcript line of the last such
    # event, so the hook can tell a Next-goal block written after it from a
    # stale one written for an earlier goal.
    local goal_line epic_line
    goal_line=$(printf '%s\n' "$text" | jq -Rr 'input_line_number as $n | fromjson?
        | select(type == "object" and .type == "attachment"
            and .attachment.type? == "goal_status" and .attachment.met? == true) | $n' 2>/dev/null \
        | tail -n 1) || true
    epic_line=$(_signals_epic_closed "$text") || true
    CLAVAIN_GOAL_COMPLETED_LINE=$(( ${goal_line:-0} > ${epic_line:-0} ? ${goal_line:-0} : ${epic_line:-0} ))
    if (( CLAVAIN_GOAL_COMPLETED_LINE > 0 )); then
        CLAVAIN_SIGNALS="${CLAVAIN_SIGNALS}goal-completed,"
    fi

    # Remove trailing comma
    CLAVAIN_SIGNALS="${CLAVAIN_SIGNALS%,}"
}
