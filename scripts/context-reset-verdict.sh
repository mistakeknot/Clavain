#!/usr/bin/env bash
# context-reset-verdict.sh — the observe-mode "verdict" for mk-42j9.40.
#
# NOT A SECURITY BOUNDARY. Reads one telemetry row (a JSON object) on stdin,
# stamps it verdict "allow", and appends it to <store>/events.jsonl. It always
# prints an allow decision and always exits 0. There is no other verdict, and
# nothing here blocks, enforces, or resets. A row that cannot be written is
# reported on stderr, never silently dropped. The store is plain JSON and is not
# tamper-resistant.
#
# Usage: context-reset-verdict.sh [--store DIR] < row.json
set -uo pipefail

store="${CLAVAIN_CONTEXT_RESET_DIR:-${HOME:-.}/.clavain/context-reset}"
while [[ $# -gt 0 ]]; do
    case "$1" in
        --store) store="${2:-$store}"; shift 2 || shift ;;
        --store=*) store="${1#--store=}"; shift ;;
        -h|--help)
            printf 'Usage: context-reset-verdict.sh [--store DIR] < row.json\n'
            printf 'Observe-mode telemetry only; NOT a security boundary. Always allows.\n'
            exit 0 ;;
        *) shift ;;
    esac
done

row=$(cat 2>/dev/null) || row=""
line=$(printf '%s' "$row" | jq -cs 'if length == 1 and (.[0] | type) == "object"
    then .[0] + {verdict: "allow"} else error("row is not one JSON object") end' 2>/dev/null) || line=""
if [[ -z "$line" ]]; then
    line=$(jq -nc --argjson len "${#row}" '{event: "hook_error", stage: "verdict-input", raw_len: $len,
        verdict: "allow", security_boundary: false}' 2>/dev/null) || line='{"event":"hook_error","stage":"verdict-input","verdict":"allow","security_boundary":false}'
fi

recorded=false
if { mkdir -p "$store" && printf '%s\n' "$line" >> "$store/events.jsonl"; } 2>/dev/null; then
    recorded=true
else
    printf 'context-reset: row NOT recorded in %s (observe-mode telemetry only, not a security boundary; nothing was blocked)\n' "$store/events.jsonl" >&2
fi
printf '{"decision":"allow","recorded":%s}\n' "$recorded"
exit 0
