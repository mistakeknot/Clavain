#!/usr/bin/env bash
# lib-headless.sh — detect non-interactive (claude -p / --print) sessions.
#
# Stop hooks that emit decision:"block" inject their reason as a NEW PROMPT
# TURN. Interactively a human sees the result; in a headless `claude -p` run
# the model's answer to the injected turn REPLACES the reply the caller asked
# for (observed live 2026-07-20: a scripted data pass lost 44/45 responses to
# hook chatter — Sylveste-364). Turn-injecting hooks must no-op when headless.
#
# Fail-open: on any error report "not headless" (return 1) so interactive
# behavior is never lost to a detector bug.

clavain_is_headless() {
    local pid=$$ args
    for _ in 1 2 3 4 5 6 7 8; do
        pid=$(ps -o ppid= -p "$pid" 2>/dev/null | tr -d ' ') || return 1
        [[ -z "$pid" || "$pid" == "0" || "$pid" == "1" ]] && return 1
        args=$(ps -o args= -p "$pid" 2>/dev/null) || return 1
        if [[ "$args" == *claude* ]]; then
            case " $args " in
                *" -p "*|*" --print "*) return 0 ;;
            esac
            return 1   # found the claude ancestor and it is interactive
        fi
    done
    return 1
}
