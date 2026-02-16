#!/usr/bin/env bash
# lib-verdict.sh — Verdict file utilities for structured agent handoffs.
# Source this from sprint/quality-gates skills or hooks.

set -euo pipefail

VERDICT_DIR="${CLAVAIN_VERDICT_DIR:-.clavain/verdicts}"

# Initialize verdict directory, ensure git-ignored.
verdict_init() {
    mkdir -p "$VERDICT_DIR" 2>/dev/null || true
    local gitignore
    gitignore="$(git rev-parse --show-toplevel 2>/dev/null)/.gitignore" || gitignore=".gitignore"
    if [[ -f "$gitignore" ]]; then
        grep -qxF '.clavain/verdicts/' "$gitignore" 2>/dev/null || echo '.clavain/verdicts/' >> "$gitignore"
    fi
}

# Write a verdict JSON file.
# Usage: verdict_write <agent-name> <type> <status> <model> <summary> [detail-path] [files-changed] [findings-count] [tokens-spent]
verdict_write() {
    local agent="${1:?agent name required}"
    local type="${2:?type required}"    # verdict | implementation
    local status="${3:?status required}" # CLEAN | NEEDS_ATTENTION | etc.
    local model="${4:?model required}"
    local summary="${5:?summary required}"
    local detail_path="${6:-${VERDICT_DIR}/${agent}.md}"
    local files_changed="${7:-[]}"
    local findings_count="${8:-0}"
    local tokens_spent="${9:-0}"

    verdict_init

    local tmp="${VERDICT_DIR}/.${agent}.json.tmp"
    jq -n \
        --arg type "$type" \
        --arg status "$status" \
        --arg model "$model" \
        --arg summary "$summary" \
        --arg detail_path "$detail_path" \
        --argjson files_changed "$files_changed" \
        --argjson findings_count "$findings_count" \
        --argjson tokens_spent "$tokens_spent" \
        --arg timestamp "$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
        '{type: $type, status: $status, model: $model, tokens_spent: $tokens_spent,
          files_changed: $files_changed, findings_count: $findings_count,
          summary: $summary, detail_path: $detail_path, timestamp: $timestamp}' \
        > "$tmp" && mv "$tmp" "${VERDICT_DIR}/${agent}.json"
}

# Read a single verdict's structured header (one-line summary).
# Usage: verdict_read <agent-name>
# Output: STATUS AGENT SUMMARY (tab-separated)
verdict_read() {
    local agent="${1:?agent name required}"
    local f="${VERDICT_DIR}/${agent}.json"
    [[ -f "$f" ]] || return 1
    jq -r '"\(.status)\t\(.model)\t\(.summary)"' "$f" 2>/dev/null
}

# Parse all verdicts and output a summary table.
# Output: one line per agent — STATUS  AGENT  SUMMARY
verdict_parse_all() {
    [[ -d "$VERDICT_DIR" ]] || return 0
    local found=0
    for f in "$VERDICT_DIR"/*.json; do
        [[ -f "$f" ]] || continue
        found=1
        local agent
        agent="$(basename "$f" .json)"
        jq -r --arg a "$agent" '"\(.status)\t\($a)\t\(.summary)"' "$f" 2>/dev/null || true
    done
    [[ $found -eq 0 ]] && return 0
}

# Count verdicts by status.
# Output: "3 CLEAN, 1 NEEDS_ATTENTION"
verdict_count_by_status() {
    [[ -d "$VERDICT_DIR" ]] || { echo "0 verdicts"; return 0; }
    local counts=""
    for status in CLEAN NEEDS_ATTENTION BLOCKED ERROR COMPLETE PARTIAL FAILED; do
        local count=0
        for f in "$VERDICT_DIR"/*.json; do
            [[ -f "$f" ]] || continue
            local s
            s=$(jq -r '.status // ""' "$f" 2>/dev/null) || s=""
            [[ "$s" == "$status" ]] && count=$((count + 1))
        done
        [[ $count -gt 0 ]] && counts="${counts}${count} ${status}, "
    done
    counts="${counts%, }"
    echo "${counts:-0 verdicts}"
}

# Get only NEEDS_ATTENTION verdicts with detail paths.
# Output: AGENT  FINDINGS_COUNT  DETAIL_PATH (tab-separated)
verdict_get_attention() {
    [[ -d "$VERDICT_DIR" ]] || return 0
    for f in "$VERDICT_DIR"/*.json; do
        [[ -f "$f" ]] || continue
        local s
        s=$(jq -r '.status // ""' "$f" 2>/dev/null) || s=""
        if [[ "$s" == "NEEDS_ATTENTION" || "$s" == "FAILED" ]]; then
            local agent
            agent="$(basename "$f" .json)"
            jq -r --arg a "$agent" '"\($a)\t\(.findings_count)\t\(.detail_path)"' "$f" 2>/dev/null || true
        fi
    done
}

# Remove all verdict files (called at sprint start).
verdict_clean() {
    [[ -d "$VERDICT_DIR" ]] || return 0
    rm -f "$VERDICT_DIR"/*.json "$VERDICT_DIR"/.*.json.tmp 2>/dev/null || true
}

# Total tokens spent across all verdicts.
verdict_total_tokens() {
    [[ -d "$VERDICT_DIR" ]] || { echo "0"; return 0; }
    local total=0
    for f in "$VERDICT_DIR"/*.json; do
        [[ -f "$f" ]] || continue
        local t
        t=$(jq -r '.tokens_spent // 0' "$f" 2>/dev/null) || t=0
        total=$((total + t))
    done
    echo "$total"
}
