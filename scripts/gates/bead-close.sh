#!/usr/bin/env bash
# Gate wrapper for `bd close <bead-id>`.
#
# Usage: bead-close.sh <bead-id> [reason]
#
# Policy check enforces the bead-close rule from the merged policy.
# On auto, runs `bd close` silently. On confirm (rc=1), prompts (tty) or
# aborts (non-tty). On block (rc=2) or malformed (rc=3), aborts.
set -euo pipefail

BEAD_ID="${1:?usage: bead-close.sh <bead-id> [reason]}"
REASON="${2:-}"

# shellcheck source=/dev/null
source "$(dirname "$0")/_common.sh"

check_flags=( --target="$BEAD_ID" --bead="$BEAD_ID" )
if [[ -n "${CLAVAIN_VETTED_AT:-}"         ]]; then check_flags+=( --vetted-at="$CLAVAIN_VETTED_AT" ); fi
if [[ -n "${CLAVAIN_VETTED_SHA:-}"        ]]; then check_flags+=( --vetted-sha="$CLAVAIN_VETTED_SHA" ); fi
if [[ "${CLAVAIN_TESTS_PASSED:-0}"  == "1" ]]; then check_flags+=( --tests-passed ); fi
if [[ "${CLAVAIN_SPRINT_OR_WORK:-0}" == "1" ]]; then check_flags+=( --sprint-or-work-flow ); fi

rc=0
gate_check bead-close "${check_flags[@]}" >/dev/null || rc=$?
gate_decide_mode "$rc" bead-close

if [[ -n "$REASON" ]]; then
  bd close "$BEAD_ID" --reason="$REASON"
else
  bd close "$BEAD_ID"
fi

gate_record bead-close "$BEAD_ID" "$BEAD_ID"
