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
#   goal-completed  (weight 0) — /goal completion or goal-scale milestone language.
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

    # 7. Goal completion / goal-scale milestone (weight 0 — structural trigger,
    # not a weight-ladder contributor; see goal-cadence tier in
    # auto-stop-actions.sh, which fires independently of CLAVAIN_SIGNAL_WEIGHT).
    if echo "$text" | grep -iq '/goal\b.*\(complet\|done\|shipped\|landed\)\|goal.*\(is\|was\)\s*complet\|goal-scale milestone\|milestone.*landed\|epic.*\(closed\|complete\)\b'; then
        CLAVAIN_SIGNALS="${CLAVAIN_SIGNALS}goal-completed,"
    fi

    # Remove trailing comma
    CLAVAIN_SIGNALS="${CLAVAIN_SIGNALS%,}"
}
