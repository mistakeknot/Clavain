#!/usr/bin/env bash
# Summarize [executor-shadow] would-route decisions per parity class.
# Feeds phase-2: which classes have enough volume to be worth a parity eval.
set -uo pipefail
FROM_FILE=""; JSON=false
while [[ $# -gt 0 ]]; do case "$1" in
  --from-file) FROM_FILE="$2"; shift 2;;
  --json) JSON=true; shift;;
  *) shift;; esac; done
lines=""
if [[ -n "$FROM_FILE" && -f "$FROM_FILE" ]]; then
  lines="$(grep -h '\[executor-shadow\]' "$FROM_FILE" 2>/dev/null || true)"
else
  lines="$(find /tmp -maxdepth 1 -name 'interstat-*' -mtime -7 -exec grep -h '\[executor-shadow\]' {} + 2>/dev/null || true)"
fi
if [[ -z "$lines" ]]; then echo "No [executor-shadow] lines found."; exit 0; fi
# tally class= occurrences
printf '%s\n' "$lines" | sed -n 's/.*class=\([^ ]*\).*/\1/p' | sort | uniq -c | \
while read -r n cls; do
  if $JSON; then printf '{"class":"%s","count":%s}\n' "$cls" "$n"; else printf '  %-10s %s would-route events\n' "$cls" "$n"; fi
done
