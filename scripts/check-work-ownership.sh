#!/usr/bin/env bash
# Fixture-only checks. No installation or live ownership authority.
set -euo pipefail
root=$(git rev-parse --show-toplevel)
cd "$root/cmd/clavain-cli"
if [[ -n ${CI:-} || -n ${CI_SOURCE_SHA:-} ]]; then
  [[ ${CI_SOURCE_SHA:-} =~ ^[0-9a-f]{40}$ ]] || { echo 'UNVERIFIABLE: exact source SHA required' >&2; exit 2; }
  [[ $(git rev-parse HEAD) == "$CI_SOURCE_SHA" ]] || { echo 'UNVERIFIABLE: source SHA mismatch' >&2; exit 2; }
fi
evidence=$(mktemp -d "${TMPDIR:-/tmp}/work-ownership-check.XXXXXX")
trap 'rm -f "$evidence/preview"' EXIT
# A misspelled test selector must not silently qualify a zero-test replay.
go test -list 'TestWorkOwnership|TestWorkRoutingIncident' ./... > "$evidence/inventory.txt"
python3 - "$evidence/inventory.txt" <<'PY'
from pathlib import Path
import sys
tests = [s for s in Path(sys.argv[1]).read_text().splitlines()
         if s.startswith('TestWorkOwnership')]
if not tests:
    raise SystemExit('UNVERIFIABLE: ownership replay tests are absent')
if 'TestWorkRoutingIncidentReplay' not in Path(sys.argv[1]).read_text().splitlines():
    raise SystemExit('UNVERIFIABLE: routing incident replay test is absent')
print('ownership_replay_inventory=' + ','.join(tests))
PY
go test ./... -count=1
go test ./... -run 'TestWorkOwnership|TestWorkRoutingIncident' -count=1 -v
go test -race ./... -run '^TestWorkOwnership' -count=1
go vet ./...
go build -o "$evidence/preview" .
printf '%s\n' 'Fixture checks passed; production ownership and host enforcement remain unverified.'
