#!/usr/bin/env bash
set -euo pipefail
# Clavain/interlab-satisfaction.sh — benchmark satisfaction scoring for interlab.
# Primary: scenario_score_ns (BenchmarkScoreScenarioResult)
# go.mod is at cmd/clavain-cli/, not at Clavain root.

# Clavain has its own .git — walk up to find the monorepo root
MONOREPO="$(cd "$(dirname "$0")/../.." && pwd)"
HARNESS="${INTERLAB_HARNESS:-$MONOREPO/interverse/interlab/scripts/go-bench-harness.sh}"
DIR="$(cd "$(dirname "$0")" && pwd)"

bash "$HARNESS" --pkg . --bench 'BenchmarkScoreScenarioResult$' --metric scenario_score_ns --dir "$DIR/cmd/clavain-cli"
