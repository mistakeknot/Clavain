#!/usr/bin/env bash
# Socket-free, dummy-only acceptance. Never falls back to a networked run.
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."
exec unshare --user --map-root-user --net python3 -m pytest -p no:cacheprovider --tb=short \
  tests/structural/test_selector_support.py \
  tests/structural/test_selector_support_accounting.py \
  tests/structural/test_selector_support_cli.py \
  tests/structural/test_selector_support_selector.py \
  tests/structural/test_selector_support_burn.py
