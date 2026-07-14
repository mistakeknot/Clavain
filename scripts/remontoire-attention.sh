#!/usr/bin/env bash
set -uo pipefail

format="hook"
case "${1:-}" in
  "") ;;
  --format=hook) format="hook" ;;
  --format=json) format="json" ;;
  *)
    echo "usage: remontoire-attention.sh [--format=hook|--format=json]" >&2
    exit 2
    ;;
esac
[[ $# -le 1 ]] || {
  echo "usage: remontoire-attention.sh [--format=hook|--format=json]" >&2
  exit 2
}

degraded_json='{"schema_version":"clavain.remontoire-attention/v1","available":false,"action":null,"promotions":[]}'

degrade() {
  if [[ "$format" == "json" ]]; then
    printf '%s\n' "$degraded_json"
  fi
  exit 0
}

command -v jq >/dev/null 2>&1 || degrade

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)"
candidates=()
[[ -n "${CLAVAIN_REMONTOIRE_ADAPTER:-}" ]] && candidates+=("$CLAVAIN_REMONTOIRE_ADAPTER")
[[ -n "${CLAUDE_PLUGIN_ROOT:-}" ]] && candidates+=("$CLAUDE_PLUGIN_ROOT/scripts/remontoire-operator.sh")
candidates+=("$script_dir/remontoire-operator.sh")
if [[ -n "${HOME:-}" ]]; then
  candidates+=(
    "$HOME/.codex/clavain/scripts/remontoire-operator.sh"
    "$HOME/projects/Sylveste/os/Clavain/scripts/remontoire-operator.sh"
  )
fi

adapter=""
for candidate in "${candidates[@]}"; do
  if [[ -f "$candidate" ]]; then
    adapter="$candidate"
    break
  fi
done
[[ -n "$adapter" ]] || degrade

# Ambient consumers have one read-only capability: the attention projection.
projection="$(bash "$adapter" attention 2>/dev/null)" || degrade
projection="$(printf '%s' "$projection" | jq -ce '
  select(.schema_version == "remontoire.attention/v1")
  | select((.cycle | type) == "object")
  | select((.promotions | type) == "array")
' 2>/dev/null)" || degrade
[[ -n "$projection" ]] || degrade

cycle_id="$(printf '%s' "$projection" | jq -r '.cycle.id // empty')"
stage="$(printf '%s' "$projection" | jq -r '.cycle.stage // empty')"
receipt_id="$(printf '%s' "$projection" | jq -r '.cycle.signed_receipt_id // empty')"
failure="$(printf '%s' "$projection" | jq -r '.cycle.failure // empty')"
[[ -n "$cycle_id" && -n "$stage" ]] || degrade

surface="${CLAVAIN_AGENT_SURFACE:-claude}"
if [[ "$surface" == "codex" ]]; then
  command_prefix="/prompts:clavain-remontoire"
else
  command_prefix="/clavain:remontoire"
fi

action_kind=""
next_command=""
context=""
case "$stage" in
  awaiting_approval)
    action_kind="principal_decision"
    next_command="$command_prefix inspect $cycle_id"
    context="Remontoire cycle $cycle_id is awaiting a principal decision. Inspect it with $next_command. This ambient notice is read-only and does not approve or resume the cycle."
    ;;
  approved|executing|reviewing|compounding)
    action_kind="resume_required"
    next_command="$command_prefix resume $cycle_id"
    context="Remontoire cycle $cycle_id remains in stage $stage. Resuming is an explicit operator action: $next_command. This ambient notice does not resume it."
    ;;
  failed)
    if [[ -n "$receipt_id" ]]; then
      action_kind="receipt_replay"
      next_command="$command_prefix receipt replay $cycle_id"
      context="Remontoire cycle $cycle_id failed. A signed receipt is available; replay it with $next_command."
    else
      action_kind="doctor"
      next_command="$command_prefix doctor"
      context="Remontoire cycle $cycle_id failed without a signed receipt. Diagnose the agency with $next_command."
    fi
    [[ -z "$failure" ]] || context+=" Failure: $failure"
    ;;
esac

promotions="$(printf '%s' "$projection" | jq -c '
  [.promotions[] | {
    id: (.id // ""),
    title: (.title // ""),
    description: (.description // ""),
    acceptance_criteria: (.acceptance_criteria // ""),
    status: (.status // "open"),
    priority: (.priority // 2),
    issue_type: (.issue_type // "task"),
    dependent_count: (.dependent_count // 0),
    labels: (.labels // []),
    dependencies: (.dependencies // [])
  }]
' 2>/dev/null)" || degrade

action="null"
if [[ -n "$action_kind" ]]; then
  action="$(jq -cn \
    --arg cycle_id "$cycle_id" \
    --arg stage "$stage" \
    --arg kind "$action_kind" \
    --arg next_command "$next_command" \
    --arg failure "$failure" \
    '{cycle_id: $cycle_id, stage: $stage, kind: $kind, next_command: $next_command}
     + (if $failure == "" then {} else {failure: $failure} end)')" || degrade
fi

if [[ "$format" == "json" ]]; then
  jq -cn \
    --argjson action "$action" \
    --argjson promotions "$promotions" \
    '{
      schema_version: "clavain.remontoire-attention/v1",
      available: true,
      action: $action,
      promotions: $promotions
    }' || degrade
  exit 0
fi

[[ -n "$context" ]] || exit 0
jq -cn --arg context "$context" '{
  hookSpecificOutput: {
    hookEventName: "SessionStart",
    additionalContext: $context
  }
}' || exit 0
