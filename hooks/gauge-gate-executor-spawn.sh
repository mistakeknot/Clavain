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
set -uo pipefail

payload=$(cat)
[[ -z "$payload" ]] && exit 0

prompt=$(jq -r '.tool_input.prompt // empty' <<<"$payload" 2>/dev/null) || exit 0
[[ -z "$prompt" ]] && exit 0

plan=$(printf '%s\n' "$prompt" | sed -n 's/^PATTERN-F EXECUTOR PLAN:[[:space:]]*//p' | head -1 | sed 's/[[:space:]]*$//')
[[ -z "$plan" ]] && exit 0

repo=$(printf '%s\n' "$prompt" | sed -n 's/^REPO:[[:space:]]*//p' | head -1 | sed 's/[[:space:]]*$//')
[[ -z "$repo" ]] && repo="${CLAUDE_PROJECT_DIR:-$PWD}"

script_dir=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
root="${CLAUDE_PLUGIN_ROOT:-$script_dir/..}"
linter="$root/scripts/plan-gauge-lint.py"

block() {
  jq -nc --arg r "$1" '{decision:"block",reason:$r}'
  exit 0
}

[[ -f "$plan" ]] || block "pattern-f gauge gate: plan not found: $plan"
[[ -f "$linter" ]] || block "pattern-f gauge gate: plan-gauge-lint.py not found at $linter"

# --repo-root must precede the positional plan path (argparse layout).
lint_out=$(python3 "$linter" --repo-root "$repo" "$plan" 2>&1)
rc=$?
case "$rc" in
  0) exit 0 ;;
  1)
    findings=$(printf '%s\n' "$lint_out" | awk '/^  GAUGE[0-9]+/ { sub(/^  /, ""); if (n++) printf "; "; printf "%s", $0 }')
    reason="pattern-f gauge gate: plan-gauge-lint refused $plan: $findings"
    block "${reason:0:600}"
    ;;
  *) block "pattern-f gauge gate: plan-gauge-lint could not read $plan (rc $rc)" ;;
esac
