#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"

# Benchmark sprint_read_state — measures the shell function that reads sprint state.
# This is the hot path called on every phase transition.

# Source the library
export CLAVAIN_ROOT="$(pwd)"
export CLAVAIN_CLI="$(pwd)/bin/clavain-cli"

# Time the sprint_find_active function (which calls sprint_read_state internally)
START=$(date +%s%N)
source hooks/lib-sprint.sh 2>/dev/null
LOAD_END=$(date +%s%N)
LOAD_MS=$(( (LOAD_END - START) / 1000000 ))
echo "METRIC lib_load_ms=$LOAD_MS"

# Count lines in lib-sprint.sh
LOC=$(wc -l < hooks/lib-sprint.sh)
echo "METRIC lib_sprint_loc=$LOC"

# Count function definitions
FUNC_COUNT=$(grep -c '^[a-z_]*()' hooks/lib-sprint.sh 2>/dev/null || echo 0)
echo "METRIC function_count=$FUNC_COUNT"

# Measure a dry-run of sprint_find_active (will be fast if no sprints active)
FIND_START=$(date +%s%N)
sprint_find_active >/dev/null 2>&1 || true
FIND_END=$(date +%s%N)
FIND_MS=$(( (FIND_END - FIND_START) / 1000000 ))
echo "METRIC find_active_ms=$FIND_MS"
