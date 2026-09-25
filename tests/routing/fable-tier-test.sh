#!/usr/bin/env bash
# mk-3b8z acceptance: Fable 5.1 is retired and Opus 5.5 took every Fable seat.
# A legacy `fable` tier from any bash-resolver input (phase, complexity override,
# safety floor) must leave the resolver as opus, never above it.
set -euo pipefail
cd "$(dirname "$0")/../.."

fail() { echo "FAIL: $1" >&2; exit 1; }
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
cat > "$TMP/legacy.yaml" <<'YAML'
subagents:
  defaults:
    model: sonnet
  phases:
    planned:
      model: fable

complexity:
  mode: enforce
  tiers:
    C5:
      description: Architectural
      prompt_tokens: 4000
      file_count: 15
      reasoning_depth: 5
  overrides:
    C5:
      subagent_model: fable
YAML
export CLAVAIN_ROUTING_CONFIG="$TMP/legacy.yaml"
source scripts/lib-routing.sh

[[ "$(_routing_model_tier fable)" == "$(_routing_model_tier opus)" ]] || fail "fable ranks apart from opus"
[[ "$(_routing_downgrade fable)" == "opus" ]] || fail "_routing_downgrade fable != opus"

[[ "$(routing_resolve_model --phase planned 2>/dev/null)" == "opus" ]] || fail "legacy fable phase not retired"
[[ "$(routing_resolve_model_complex --complexity C5 --phase planned 2>/dev/null)" == "opus" ]] \
  || fail "legacy fable complexity override not retired"

# A legacy fable floor clamps up to opus, never to fable; an opus result is kept.
_ROUTING_SF_AGENT_MIN[fd-x]="fable"
[[ "$(_routing_apply_safety_floor fd-x sonnet test 2>/dev/null)" == "opus" ]] || fail "fable floor clamped to fable"
[[ "$(routing_resolve_model --phase planned --agent fd-x 2>/dev/null)" == "opus" ]] || fail "fable floor raised opus"
# The retirement notice goes to stderr so callers still see a clean model name.
[[ "$(routing_resolve_model --phase planned 2>&1 >/dev/null)" == *"[fable-retired]"* ]] || fail "no retirement notice"

echo "PASS: legacy fable tier retires to opus in every bash-resolver path"
