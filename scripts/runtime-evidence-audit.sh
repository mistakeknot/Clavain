#!/usr/bin/env bash
# Read-only reconciliation for close-gate:runtime-evidence beads.

set -uo pipefail

LABEL="close-gate:runtime-evidence"
ARTIFACT_TYPE="runtime-evidence/v1"
FINDINGS='[]'
BEAD_COUNT=0

usage() {
  cat <<'EOF'
Usage: runtime-evidence-audit.sh [--json]

Audits runtime-evidence bead/run correlation without modifying tracker or run
state. Output is always JSON. Exit status is 1 for findings and 2 when an
otherwise supported audit cannot complete.
EOF
}

case "${1:-}" in
  ""|--json) ;;
  -h|--help)
    usage
    exit 0
    ;;
  *)
    usage >&2
    exit 2
    ;;
esac
[[ $# -le 1 ]] || { usage >&2; exit 2; }

json_result() {
  local supported="$1" reason="${2:-}" repository=""
  repository="$(git rev-parse --show-toplevel 2>/dev/null || true)"
  jq -cn \
    --argjson supported "$supported" \
    --arg reason "$reason" \
    --arg repository "$repository" \
    --arg label "$LABEL" \
    --arg generated_at "$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
    --argjson beads "$BEAD_COUNT" \
    --argjson findings "$FINDINGS" '
      {
        schema_version: 1,
        supported: $supported,
        generated_at: $generated_at,
        scope: {label: $label, repository: $repository},
        counts: {beads: $beads, findings: ($findings | length)},
        findings: $findings
      }
      + (if $reason == "" then {} else {reason: $reason} end)
    '
}

unsupported() {
  local reason="$1" status="${2:-0}"
  json_result false "$reason"
  exit "$status"
}

command -v jq >/dev/null 2>&1 || {
  printf '{"schema_version":1,"supported":false,"reason":"jq is unavailable","counts":{"beads":0,"findings":0},"findings":[]}\n'
  exit 0
}

BD_BIN="${CLAVAIN_RUNTIME_AUDIT_BD:-$(command -v bd 2>/dev/null || true)}"
IC_BIN="${CLAVAIN_RUNTIME_AUDIT_IC:-$(command -v ic 2>/dev/null || true)}"
CLI_BIN="${CLAVAIN_RUNTIME_AUDIT_CLI:-$(command -v clavain-cli 2>/dev/null || true)}"

[[ -n "$BD_BIN" ]] || unsupported "bd is unavailable"
[[ -n "$IC_BIN" ]] || unsupported "ic is unavailable"
[[ -n "$CLI_BIN" ]] || unsupported "clavain-cli is unavailable"

add_finding() {
  local code="$1" severity="$2" bead_id="$3" run_id="$4" message="$5" action="$6"
  FINDINGS="$(jq -cn \
    --argjson current "$FINDINGS" \
    --arg code "$code" \
    --arg severity "$severity" \
    --arg bead_id "$bead_id" \
    --arg run_id "$run_id" \
    --arg message "$message" \
    --arg action "$action" '
      $current + [{
        code: $code,
        severity: $severity,
        bead_id: $bead_id,
        run_id: (if $run_id == "" then null else $run_id end),
        message: $message,
        action: $action
      }]
  ')"
}

read_state() {
  local bead_id="$1" dimension="$2" value
  value="$("$BD_BIN" --readonly state "$bead_id" "$dimension" 2>/dev/null)" || return 1
  case "$value" in
    ""|null|"(no "*) printf '' ;;
    *) printf '%s' "$value" ;;
  esac
}

summary_valid() {
  local summary="$1" linked_run_id="$2"
  jq -e --arg linked "$linked_run_id" '
    type == "object" and
    (keys | sort) == ["git_head","host_fingerprint","proof_hash","run_id","schema_version","verified_at"] and
    .schema_version == 1 and
    (.proof_hash | type == "string" and test("^sha256:[0-9a-f]{64}$")) and
    (.run_id | type == "string" and length > 0) and
    (.git_head | type == "string" and test("^[0-9a-f]{40,64}$")) and
    (.verified_at | type == "string" and test("^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}(\\.[0-9]+)?(Z|[+-][0-9]{2}:[0-9]{2})$")) and
    (.host_fingerprint | type == "string" and test("^sha256:[0-9a-f]{64}$")) and
    ($linked == "" or .run_id == $linked)
  ' >/dev/null 2>&1 <<<"$summary"
}

run_is_bound() {
  local run_json="$1" bead_id="$2"
  jq -e --arg bead "$bead_id" --arg requirement "$ARTIFACT_TYPE" '
    def metadata_object:
      if (.metadata | type) == "object" then .metadata
      elif (.metadata | type) == "string" then (try (.metadata | fromjson) catch {})
      else {}
      end;
    metadata_object as $metadata |
    (($metadata.close_gate.requirements // []) | index($requirement)) != null and
    $metadata.close_gate.bead_id == $bead
  ' >/dev/null 2>&1 <<<"$run_json"
}

backend_error="$(mktemp "${TMPDIR:-/tmp}/clavain-runtime-audit.XXXXXX")" || unsupported "cannot allocate audit scratch space" 2
trap 'rm -f "$backend_error"' EXIT

if ! beads_json="$("$BD_BIN" --readonly list --all --label="$LABEL" --limit=0 --json 2>"$backend_error")"; then
  backend_message="$(cat "$backend_error" 2>/dev/null || true)"
  if [[ "$backend_message" == *"no beads database found"* || "$backend_message" == *"not initialized"* ]]; then
    unsupported "repository has no Beads tracker"
  fi
  unsupported "Beads tracker query failed" 2
fi
if ! jq -e 'type == "array"' >/dev/null 2>&1 <<<"$beads_json"; then
  unsupported "Beads tracker returned malformed JSON" 2
fi

BEAD_COUNT="$(jq 'length' <<<"$beads_json")"

while IFS= read -r bead_json; do
  bead_id="$(jq -r '.id // empty' <<<"$bead_json")"
  bead_status="$(jq -r '.status // empty' <<<"$bead_json")"
  [[ -n "$bead_id" ]] || {
    add_finding "tracker_record_invalid" "error" "unknown" "" \
      "A labeled tracker record has no bead ID." \
      "Run bd doctor before relying on runtime evidence state."
    continue
  }

  linked_run_id=""
  if ! linked_run_id="$(read_state "$bead_id" ic_run_id)"; then
    add_finding "run_lookup_failed" "error" "$bead_id" "" \
      "The bead's Intercore run binding could not be read." \
      "Repair tracker state, then rerun the runtime evidence audit."
    continue
  fi

  # Historical evidence is intentionally self-contained. Never reopen a local
  # receipt path or apply the live freshness window after the bead is closed.
  if [[ "$bead_status" == "closed" ]]; then
    durable_summary=""
    if ! durable_summary="$(read_state "$bead_id" runtime_evidence_summary)"; then
      add_finding "durable_summary_malformed" "error" "$bead_id" "$linked_run_id" \
        "The closed bead's durable runtime proof summary cannot be read." \
        "Restore the sanitized close summary from canonical tracker history."
      continue
    fi
    if [[ -z "$durable_summary" ]]; then
      add_finding "durable_summary_missing" "error" "$bead_id" "$linked_run_id" \
        "The closed runtime-gated bead has no durable proof summary." \
        "Restore the verified six-field summary from canonical close history."
    elif ! summary_valid "$durable_summary" "$linked_run_id"; then
      add_finding "durable_summary_malformed" "error" "$bead_id" "$linked_run_id" \
        "The closed bead's durable proof summary is malformed or names a different run." \
        "Reconcile the sanitized summary against canonical close and run history."
    fi
    continue
  fi

  if ! scoped_runs="$("$IC_BIN" --json run list --scope="$bead_id" 2>/dev/null)" || \
     ! jq -e 'type == "array"' >/dev/null 2>&1 <<<"$scoped_runs"; then
    add_finding "run_lookup_failed" "error" "$bead_id" "$linked_run_id" \
      "Intercore run state is unavailable for this active gated bead." \
      "Repair Intercore access, then rerun the runtime evidence audit."
    continue
  fi

  active_scope_count="$(jq '[.[] | select((.status // "") != "completed" and (.status // "") != "cancelled")] | length' <<<"$scoped_runs")"
  if [[ -z "$linked_run_id" ]]; then
    add_finding "run_missing" "error" "$bead_id" "" \
      "The active runtime-gated bead has no durable Intercore run binding." \
      "Run clavain-cli runtime-evidence adopt with project and provenance."
    continue
  fi
  if [[ "$active_scope_count" -gt 1 ]]; then
    add_finding "run_conflict" "error" "$bead_id" "$linked_run_id" \
      "More than one nonterminal Intercore run claims this gated bead." \
      "Reconcile the duplicate runs and retain one canonical binding."
    continue
  fi

  linked_run="$(jq -c --arg run "$linked_run_id" '.[] | select(.id == $run)' <<<"$scoped_runs" | head -n 1)"
  if [[ -z "$linked_run" ]]; then
    linked_run="$("$IC_BIN" --json run status "$linked_run_id" 2>/dev/null || true)"
  fi
  if ! jq -e --arg run "$linked_run_id" --arg bead "$bead_id" \
      'type == "object" and .id == $run and .scope_id == $bead' \
      >/dev/null 2>&1 <<<"$linked_run"; then
    add_finding "run_conflict" "error" "$bead_id" "$linked_run_id" \
      "The bead's stored run binding is missing or belongs to another scope." \
      "Reconcile ic_run_id with the canonical scoped Intercore run."
    continue
  fi
  if ! run_is_bound "$linked_run" "$bead_id"; then
    add_finding "run_conflict" "error" "$bead_id" "$linked_run_id" \
      "The linked run is not sealed to this bead's runtime evidence requirement." \
      "Run clavain-cli runtime-evidence bind for this bead."
    continue
  fi

  run_status="$(jq -r '.status // empty' <<<"$linked_run")"
  run_phase="$(jq -r '.phase // empty' <<<"$linked_run")"
  if [[ "$run_status" == "completed" ]]; then
    if [[ "$run_phase" == "done" ]]; then
      add_finding "bead_open_after_run_completed" "error" "$bead_id" "$linked_run_id" \
        "The Intercore run completed at done but the gated bead remains open." \
        "Reconcile close authorization and close through scripts/gates/bead-close.sh."
    else
      add_finding "run_conflict" "error" "$bead_id" "$linked_run_id" \
        "The linked run is completed outside the terminal done phase." \
        "Inspect the run event history before changing tracker state."
    fi
    continue
  fi
  if [[ "$run_status" == "cancelled" ]]; then
    add_finding "run_conflict" "error" "$bead_id" "$linked_run_id" \
      "The active gated bead points to a cancelled run." \
      "Adopt or bind the one canonical nonterminal run before continuing."
    continue
  fi

  project_dir="$(jq -r '.project_dir // empty' <<<"$linked_run")"
  if [[ "$project_dir" != /* || ! -d "$project_dir" ]]; then
    continue
  fi

  if ! artifacts="$("$IC_BIN" --json run artifact list "$linked_run_id" 2>/dev/null)" || \
     ! jq -e 'type == "array"' >/dev/null 2>&1 <<<"$artifacts"; then
    add_finding "receipt_invalid" "error" "$bead_id" "$linked_run_id" \
      "Runtime artifact state is unavailable for this current-host active run." \
      "Repair Intercore artifact access, then recollect runtime evidence."
    continue
  fi
  newest_receipt="$(jq -c --arg kind "$ARTIFACT_TYPE" \
    '[.[] | select(.type == $kind and ((.status // "active") == "active"))] | last // empty' \
    <<<"$artifacts")"
  if [[ -z "$newest_receipt" ]]; then
    add_finding "receipt_missing" "error" "$bead_id" "$linked_run_id" \
      "The current-host active run has no registered runtime evidence receipt." \
      "Run clavain-cli runtime-evidence collect with the tracked config."
    continue
  fi

  receipt_path="$(jq -r '.path // empty' <<<"$newest_receipt")"
  verified_summary=""
  if [[ -z "$receipt_path" || ! -f "$receipt_path" ]] || \
     ! verified_summary="$("$CLI_BIN" runtime-evidence verify "$bead_id" 2>/dev/null)" || \
     ! summary_valid "$verified_summary" "$linked_run_id"; then
    add_finding "receipt_invalid" "error" "$bead_id" "$linked_run_id" \
      "The newest current-host receipt is missing, stale, or fails live verification." \
      "Reinstall if needed, then recollect runtime evidence before terminal advance."
  fi
done < <(jq -c '.[]' <<<"$beads_json")

json_result true
if [[ "$(jq 'length' <<<"$FINDINGS")" -gt 0 ]]; then
  exit 1
fi
exit 0
