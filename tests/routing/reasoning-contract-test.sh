#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT
printf '%s\n' '{"reasons":["foundational-invariants"],"rationale":"shared admission policy"}' > "$work/context.json"
out="$(bash "$ROOT/scripts/dispatch.sh" --dry-run --role plan-review --producer-identity gpt-6-astra --context-file "$work/context.json" -C "$work" fixture 2>&1)"
[[ "$out" == *'claude-fable-5-1'* && "$out" == *'--effort high'* ]] || { echo 'FAIL: Claude effort not propagated'; exit 1; }
for host in codex claude hermes gemini kimi opencode cursor vscode; do
  python3 "$ROOT/scripts/sync-agent-instructions.py" --source "$ROOT" --host "$host" --file "$work/$host.md" >/dev/null
  (cd "$work" && ic --json route dispatch --policy="$ROOT/config/routing.yaml" --role=planning --context-file="$work/context.json") > "$work/$host.json"
  cmp "$work/codex.json" "$work/$host.json"
done
jq -e '.frontier_required and .review_requirement == "other-frontier" and (.policy_hash | length == 64)' "$work/codex.json" >/dev/null
echo 'PASS: identical contracts across host surfaces and Claude effort propagation'
