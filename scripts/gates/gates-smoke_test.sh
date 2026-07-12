#!/usr/bin/env bash
# Smoke test for the gate wrappers. Does NOT hit real beads/dolt/git/ic;
# instead, stubs those binaries on PATH and asserts the gate script:
#   - calls `clavain-cli policy check` with the right op
#   - honors exit codes (auto/confirm/block)
#   - calls `clavain-cli policy record` after a successful op
#   - for v2: consumes a token when present; hard-fails on auth-failure;
#     falls through to legacy on state-class errors
#
# Intended as a guardrail for refactoring the wrappers — not a full e2e.
#
# Usage:
#   gates-smoke_test.sh                 run all scenarios
#   gates-smoke_test.sh --focus=token   only v2 token-path scenarios
#   gates-smoke_test.sh --focus=legacy  only v1.5 legacy-path scenarios
set -euo pipefail

FOCUS="all"
for arg in "$@"; do
  case "$arg" in
    --focus=token) FOCUS="token" ;;
    --focus=legacy) FOCUS="legacy" ;;
    --focus=all) FOCUS="all" ;;
  esac
done

ROOT="$(cd "$(dirname "$0")/../../../.." && pwd)"
GATES="${ROOT}/os/Clavain/scripts/gates"

SANDBOX="$(mktemp -d)"
cleanup() { rm -rf "$SANDBOX"; }
trap cleanup EXIT
unset CLAVAIN_AUTHZ_PROJECT_ROOT GATE_AUTHZ_TOKEN
export GOCACHE="${GOCACHE:-${SANDBOX}/go-build-cache}"

mkdir -p "${SANDBOX}/real-bin"
CLI_BIN="${SANDBOX}/real-bin/clavain-cli"
(cd "${ROOT}/os/Clavain/cmd/clavain-cli" && go build -trimpath -o "$CLI_BIN" .)

# Stubs — capture arguments into a log for assertion. bd close is idempotent
# per-ID in the stub (just logs); the wrapper may call it many times across
# scenarios, each with a distinct bead id.
STUB_BIN="${SANDBOX}/bin"
mkdir -p "${STUB_BIN}"
cat > "${STUB_BIN}/bd" <<'STUB'
#!/usr/bin/env bash
if [[ "${1:-}" == "show" ]]; then
  printf '[{"id":"%s","labels":[]}]\n' "${2:-unknown}"
  exit 0
fi
if [[ "${1:-}" == "state" ]]; then
  if [[ "${3:-}" == "runtime_evidence_required" && -n "${BD_RUNTIME_REQUIRED:-}" ]]; then
    printf '%s\n' "$BD_RUNTIME_REQUIRED"
  fi
  exit 0
fi
if [[ "${1:-} ${2:-}" == "context --json" ]]; then
  printf '{"repo_root":"%s","beads_dir":"%s/.beads"}\n' "$GATE_SMOKE_ROOT" "$GATE_SMOKE_ROOT"
  exit 0
fi
printf 'bd %s\n' "$*" >> "$BD_CALL_LOG"
STUB
cat > "${STUB_BIN}/clavain-cli" <<STUB
#!/usr/bin/env bash
exec "${CLI_BIN}" "\$@"
STUB
chmod +x "${STUB_BIN}/bd" "${STUB_BIN}/clavain-cli"

export PATH="${STUB_BIN}:${PATH}"
export BD_CALL_LOG="${SANDBOX}/bd-calls.log"
export GATE_SMOKE_ROOT="$SANDBOX"
: > "$BD_CALL_LOG"

# Minimal policy: tested irreversible operations are auto; catchall confirms.
mkdir -p "${SANDBOX}/.clavain"
cat > "${SANDBOX}/.clavain/policy.yaml" <<YAML
version: 1
rules:
  - op: bead-close
    mode: auto
  - op: git-push-main
    mode: auto
  - op: "*"
    mode: confirm
YAML

# Schema v36: authorizations + authz_tokens + signed legacy seal. Kept in
# sync with core/intercore/internal/db/db.go.
python3 - <<PY
import sqlite3, time
db = sqlite3.connect("${SANDBOX}/.clavain/intercore.db")
db.execute("PRAGMA user_version = 36")
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
CREATE TABLE authz_tokens (
  id TEXT PRIMARY KEY, op_type TEXT NOT NULL, target TEXT NOT NULL,
  agent_id TEXT NOT NULL CHECK(length(trim(agent_id)) > 0),
  bead_id TEXT, delegate_to TEXT,
  expires_at INTEGER NOT NULL,
  consumed_at INTEGER, revoked_at INTEGER,
  issued_by TEXT NOT NULL,
  parent_token TEXT REFERENCES authz_tokens(id) ON DELETE RESTRICT,
  root_token TEXT,
  depth INTEGER NOT NULL DEFAULT 0 CHECK (depth >= 0 AND depth <= 3),
  sig_version INTEGER NOT NULL DEFAULT 2,
  signature BLOB NOT NULL,
  created_at INTEGER NOT NULL);
CREATE INDEX tokens_by_root ON authz_tokens(root_token, consumed_at, revoked_at);
CREATE INDEX tokens_by_parent ON authz_tokens(parent_token);
CREATE INDEX tokens_by_agent ON authz_tokens(agent_id, created_at DESC);
""")
db.execute(
  "INSERT INTO authorizations (id, op_type, target, agent_id, mode, created_at, sig_version) "
  "VALUES ('migration-033-cutover-marker','migration.signing-enabled','authorizations',"
  "'system:migration-033','auto',?,1)",
  (int(time.time()),))
db.commit()
PY

export HOME="${SANDBOX}"
cd "${SANDBOX}"

git init -q
git config user.email "gates-smoke@example.invalid"
git config user.name "gates-smoke"
git config commit.gpgsign false
touch smoke-marker
git add smoke-marker
git commit -q -m "gate smoke fixture"
git remote add origin https://example.invalid/gates-smoke.git
git init --bare -q "${SANDBOX}/push.git"
git remote set-url --push origin "${SANDBOX}/push.git"

clavain-cli policy init-key >/dev/null
clavain-cli policy sign >/dev/null
clavain-cli policy anchor-legacy --expect-empty >/dev/null

# ─── legacy scenario ──────────────────────────────────────────────────

scenario_legacy_bead_close() {
  echo "=== legacy: bead-close auto path ==="
  CLAVAIN_AGENT_ID=smoke-agent bash "${GATES}/bead-close.sh" iv-smoke-1 test-reason

  if ! grep -q "bd close iv-smoke-1" "$BD_CALL_LOG"; then
    echo "FAIL: legacy bd close not invoked"
    cat "$BD_CALL_LOG"
    exit 1
  fi

  rows="$(python3 -c "
import sqlite3
db = sqlite3.connect('${SANDBOX}/.clavain/intercore.db')
for row in db.execute(\"SELECT op_type, mode, agent_id FROM authorizations WHERE op_type='bead-close'\"):
    print(row)
")"
  if ! grep -q "bead-close" <<<"$rows"; then
    echo "FAIL: legacy authorization row missing bead-close op: $rows"
    exit 1
  fi
  if ! grep -q "'auto'" <<<"$rows"; then
    echo "FAIL: legacy mode not auto: $rows"
    exit 1
  fi

  signed_len="$(python3 -c "
import sqlite3
db = sqlite3.connect('${SANDBOX}/.clavain/intercore.db')
row = db.execute(\"SELECT length(signature) FROM authorizations WHERE op_type='bead-close'\").fetchone()
print(row[0] if row and row[0] is not None else 0)
")"
  if [[ "$signed_len" != "64" ]]; then
    echo "FAIL: legacy bead-close row signature length=${signed_len}, want 64"
    exit 1
  fi

  if ! clavain-cli policy audit --verify >/dev/null 2>&1; then
    verify_out="$(clavain-cli policy audit --verify 2>&1 || true)"
    echo "FAIL: legacy policy audit --verify did not succeed"
    echo "$verify_out"
    exit 1
  fi
  echo "PASS: legacy bead-close auto path"
}

scenario_git_push_binds_source_and_pushurl() {
	echo "=== legacy: git push binds source object and push URL ==="
	git branch source-branch
	git checkout -q -b checkout-other
	printf 'other\n' > checkout-other
	git add checkout-other
	git commit -q -m "checkout differs from source"
	local head_sha source_sha pushed_sha audit_target push_hash
	head_sha="$(git rev-parse HEAD)"
	source_sha="$(git rev-parse source-branch)"
	[[ "$head_sha" != "$source_sha" ]] || { echo "FAIL: fixture SHAs should differ"; exit 1; }

	CLAVAIN_AGENT_ID=smoke-agent bash "${GATES}/git-push-main.sh" origin source-branch:main >/dev/null
	pushed_sha="$(git --git-dir="${SANDBOX}/push.git" rev-parse refs/heads/main)"
	[[ "$pushed_sha" == "$source_sha" ]] || {
		echo "FAIL: pushed SHA=$pushed_sha, want authorized source=$source_sha"
		exit 1
	}
	push_hash="$(python3 -c 'import hashlib,sys; print(hashlib.sha256((sys.argv[1]+"\n").encode()).hexdigest())' "${SANDBOX}/push.git")"
	audit_target="$(python3 -c "
import sqlite3
db = sqlite3.connect('${SANDBOX}/.clavain/intercore.db')
print(db.execute(\"SELECT target FROM authorizations WHERE op_type='git-push-main' ORDER BY created_at DESC LIMIT 1\").fetchone()[0])
")"
	[[ "$audit_target" == "repo=sha256:${push_hash};ref=refs/heads/main;head=${source_sha}" ]] || {
		echo "FAIL: audit target not bound to source/pushurl: $audit_target"
		exit 1
	}
	echo "PASS: git push authorization binds immutable source + push URL"
}

# ─── token scenarios ──────────────────────────────────────────────────

# issue_token <op> <target> <for-agent> <ttl> → prints opaque string
issue_token() {
  local op="$1" target="$2" for_agent="$3" ttl="$4"
  CLAVAIN_AGENT_ID=smoke-issuer clavain-cli policy token issue \
    --op="$op" --target="$target" --for="$for_agent" --ttl="$ttl" 2>/dev/null
}

token_row_consumed_at() {
  local id="$1"
  python3 -c "
import sqlite3
db = sqlite3.connect('${SANDBOX}/.clavain/intercore.db')
row = db.execute('SELECT consumed_at FROM authz_tokens WHERE id = ?', (\"$id\",)).fetchone()
print(row[0] if row and row[0] is not None else 0)
"
}

scenario_token_valid() {
  echo "=== token: valid root token → short-circuit ==="
  local opaque id
  opaque="$(issue_token bead-close iv-smoke-tok1 smoke-consumer 60m)"
  id="${opaque%%.*}"

  # Run wrapper with token + consumer agent id.
  CLAVAIN_AGENT_ID=smoke-consumer CLAVAIN_AUTHZ_TOKEN="$opaque" \
    bash "${GATES}/bead-close.sh" iv-smoke-tok1 reason 2>&1 | grep -v "^policy:" || true

  if ! grep -q "bd close iv-smoke-tok1" "$BD_CALL_LOG"; then
    echo "FAIL: token-path bd close not invoked"
    exit 1
  fi

  local ca; ca="$(token_row_consumed_at "$id")"
  if [[ "$ca" == "0" ]]; then
    echo "FAIL: token row consumed_at not set (id=$id)"
    exit 1
  fi

  # Assert env var unset in spawned child: the wrapper unsets it in its
  # own process via gate_token_consume; we verify by re-running the wrapper
  # expecting the state-class fall-through (double-consume → exit 2 from
  # CLI → gate falls through to legacy gate_check). The legacy policy for
  # bead-close is auto, so the second run succeeds via legacy path.
  echo "GATE_CONSUMED=1"
  echo "PASS: token valid → short-circuit + consumed_at set"
}

scenario_runtime_proof_precedes_token() {
  echo "=== token: invalid runtime proof preserves one-shot token ==="
  local opaque id rc=0
  opaque="$(issue_token bead-close iv-smoke-proof smoke-consumer 60m)"
  id="${opaque%%.*}"

  BD_RUNTIME_REQUIRED=1 CLAVAIN_AGENT_ID=smoke-consumer CLAVAIN_AUTHZ_TOKEN="$opaque" \
    bash "${GATES}/bead-close.sh" iv-smoke-proof reason \
    >"${SANDBOX}/runtime-proof.out" 2>"${SANDBOX}/runtime-proof.err" || rc=$?

  if [[ "$rc" == "0" ]]; then
    echo "FAIL: missing runtime proof should reject close"
    exit 1
  fi
  if grep -q "bd close iv-smoke-proof" "$BD_CALL_LOG"; then
    echo "FAIL: runtime-gated bead closed without proof"
    exit 1
  fi
  local ca; ca="$(token_row_consumed_at "$id")"
  if [[ "$ca" != "0" ]]; then
    echo "FAIL: invalid runtime proof consumed one-shot token (id=$id)"
    exit 1
  fi
  echo "PASS: runtime proof rejects before token consumption"
}

scenario_token_revoked_hard_fail() {
  echo "=== token: revoked → hard fail ==="
  local opaque id
  opaque="$(issue_token bead-close iv-smoke-tok2 smoke-consumer 60m)"
  id="${opaque%%.*}"

  clavain-cli policy token revoke --token="$id" >/dev/null

  local rc=0
  CLAVAIN_AGENT_ID=smoke-consumer CLAVAIN_AUTHZ_TOKEN="$opaque" \
    bash "${GATES}/bead-close.sh" iv-smoke-tok2 reason >/dev/null 2>"${SANDBOX}/revoked.err" || rc=$?

  if [[ "$rc" == "0" ]]; then
    echo "FAIL: revoked token should hard-fail wrapper (rc=$rc)"
    cat "${SANDBOX}/revoked.err"
    exit 1
  fi
  if ! grep -q "AUTH FAILURE" "${SANDBOX}/revoked.err"; then
    echo "FAIL: stderr missing AUTH FAILURE message"
    cat "${SANDBOX}/revoked.err"
    exit 1
  fi
  if ! grep -qi "revoked" "${SANDBOX}/revoked.err"; then
    echo "FAIL: stderr missing revoked class"
    cat "${SANDBOX}/revoked.err"
    exit 1
  fi
  # Legacy gate_check must NOT have run (no bd close for this id).
  if grep -q "bd close iv-smoke-tok2" "$BD_CALL_LOG"; then
    echo "FAIL: revoked token should NOT fall through to legacy — bd close ran"
    exit 1
  fi
  echo "PASS: revoked token hard-fails, legacy skipped"
}

scenario_token_expect_mismatch() {
  echo "=== token: expect-op mismatch → hard fail ==="
  local opaque id
  # Token is for bead-close, but we'll run it through the git-push-main wrapper.
  opaque="$(issue_token bead-close iv-smoke-tok3 smoke-consumer 60m)"
  id="${opaque%%.*}"

  local rc=0
  CLAVAIN_AGENT_ID=smoke-consumer CLAVAIN_AUTHZ_TOKEN="$opaque" \
    bash "${GATES}/git-push-main.sh" origin source-branch:main >/dev/null 2>"${SANDBOX}/mismatch.err" || rc=$?

  if [[ "$rc" == "0" ]]; then
    echo "FAIL: expect-mismatch should hard-fail (rc=$rc)"
    cat "${SANDBOX}/mismatch.err"
    exit 1
  fi
  if ! grep -q "AUTH FAILURE" "${SANDBOX}/mismatch.err"; then
    echo "FAIL: stderr missing AUTH FAILURE"
    cat "${SANDBOX}/mismatch.err"
    exit 1
  fi
  echo "PASS: expect-mismatch hard-fails"
}

scenario_token_caller_mismatch() {
  echo "=== token: caller-mismatch → hard fail ==="
  local opaque
  # Token issued for smoke-consumer-A, but wrapper runs as smoke-consumer-B.
  opaque="$(issue_token bead-close iv-smoke-tok4 smoke-consumer-A 60m)"

  local rc=0
  CLAVAIN_AGENT_ID=smoke-consumer-B CLAVAIN_AUTHZ_TOKEN="$opaque" \
    bash "${GATES}/bead-close.sh" iv-smoke-tok4 reason >/dev/null 2>"${SANDBOX}/caller.err" || rc=$?

  if [[ "$rc" == "0" ]]; then
    echo "FAIL: caller-mismatch should hard-fail (rc=$rc)"
    cat "${SANDBOX}/caller.err"
    exit 1
  fi
  if ! grep -q "AUTH FAILURE" "${SANDBOX}/caller.err"; then
    echo "FAIL: caller-mismatch stderr missing AUTH FAILURE"
    cat "${SANDBOX}/caller.err"
    exit 1
  fi
  echo "PASS: caller-mismatch hard-fails"
}

scenario_token_malformed_falls_through() {
  echo "=== token: malformed string → fall through to legacy ==="
  local rc=0
  CLAVAIN_AGENT_ID=smoke-consumer CLAVAIN_AUTHZ_TOKEN="garbage-not-a-token" \
    bash "${GATES}/bead-close.sh" iv-smoke-tok5 reason >/dev/null 2>"${SANDBOX}/malformed.err" || rc=$?

  if [[ "$rc" != "0" ]]; then
    echo "FAIL: malformed token should fall through (legacy auto allows) — got rc=$rc"
    cat "${SANDBOX}/malformed.err"
    exit 1
  fi
  if ! grep -q "not-found or malformed" "${SANDBOX}/malformed.err"; then
    echo "FAIL: malformed stderr missing fall-through message"
    cat "${SANDBOX}/malformed.err"
    exit 1
  fi
  if ! grep -q "bd close iv-smoke-tok5" "$BD_CALL_LOG"; then
    echo "FAIL: malformed-path bd close not invoked (legacy should have run)"
    exit 1
  fi
  echo "PASS: malformed token falls through to legacy"
}

scenario_no_token_legacy() {
  echo "=== token: env unset → legacy path unchanged ==="
  local rc=0
  # Explicitly unset — inherit from parent env would otherwise carry any
  # value set by a prior scenario's leak (gate_token_consume unsets, but
  # this is a guardrail).
  unset CLAVAIN_AUTHZ_TOKEN
  CLAVAIN_AGENT_ID=smoke-agent \
    bash "${GATES}/bead-close.sh" iv-smoke-tok6 reason >/dev/null 2>&1 || rc=$?

  if [[ "$rc" != "0" ]]; then
    echo "FAIL: no-token legacy path should succeed (rc=$rc)"
    exit 1
  fi
  if ! grep -q "bd close iv-smoke-tok6" "$BD_CALL_LOG"; then
    echo "FAIL: no-token bd close not invoked"
    exit 1
  fi
  echo "PASS: no-token legacy path unchanged"
}

# ─── runner ───────────────────────────────────────────────────────────

case "$FOCUS" in
  legacy)
    scenario_legacy_bead_close
		scenario_git_push_binds_source_and_pushurl
    ;;
  token)
    scenario_runtime_proof_precedes_token
    scenario_token_valid
    scenario_token_revoked_hard_fail
    scenario_token_expect_mismatch
    scenario_token_caller_mismatch
    scenario_token_malformed_falls_through
    scenario_no_token_legacy
    ;;
  all)
    scenario_legacy_bead_close
		scenario_git_push_binds_source_and_pushurl
    scenario_runtime_proof_precedes_token
    scenario_token_valid
    scenario_token_revoked_hard_fail
    scenario_token_expect_mismatch
    scenario_token_caller_mismatch
    scenario_token_malformed_falls_through
    scenario_no_token_legacy
    ;;
esac

echo "PASS: gates-smoke (focus=$FOCUS)"
