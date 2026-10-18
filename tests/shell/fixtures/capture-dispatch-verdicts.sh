#!/usr/bin/env bash
# Prints what the real dispatch.sh _extract_verdict writes as the sidecar for
# every combination of reviewer-output shape. Columns (TAB separated):
#   shape  body-verdict  terminal-block  provisional  sidecar-STATUS  sidecar-PROVISIONAL
# shape: tail = verdict only on the last line; both = same verdict on the
# first line too. terminal-block: none | pass | warn | fail (the reviewer's own
# "--- VERDICT ---" block). provisional: 0|1 (capacity-substitute seat).
# Usage: capture-dispatch-verdicts.sh /path/to/dispatch.sh
set -euo pipefail
D=${1:?dispatch.sh path}
T=$(mktemp -d); trap 'rm -rf "$T"' EXIT
awk '/^_extract_verdict\(\)[[:space:]]*\{/ {e=1} e {print} e && /^}[[:space:]]*$/ {e=0}' "$D" > "$T/fn.sh"
write_verdict_block_needed=$(grep -c '_write_verdict_block' "$T/fn.sh" || true)
[ "$write_verdict_block_needed" -eq 0 ] || awk '/^_write_verdict_block\(\)[[:space:]]*\{/ {e=1} e {print} e && /^}[[:space:]]*$/ {e=0}' "$D" >> "$T/fn.sh"
# shellcheck disable=SC1091
source "$T/fn.sh"
for shape in tail both; do
for bv in "PASS" "PASS WITH NOTES" "FAIL"; do
for blk in none pass warn fail; do
for prov in 0 1; do
  o="$T/out.md"; rm -f "$o.verdict"
  { [ "$shape" = both ] && printf 'VERDICT: %s\n' "$bv"; printf -- '- MEDIUM: x\nVERDICT: %s\n' "$bv"
    [ "$blk" = none ] || printf -- '--- VERDICT ---\nSTATUS: %s\n---\n' "$blk"; } > "$o"
  if [ "$prov" = 1 ]; then export CAPACITY_SUBSTITUTE_JSON='{"producer_lab":"a","reviewer_lab":"a","failure_class":"quota"}'; else unset CAPACITY_SUBSTITUTE_JSON; fi
  _extract_verdict "$o" 2>/dev/null
  st=$(sed -n 's/^STATUS: //p' "$o.verdict" | head -1)
  pl=0; ! grep -q '^PROVISIONAL:' "$o.verdict" || pl=1
  printf '%s\t%s\t%s\t%s\t%s\t%s\n' "$shape" "$bv" "$blk" "$prov" "$st" "$pl"
done; done; done; done
