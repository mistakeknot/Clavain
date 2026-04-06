#!/usr/bin/env bash
# routing-b5-shadow-report.sh — Analyze Track B5 (local model) shadow routing logs.
# Shows would-route-locally count, ineligible count, unavailable count, and enforce readiness.
#
# Usage: bash routing-b5-shadow-report.sh [--days N] [--json]

set -euo pipefail

DAYS="${1:-7}"
JSON_MODE=""
[[ "${1:-}" == "--json" || "${2:-}" == "--json" ]] && JSON_MODE=1
[[ "${1:-}" =~ ^[0-9]+$ ]] && DAYS="$1"

echo "=== Track B5 Local Model Routing Shadow Report ==="
echo "Period: last ${DAYS} days"
echo ""

# Search for [B5-shadow] lines
SHADOW_LINES=""
if command -v cass >/dev/null 2>&1; then
  SHADOW_LINES=$(cass search "B5-shadow" --robot --limit 500 --mode hybrid --since "${DAYS}d" 2>/dev/null | grep -o '\[B5-shadow\].*' || true)
fi

# Fallback: grep interstat session logs
if [[ -z "$SHADOW_LINES" ]]; then
  SHADOW_LINES=$(find /tmp -maxdepth 1 -name 'interstat-*' -mtime "-${DAYS}" -exec grep -h '\[B5-shadow\]' {} + 2>/dev/null || true)
fi

if [[ -z "$SHADOW_LINES" ]]; then
  echo "No [B5-shadow] log lines found in the last ${DAYS} days."
  echo ""
  echo "This means either:"
  echo "  1. B5 shadow mode is not active (mode=off in routing.yaml)"
  echo "  2. interfer server has not been running during sessions"
  echo "  3. No complexity-routed tasks have been dispatched"
  echo ""
  echo "Readiness verdict: NOT READY (no shadow data)"
  exit 0
fi

# Parse shadow lines
echo "--- Event Distribution ---"
TOTAL=$(echo "$SHADOW_LINES" | wc -l | tr -d ' ')
WOULD_ROUTE=$(echo "$SHADOW_LINES" | grep -c 'would route locally' || echo "0")
INELIGIBLE=$(echo "$SHADOW_LINES" | grep -c 'ineligible' || echo "0")
UNAVAILABLE=$(echo "$SHADOW_LINES" | grep -c 'unavailable' || echo "0")

echo "  Total events:      $TOTAL"
echo "  Would route local: $WOULD_ROUTE"
echo "  Ineligible:        $INELIGIBLE (safety floor agents)"
echo "  Unavailable:       $UNAVAILABLE (interfer down)"
echo ""

echo "--- Would-Route-Locally Breakdown ---"
echo "$SHADOW_LINES" | grep 'would route locally' | grep -oP '→ \K[^ ]+' | sort | uniq -c | sort -rn || echo "  (none)"
echo ""

echo "--- Per-Complexity Tier ---"
echo "$SHADOW_LINES" | grep -oP 'complexity=\KC[0-9]' | sort | uniq -c | sort -rn || echo "  (no tier data)"
echo ""

echo "--- Ineligible Agents ---"
echo "$SHADOW_LINES" | grep 'ineligible' | grep -oP 'ineligible: \K[^ ]+' | sort | uniq -c | sort -rn || echo "  (none)"
echo ""

# Readiness verdict
echo "--- Enforce Readiness ---"
if [[ "$WOULD_ROUTE" -gt 0 && "$UNAVAILABLE" -eq 0 ]]; then
  echo "  Verdict: READY TO ENFORCE"
  echo "  $WOULD_ROUTE tasks would route locally, interfer was always available."
elif [[ "$WOULD_ROUTE" -gt 0 && "$UNAVAILABLE" -gt 0 ]]; then
  AVAIL_PCT=$(( (TOTAL - UNAVAILABLE) * 100 / TOTAL ))
  echo "  Verdict: CAUTION — interfer availability ${AVAIL_PCT}%"
  echo "  $UNAVAILABLE events found interfer unavailable. Start the server before enforcing."
else
  echo "  Verdict: NOT READY — no eligible tasks routed locally"
  echo "  All $TOTAL events were ineligible or unavailable."
fi
