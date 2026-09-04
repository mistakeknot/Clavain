#!/usr/bin/env bash
# gauge-gate-executor-spawn.sh — PreToolUse gate on Pattern F executor spawns.
#
# Fires on Task/Agent tool calls. Keys on the two marker lines that open every
# Pattern F executor prompt:
#   PATTERN-F EXECUTOR PLAN: <abs plan path>
#   REPO: <abs repo path>
# and runs scripts/plan-gauge-lint.py on that plan. The spawn is blocked
# ({"decision":"block"} on stdout, exit 0) when the plan file is missing, the
# linter is missing, the linter finds gauge defects (exit 1), or the linter
# cannot read the plan (exit 2 or any other non-zero). Prompts without the
# first marker are not executor spawns and pass through silently, as do empty
# prompts and non-JSON stdin. Allowing = print nothing, exit 0.
#
# Every refusal is also recorded as one evidence row (role gate, kind gate,
# verdict FAIL, the refusal reason as the note) through
# scripts/pattern-f-verdict.sh, in the register at $INTERSPECT_DB, else
# $CLAUDE_PROJECT_DIR/.clavain/interspect/interspect.db, else the REPO's. A
# failed write changes only stderr, never the decision: the spawn is still
# blocked and stderr names the register that did not take the row.
set -euo pipefail

payload=$(cat) || true
[[ -z "$payload" ]] && exit 0

prompt=$(jq -r '.tool_input.prompt // empty' <<<"$payload" 2>/dev/null) || exit 0
[[ -z "$prompt" ]] && exit 0

plan=$(printf '%s\n' "$prompt" | sed -n 's/^PATTERN-F EXECUTOR PLAN:[[:space:]]*//p' | head -1 | sed 's/[[:space:]]*$//') || true
[[ -z "$plan" ]] && exit 0

repo=$(printf '%s\n' "$prompt" | sed -n 's/^REPO:[[:space:]]*//p' | head -1 | sed 's/[[:space:]]*$//') || true
[[ -z "$repo" ]] && repo="${CLAUDE_PROJECT_DIR:-$PWD}"

script_dir=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
root="${CLAUDE_PLUGIN_ROOT:-$script_dir/..}"
linter="$root/scripts/plan-gauge-lint.py"

record_refusal() {
  local reason="$1" note sid db script
  # The register keeps 300 characters of the note; keep it to the findings by
  # dropping the fixed prefixes (the row's plan field already carries the
  # plan's basename) and shortening any remaining plan path to its name.
  note="${reason#pattern-f gauge gate: }"
  note="${note//"$plan"/"${plan##*/}"}"
  note="${note#plan-gauge-lint refused "${plan##*/}": }"
  sid=$(jq -r '.session_id // empty' <<<"$payload" 2>/dev/null) || sid=""
  [[ -n "$sid" ]] || sid="unknown-session"
  db="${INTERSPECT_DB:-${CLAUDE_PROJECT_DIR:-$repo}/.clavain/interspect/interspect.db}"
  script="$root/scripts/pattern-f-verdict.sh"
  if [[ -f "$script" ]]; then
    # Bounded: a slow or locked register must not eat the hook's 30s budget,
    # or the harness times the hook out and the spawn proceeds (fail-open).
    local -a runner=(bash)
    if command -v timeout >/dev/null 2>&1; then runner=(timeout 15 bash); fi
    "${runner[@]}" "$script" --db "$db" --session "$sid" --plan "$plan" --commit none \
      --role gate --kind gate --verdict FAIL --note "$note" >&2 \
      || echo "pattern-f gauge gate: refusal NOT recorded in $db (rc $?)" >&2
  else
    echo "pattern-f gauge gate: refusal NOT recorded (no $script)" >&2
  fi
}

block() {
  record_refusal "$1"
  jq -nc --arg r "$1" '{decision:"block",reason:$r}'
  exit 0
}

[[ -f "$plan" ]] || block "pattern-f gauge gate: plan not found: $plan"
[[ -f "$linter" ]] || block "pattern-f gauge gate: plan-gauge-lint.py not found at $linter"

# --repo-root is required for a real dry run; without it the linter matches
# emitted text only and still exits 0. Argument order does not matter.
rc=0
lint_out=$(python3 "$linter" --repo-root "$repo" "$plan" 2>&1) || rc=$?
case "$rc" in
  0) exit 0 ;;
  1)
    findings=$(printf '%s\n' "$lint_out" | awk '/^  GAUGE[0-9]+/ { sub(/^  /, ""); if (n++) printf "; "; printf "%s", $0 }') || true
    reason="pattern-f gauge gate: plan-gauge-lint refused $plan: $findings"
    block "${reason:0:600}"
    ;;
  *) block "pattern-f gauge gate: plan-gauge-lint could not read $plan (rc $rc)" ;;
esac
