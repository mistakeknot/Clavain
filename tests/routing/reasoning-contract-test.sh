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
[[ "$out" == *'claude-opus-5-5'* && "$out" == *'--effort high'* ]] || { echo 'FAIL: Claude effort not propagated'; exit 1; }
# Default producer exclusions must retain Astra and the cross-lab route.
ic --json route dispatch --policy="$ROOT/config/routing.yaml" --role=plan-review \
  --producer-identity=claude-opus-5-5 --context-file="$work/context.json" > "$work/opus-producer.json"
jq -e '.profile.model == "gpt-6-astra"' "$work/opus-producer.json" >/dev/null
ic --json route dispatch --policy="$ROOT/config/routing.yaml" --role=cross-lab-review \
  --producer-identity=claude-opus-5-5 --context-file="$work/routine.json" > "$work/crosslab.json"
jq -e '.profile.backend != "claude"' "$work/crosslab.json" >/dev/null
# Code review reaches another frontier lab first (mk ruling 2026-09-24): Claude
# work goes to Sol, then a distinct Claude model as the same-lab substitute,
# never the producer itself; Codex work keeps the policy order with Opus first.
# Needs ic >= intercore 2caa435.
ic --json route dispatch --policy="$ROOT/config/routing.yaml" --role=validation \
  --producer-identity=claude-sonnet-5 --context-file="$work/routine.json" > "$work/claude-review.json"
jq -e '.profile.model == "gpt-5.6-sol" and .fallback_chain[0].profile.model == "claude-opus-5-5"
  and ([.profile.model, .fallback_chain[].profile.model] | index("claude-sonnet-5") == null)
  and .cross_lab_reorder.to[0] == "validation-sol"' "$work/claude-review.json" >/dev/null ||
  { echo 'FAIL: Claude-produced code does not reach Sol, then Opus'; exit 1; }
ic --json route dispatch --policy="$ROOT/config/routing.yaml" --role=validation \
  --producer-identity=claude-opus-5-5 --context-file="$work/routine.json" > "$work/opus-review.json"
jq -e '.profile.model == "gpt-5.6-sol"
  and ([.profile.model, .fallback_chain[].profile.model] | index("claude-opus-5-5") == null)' "$work/opus-review.json" >/dev/null ||
  { echo 'FAIL: Opus-produced code reaches Opus or skips Sol'; exit 1; }
printf '%s\n' '{"reasons":[],"rationale":"codex lane out","available_models":["claude-opus-5-5","claude-sonnet-5","kimi-code/k3"]}' > "$work/codex-out.json"
ic --json route dispatch --policy="$ROOT/config/routing.yaml" --role=validation \
  --producer-identity=claude-sonnet-5 --context-file="$work/codex-out.json" > "$work/codex-out-review.json"
jq -e '.profile.model == "claude-opus-5-5"' "$work/codex-out-review.json" >/dev/null ||
  { echo 'FAIL: Codex out does not fall back to Opus'; exit 1; }
ic --json route dispatch --policy="$ROOT/config/routing.yaml" --role=validation \
  --producer-identity=gpt-6-astra --context-file="$work/routine.json" > "$work/codex-review.json"
jq -e '.profile.model == "claude-opus-5-5" and .cross_lab_reorder == null' "$work/codex-review.json" >/dev/null ||
  { echo 'FAIL: Codex-produced code review order changed'; exit 1; }
# Opus 5.5 is the packaged plan reviewer (mk-3b8z): a distinct frontier model
# for Astra-authored plans, never a downgrade.
ic --json route dispatch --policy="$ROOT/config/routing.yaml" --role=plan-review \
  --producer-identity=gpt-6-astra --context-file="$work/context.json" > "$work/astra-plan-route.json"
jq -e '.profile.model == "claude-opus-5-5" and .frontier_required and .validator_relationship == "different-model"' "$work/astra-plan-route.json" >/dev/null
# With Astra out an Opus-authored plan has no routed reviewer: resolution
# fails closed rather than admitting Opus as its own reviewer (the agent then
# runs the declared adversarial Opus review by hand; mk-2e1e).
jq '.available_models = ["claude-opus-5-5", "claude-sonnet-5"]' "$work/context.json" > "$work/no-astra.json"
if ic --json route dispatch --policy="$ROOT/config/routing.yaml" --role=plan-review \
  --producer-identity=claude-opus-5-5 --context-file="$work/no-astra.json" > "$work/producer-route.json" 2>&1; then
  echo 'FAIL: Opus producer admitted as its own plan reviewer'; exit 1
fi
grep -Eq 'no model distinct from producer "claude-opus-5-5"|no eligible model satisfies reasoning contract' "$work/producer-route.json"
# A review-lane edit is fixtured separately so the guard below can prove it
# never reaches the authoring lane.
python3 - "$ROOT/config/routing.yaml" "$work/capacity.yaml" <<'PYFIXTURE'
from pathlib import Path
import sys
text = Path(sys.argv[1]).read_text()
assert text.count('    plan-review: review-opus\n') == 1
text = text.replace('    plan-review: review-opus\n', '    plan-review: review-astra\n')
Path(sys.argv[2]).write_text(text)
PYFIXTURE
jq '.available_models = ["claude-opus-5-5"]' "$work/context.json" > "$work/opus-only.json"
# Frontier authoring has its own declared Opus seat as of mk's 2026-09-18 ruling,
# so with only Opus reachable `planning` resolves rather than refusing. What this
# guard still protects is the ORIGINAL intent: the authoring lane must reach that
# seat through its OWN chain, never by leaking across from the review lane. The
# fixture above rewrites only `plan-review`, so if editing the review lane can
# change an authoring receipt, the lanes have been re-coupled.
for policy in "$ROOT/config/routing.yaml" "$work/capacity.yaml"; do
  ic --json route dispatch --policy="$policy" --role=planning \
    --context-file="$work/opus-only.json" > "$work/planning.json"
  jq -e '.profile_ref == "planning-opus" and .profile.role == "frontier-planning" and .frontier_required' \
    "$work/planning.json" >/dev/null \
    || { echo 'FAIL: frontier authoring did not reach its own declared capacity seat'; exit 1; }
done
# The review-lane fixture must not have moved the authoring receipt at all.
if ! cmp -s <(jq -S '.profile' "$work/planning.json") \
            <(ic --json route dispatch --policy="$ROOT/config/routing.yaml" --role=planning \
                --context-file="$work/opus-only.json" | jq -S '.profile'); then
  echo 'FAIL: capacity review substitution changed frontier planning'; exit 1
fi
# A healthy estate still authors on Astra: the substitute is last, not preferred.
ic --json route dispatch --policy="$ROOT/config/routing.yaml" --role=planning \
  --context-file="$work/context.json" > "$work/planning-healthy.json"
jq -e '.profile.model_identity == "gpt-6-astra"' "$work/planning-healthy.json" >/dev/null \
  || { echo 'FAIL: frontier authoring no longer prefers Astra while it is reachable'; exit 1; }
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
