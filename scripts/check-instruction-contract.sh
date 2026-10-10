#!/bin/bash
# Check that a host instruction file carries the current Clavain contract block.
#
#   CLAVAIN_SELECTED_ROOT=<installPath> check-instruction-contract.sh --host H --file F [--explicit]
#
# Default checks the portable-policy block. --explicit checks a standalone
# installation synced without --portable-policy.
#
# Prints one JSON object on stdout. Exit 0 = current, 1 = drifted, 2 = usage or
# runtime error. Compares the whole rendered block, the version, and the policy
# hash (sha256 of the installed config/routing.yaml) recorded in the file's
# receipt, so a policy change under an unchanged version still reports drift.
set -euo pipefail

host=""
file=""
mode=portable
while [ $# -gt 0 ]; do
  case "$1" in
    --host|--file)
      [ $# -ge 2 ] || { echo "$1 needs a value" >&2; exit 2; }
      if [ "$1" = --host ]; then host="$2"; else file="$2"; fi
      shift 2 ;;
    --explicit) mode=explicit; shift ;;
    -h|--help) sed -n 2,13p "$0"; exit 0 ;;
    *) echo "unknown argument: $1" >&2; exit 2 ;;
  esac
done
if [ -z "$host" ] || [ -z "$file" ]; then
  echo "usage: CLAVAIN_SELECTED_ROOT=<root> $0 --host H --file F [--explicit]" >&2
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
flags=(--check)
[ "$mode" = portable ] && flags+=(--portable-policy)
python3 -I "$root/scripts/sync-agent-instructions.py" --source "$root" \
  --host "$host" --file "$file" "${flags[@]}" >"$out" 2>&1 || rc=$?

python3 -I - "$out" "$rc" "$file" <<'PY'
import json, re, sys
from pathlib import Path

START, END = '<!-- BEGIN CLAVAIN CODEX TOOL MAP -->', '<!-- END CLAVAIN CODEX TOOL MAP -->'
out, rc, path = Path(sys.argv[1]), int(sys.argv[2]), Path(sys.argv[3])


def fail(message):
    print(json.dumps(dict(current=False, error=message[:500], drift=['renderer-error'])))
    sys.exit(2)


text = out.read_text()
try:
    meta = json.loads(text.strip().splitlines()[-1])
except (ValueError, IndexError):
    fail(text.strip())
if rc not in (0, 1):
    fail(f'renderer exited {rc}: {text.strip()}')
if (not isinstance(meta, dict) or not isinstance(meta.get('current'), bool)
        or not isinstance(meta.get('version'), str) or not meta['version']
        or not isinstance(meta.get('policy_hash'), str)
        or not re.fullmatch(r'[0-9a-f]{64}', meta['policy_hash'])):
    fail(f'renderer output has missing or mistyped fields: {text.strip()}')
if bool(meta['current']) != (rc == 0):
    fail(f'renderer exit {rc} disagrees with current={meta["current"]}')

drift = []
file_version = file_policy = None
if path.exists():
    body = path.read_text(errors='replace')
    # Only the managed block counts; receipts quoted elsewhere in the file do not.
    if body.count(START) == 1 and body.count(END) == 1 and body.index(START) < body.index(END):
        body = body[body.index(START):body.index(END)]
        m = re.search(r'package: ([^;]+); policy selection: [^;]+; policy SHA256: ([0-9a-f]{64})', body)
        if m:
            file_version, file_policy = m.group(1), m.group(2)
else:
    drift.append('file-missing')
if file_version is None:
    if 'file-missing' not in drift:
        drift.append('no-receipt')
else:
    if file_version != meta['version']:
        drift.append('version')
    if file_policy != meta['policy_hash']:
        drift.append('policy-hash')
if not meta['current'] and not drift:
    drift.append('block-content')

meta.update(file=str(path), file_version=file_version, file_policy_hash=file_policy,
            installed_version=meta['version'], drift=drift,
            current=meta['current'] and not drift)
print(json.dumps(meta, sort_keys=True))
sys.exit(0 if meta['current'] else 1)
PY
