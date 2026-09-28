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
#
# Removed: insight (weight 1) — ★ Insight block marker. This is a style artifact
# from explanatory output mode, always present, and inflated signal weight.
#
# Removed (mk-4hqi, 2026-09-28): goal-completed (weight 0) — a met /goal or an
# epic closing, plus the CLAVAIN_GOAL_COMPLETED_LINE line-tracking and the
# _signals_epic_closed/_signals_bd_segment/_signals_tokenize helpers that fed
# it. This existed solely for the goal-cadence Stop-hook tier and its
# provenance audit (auto-stop-actions.sh, hooks/lib-next-goal-provenance.sh),
# both removed in the same change; nothing else consumed the signal.

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

    # Remove trailing comma
    CLAVAIN_SIGNALS="${CLAVAIN_SIGNALS%,}"
}
