#!/usr/bin/env bash
# fc5.1 acceptance: fable tier vocabulary + window fallback (bash resolver).
set -euo pipefail
cd "$(dirname "$0")/../.."
source scripts/lib-routing.sh

fail() { echo "FAIL: $1" >&2; exit 1; }

[[ "$(_routing_model_tier fable)" == "4" ]] || fail "_routing_model_tier fable != 4"
[[ "$(_routing_model_tier opus)" == "3" ]] || fail "opus tier changed"
[[ "$(_routing_downgrade fable)" == "opus" ]] || fail "_routing_downgrade fable != opus"

# Floor semantics: fable (4) vs a sonnet floor (2) must NOT clamp.
declare -A _ROUTING_SF_AGENT_MIN=( [fd-safety]="sonnet" )
[[ "$(_routing_apply_safety_floor fd-safety fable test)" == "fable" ]] || fail "fable clamped by sonnet floor"

echo "PASS: fable tier bash suite"
