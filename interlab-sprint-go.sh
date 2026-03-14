#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"

# Benchmark clavain-cli sprint Go commands.

# Build if needed
if [[ ! -x bin/clavain-cli ]]; then
    go build -o bin/clavain-cli ./cmd/clavain-cli/ 2>/dev/null
fi

# Time sprint-related Go operations
CLI="bin/clavain-cli"

# sprint-find-active (the Go fast path)
START=$(date +%s%N)
"$CLI" sprint-find-active >/dev/null 2>&1 || true
END=$(date +%s%N)
FIND_MS=$(( (END - START) / 1000000 ))
echo "METRIC cli_find_active_ms=$FIND_MS"

# complexity-label (called per sprint)
START=$(date +%s%N)
"$CLI" complexity-label 3 >/dev/null 2>&1 || true
END=$(date +%s%N)
LABEL_MS=$(( (END - START) / 1000000 ))
echo "METRIC cli_complexity_ms=$LABEL_MS"

# Lines of Go code in sprint.go
LOC=$(wc -l < cmd/clavain-cli/sprint.go)
echo "METRIC sprint_go_loc=$LOC"

# Go test time for the CLI package
TEST_START=$(date +%s%N)
command go test ./cmd/clavain-cli/ -count=1 > /dev/null 2>&1 || true
TEST_END=$(date +%s%N)
TEST_MS=$(( (TEST_END - TEST_START) / 1000000 ))
echo "METRIC go_test_ms=$TEST_MS"
