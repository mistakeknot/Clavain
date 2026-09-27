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
#   CLAVAIN_GOAL_COMPLETED_LINE — first line that can answer the last
#                           goal-completed event (see step 7), or 0
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
    # KILL, not TERM: a child that ignores TERM must not outlast the hook.
    ( sleep "$secs"; kill -9 "$pid" 2>/dev/null ) >/dev/null 2>&1 &
    watchdog=$!
    wait "$pid" || rc=$?
    kill "$watchdog" 2>/dev/null
    (( rc == 0 )) && cat "$out"
    rm -f "$out"
    return "$rc"
}

# _signals_tokenize
# Reads "<line>\t<tool id>\t<epoch>\t<command>" records and prints one record
# per simple command: the same three fields, then its words joined by \037.
# Commands split on && || ; | & and newlines (which the caller writes as
# \036), words on blanks, both only outside quotes; quotes are removed, a
# backslash escapes the next character and an unquoted # starting a word
# comments out the rest of the line. So `echo "x; bd close y"` is one
# command whose words are echo and "x; bd close y". The & of 2>&1, >&2 and
# &> is not a separator. $(...) and heredocs are not modelled.
_signals_tokenize() {
    awk -F'\t' '
    function flush_word() { if (have) { seg = seg (nw++ ? "\037" : "") word }; word = ""; have = 0 }
    function flush_seg() { flush_word(); if (nw) print head seg; seg = ""; nw = 0 }
    {
        head = $1 "\t" $2 "\t" $3 "\t"
        cmd = $0; sub(/^[^\t]*\t[^\t]*\t[^\t]*\t/, "", cmd)
        seg = ""; nw = 0; word = ""; have = 0; q = ""; comment = 0
        for (i = 1; i <= length(cmd); i++) {
            c = substr(cmd, i, 1)
            if (comment) { if (c == "\036") { comment = 0; flush_seg() }; continue }
            if (q != "") {
                if (c == q) q = ""
                else if (c == "\\" && q == "\"" && i < length(cmd)) { word = word substr(cmd, ++i, 1) }
                else word = word c
                continue
            }
            if (c == "\\" && i < length(cmd)) { word = word substr(cmd, ++i, 1); have = 1; continue }
            if (c == "\"" || c == "\047") { q = c; have = 1; continue }
            if (c == "#" && !have) { comment = 1; continue }
            if (c == "&" && (substr(cmd, i - 1, 1) ~ /[<>]/ || substr(cmd, i + 1, 1) == ">")) { word = word c; have = 1; continue }
            if (c == ";" || c == "|" || c == "&" || c == "\036") {
                flush_seg()
                if ((c == "|" || c == "&") && substr(cmd, i + 1, 1) == c) i++
                continue
            }
            if (c == " " || c == "\t") { flush_word(); continue }
            word = word c; have = 1
        }
        flush_seg()
    }'
}

# _signals_bd_segment <word>...
# If the words of a simple command run bd as the command, print
# "<dir>^_<verb>^_<ids>" (unit separators): verb is close, with the words it
# was given as IDs, or eligible for a real `bd epic close-eligible`. Help and
# dry runs print nothing, and so does `echo bd close x`.
_signals_bd_segment() {
    local -a w=("$@")
    local i=0 n=$# dir=""
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
    # Global flags may come before or after the verb; flags that take a
    # value have it skipped, so it is never read as the verb or an ID.
    local verb="" args="" eligible=0
    while (( i < n )); do
        case "${w[i]}" in
            -h|--help|--dry-run) return 0 ;;
            -C|--directory) dir="${w[i+1]:-}"; i=$((i + 2)); continue ;;
            --directory=*) dir="${w[i]#--directory=}" ;;
            --actor|--db|--dolt-auto-commit|-r|--reason|--reason-file|--session) i=$((i + 2)); continue ;;
            -*) ;;
            *)
                if [[ -z "$verb" ]]; then
                    verb="${w[i]}"
                    case "$verb" in
                        close|done) ;;
                        epic) [[ "${w[i+1]:-}" == close-eligible ]] || return 0; i=$((i + 1)); eligible=1 ;;
                        *) return 0 ;;
                    esac
                elif (( ! eligible )); then
                    args+="${w[i]} "
                fi ;;
        esac
        i=$((i + 1))
    done
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
# reports it as an epic, closed, with a closed_at from 1s before the call (the
# rounding of two clocks to the second) to 120s after it. So a failed close,
# a close of an epic that was already closed, and `false && bd close` do not
# count. Reads only Bash tool_use commands, never prose or tool output text.
#
# Budget: the Stop hook has 5s, and its shadow scan may take 3s. One jq pass
# and one awk pass read the newest 20 bd calls; the tracker is asked only when
# a close ran, once, for the newest 50 IDs closed in the directory of the
# newest close, with a 1s deadline. Every failure answers "no": a missed
# Next-goal block costs less than a stop blocked for work that did not finish.
#
# Known miss, quiet: a failed close followed within 120s by someone else's
# close of the same epic counts.
_signals_epic_closed() {
    command -v jq >/dev/null 2>&1 || return 1
    local segs
    segs=$(printf '%s\n' "$1" | jq -Rr "${_SIGNALS_JQ_EPOCH}"'input_line_number as $n | fromjson?
        | select(type == "object" and .type == "assistant")
        | (.timestamp | epoch) as $t
        | .message.content[]? | select(type == "object" and .type == "tool_use" and .name == "Bash")
        | (.input.command? | strings) as $c | select($c | test("\\bbd\\b"))
        | "\($n)\t\(.id // "-" | if . == "" then "-" else . end)\t\($t)\t\($c | gsub("\t"; " ") | gsub("\n"; "\u001e"))"' 2>/dev/null \
        | tail -n 20 | _signals_tokenize) || true
    [[ -n "$segs" ]] || return 1
    command -v bd >/dev/null 2>&1 || return 1

    # Candidate records: "<line>\t<dir>\t<id>\t<call epoch>".
    local n tid ts words key="" cd_dir="" hit dir verb ids id out cands=""
    local -a w
    while IFS=$'\t' read -r n tid ts words; do
        [[ "$n:$tid" == "$key" ]] || { key="$n:$tid"; cd_dir=""; }
        IFS=$'\037' read -r -a w <<<"$words"
        if [[ "${w[0]:-}" == cd ]]; then
            cd_dir="${w[1]:-}"
            continue
        fi
        hit=$(_signals_bd_segment "${w[@]}")
        [[ -n "$hit" ]] || continue
        IFS=$'\037' read -r dir verb ids <<<"$hit"
        [[ -n "$dir" ]] || dir="$cd_dir"
        dir="${dir/#\~/$HOME}"
        if [[ "$verb" == eligible ]]; then
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
    done <<<"$segs"
    [[ -n "$cands" ]] || return 1
    cands=$(printf '%s' "$cands" | tail -n 50)

    # One lookup, in the directory of the newest close: the hook's shadow
    # scan may take 3s of the same 5s.
    local closed best=0 line at rec
    dir=$(tail -n 1 <<<"$cands" | cut -f2)
    ids=$(awk -F'\t' -v d="$dir" '$2 == d { print $3 }' <<<"$cands" | sort -u | tr '\n' ' ')
    # shellcheck disable=SC2086  # IDs are validated tokens, split on purpose
    closed=$( (cd "${dir:-.}" 2>/dev/null && _signals_deadline 1 bd show $ids --json 2>/dev/null) \
        | jq -r "${_SIGNALS_JQ_EPOCH}"'(if type == "array" then .[] else . end)
            | select(.issue_type == "epic" and .status == "closed")
            | "\(.id)=\(.closed_at | epoch)"' 2>/dev/null) || true
    for rec in $closed; do
        id=${rec%%=*} at=${rec#*=}
        line=$(awk -F'\t' -v d="$dir" -v i="$id" -v at="$at" \
            '$2 == d && $3 == i && $4 >= 0 && at >= $4 - 1 && at <= $4 + 120 { l = $1 } END { print l + 0 }' <<<"$cands")
        (( line > best )) && best=$line
    done
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
    # CLAVAIN_GOAL_COMPLETED_LINE is the first transcript line from which a
    # Next-goal block answers the last such event, so the hook can tell it
    # from a stale block written for an earlier goal. Claude Code writes the
    # goal_status attachment at stop time, after the reply that met the goal,
    # so for a met goal that is the last assistant record before it. For an
    # epic close it is the line after the tool call.
    local goal_at epic_line goal_line=0 goal_from=0
    goal_at=$(printf '%s\n' "$text" | jq -Rr 'input_line_number as $n | fromjson?
        | select(type == "object")
        | if .type == "assistant" then "a \($n)"
          elif .type == "attachment" and .attachment.type? == "goal_status"
            and .attachment.met? == true then "g \($n)"
          else empty end' 2>/dev/null \
        | awk '$1 == "a" { a = $2 } $1 == "g" { g = $2; f = a ? a : $2 } END { print (g + 0) " " (f + 0) }') || true
    read -r goal_line goal_from <<<"${goal_at:-0 0}"
    epic_line=$(_signals_epic_closed "$text") || epic_line=0
    if (( goal_line > epic_line )); then
        CLAVAIN_GOAL_COMPLETED_LINE=$goal_from
    elif (( epic_line > 0 )); then
        CLAVAIN_GOAL_COMPLETED_LINE=$(( epic_line + 1 ))
    fi
    if (( CLAVAIN_GOAL_COMPLETED_LINE > 0 )); then
        CLAVAIN_SIGNALS="${CLAVAIN_SIGNALS}goal-completed,"
    fi

    # Remove trailing comma
    CLAVAIN_SIGNALS="${CLAVAIN_SIGNALS%,}"
}
