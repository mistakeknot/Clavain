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
  --producer-identity=claude-sonnet-5-5 --context-file="$work/routine.json" > "$work/claude-review.json"
jq -e '.profile.model == "gpt-6-sol" and .fallback_chain[0].profile.model == "claude-opus-5-5"
  and ([.profile.model, .fallback_chain[].profile.model] | index("claude-sonnet-5-5") == null)
  and .cross_lab_reorder.to[0] == "validation-sol"' "$work/claude-review.json" >/dev/null ||
  { echo 'FAIL: Claude-produced code does not reach Sol, then Opus'; exit 1; }
ic --json route dispatch --policy="$ROOT/config/routing.yaml" --role=validation \
  --producer-identity=claude-opus-5-5 --context-file="$work/routine.json" > "$work/opus-review.json"
jq -e '.profile.model == "gpt-6-sol"
  and ([.profile.model, .fallback_chain[].profile.model] | index("claude-opus-5-5") == null)' "$work/opus-review.json" >/dev/null ||
  { echo 'FAIL: Opus-produced code reaches Opus or skips Sol'; exit 1; }
printf '%s\n' '{"reasons":[],"rationale":"codex lane out","available_models":["claude-opus-5-5","claude-sonnet-5-5","kimi-code/k3"]}' > "$work/codex-out.json"
ic --json route dispatch --policy="$ROOT/config/routing.yaml" --role=validation \
  --producer-identity=claude-sonnet-5-5 --context-file="$work/codex-out.json" > "$work/codex-out-review.json"
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
jq '.available_models = ["claude-opus-5-5", "claude-sonnet-5-5"]' "$work/context.json" > "$work/no-astra.json"
if ic --json route dispatch --policy="$ROOT/config/routing.yaml" --role=plan-review \
  --producer-identity=claude-opus-5-5 --context-file="$work/no-astra.json" > "$work/producer-route.json" 2>&1; then
  echo 'FAIL: Opus producer admitted as its own plan reviewer'; exit 1
fi
grep -q 'no eligible model satisfies reasoning contract' "$work/producer-route.json"
# ic's refusal is generic, so pin its cause: the same context with a
# non-Opus producer still routes to Opus 5.5.
ic --json route dispatch --policy="$ROOT/config/routing.yaml" --role=plan-review \
  --producer-identity=claude-sonnet-5-5 --context-file="$work/no-astra.json" \
  | jq -e '.profile.model == "claude-opus-5-5"' >/dev/null
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

# mk-42j9.28: a minimum reasoning effort applies after fallback expansion to
# EVERY candidate a role resolves to, not just the primary, and never
# invents an effort level a backend can't run. See config/routing.yaml
# dispatch.effort_floors and docs/research/2026-09-27-effort-per-role-validation.md.

# A medium-configured fallback candidate under a floored reason is raised,
# and the raise is receipted with its from/to and the reason that fired.
ic --json route dispatch --policy="$ROOT/config/routing.yaml" --role=validation \
  --producer-identity=gpt-6-astra --context-file="$work/context.json" > "$work/floor-medium.json"
jq -e '(.fallback_chain[] | select(.profile_ref == "validation-sol") | .profile.reasoning_effort) == "high"
  and (.effort_floors_applied[] | select(.profile_ref == "validation-sol")
    | .from == "medium" and .to == "high" and (.reasons | index("foundational-invariants")) != null)' \
  "$work/floor-medium.json" >/dev/null \
  || { echo 'FAIL: medium fallback candidate not raised to the floor'; exit 1; }

# A candidate already at or above the floor is left untouched: no rewrite,
# no no-op entry in the receipt.
jq -e '(.fallback_chain[] | select(.profile_ref == "validation-kimi") | .profile.reasoning_effort) == "high"
  and ((.effort_floors_applied // []) | map(select(.profile_ref == "validation-kimi")) | length) == 0' \
  "$work/floor-medium.json" >/dev/null \
  || { echo 'FAIL: floor recorded a no-op raise for an already-compliant candidate'; exit 1; }

# The floor applies to every expanded candidate, including the primary
# itself -- crosslab-sol is the declared primary for cross-lab-review at
# medium (mk ruling 2026-09-26), and a floored reason must still raise it.
printf '%s\n' '{"reasons":["difficult-verification"],"rationale":"cross-lab floor check"}' > "$work/dv.json"
ic --json route dispatch --policy="$ROOT/config/routing.yaml" --role=cross-lab-review \
  --producer-identity=claude-opus-5-5 --context-file="$work/dv.json" > "$work/floor-primary.json"
jq -e '.profile_ref == "crosslab-sol" and .profile.reasoning_effort == "high"
  and (.effort_floors_applied[] | select(.profile_ref == "crosslab-sol") | .to == "high")' \
  "$work/floor-primary.json" >/dev/null \
  || { echo 'FAIL: floor did not raise the primary candidate itself'; exit 1; }

# Floors apply after cross-lab reordering too: Claude-produced work moves
# validation-sol to the front (mk ruling 2026-09-24), and the floor must
# still raise it there rather than only checking the pre-reorder chain.
printf '%s\n' '{"reasons":["foundational-invariants"],"rationale":"reorder floor check"}' > "$work/fi-reorder.json"
ic --json route dispatch --policy="$ROOT/config/routing.yaml" --role=validation \
  --producer-identity=claude-sonnet-5-5 --context-file="$work/fi-reorder.json" > "$work/floor-reorder.json"
jq -e '.profile_ref == "validation-sol" and .profile.reasoning_effort == "high"
  and (.effort_floors_applied[] | select(.profile_ref == "validation-sol") | .to == "high")' \
  "$work/floor-reorder.json" >/dev/null \
  || { echo 'FAIL: floor did not survive cross-lab reordering'; exit 1; }

# A floor that cannot be represented by a backend's effort levels excludes
# that candidate with unsupported_adapter rather than inventing an effort
# level it cannot run. pilot-opus's backend, main, has no effort order, so
# fixture it into validation's chain and confirm it is excluded, not clamped.
python3 - "$ROOT/config/routing.yaml" "$work/unsupported-adapter.yaml" <<'PYFIXTURE'
from pathlib import Path
import sys
text = Path(sys.argv[1]).read_text()
needle = '      fallbacks: [validation-sonnet, validation-sol, validation-kimi]\n'
assert text.count(needle) == 1
text = text.replace(needle, '      fallbacks: [validation-sonnet, pilot-opus, validation-sol, validation-kimi]\n')
Path(sys.argv[2]).write_text(text)
PYFIXTURE
ic --json route dispatch --policy="$work/unsupported-adapter.yaml" --role=validation \
  --producer-identity=gpt-6-astra --context-file="$work/context.json" > "$work/floor-unsupported.json"
jq -e '(.excluded[]? | select(.profile_ref == "pilot-opus") | .reason) == "unsupported_adapter"
  and (([.profile_ref] + [.fallback_chain[]?.profile_ref]) | index("pilot-opus")) == null' \
  "$work/floor-unsupported.json" >/dev/null \
  || { echo 'FAIL: unrepresentable floor did not exclude the candidate via unsupported_adapter'; exit 1; }

# --effort-override is receipted (requested/applied/changed/from/to) and
# targets only the resolved primary. It can genuinely lower that candidate's
# effort, but the floor is applied AFTER the override, so a floored reason
# still wins: final_effort reflects the floor, never the requested value
# (mk-42j9.30 -- experiment-only, can never go below effort_floors).
ic --json route dispatch --policy="$ROOT/config/routing.yaml" --role=cross-lab-review \
  --producer-identity=claude-opus-5-5 --context-file="$work/context.json" --effort-override=low \
  > "$work/override-below-floor.json"
jq -e '.profile_ref == "crosslab-sol"
  and .effort_override.requested == "low" and .effort_override.applied == true
  and .effort_override.changed == true and .effort_override.from == "medium" and .effort_override.to == "low"
  and .effort_override.final_effort == "high" and .profile.reasoning_effort == "high"
  and (.effort_floors_applied[] | select(.profile_ref == "crosslab-sol") | .from == "low" and .to == "high")' \
  "$work/override-below-floor.json" >/dev/null \
  || { echo 'FAIL: effort override was admitted below the floor'; exit 1; }

# An override matching the already-resolved effort is still receipted, with
# applied true and changed false -- a no-op override is not silently dropped.
ic --json route dispatch --policy="$ROOT/config/routing.yaml" --role=validation \
  --producer-identity=gpt-6-astra --context-file="$work/routine.json" --effort-override=high \
  > "$work/override-noop.json"
jq -e '.effort_override.requested == "high" and .effort_override.applied == true
  and .effort_override.changed == false and .effort_override.from == "high" and .effort_override.to == "high"' \
  "$work/override-noop.json" >/dev/null \
  || { echo 'FAIL: no-op override not receipted correctly'; exit 1; }

# The floor-raised effort, not the tier's configured value, is what reaches
# the dispatched child process (Claude backend, real --effort propagation).
python3 - "$ROOT/config/routing.yaml" "$work/claude-propagation.yaml" <<'PYFIXTURE'
from pathlib import Path
import sys
text = Path(sys.argv[1]).read_text()
needle = '      model: claude-opus-5-5\n      reasoning_effort: high\n      service_tier: standard\n      # Plan-review primary'
assert text.count(needle) == 1
text = text.replace(needle, needle.replace('reasoning_effort: high', 'reasoning_effort: medium'))
Path(sys.argv[2]).write_text(text)
PYFIXTURE
out="$(bash "$ROOT/scripts/dispatch.sh" --dry-run --role plan-review --policy "$work/claude-propagation.yaml" \
  --producer-identity gpt-6-astra --context-file "$work/context.json" -C "$work" fixture 2>&1)"
[[ "$out" == *'claude-opus-5-5'* && "$out" == *'--effort high'* ]] \
  || { echo 'FAIL: floor-raised effort did not propagate to the dispatched child'; exit 1; }

# Real-policy coverage: main-integrator's actual fallback chain (not a synthetic
# fixture) already has a backend: main candidate (pilot-opus) unrepresentable in
# effort.go's capability table. A floored reason must exclude it via
# unsupported_adapter against the real committed routing.yaml, not just a
# fixture that artificially injects a backend: main candidate.
printf '%s\n' '{"reasons":["capability-failure"],"rationale":"real-policy main-integrator floor sweep"}' > "$work/main-integrator.json"
ic --json route dispatch --policy="$ROOT/config/routing.yaml" --role=main-integrator \
  --context-file="$work/main-integrator.json" > "$work/floor-real-policy.json"
jq -e '.profile_ref == "main-astra"
  and (.fallback_chain[] | select(.profile_ref == "main-sol") | .profile.reasoning_effort) == "high"
  and (.excluded[] | select(.profile_ref == "pilot-opus") | .reason) == "unsupported_adapter"' \
  "$work/floor-real-policy.json" >/dev/null \
  || { echo 'FAIL: real-policy main-integrator chain did not exclude pilot-opus via unsupported_adapter'; exit 1; }

# mk ruling 2026-09-27 (mk-42j9.28 effort-floor conflict, option 3): pilot-opus
# (backend: main) is correctly excluded via unsupported_adapter under a
# floored reason, but that must not leave main-integrator with zero eligible
# seats when Codex is ALSO exhausted -- main-opus (backend: claude,
# claude-opus-5-5, high) is pilot-opus's declared fallback for exactly this
# case and already meets every floor.
jq '.available_models = ["claude-opus-5-5", "claude-sonnet-5-5"]' "$work/main-integrator.json" > "$work/main-integrator-codex-out.json"
ic --json route dispatch --policy="$ROOT/config/routing.yaml" --role=main-integrator \
  --context-file="$work/main-integrator-codex-out.json" > "$work/floor-codex-out.json"
jq -e '.profile_ref == "main-opus" and .profile.reasoning_effort == "high"
  and (.excluded[] | select(.profile_ref == "pilot-opus") | .reason) == "unsupported_adapter"' \
  "$work/floor-codex-out.json" >/dev/null \
  || { echo 'FAIL: Codex exhausted plus a floored reason did not fall back to main-opus at high'; exit 1; }

echo 'PASS: identical contracts across host surfaces, Claude effort propagation, and effort floors'
