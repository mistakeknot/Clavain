#!/bin/bash
# Bounded verification pilot for the independent zklw fleet worker.
set -euo pipefail
cd "$(git rev-parse --show-toplevel)"
if [[ -n "${CI:-}" || -n "${CI_SOURCE_SHA:-}" ]]; then
  [[ -n "${CI_SOURCE_SHA:-}" ]] || { echo 'UNVERIFIABLE: fleet source SHA is required' >&2; exit 2; }
  [[ "$CI_SOURCE_SHA" == "$(git rev-parse HEAD)" ]] || { echo 'UNVERIFIABLE: wrong CI source SHA' >&2; exit 2; }
fi
# Updating the reviewed contract requires updating the pinned recipe too.
python3 - <<'PY'
import hashlib
import sys
from pathlib import Path
expected = '9a4a13c3c7f6ae4ec16c15afe727d5dd4ff8d34ff3cbd2a5bb9cfa1ceb2965dc'
if hashlib.sha256(Path('tests/verification-pilot.json').read_bytes()).hexdigest() != expected:
    print('UNVERIFIABLE: verification contract differs from pinned recipe', file=sys.stderr)
    raise SystemExit(2)
PY
evidence="$(mktemp -d "${TMPDIR:-/tmp}/clavain-verification.XXXXXX")"
evidence="$(cd "$evidence" && pwd -P)"
status=0
python3 scripts/verification_runner.py \
  --spec tests/verification-pilot.json --project-dir "$PWD" \
  --evidence-dir "$evidence" --run-id "${CI_SOURCE_SHA:-local}" \
  --task-id verification-pilot > "$evidence/step.json" || status=$?
cat "$evidence/step.json"
# Fleet retains a private, hashed job log; guests are destroyed. Preserve the
# exact receipt and artifacts inside that log, never just ephemeral paths.
python3 - "$evidence" <<'PY'
import base64
import hashlib
from pathlib import Path
import sys
import tarfile
import tempfile

root = Path(sys.argv[1])
with tempfile.TemporaryFile() as archive:
    with tarfile.open(fileobj=archive, mode='w:gz') as bundle:
        for path in sorted(root.rglob('*')):
            if path.is_symlink() or not (path.is_file() or path.is_dir()):
                raise SystemExit('unsafe evidence export entry')
            bundle.add(path, arcname=str(path.relative_to(root)), recursive=False)
    if archive.tell() > 32 * 1024 * 1024:
        raise SystemExit('evidence export exceeds 32 MiB compressed limit')
    archive.seek(0)
    digest = hashlib.sha256()
    while chunk := archive.read(1024 * 1024):
        digest.update(chunk)
    archive.seek(0)
    print('BEGIN_VERIFICATION_EVIDENCE_TGZ_BASE64 sha256=' + digest.hexdigest(), flush=True)
    base64.encode(archive, sys.stdout.buffer)
    print('END_VERIFICATION_EVIDENCE_TGZ_BASE64', flush=True)
PY
exit "$status"
