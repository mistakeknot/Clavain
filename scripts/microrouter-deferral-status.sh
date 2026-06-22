#!/usr/bin/env bash
# Surface microrouter architecture-decision deferral state for /clavain:status.
#
# Reads bd state fields (labels) on sylveste-s3z6.19.10 and reports the active
# deferral tier relative to today's date. Filed as F4 of the .19.10 decision
# (sylveste-58tb); the deferral mechanics themselves were shipped in 21ee907f.
#
# State fields read (bd labels, "key:value"):
#   deferral_check_in           (YYYY-MM-DD) escalating check-in date
#   deferral_deadline           (YYYY-MM-DD) hard decision deadline
#   decision_authority_primary  named primary authority
#   decision_authority_backup   named backup authority
#   auto_revert_action          what happens at deadline (surface-forced-reentry)
#   d2_result                   D2 measurement outcome; "kill-epic" forces re-entry
#
# Tiers (check-in track):
#   healthy   today < check_in
#   due       check_in <= today < check_in+7d
#   overdue   check_in+7d <= today < check_in+14d   -> "extend or re-enter" nudge
#   stale     today >= check_in+14d                 -> BLOCKING-style notice
# Tiers (deadline track):
#   approaching  today within 7d of deadline
#   exceeded     today > deadline                   -> forced-reentry notice
# Override:
#   d2_result=kill-epic                             -> forced-reentry regardless of date
#
# Usage: microrouter-deferral-status.sh [--bead ID] [--today YYYY-MM-DD]
#   --today is for testing; defaults to the system date.
#
# Exit: 0 always (fail-open -- never block status output). Prints nothing when
#       the bead or its deferral fields are unavailable, so /clavain:status
#       stays silent for environments without the microrouter epic.

set -uo pipefail

BEAD="sylveste-s3z6.19.10"
TODAY="$(date +%F)"

while [[ $# -gt 0 ]]; do
    case "$1" in
        --bead) BEAD="$2"; shift 2 ;;
        --today) TODAY="$2"; shift 2 ;;
        *) shift ;;
    esac
done

command -v bd &>/dev/null || exit 0
command -v jq &>/dev/null || exit 0

labels_json=$(bd show "$BEAD" --json 2>/dev/null) || exit 0
[[ -n "$labels_json" ]] || exit 0

# bd show --json returns an array of one issue.
get_label() {
    echo "$labels_json" | jq -r --arg p "$1:" \
        '(.[0].labels // [])[] | select(startswith($p)) | sub("^" + $p; "")' \
        2>/dev/null | head -1
}

CHECK_IN=$(get_label deferral_check_in)
DEADLINE=$(get_label deferral_deadline)
AUTH_PRIMARY=$(get_label decision_authority_primary)
AUTH_BACKUP=$(get_label decision_authority_backup)
AUTO_REVERT=$(get_label auto_revert_action)
D2_RESULT=$(get_label d2_result)

# No deferral fields -> nothing to surface (silent).
[[ -n "$CHECK_IN" || -n "$DEADLINE" ]] || exit 0

# Date math in whole days. Uses python3 for portable parsing (BSD vs GNU date).
days_between() {
    # echoes (b - a) in days; empty on parse failure
    python3 - "$1" "$2" <<'PY' 2>/dev/null
import sys, datetime
try:
    a = datetime.date.fromisoformat(sys.argv[1])
    b = datetime.date.fromisoformat(sys.argv[2])
    print((b - a).days)
except Exception:
    pass
PY
}

verdict="PASS"
lines=()

if [[ -n "$CHECK_IN" ]]; then
    d=$(days_between "$CHECK_IN" "$TODAY")
    if [[ -n "$d" ]]; then
        if (( d < 0 )); then
            lines+=("check-in healthy -- next check-in $CHECK_IN ($((-d))d out)")
        elif (( d < 7 )); then
            lines+=("check-in DUE (since $CHECK_IN) -- review the deferral")
            [[ "$verdict" == "PASS" ]] && verdict="WARN"
        elif (( d < 14 )); then
            lines+=("check-in OVERDUE (${d}d past $CHECK_IN) -- extend or re-enter: /clavain:route $BEAD")
            verdict="WARN"
        else
            lines+=("check-in STALE (${d}d past $CHECK_IN) -- BLOCKING: re-enter the decision now: /clavain:route $BEAD")
            verdict="FAIL"
        fi
    fi
fi

if [[ -n "$DEADLINE" ]]; then
    d=$(days_between "$TODAY" "$DEADLINE")
    if [[ -n "$d" ]]; then
        if (( d < 0 )); then
            lines+=("deadline EXCEEDED ($DEADLINE, ${d#-}d ago) -- forced re-entry: Run /clavain:route $BEAD -- deadline passed")
            verdict="FAIL"
        elif (( d <= 7 )); then
            lines+=("deadline APPROACHING ($DEADLINE, ${d}d out) -- decide or extend before the deadline")
            [[ "$verdict" != "FAIL" ]] && verdict="WARN"
        else
            lines+=("deadline $DEADLINE (${d}d out)")
        fi
    fi
fi

if [[ "$D2_RESULT" == "kill-epic" ]]; then
    lines+=("d2_result=kill-epic -- forced re-entry regardless of date: Run /clavain:route $BEAD")
    verdict="FAIL"
fi

echo "Microrouter deferral ($BEAD): $verdict"
authority="$AUTH_PRIMARY"
[[ -n "$AUTH_BACKUP" && "$AUTH_BACKUP" != "$AUTH_PRIMARY" ]] && authority="$AUTH_PRIMARY / $AUTH_BACKUP (backup)"
[[ -n "$authority" ]] && echo "  authority: $authority${AUTO_REVERT:+ . at deadline: $AUTO_REVERT}"
for l in "${lines[@]}"; do
    echo "  - $l"
done

exit 0
