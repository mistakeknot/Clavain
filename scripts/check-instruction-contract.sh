#!/bin/bash
# Check that a host instruction file carries the current Clavain contract block.
#
#   CLAVAIN_SELECTED_ROOT=<installPath> check-instruction-contract.sh --host H --file F
#
# Prints one JSON object on stdout. Exit 0 = current, 1 = drifted, 2 = usage or
# runtime error. Compares the whole rendered block, the version, and the policy
# hash (sha256 of the installed config/routing.yaml) recorded in the file's
# receipt, so a policy change under an unchanged version still reports drift.
set -euo pipefail

host=""
file=""
while [ $# -gt 0 ]; do
  case "$1" in
    --host) host="${2:-}"; shift 2 || true ;;
    --file) file="${2:-}"; shift 2 || true ;;
    -h|--help) sed -n 2,9p "$0"; exit 0 ;;
    *) echo "unknown argument: $1" >&2; exit 2 ;;
  esac
done
if [ -z "$host" ] || [ -z "$file" ]; then
  echo "usage: CLAVAIN_SELECTED_ROOT=<root> $0 --host H --file F" >&2
  exit 2
fi
root="${CLAVAIN_SELECTED_ROOT:-}"
if [ -z "$root" ] || [ ! -f "$root/scripts/sync-agent-instructions.py" ]; then
  echo "CLAVAIN_SELECTED_ROOT must name an installed Clavain root" >&2
  exit 2
fi

out="$(mktemp)"
trap 'rm -f "$out"' EXIT
rc=0
python3 -I "$root/scripts/sync-agent-instructions.py" --source "$root" \
  --host "$host" --file "$file" --portable-policy --check >"$out" 2>&1 || rc=$?

python3 -I - "$out" "$rc" "$file" <<'PY'
import hashlib, json, re, sys
from pathlib import Path

out, rc, path = Path(sys.argv[1]), int(sys.argv[2]), Path(sys.argv[3])
text = out.read_text()
try:
    meta = json.loads(text.strip().splitlines()[-1])
except (ValueError, IndexError):
    print(json.dumps(dict(current=False, error=text.strip()[:500], drift=['renderer-error'])))
    sys.exit(2)

drift = []
file_version = file_policy = None
if path.exists():
    m = re.search(r'package: ([^;]+); policy selection: [^;]+; policy SHA256: ([0-9a-f]{64})',
                  path.read_text(errors='replace'))
    if m:
        file_version, file_policy = m.group(1), m.group(2)
else:
    drift.append('file-missing')
if file_version is None:
    drift.append('no-receipt')
else:
    if file_version != meta['version']:
        drift.append('version')
    if file_policy != meta['policy_hash']:
        drift.append('policy-hash')
if not meta.get('current') and not drift:
    drift.append('block-content')

meta.update(file=str(path), file_version=file_version, file_policy_hash=file_policy,
            installed_version=meta['version'], drift=drift,
            current=bool(meta.get('current')) and not drift)
print(json.dumps(meta, sort_keys=True))
sys.exit(0 if meta['current'] else 1)
PY
