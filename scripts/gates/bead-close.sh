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

# A proof-labeled close gate is checked before authorization so a failed proof
# cannot consume a one-shot token. Label lookup is read-only and unlabeled
# beads retain the existing close path.
bead_has_label() {
  local bead="$1" label="$2" raw
  raw="$(bd show "$bead" --json 2>/dev/null)" || return 1
  if command -v jq >/dev/null 2>&1; then
    jq -e --arg label "$label" '.[0].labels // [] | index($label) != null' <<<"$raw" >/dev/null 2>&1
  else
    printf '%s' "$raw" | grep -Fq "\"${label}\""
  fi
}

if bead_has_label "$BEAD_ID" "close-gate:calibration-streak"; then
  clavain-cli calibration-streak verify --target=10
fi

# Runtime evidence is durable once bound. Requirement discovery therefore goes
# through the CLI instead of consulting only the bead's current labels. Every
# fallible proof operation, including the durable summary write, precedes
# one-shot authorization consumption.
runtime_required="$(clavain-cli runtime-evidence required "$BEAD_ID")" || {
  echo "runtime-evidence: failed to determine requirement for $BEAD_ID" >&2
  exit 1
}

case "$runtime_required" in
  true)
    command -v jq >/dev/null 2>&1 || {
      echo "runtime-evidence: jq is required to validate the proof summary" >&2
      exit 1
    }

    runtime_summary="$(clavain-cli runtime-evidence verify "$BEAD_ID")" || {
      echo "runtime-evidence: verification failed for $BEAD_ID" >&2
      exit 1
    }
    if ! runtime_summary="$(jq -ce '
      select(
        type == "object" and
        (keys | sort) == ["git_head","host_fingerprint","proof_hash","run_id","schema_version","verified_at"] and
        .schema_version == 1 and
        (.proof_hash | type == "string" and test("^sha256:[0-9a-f]{64}$")) and
        (.run_id | type == "string" and length > 0) and
        (.git_head | type == "string" and test("^[0-9a-f]{40,64}$")) and
        (.verified_at | type == "string" and length > 0) and
        (.host_fingerprint | type == "string" and test("^sha256:[0-9a-f]{64}$"))
      ) |
      {schema_version,proof_hash,run_id,git_head,verified_at,host_fingerprint}
    ' <<<"$runtime_summary")"; then
      echo "runtime-evidence: verifier returned a malformed or unsafe summary" >&2
      exit 1
    fi

    runtime_run_id="$(jq -er '.run_id' <<<"$runtime_summary")" || {
      echo "runtime-evidence: verified summary has no run ID" >&2
      exit 1
    }
    runtime_run="$(ic --json run status "$runtime_run_id")" || {
      echo "runtime-evidence: cannot read associated run $runtime_run_id" >&2
      exit 1
    }
    if ! jq -e --arg run "$runtime_run_id" '
      type == "object" and .id == $run and .status == "completed" and .phase == "done"
    ' >/dev/null 2>&1 <<<"$runtime_run"; then
      echo "runtime-evidence: associated run must be completed at done" >&2
      exit 1
    fi

    bd set-state "$BEAD_ID" "runtime_evidence_summary=$runtime_summary" \
      --reason="Verified installed runtime before close"
    ;;
  false) ;;
  *)
    echo "runtime-evidence: unexpected requirement result for $BEAD_ID: $runtime_required" >&2
    exit 1
    ;;
esac

# v2 token path: if $CLAVAIN_AUTHZ_TOKEN is set, try to consume it first.
# Hard-fails on auth-failure class (revoked | sig-verify | POP | mismatch);
# state-class errors fall through to legacy gate_check below.
if ! gate_token_consume bead-close "$BEAD_ID"; then
  exit 1
fi

if [[ "${GATE_CONSUMED:-0}" != "1" ]]; then
  gate_populate_vetting "$BEAD_ID"

  check_flags=( --target="$BEAD_ID" --bead="$BEAD_ID" )
  if [[ -n "${CLAVAIN_VETTED_AT:-}"         ]]; then check_flags+=( --vetted-at="$CLAVAIN_VETTED_AT" ); fi
  if [[ -n "${CLAVAIN_VETTED_SHA:-}"        ]]; then check_flags+=( --vetted-sha="$CLAVAIN_VETTED_SHA" ); fi
  if [[ "${CLAVAIN_TESTS_PASSED:-0}"  == "1" ]]; then check_flags+=( --tests-passed ); fi
  if [[ "${CLAVAIN_SPRINT_OR_WORK:-0}" == "1" ]]; then check_flags+=( --sprint-or-work-flow ); fi

  rc=0
  gate_check bead-close "${check_flags[@]}" >/dev/null || rc=$?
  gate_decide_mode "$rc" bead-close
fi

if [[ -n "$REASON" ]]; then
  bd close "$BEAD_ID" --reason="$REASON"
else
  bd close "$BEAD_ID"
fi

gate_record bead-close "$BEAD_ID" "$BEAD_ID"
gate_sign   bead-close "$BEAD_ID" "$BEAD_ID"
