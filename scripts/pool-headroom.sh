#!/usr/bin/env bash
# Read-only pool probe; --stdin runs the pure fixture/forecast core instead.
set -euo pipefail
exec python3 "$(dirname "${BASH_SOURCE[0]}")/pool-headroom.py" "$@"
