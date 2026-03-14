#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"

# Benchmark sprint-scan.sh — measures session startup scan performance.

export CLAVAIN_ROOT="$(pwd)"
export CLAVAIN_CLI="$(pwd)/bin/clavain-cli"

# Time the scan script load + execution
START=$(date +%s%N)
source hooks/sprint-scan.sh 2>/dev/null || true
END=$(date +%s%N)
SCAN_MS=$(( (END - START) / 1000000 ))
echo "METRIC scan_load_ms=$SCAN_MS"

# Count lines in sprint-scan.sh
LOC=$(wc -l < hooks/sprint-scan.sh)
echo "METRIC sprint_scan_loc=$LOC"

# Count grep/sed calls (pattern matching density)
GREP_COUNT=$(grep -c 'grep\|sed\|awk' hooks/sprint-scan.sh 2>/dev/null || echo 0)
echo "METRIC pattern_match_calls=$GREP_COUNT"

# Measure orphan brainstorm detection
ORPHAN_START=$(date +%s%N)
sprint_count_orphaned_brainstorms >/dev/null 2>&1 || true
ORPHAN_END=$(date +%s%N)
ORPHAN_MS=$(( (ORPHAN_END - ORPHAN_START) / 1000000 ))
echo "METRIC orphan_detect_ms=$ORPHAN_MS"
