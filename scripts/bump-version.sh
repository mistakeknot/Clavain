#!/bin/bash
# Thin wrapper — delegates to shared interbump.sh
SHARED="$(cd "$(dirname "$0")/../../.." && pwd)/scripts/interbump.sh"
[ -f "$SHARED" ] || { echo "Error: interbump.sh not found at $SHARED" >&2; exit 1; }
exec "$SHARED" "$@"
