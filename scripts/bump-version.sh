#!/bin/bash
set -euo pipefail
# Plugin version bump — prefers ic publish, falls back to interbump.sh

if command -v ic &>/dev/null; then
    exec ic publish "$@"
fi

# Fallback to legacy interbump.sh
SHARED="$(cd "$(dirname "$0")/../../.." && pwd)/scripts/interbump.sh"
[ -f "$SHARED" ] || { echo "Error: neither ic nor interbump.sh found" >&2; exit 1; }
exec "$SHARED" "$@"
