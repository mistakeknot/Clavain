#!/usr/bin/env bash
# lib-goal-audit.sh — entity-backed goal-cadence check (f-016/f-030).
# The standing auditor: fires on ic goal audit defects, independent of the
# goal-completed prose signal. Everything fails open (lib-intercore.sh idiom).

# Callers must have sourced lib-intercore.sh first.

# goal_audit_reason <session_id>
# Prints a Stop-hook REASON string when audit defects exist; empty otherwise.
# Always returns 0 (fail-open).
goal_audit_reason() {
    local session_id="$1"
    if ! type intercore_available >/dev/null 2>&1 || ! intercore_available 2>/dev/null; then
        return 0
    fi
    if ! intercore_sentinel_check_or_legacy "goal_audit_throttle" "$session_id" 3600; then
        return 0
    fi

    local defects audit_rc=0
    defects=$("$INTERCORE_BIN" goal audit --project="$PWD" --dormant-after=604800 2>/dev/null) || audit_rc=$?
    if [[ $audit_rc -gt 1 ]]; then
        return 0
    fi
    if [[ -n "$defects" && "$defects" != "[]" && "$defects" != "null" ]]; then
        # Keep the ready-to-paste command's backticks literal; %s is a printf placeholder.
        # shellcheck disable=SC2016
        printf 'Goal audit: this project has goal defects (dormant, stuck-closing, or closed-without-successor). Run `ic goal audit --project="%s"` and surface each defect to the user with a proposed action (resume, abandon-with-reason, or propose successor).' "$PWD"
    fi
    return 0
}
