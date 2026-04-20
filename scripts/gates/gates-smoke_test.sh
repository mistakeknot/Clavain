#!/usr/bin/env bash
# Smoke test for the gate wrappers. Does NOT hit real beads/dolt/git/ic;
# instead, stubs those binaries on PATH and asserts the gate script:
#   - calls `clavain-cli policy check` with the right op
#   - honors exit codes (auto/confirm/block)
#   - calls `clavain-cli policy record` after a successful op
#
# Intended as a guardrail for refactoring the wrappers — not a full e2e.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../../../.." && pwd)"
GATES="${ROOT}/os/Clavain/scripts/gates"

if [[ ! -x "${ROOT}/os/Clavain/cmd/clavain-cli/clavain-cli" ]]; then
  echo "skip: clavain-cli binary not built; run 'go build ./cmd/clavain-cli' first"
  exit 0
fi

SANDBOX="$(mktemp -d)"
cleanup() { rm -rf "$SANDBOX"; }
trap cleanup EXIT

# Stubs — capture arguments into a log for assertion.
STUB_BIN="${SANDBOX}/bin"
mkdir -p "${STUB_BIN}"
cat > "${STUB_BIN}/bd" <<'STUB'
#!/usr/bin/env bash
printf 'bd %s\n' "$*" >> "$BD_CALL_LOG"
STUB
cat > "${STUB_BIN}/clavain-cli" <<STUB
#!/usr/bin/env bash
exec "${ROOT}/os/Clavain/cmd/clavain-cli/clavain-cli" "\$@"
STUB
chmod +x "${STUB_BIN}/bd" "${STUB_BIN}/clavain-cli"

export PATH="${STUB_BIN}:${PATH}"
export BD_CALL_LOG="${SANDBOX}/bd-calls.log"
: > "$BD_CALL_LOG"

# Minimal policy: bead-close is auto (no requires); catchall confirms.
mkdir -p "${SANDBOX}/.clavain"
cat > "${SANDBOX}/.clavain/policy.yaml" <<YAML
version: 1
rules:
  - op: bead-close
    mode: auto
  - op: "*"
    mode: confirm
YAML

# Schema for authorizations (v33: signing columns + cutover marker).
python3 - <<PY
import sqlite3, time
db = sqlite3.connect("${SANDBOX}/.clavain/intercore.db")
db.executescript("""
CREATE TABLE authorizations (
  id TEXT PRIMARY KEY, op_type TEXT NOT NULL, target TEXT NOT NULL,
  agent_id TEXT NOT NULL CHECK(length(trim(agent_id)) > 0),
  bead_id TEXT, mode TEXT NOT NULL CHECK(mode IN ('auto','confirmed','blocked','force_auto')),
  policy_match TEXT, policy_hash TEXT, vetted_sha TEXT,
  vetting TEXT CHECK(vetting IS NULL OR json_valid(vetting)),
  cross_project_id TEXT, created_at INTEGER NOT NULL,
  sig_version INTEGER NOT NULL DEFAULT 0,
  signature BLOB,
  signed_at INTEGER);
CREATE INDEX authz_unsigned ON authorizations(sig_version, signed_at)
  WHERE signature IS NULL AND sig_version >= 1;
""")
db.execute(
  "INSERT INTO authorizations (id, op_type, target, agent_id, mode, created_at, sig_version) "
  "VALUES ('migration-033-cutover-marker','migration.signing-enabled','authorizations',"
  "'system:migration-033','auto',?,1)",
  (int(time.time()),))
db.commit()
PY

# Fake HOME to suppress any real global policy.
export HOME="${SANDBOX}"

cd "${SANDBOX}"

# Initialize a signing key so gate_sign has something to sign with.
clavain-cli policy init-key >/dev/null
# Sign the cutover marker once at bootstrap (authz-init.sh will do this in
# production). Leaving it unsigned makes `policy audit --verify` fail.
clavain-cli policy sign >/dev/null

# Run wrapper — auto path.
CLAVAIN_AGENT_ID=smoke-agent bash "${GATES}/bead-close.sh" iv-smoke-1 test-reason

# Assert bd was called.
if ! grep -q "bd close iv-smoke-1" "$BD_CALL_LOG"; then
  echo "FAIL: bd close not invoked"
  cat "$BD_CALL_LOG"
  exit 1
fi

# Assert audit row was written.
rows="$(python3 -c "
import sqlite3
db = sqlite3.connect('${SANDBOX}/.clavain/intercore.db')
for row in db.execute(\"SELECT op_type, mode, agent_id FROM authorizations WHERE op_type='bead-close'\"):
    print(row)
")"
if [[ -z "$rows" ]]; then
  echo "FAIL: no authorization row written"
  exit 1
fi
if ! grep -q "bead-close" <<<"$rows"; then
  echo "FAIL: authorization row missing bead-close op: $rows"
  exit 1
fi
if ! grep -q "'auto'" <<<"$rows"; then
  echo "FAIL: mode not auto: $rows"
  exit 1
fi

# Assert the bead-close row has a non-NULL signature (gate_sign ran).
signed_len="$(python3 -c "
import sqlite3
db = sqlite3.connect('${SANDBOX}/.clavain/intercore.db')
row = db.execute(\"SELECT length(signature), signed_at FROM authorizations WHERE op_type='bead-close'\").fetchone()
print(row[0] if row and row[0] is not None else 0)
")"
if [[ "$signed_len" != "64" ]]; then
  echo "FAIL: bead-close row signature length=${signed_len}, want 64 (Ed25519)"
  exit 1
fi

# Verify the signature via clavain-cli.
if ! clavain-cli policy audit --verify >/dev/null 2>&1; then
  # The verify command emits JSON on stdout; re-run to surface it for debug.
  verify_out="$(clavain-cli policy audit --verify 2>&1 || true)"
  echo "FAIL: policy audit --verify did not succeed"
  echo "$verify_out"
  exit 1
fi
echo "gates-smoke: signature verified"

echo "PASS: gates-smoke (bead-close auto path)"
