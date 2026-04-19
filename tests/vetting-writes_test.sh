#!/usr/bin/env bash
# Regression test for Task 7 vetting-signal writes.
#
# Ensures /work Phase 3, /sprint Step 6/7, and executing-plans Step 2D all
# contain bd set-state calls for vetted_at / vetted_sha / tests_passed /
# sprint_or_work_flow. A rename or refactor that drops these calls breaks
# the auto-proceed gate silently — this test catches that regression.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"

fail=0

check_file() {
  local path="$1" context="$2"
  local full="${ROOT}/${path}"
  if [[ ! -f "$full" ]]; then
    echo "FAIL [${context}]: file not found: ${path}"
    fail=1
    return
  fi

  local keys=(vetted_at vetted_sha tests_passed sprint_or_work_flow)
  for key in "${keys[@]}"; do
    if ! grep -q "bd set-state.*${key}" "$full"; then
      echo "FAIL [${context}]: missing 'bd set-state ... ${key}' in ${path}"
      fail=1
    fi
  done
}

check_file "commands/work.md"                    "/clavain:work Phase 3"
check_file "commands/sprint.md"                  "/clavain:sprint Step 6"
check_file "skills/executing-plans/SKILL.md"     "executing-plans Step 2D"

# sprint.md additionally refreshes vetting signals after Step 7 quality gates.
# Require at least 2 bd set-state blocks for vetted_at (one per insertion point).
count="$(grep -c 'bd set-state.*vetted_at' "${ROOT}/commands/sprint.md" || true)"
if [[ "${count:-0}" -lt 2 ]]; then
  echo "FAIL: sprint.md should have ≥2 vetted_at bd set-state blocks (step 6 + step 7), got ${count}"
  fail=1
fi

if [[ "$fail" == "0" ]]; then
  echo "PASS: vetting-writes regression (4 keys × 3 files + sprint-step-7 refresh)"
else
  exit 1
fi
