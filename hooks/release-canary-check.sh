#!/usr/bin/env bash
# SessionStart hook: release canary check (sylveste-ao0q)
#
# `ic publish` registers a pending release canary per publish
# (~/.clavain/release-canaries.json). This hook verifies each pending canary
# against THIS session's actual plugin resolution surface: the
# installed_plugins.json installPath must exist and its plugin.json must
# parse — exactly the surface that fails silently when a publish breaks the
# install (Sylveste-0lt: cache dir deleted, every command gone, no signal).
#
# Passed  → canary marked passed, no output.
# Failed  → canary marked failed + loud systemMessage carrying the
#           ready-to-run rollback command.
#
# Env overrides (test harness): CLAVAIN_CANARY_FILE, CLAVAIN_INSTALLED_FILE.
# Exit: 0 always (fail-open).

set -uo pipefail
trap 'exit 0' ERR

CANARY_FILE="${CLAVAIN_CANARY_FILE:-$HOME/.clavain/release-canaries.json}"
INSTALLED_FILE="${CLAVAIN_INSTALLED_FILE:-$HOME/.claude/plugins/installed_plugins.json}"

command -v jq &>/dev/null || exit 0
[[ -f "$CANARY_FILE" && -f "$INSTALLED_FILE" ]] || exit 0

pending="$(jq -c '.[] | select(.status=="pending")' "$CANARY_FILE" 2>/dev/null || true)"
[[ -n "$pending" ]] || exit 0

now="$(date +%s)"
alerts=""

while IFS= read -r rec; do
    plugin="$(jq -r '.plugin // empty' <<<"$rec")"
    mkt="$(jq -r '.marketplace // empty' <<<"$rec")"
    ver="$(jq -r '.version // empty' <<<"$rec")"
    [[ -n "$plugin" && -n "$mkt" ]] || continue
    key="${plugin}@${mkt}"

    install_path="$(jq -r --arg k "$key" '.plugins[$k][0].installPath // empty' "$INSTALLED_FILE" 2>/dev/null || true)"

    status="failed"
    if [[ -n "$install_path" && -d "$install_path" ]] \
        && jq -e . "$install_path/.claude-plugin/plugin.json" >/dev/null 2>&1; then
        status="passed"
        note="resolved at session start"
    else
        note="installPath missing or plugin.json invalid: ${install_path:-<no installed record>}"
        alerts+="RELEASE CANARY FAILED: ${plugin} v${ver} did not load (${note}). Roll back with: ic publish rollback ${plugin}"$'\n'
    fi

    tmp="$(mktemp)"
    if jq --arg p "$plugin" --arg m "$mkt" --arg s "$status" --arg n "$note" --argjson t "$now" \
        'map(if .plugin==$p and .marketplace==$m then .status=$s | .note=$n | .checked_at=$t else . end)' \
        "$CANARY_FILE" > "$tmp" 2>/dev/null; then
        mv "$tmp" "$CANARY_FILE"
    else
        rm -f "$tmp"
    fi
done <<<"$pending"

if [[ -n "$alerts" ]]; then
    jq -n --arg msg "$alerts" \
        '{"systemMessage": $msg, "hookSpecificOutput": {"hookEventName": "SessionStart", "additionalContext": $msg}}'
fi
exit 0
