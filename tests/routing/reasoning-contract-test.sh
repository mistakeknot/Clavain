#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT
# Routine classification still has a record; an empty reasons list is valid and
# must not invent a frontier trigger. This resolves locally without a model call.
printf '%s\n' '{"reasons":[],"rationale":"settled one-function behavior correction"}' > "$work/routine.json"
ic --json route dispatch --policy="$ROOT/config/routing.yaml" --role=routine-execution \
  --context-file="$work/routine.json" > "$work/routine-resolution.json"
jq -e '.classification_reasons == [] and .frontier_required == false and .decision_context.reasons == []' \
  "$work/routine-resolution.json" >/dev/null
printf '%s\n' '{"reasons":["foundational-invariants"],"rationale":"shared admission policy"}' > "$work/context.json"
out="$(bash "$ROOT/scripts/dispatch.sh" --dry-run --role plan-review --producer-identity gpt-6-astra --context-file "$work/context.json" -C "$work" fixture 2>&1)"
[[ "$out" == *'claude-fable-5-1'* && "$out" == *'--effort high'* ]] || { echo 'FAIL: Claude effort not propagated'; exit 1; }
for host in codex claude hermes gemini kimi opencode cursor vscode; do
  python3 "$ROOT/scripts/sync-agent-instructions.py" --source "$ROOT" --host "$host" --file "$work/$host.md" >/dev/null
  (cd "$work" && ic --json route dispatch --policy="$ROOT/config/routing.yaml" --role=planning --context-file="$work/context.json") > "$work/$host.json"
  cmp "$work/codex.json" "$work/$host.json"
done
jq -e '.frontier_required and .review_requirement == "other-frontier" and (.policy_hash | length == 64)' "$work/codex.json" >/dev/null
# Claude governed seats exclude user settings. Verify the child still receives
# the packaged policy and the classified decision, without a real model call.
mkdir "$work/bin"
cat > "$work/bin/claude" <<'FIXTURE'
#!/usr/bin/env bash
printf '%s\n' "$@" > "$CONTRACT_ARGS"
cat > "$CONTRACT_PROMPT"
echo 'VERDICT: CLEAN'
FIXTURE
chmod +x "$work/bin/claude"
(cd "$work" && ic init >/dev/null)
PATH="$work/bin:$PATH" CONTRACT_PROMPT="$work/child-prompt.md" CONTRACT_ARGS="$work/child-args.txt" \
  CLAVAIN_CONTEXT_GATEWAY_MODE=off bash "$ROOT/scripts/dispatch.sh" --role plan-review \
  --producer-identity gpt-6-astra --context-file "$work/context.json" -C "$work" \
  -o "$work/answer.md" 'Replay the admission criteria.' >/dev/null
grep -q 'project,local' "$work/child-args.txt"
grep -q 'Sylveste operating contract' "$work/child-prompt.md"
grep -q "$(jq -r '.policy_hash' "$work/codex.json")" "$work/child-prompt.md"
grep -q 'foundational-invariants' "$work/child-prompt.md"
grep -q 'other-frontier' "$work/child-prompt.md"
grep -q 'Replay the admission criteria' "$work/child-prompt.md"
# A policy edit after resolution must stop before the backend sees any task.
cp -f "$ROOT/config/routing.yaml" "$work/changed-policy.yaml"
cat > "$work/bin/change-policy" <<'GATEWAY'
#!/usr/bin/env bash
printf '\n# changed after resolution\n' >> "$CHANGING_POLICY"
cat
GATEWAY
chmod +x "$work/bin/change-policy"
if PATH="$work/bin:$PATH" CONTRACT_PROMPT="$work/should-not-run" CONTRACT_ARGS="$work/should-not-have-args" \
  CHANGING_POLICY="$work/changed-policy.yaml" CLAVAIN_CONTEXT_GATEWAY_BIN="$work/bin/change-policy" \
  bash "$ROOT/scripts/dispatch.sh" --role plan-review --producer-identity gpt-6-astra \
  --policy "$work/changed-policy.yaml" --context-file "$work/context.json" -C "$work" \
  -o "$work/should-not-exist.md" fixture > "$work/drift.log" 2>&1; then
  echo 'FAIL: policy drift admitted'; exit 1
fi
grep -q 'policy changed after resolution' "$work/drift.log"
[[ ! -e "$work/should-not-run" && ! -e "$work/should-not-have-args" ]]
echo 'PASS: identical contracts across host surfaces and Claude effort propagation'
