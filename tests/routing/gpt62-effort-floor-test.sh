#!/usr/bin/env bash
# mk-au6a1: acceptance requires the companion Intercore effort ladder.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT
failed=0
for reason in foundational-invariants difficult-verification capability-failure; do
  jq -n --arg reason "$reason" \
    '{reasons:[$reason],rationale:"Verify GPT-6.2 effort-floor eligibility"}' > "$work/context.json"
  for role in plan-review validation; do
    if [[ "$role" == plan-review ]]; then model=gpt-6.2-astra; else model=gpt-6.2-sol; fi
    if ic --json route dispatch --policy="$ROOT/config/routing.yaml" \
      --role="$role" --producer-identity=claude-opus-5-5 \
      --context-file="$work/context.json" > "$work/route.json" 2> "$work/error" &&
      jq -e --arg model "$model" \
        '.profile.model == $model and .profile.reasoning_effort == "high"' \
        "$work/route.json" >/dev/null; then
      echo "PASS: $role / $reason -> $model high"
    else
      echo "FAIL: $role / $reason must retain $model high (Intercore 6.2 ladder required)"
      cat "$work/error"
      failed=$((failed + 1))
    fi
  done
done
echo "GPT-6.2 effort-floor acceptance: $((6 - failed))/6 passed"
[[ "$failed" == 0 ]]
