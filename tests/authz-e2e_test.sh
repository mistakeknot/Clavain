#!/usr/bin/env bash
# End-to-end test for the auto-proceed authz v1 stack.
#
# Exercises: realistic bead-close policy (with requires) → vetting signals
# populated via env → gate wrapper runs check → `bd close` stub invoked →
# authorizations row captured with the exact policy_hash from check time.
#
# Unlike gates-smoke_test.sh (no requires), this verifies the common
# production path where /work or /sprint has populated vetting state and
# the policy gate evaluates the full `requires` block.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../../.." && pwd)"
CLAVAIN_ROOT="${ROOT}/os/Clavain"
CLI_BIN="${CLAVAIN_ROOT}/cmd/clavain-cli/clavain-cli"

if [[ ! -x "$CLI_BIN" ]]; then
  (cd "${CLAVAIN_ROOT}/cmd/clavain-cli" && PATH="/usr/local/go/bin:$PATH" go build .)
fi

SANDBOX="$(mktemp -d)"
cleanup() { rm -rf "$SANDBOX"; }
trap cleanup EXIT

STUB_BIN="${SANDBOX}/bin"
mkdir -p "$STUB_BIN"
cat > "${STUB_BIN}/bd" <<'STUB'
#!/usr/bin/env bash
printf 'bd %s\n' "$*" >> "$BD_CALL_LOG"
STUB
cat > "${STUB_BIN}/clavain-cli" <<STUB
#!/usr/bin/env bash
exec "${CLI_BIN}" "\$@"
STUB
chmod +x "${STUB_BIN}/bd" "${STUB_BIN}/clavain-cli"

export PATH="${STUB_BIN}:${PATH}"
export BD_CALL_LOG="${SANDBOX}/bd-calls.log"
: > "$BD_CALL_LOG"
export HOME="$SANDBOX"

mkdir -p "${SANDBOX}/.clavain"

# Realistic project policy — matches config/policy.yaml.example shape.
cat > "${SANDBOX}/.clavain/policy.yaml" <<YAML
version: 1
rules:
  - op: bead-close
    mode: auto
    requires:
      vetted_within_minutes: 60
      tests_passed: true
      sprint_or_work_flow: true
  - op: "*"
    mode: confirm
YAML

# Schema for authorizations.
python3 - <<PY
import sqlite3
db = sqlite3.connect("${SANDBOX}/.clavain/intercore.db")
db.executescript("""
CREATE TABLE authorizations (
  id TEXT PRIMARY KEY, op_type TEXT NOT NULL, target TEXT NOT NULL,
  agent_id TEXT NOT NULL CHECK(length(trim(agent_id)) > 0),
  bead_id TEXT, mode TEXT NOT NULL CHECK(mode IN ('auto','confirmed','blocked','force_auto')),
  policy_match TEXT, policy_hash TEXT, vetted_sha TEXT,
  vetting TEXT CHECK(vetting IS NULL OR json_valid(vetting)),
  cross_project_id TEXT, created_at INTEGER NOT NULL);
""")
db.commit()
PY

cd "$SANDBOX"

# Populate vetting signals as if /work Phase 3 or /sprint Step 6 had just run.
export CLAVAIN_AGENT_ID=e2e-test
export CLAVAIN_VETTED_AT="$(date +%s)"
export CLAVAIN_VETTED_SHA="$(openssl rand -hex 20 2>/dev/null || printf 'dead%.0sbeef' {1..4})"
export CLAVAIN_TESTS_PASSED=1
export CLAVAIN_SPRINT_OR_WORK=1

# Capture the policy hash emitted by a bare check so we can assert the
# wrapper records the same hash.
check_json="$(clavain-cli policy check bead-close --target=iv-e2e-1 --bead=iv-e2e-1 \
  --vetted-at="$CLAVAIN_VETTED_AT" --vetted-sha="$CLAVAIN_VETTED_SHA" \
  --tests-passed --sprint-or-work-flow)"
expected_hash="$(python3 -c "import json,sys; print(json.loads(sys.argv[1])['policy_hash'])" "$check_json")"
if [[ -z "$expected_hash" ]]; then
  echo "FAIL: policy check did not emit a policy_hash"
  exit 1
fi

# Now run the wrapper end to end.
bash "${CLAVAIN_ROOT}/scripts/gates/bead-close.sh" iv-e2e-1 "shipped via e2e"

# Assertion 1: bd close was called with the right bead.
if ! grep -q "bd close iv-e2e-1" "$BD_CALL_LOG"; then
  echo "FAIL: bd close not invoked"
  cat "$BD_CALL_LOG"
  exit 1
fi

# Assertion 2: one audit row exists, mode=auto, policy_hash matches check.
row="$(python3 - <<PY
import sqlite3
db = sqlite3.connect("${SANDBOX}/.clavain/intercore.db")
cur = db.execute("SELECT op_type, mode, policy_match, policy_hash, agent_id, bead_id FROM authorizations")
rows = cur.fetchall()
if len(rows) != 1:
    print("FAIL: expected 1 row, got %d" % len(rows)); raise SystemExit(2)
print("|".join(str(v) for v in rows[0]))
PY
)"
if [[ "$row" == FAIL:* ]]; then
  echo "$row"
  exit 1
fi

IFS='|' read -r op mode match hash agent bead <<< "$row"
[[ "$op"    == "bead-close"   ]] || { echo "FAIL: op=$op, want bead-close"; exit 1; }
[[ "$mode"  == "auto"         ]] || { echo "FAIL: mode=$mode, want auto";   exit 1; }
[[ "$match" == "bead-close#0" ]] || { echo "FAIL: policy_match=$match, want bead-close#0"; exit 1; }
[[ "$hash"  == "$expected_hash" ]] || { echo "FAIL: policy_hash=$hash, want $expected_hash (TOCTOU mitigation broken)"; exit 1; }
[[ "$agent" == "e2e-test"     ]] || { echo "FAIL: agent=$agent, want e2e-test"; exit 1; }
[[ "$bead"  == "iv-e2e-1"     ]] || { echo "FAIL: bead=$bead, want iv-e2e-1";   exit 1; }

echo "PASS: authz-e2e (policy check → bd close → audit row with pinned hash)"
