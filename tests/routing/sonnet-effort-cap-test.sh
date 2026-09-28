#!/usr/bin/env bash
# mk-hpwq (mk ruling 2026-09-28): Claude Sonnet 5.5 is capped at xhigh. At max,
# Anthropic reports its review subagents time out or make out-of-scope edits.
# No Sonnet 5.5 seat may configure or resolve to max, and dispatch refuses it.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
POLICY="${CLAVAIN_ROUTING_POLICY:-$ROOT/config/routing.yaml}"
WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT
fail() { echo "FAIL: $*" >&2; exit 1; }

# 1. Configuration: every tier that runs Sonnet 5.5 (by id or by the `sonnet`
#    alias) declares a real effort at or below xhigh, and there is at least one.
python3 - "$POLICY" <<'PY' || fail "a Sonnet 5.5 tier is unset, unknown, or at max"
import sys, yaml
cfg = yaml.safe_load(open(sys.argv[1])) or {}
d = cfg.get("dispatch") or {}
aliases = d.get("model_aliases") or {}
ok = {"low", "medium", "high", "xhigh"}
seen = 0
for name, t in (d.get("tiers") or {}).items():
    if aliases.get(t.get("model"), t.get("model")) != "claude-sonnet-5-5":
        continue
    seen += 1
    if t.get("reasoning_effort") not in ok:
        sys.exit(f"{name}: reasoning_effort {t.get('reasoning_effort')!r} not in {sorted(ok)}")
sys.exit(0 if seen else "no Sonnet 5.5 tier found")
PY

# 2. Resolution: no role's primary or fallback that is Sonnet 5.5 resolves to
#    max, in a routine context and in an elevated one.
printf '%s\n' '{"reasons":[],"rationale":"routine change"}' > "$WORK/routine.json"
printf '%s\n' '{"reasons":["foundational-invariants","difficult-verification","capability-failure"],"rationale":"elevated"}' > "$WORK/elevated.json"
roles="$(python3 -c 'import sys,yaml;print(*yaml.safe_load(open(sys.argv[1]))["dispatch"]["roles"])' "$POLICY")"
for role in $roles; do
  for ctx in routine elevated; do
    receipt="$(ic --json route dispatch --policy="$POLICY" --role="$role" --context-file="$WORK/$ctx.json" 2>/dev/null)" || continue
    jq -e '[.profile, (.fallback_chain[]?.profile)]
           | map(select(.model_identity == "claude-sonnet-5-5" and .reasoning_effort == "max")) | length == 0' \
      <<< "$receipt" >/dev/null || fail "$role ($ctx) resolves Sonnet 5.5 at max"
  done
done

# 3. Dispatch: max is refused for the model id and the alias; high is accepted.
export CLAVAIN_CONTEXT_GATEWAY_MODE=off
for model in claude-sonnet-5-5 sonnet; do
  if bash "$ROOT/scripts/dispatch.sh" --dry-run --to claude --model "$model" --reasoning-effort max "x" >"$WORK/max.out" 2>&1; then
    fail "dispatch accepted $model at max"
  fi
  grep -q "capped at xhigh" "$WORK/max.out" || fail "dispatch refused $model at max for the wrong reason: $(cat "$WORK/max.out")"
  bash "$ROOT/scripts/dispatch.sh" --dry-run --to claude --model "$model" --reasoning-effort high "x" >/dev/null 2>&1 \
    || fail "dispatch refused $model at high"
done
bash "$ROOT/scripts/dispatch.sh" --dry-run --to claude --model claude-opus-5-5 --reasoning-effort max "x" >/dev/null 2>&1 \
  || fail "the Sonnet 5.5 cap leaked onto Opus"

echo "PASS: Sonnet 5.5 is capped at xhigh in policy, resolution and dispatch"
