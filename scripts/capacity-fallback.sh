#!/usr/bin/env bash
# capacity-fallback.sh — record an observed capacity failure and re-resolve the
# affected roles against it. Generalizes the pattern proven on After-Them-rust
# 2026-09-18 (mk-9yyt).
#
# Capacity exhaustion is an OPERATIONAL failure: it consumes no capability strike,
# and it must neither silently downgrade the work nor silently stall it. The
# packaged policy already declares a non-Codex destination at the end of every
# role chain; what a caller has to supply is the OBSERVATION that a seat is down.
# The kernel's channel for that is `available_models` in the decision context:
# absent means unprobed, an empty array means none, and any model missing from a
# present array is excluded with reason `model_unavailable`.
#
# This script never edits config/routing.yaml and never edits a policy snapshot.
# It writes a derived decision context next to the original and prints receipts.
#
#   scripts/capacity-fallback.sh --seat gpt-6-astra \
#     --context .clavain/decisions/2026-09-17-rift-slice-1-planning.json \
#     --evidence .clavain/capacity/2026-09-18-astra-usage-limit.md \
#     --role plan-review --producer-identity claude-fable-5-1 \
#     --role deep-execution
#
# Exit 0 only when every requested role resolved AND no resolution landed on the
# bound producer. Reviewer separation is enforced structurally by intercore; the
# producer check here is a second, independent assertion, never a substitute.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
POLICY="${CLAVAIN_ROUTING_POLICY:-$ROOT/config/routing.yaml}"
CONTEXT=""
EVIDENCE=""
OUT=""
PRODUCER=""
SEATS=()
ROLES=()
AVAILABLE=()

die() { echo "capacity-fallback: $*" >&2; exit 2; }

usage() {
  cat >&2 <<'USAGE'
usage: capacity-fallback.sh --context <decision.json> --evidence <capacity.md>
                            (--seat <model> | --available <model>)...
                            --role <role> [--role <role>]...
                            [--producer-identity <model>] [--policy <routing.yaml>]
                            [--out <derived-context.json>]

  --seat        a model observed UNAVAILABLE; repeatable. Every other model named
                in the policy is treated as available.
  --available   a model observed AVAILABLE; repeatable. Mutually exclusive with
                --seat; use it when the probe enumerated what works instead of
                what failed.
  --evidence    path to the capacity note holding the probe and its verbatim
                output. Required: an unevidenced outage is not an observation.
USAGE
  exit 2
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --context) CONTEXT="${2:-}"; shift 2 ;;
    --evidence) EVIDENCE="${2:-}"; shift 2 ;;
    --out) OUT="${2:-}"; shift 2 ;;
    --policy) POLICY="${2:-}"; shift 2 ;;
    --producer-identity) PRODUCER="${2:-}"; shift 2 ;;
    --seat) SEATS+=("${2:-}"); shift 2 ;;
    --available) AVAILABLE+=("${2:-}"); shift 2 ;;
    --role) ROLES+=("${2:-}"); shift 2 ;;
    -h|--help) usage ;;
    *) die "unknown argument: $1" ;;
  esac
done

command -v ic >/dev/null || die "ic not on PATH"
command -v jq >/dev/null || die "jq not on PATH"
[[ -n "$CONTEXT" ]] || usage
[[ -n "$EVIDENCE" ]] || usage
[[ ${#ROLES[@]} -gt 0 ]] || usage
[[ -f "$CONTEXT" ]] || die "decision context not found: $CONTEXT"
[[ -f "$POLICY" ]] || die "routing policy not found: $POLICY"
[[ -s "$EVIDENCE" ]] || die "capacity evidence missing or empty: $EVIDENCE
  Probe the seat and record the verbatim error before claiming it is down.
  Usage after a quota error is unknown, never zero."
[[ ${#SEATS[@]} -gt 0 || ${#AVAILABLE[@]} -gt 0 ]] || usage
[[ ${#SEATS[@]} -eq 0 || ${#AVAILABLE[@]} -eq 0 ]] || die "--seat and --available are mutually exclusive"

# Every concrete model the policy can select. --seat subtracts from this set so a
# caller does not have to enumerate a whole lane by hand.
mapfile -t POLICY_MODELS < <(
  python3 - "$POLICY" <<'PY'
import sys, yaml
cfg = yaml.safe_load(open(sys.argv[1])) or {}
dispatch = cfg.get("dispatch") or {}
aliases = dispatch.get("model_aliases") or {}
seen = []
for tier in (dispatch.get("tiers") or {}).values():
    model = (tier or {}).get("model")
    if not model:
        continue
    model = aliases.get(model, model)
    if model not in seen:
        seen.append(model)
print("\n".join(seen))
PY
)
[[ ${#POLICY_MODELS[@]} -gt 0 ]] || die "policy declares no dispatch models: $POLICY"

if [[ ${#AVAILABLE[@]} -eq 0 ]]; then
  for model in "${POLICY_MODELS[@]}"; do
    down=0
    for seat in "${SEATS[@]}"; do
      [[ "$model" == "$seat" ]] && down=1
    done
    [[ $down -eq 0 ]] && AVAILABLE+=("$model")
  done
  for seat in "${SEATS[@]}"; do
    printf '%s\n' "${POLICY_MODELS[@]}" | grep -qx -- "$seat" \
      || die "--seat $seat is not a model this policy can select; check the spelling"
  done
fi

[[ ${#AVAILABLE[@]} -gt 0 ]] || die "no models left available; an empty array means the whole fleet is down"

: "${OUT:=${CONTEXT%.json}.capacity-$(date +%Y-%m-%d).json}"
EVIDENCE_ABS="$(cd "$(dirname "$EVIDENCE")" && pwd)/$(basename "$EVIDENCE")"

# The decision context is a closed schema: intercore rejects unknown fields, so
# the evidence reference is bound into `rationale`, which the durable receipt
# carries in context_json. The classification reasons are left untouched — a
# capacity failure is operational and reclassifies nothing.
jq --argjson models "$(printf '%s\n' "${AVAILABLE[@]}" | jq -R . | jq -s .)" \
   --arg evidence "$EVIDENCE_ABS" \
   '. + {available_models: $models,
         rationale: ((.rationale // "") + " Observed capacity failure; evidence: " + $evidence + ".")}' \
   "$CONTEXT" > "$OUT"

echo "capacity context: $OUT"
echo "policy:           $POLICY"
echo "evidence:         $EVIDENCE_ABS"
echo "available_models: ${AVAILABLE[*]}"
[[ -n "$PRODUCER" ]] && echo "producer:         $PRODUCER"
echo

status=0
for role in "${ROLES[@]}"; do
  args=(--json route dispatch "--policy=$POLICY" "--role=$role" "--context-file=$OUT")
  [[ -n "$PRODUCER" ]] && args+=("--producer-identity=$PRODUCER")
  if ! receipt="$(ic "${args[@]}" 2>&1)"; then
    echo "FAIL $role: $receipt" >&2
    echo "  Every declared candidate was excluded. Freeze a policy snapshot only" >&2
    echo "  now, as the packaged default plus the smallest possible addition." >&2
    status=1
    continue
  fi
  echo "$receipt" | jq -c --arg role "$role" '{
    role: $role,
    profile_ref,
    model: .profile.model,
    backend: .profile.backend,
    effort: .profile.reasoning_effort,
    fallback_reason,
    validator_relationship,
    excluded: [.excluded[]? | {profile_ref, reason}],
    policy_hash
  }'
  if [[ -n "$PRODUCER" ]]; then
    selected="$(echo "$receipt" | jq -r '.profile.model_identity // .profile.model')"
    producer_id="$(echo "$receipt" | jq -r '.producer_model // empty')"
    if [[ -n "$producer_id" && "$selected" == "$producer_id" ]]; then
      echo "FAIL $role: resolved to the bound producer ($selected)" >&2
      status=1
    fi
  fi
done

exit "$status"
