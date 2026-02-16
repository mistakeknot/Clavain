#!/bin/bash
# Thin wrapper — delegates to shared intercheck-versions.sh
SHARED="$(cd "$(dirname "$0")/../../.." && pwd)/scripts/intercheck-versions.sh"
[ -f "$SHARED" ] || { echo "Error: intercheck-versions.sh not found at $SHARED" >&2; exit 1; }
exec "$SHARED" "$@"
