#!/usr/bin/env bash
set -euo pipefail
# os/Clavain/interlab-go-bench.sh — wraps Clavain CLI Go benchmarks for interlab consumption.
# Primary metric: compose_plan_ns (BenchmarkComposePlan30Agents)
# Secondary: complexity_ns, match_role_ns, merge_spec_ns

MONOREPO="$(cd "$(dirname "$0")/../.." && pwd)"
HARNESS="${INTERLAB_HARNESS:-$MONOREPO/interverse/interlab/scripts/go-bench-harness.sh}"
DIR="$(cd "$(dirname "$0")/cmd/clavain-cli" && pwd)"

echo "--- compose plan ---" >&2
bash "$HARNESS" --pkg . --bench 'BenchmarkComposePlan30Agents$' --metric compose_plan_ns --dir "$DIR"

echo "--- complexity classify ---" >&2
bash "$HARNESS" --pkg . --bench 'BenchmarkClassifyComplexityModerate$' --metric complexity_ns --dir "$DIR"

echo "--- match role ---" >&2
bash "$HARNESS" --pkg . --bench 'BenchmarkMatchRole$' --metric match_role_ns --dir "$DIR"

echo "--- merge spec ---" >&2
bash "$HARNESS" --pkg . --bench 'BenchmarkMergeSpec$' --metric merge_spec_ns --dir "$DIR"
