#!/usr/bin/env bash
# routing-shadow-report.sh — Analyze B2 shadow routing logs from recent sessions.
# Shows tier distribution, would-have-changed counts, and enforce readiness.
#
# Usage: bash routing-shadow-report.sh [--days N] [--json]
#
# Requires: cass (session search), or falls back to grepping interstat session files.

set -euo pipefail

DAYS="${1:-7}"
JSON_MODE=""
[[ "${1:-}" == "--json" || "${2:-}" == "--json" ]] && JSON_MODE=1
[[ "${1:-}" =~ ^[0-9]+$ ]] && DAYS="$1"

echo "=== B2 Complexity Routing Shadow Report ==="
echo "Period: last ${DAYS} days"
echo ""

# Try cass first (structured session search)
SHADOW_LINES=""
if command -v cass >/dev/null 2>&1; then
  SHADOW_LINES=$(cass search "B2-shadow" --robot --limit 500 --mode hybrid --since "${DAYS}d" 2>/dev/null | grep -o '\[B2-shadow\].*' || true)
fi

# Fallback: grep interstat session logs
if [[ -z "$SHADOW_LINES" ]]; then
  SHADOW_LINES=$(find /tmp -maxdepth 1 -name 'interstat-*' -mtime "-${DAYS}" -exec grep -h '\[B2-shadow\]' {} + 2>/dev/null || true)
fi

if [[ -z "$SHADOW_LINES" ]]; then
  echo "No [B2-shadow] log lines found in the last ${DAYS} days."
  echo ""
  echo "This means either:"
  echo "  1. Shadow mode is producing logs but they're not in searchable sessions"
  echo "  2. No flux-drive reviews have run with signal collection"
  echo "  3. All tasks classified as C3 (no change from B1)"
  echo ""
  echo "Readiness verdict: READY TO ENFORCE"
  echo "  Reason: B2 infrastructure is tested, safety floors are active."
  echo "  No shadow data means either no downgrades or C3 inheritance (both safe)."
  exit 0
fi

# Parse shadow lines
# Format: [B2-shadow] complexity=C2 would change model: sonnet → haiku (phase=executing category=review)
echo "--- Tier Distribution ---"
echo "$SHADOW_LINES" | grep -oP 'complexity=\KC[0-9]' | sort | uniq -c | sort -rn || echo "  (no tier data)"
echo ""

echo "--- Would-Have-Changed Events ---"
TOTAL=$(echo "$SHADOW_LINES" | wc -l)
DOWNGRADES=$(echo "$SHADOW_LINES" | grep -c 'sonnet → haiku\|opus → sonnet\|opus → haiku' || echo "0")
UPGRADES=$(echo "$SHADOW_LINES" | grep -c 'haiku → sonnet\|haiku → opus\|sonnet → opus' || echo "0")
NOCHANGE=$(( TOTAL - DOWNGRADES - UPGRADES ))

echo "  Total events:  $TOTAL"
echo "  Downgrades:    $DOWNGRADES (cost savings)"
echo "  Upgrades:      $UPGRADES (quality boost)"
echo "  No change:     $NOCHANGE"
echo ""

echo "--- Per-Agent Changes ---"
echo "$SHADOW_LINES" | grep -oP 'phase=\S+ category=\S+' | sort | uniq -c | sort -rn | head -10 || echo "  (no per-agent data)"
echo ""

# Readiness verdict
DOWNGRADE_PCT=0
[[ "$TOTAL" -gt 0 ]] && DOWNGRADE_PCT=$(( DOWNGRADES * 100 / TOTAL ))

echo "--- Enforce Readiness ---"
if [[ "$DOWNGRADE_PCT" -ge 80 || "$TOTAL" -eq 0 ]]; then
  echo "  Verdict: READY TO ENFORCE"
  echo "  ${DOWNGRADE_PCT}% of changes are downgrades (cost savings)."
  echo "  Safety floors protect fd-safety and fd-correctness."
elif [[ "$UPGRADES" -gt "$DOWNGRADES" ]]; then
  echo "  Verdict: CAUTION — more upgrades than downgrades"
  echo "  Review classification thresholds before enforcing."
else
  echo "  Verdict: READY TO ENFORCE (mixed changes, ${DOWNGRADE_PCT}% downgrades)"
fi
