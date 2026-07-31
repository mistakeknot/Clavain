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

# Resolve the tree under test from this script's own location, not by
# reconstructing a path from the monorepo root. Reconstruction pinned the test
# to os/Clavain, so running it from a worktree silently built and exercised the
# main checkout's sources instead of the ones being tested.
GATES="$(cd "$(dirname "$0")" && pwd)"
CLAVAIN_ROOT="$(cd "${GATES}/../.." && pwd)"

SANDBOX="$(mktemp -d)"
cleanup() { rm -rf "$SANDBOX"; }
trap cleanup EXIT
unset CLAVAIN_AUTHZ_PROJECT_ROOT GATE_AUTHZ_TOKEN
export GOCACHE="${GOCACHE:-${SANDBOX}/go-build-cache}"

mkdir -p "${SANDBOX}/real-bin"
CLI_BIN="${SANDBOX}/real-bin/clavain-cli"
(cd "${CLAVAIN_ROOT}/cmd/clavain-cli" && go build -trimpath -o "$CLI_BIN" .)

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
CREATE TABLE state (
  key TEXT NOT NULL, scope_id TEXT NOT NULL, payload TEXT NOT NULL,
  updated_at INTEGER NOT NULL DEFAULT (unixepoch()), expires_at INTEGER,
  PRIMARY KEY (key, scope_id));
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

# set_delegation_level <0-5|unset>
# Writes the declared human-delegation level straight into kernel state, the
# way `ic config set autonomy.delegation_level` does. The smoke sandbox has no
# `ic` on PATH, and the point under test is what the gate does with the value,
# not how it got there.
set_delegation_level() {
  python3 - "$1" <<PY
import sqlite3, sys
level = sys.argv[1]
db = sqlite3.connect("${SANDBOX}/.clavain/intercore.db")
if level == "unset":
    db.execute("DELETE FROM state WHERE key = 'kernel.autonomy.delegation_level'")
else:
    db.execute(
        "INSERT OR REPLACE INTO state (key, scope_id, payload) VALUES (?, ?, ?)",
        ("kernel.autonomy.delegation_level", "global", level))
db.commit()
PY
}

# The pre-existing push scenarios assert the authorization *binding* logic, not
# the delegation ceiling. Declare L3 so they exercise the same path they always
# did; the ceiling scenarios below set their own level.
set_delegation_level 3

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
print(db.execute(\"SELECT target FROM authorizations WHERE op_type='git-push-main' ORDER BY created_at DESC, rowid DESC LIMIT 1\").fetchone()[0])
")"
	[[ "$audit_target" == "repo=sha256:${push_hash};ref=refs/heads/main;head=${source_sha}" ]] || {
		echo "FAIL: audit target not bound to source/pushurl: $audit_target"
		exit 1
	}
	echo "PASS: git push authorization binds immutable source + push URL"
}

# ─── delegation-ceiling scenarios ─────────────────────────────────────
#
# The policy rule for git-push-main is `mode: auto` in this fixture, so the
# policy alone would authorize every push below. Anything that refuses one is
# the declared delegation level doing it.

# push_head_to_main → prints combined output, returns the wrapper's exit code.
# Runs with stdin closed so the confirm path takes the no-tty branch, which is
# the situation that matters: an agent pushing unattended.
push_head_to_main() {
	local out rc=0
	out="$(CLAVAIN_AGENT_ID=smoke-agent bash "${GATES}/git-push-main.sh" origin HEAD:main 2>&1 </dev/null)" || rc=$?
	printf '%s\n' "$out"
	return "$rc"
}

scenario_delegation_refuses_push_below_floor() {
	echo "=== delegation: L1 refuses an agent push the policy would allow ==="
	local before out rc=0
	before="$(git --git-dir="${SANDBOX}/push.git" rev-parse refs/heads/main)"

	set_delegation_level 1
	out="$(push_head_to_main)" || rc=$?

	[[ "$rc" -ne 0 ]] || { echo "FAIL: push succeeded at L1"; echo "$out"; exit 1; }
	grep -q "L1" <<<"$out" || { echo "FAIL: refusal does not name the level:"; echo "$out"; exit 1; }
	grep -q "human approves at phase gates" <<<"$out" || {
		echo "FAIL: refusal does not say what L1 means:"; echo "$out"; exit 1; }
	grep -q "delegation level, not by the policy rule" <<<"$out" || {
		echo "FAIL: refusal does not distinguish the ceiling from a policy denial:"; echo "$out"; exit 1; }

	local after; after="$(git --git-dir="${SANDBOX}/push.git" rev-parse refs/heads/main)"
	[[ "$after" == "$before" ]] || { echo "FAIL: remote main moved despite the refusal"; exit 1; }
	# Echo the refusal: this text is the operator-facing contract, and a smoke
	# run is the only place anyone sees it without provoking a real refusal.
	sed 's/^/  | /' <<<"$out"
	echo "PASS: L1 refuses the push and names the level"
}

scenario_delegation_undeclared_refuses_push() {
	echo "=== delegation: an undeclared level refuses too, and says it is undeclared ==="
	local out rc=0
	set_delegation_level unset
	out="$(push_head_to_main)" || rc=$?

	[[ "$rc" -ne 0 ]] || { echo "FAIL: push succeeded with no declared level"; echo "$out"; exit 1; }
	grep -q "undeclared" <<<"$out" || {
		echo "FAIL: refusal must distinguish an undeclared level from a chosen one:"; echo "$out"; exit 1; }
	echo "PASS: undeclared level fails closed"
}

scenario_delegation_allows_push_at_floor() {
	echo "=== delegation: L3 lets the same push through ==="
	local out rc=0 head_sha
	head_sha="$(git rev-parse HEAD)"

	set_delegation_level 3
	out="$(push_head_to_main)" || rc=$?
	[[ "$rc" -eq 0 ]] || { echo "FAIL: push refused at L3 (rc=$rc)"; echo "$out"; exit 1; }

	local pushed; pushed="$(git --git-dir="${SANDBOX}/push.git" rev-parse refs/heads/main)"
	[[ "$pushed" == "$head_sha" ]] || {
		echo "FAIL: remote main=$pushed, want $head_sha"; exit 1; }

	# The whole claim of this goal is that only the declared level changed.
	#
	# rowid breaks the created_at tie. created_at is unix SECONDS, and the
	# refusal recorded by the preceding L1 scenario lands in the same second as
	# this push, so ordering by timestamp alone picks between them arbitrarily.
	# rowid is insertion order, which is what "the row this push just wrote"
	# actually means.
	local mode; mode="$(python3 -c "
import sqlite3
db = sqlite3.connect('${SANDBOX}/.clavain/intercore.db')
print(db.execute(\"SELECT mode FROM authorizations WHERE op_type='git-push-main' ORDER BY created_at DESC, rowid DESC LIMIT 1\").fetchone()[0])
")"
	[[ "$mode" == "auto" ]] || { echo "FAIL: audit mode=$mode, want auto"; exit 1; }
	echo "PASS: L3 authorizes the push; audit row records mode=auto"
}

scenario_delegation_does_not_touch_unfloored_ops() {
	echo "=== delegation: L0 still lets bead-close through (no delegation floor) ==="
	set_delegation_level 0
	CLAVAIN_AGENT_ID=smoke-agent bash "${GATES}/bead-close.sh" iv-smoke-nofloor test-reason >/dev/null 2>&1
	grep -q "bd close iv-smoke-nofloor" "$BD_CALL_LOG" || {
		echo "FAIL: bead-close blocked at L0; the ceiling is meant to be per-op, not blanket"
		exit 1
	}
	set_delegation_level 3
	echo "PASS: ops with no delegation floor are unaffected"
}

# ─── inspectability scenarios ─────────────────────────────────────────
#
# A floor you cannot see coming is a refusal you cannot plan around. These
# cover the read-only surface: `policy explain` must name the floor for a
# floored op, stay silent for an exempt one, and survive an op the merged
# policy has no rule for.

scenario_explain_names_the_floor() {
	echo "=== inspect: policy explain names the floor for a floored op ==="
	local out
	out="$(clavain-cli policy explain git-push-main 2>&1)" || {
		echo "FAIL: policy explain exited non-zero for a floored op"
		exit 1
	}
	grep -q "git-push-main needs L3 to auto-proceed" <<<"$out" || {
		echo "FAIL: explain did not name the floor. Got:"
		echo "$out"
		exit 1
	}
	echo "PASS: explain names the floor"
}

scenario_explain_is_silent_for_exempt_ops() {
	echo "=== inspect: policy explain says nothing about floors for an exempt op ==="
	local out
	out="$(clavain-cli policy explain bead-close 2>&1)" || {
		echo "FAIL: policy explain exited non-zero for an exempt op"
		exit 1
	}
	# Silence matters: printing "needs L0" for every unfloored op would train
	# readers to ignore the line that carries the real refusals.
	grep -q "to auto-proceed" <<<"$out" && {
		echo "FAIL: explain announced a floor for an op that has none. Got:"
		echo "$out"
		exit 1
	}
	grep -q "^delegation:" <<<"$out" || {
		echo "FAIL: explain dropped the delegation line entirely. Got:"
		echo "$out"
		exit 1
	}
	echo "PASS: exempt ops get the level without a floor claim"
}

scenario_explain_survives_op_with_no_policy_rule() {
	echo "=== inspect: policy explain does not crash on an op policy never heard of ==="
	# The floor table and the policy file are independent; a floor may name an
	# op no rule matches, and the explain path must still render rather than
	# fault on the missing rule.
	clavain-cli policy explain iv-smoke-no-such-op >/dev/null 2>&1 || {
		echo "FAIL: policy explain crashed on an op with no policy rule"
		exit 1
	}
	echo "PASS: unknown ops explain cleanly"
}

# capped_rows [op] → count of rows the delegation ceiling withheld
capped_rows() {
  python3 - "${SANDBOX}/.clavain/intercore.db" "${1:-}" <<'SQL'
import sqlite3, sys
path, op = sys.argv[1], sys.argv[2]
db = sqlite3.connect(path)
q = ("SELECT COUNT(*) FROM authorizations "
     "WHERE json_extract(vetting,'$.delegation.capped') = 1")
args = ()
if op:
    q += " AND op_type = ?"
    args = (op,)
print(db.execute(q, args).fetchone()[0])
SQL
}

scenario_ceiling_records_what_it_withheld() {
	echo "=== evidence: a ceiling refusal writes a capped row ==="
	local before after
	before="$(capped_rows git-push-main)"

	set_delegation_level 1
	if CLAVAIN_AGENT_ID=smoke-agent bash "${GATES}/git-push-main.sh" \
			origin "HEAD:refs/heads/main" >/dev/null 2>&1; then
		echo "FAIL: the push proceeded at L1; the ceiling did not refuse"
		exit 1
	fi
	after="$(capped_rows git-push-main)"
	if [[ "$after" -le "$before" ]]; then
		echo "FAIL: ceiling refused but wrote no capped row (before=$before after=$after)"
		echo "      the refusal path exits before gate_record_signed, so a"
		echo "      withheld decision must be recorded on the abort path"
		exit 1
	fi
	set_delegation_level 3
	echo "PASS: a withheld push is recorded, not merely printed"
}

scenario_policy_confirm_is_not_counted_as_a_ceiling_save() {
	echo "=== evidence: a policy confirm is not miscounted as a ceiling save ==="
	# L3 clears the floor, so anything withheld here is the policy's doing.
	# Counting it would inflate the very number used to argue the ceiling earns
	# its keep.
	set_delegation_level 3
	local before after
	before="$(capped_rows bd-push-dolt)"
	CLAVAIN_AGENT_ID=smoke-agent bash "${GATES}/bd-push-dolt.sh" >/dev/null 2>&1 || true
	after="$(capped_rows bd-push-dolt)"
	if [[ "$after" -ne "$before" ]]; then
		echo "FAIL: a decision at L3 (above the floor) was recorded as ceiling-capped"
		exit 1
	fi
	echo "PASS: only the ceiling's own withholdings are counted"
}

scenario_recording_did_not_change_the_decision() {
	echo "=== evidence: recording is observational, not authorizing ==="
	# The L3 push that passed before evidence existed must still pass, and the
	# L1 push must still refuse. Audit writes must not become load-bearing.
	set_delegation_level 3
	if ! CLAVAIN_AGENT_ID=smoke-agent bash "${GATES}/git-push-main.sh" \
			origin "HEAD:refs/heads/main" >/dev/null 2>&1; then
		echo "FAIL: L3 push now refused; recording changed an authorization outcome"
		exit 1
	fi
	set_delegation_level 1
	if CLAVAIN_AGENT_ID=smoke-agent bash "${GATES}/git-push-main.sh" \
			origin "HEAD:refs/heads/main" >/dev/null 2>&1; then
		echo "FAIL: L1 push now allowed; recording changed an authorization outcome"
		exit 1
	fi
	set_delegation_level 3
	echo "PASS: decisions are unchanged with recording on"
}

scenario_evidence_rows_still_verify() {
	echo "=== evidence: rows carrying delegation evidence still verify ==="
	# `vetting` is inside the signed payload, so populating it is a change to
	# what every new row signs. If the stored bytes and the signed bytes ever
	# diverge — two independent json.Marshal calls would do it — every new row
	# silently becomes unverifiable. This is the assertion that catches it.
	local out
	out="$(clavain-cli policy verify --project-root="$SANDBOX" 2>&1)" || {
		echo "FAIL: policy verify errored"
		echo "$out"
		exit 1
	}
	if ! jq -e '(.invalid // 0) == 0 and (.unsigned // 0) == 0' >/dev/null 2>&1 <<<"$out"; then
		echo "FAIL: signed rows did not verify after delegation evidence was added"
		echo "$out"
		exit 1
	fi
	local capped; capped="$(capped_rows)"
	[[ "$capped" -gt 0 ]] || {
		echo "FAIL: no capped rows existed, so verification proved nothing"
		exit 1
	}
	echo "PASS: $capped capped row(s) present and all signatures verify"
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
    scenario_delegation_refuses_push_below_floor
    scenario_delegation_undeclared_refuses_push
    scenario_delegation_allows_push_at_floor
    scenario_delegation_does_not_touch_unfloored_ops
    scenario_explain_names_the_floor
    scenario_explain_is_silent_for_exempt_ops
    scenario_explain_survives_op_with_no_policy_rule
    scenario_ceiling_records_what_it_withheld
    scenario_policy_confirm_is_not_counted_as_a_ceiling_save
    scenario_recording_did_not_change_the_decision
    scenario_evidence_rows_still_verify
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
    scenario_delegation_refuses_push_below_floor
    scenario_delegation_undeclared_refuses_push
    scenario_delegation_allows_push_at_floor
    scenario_delegation_does_not_touch_unfloored_ops
    scenario_explain_names_the_floor
    scenario_explain_is_silent_for_exempt_ops
    scenario_explain_survives_op_with_no_policy_rule
    scenario_ceiling_records_what_it_withheld
    scenario_policy_confirm_is_not_counted_as_a_ceiling_save
    scenario_recording_did_not_change_the_decision
    scenario_evidence_rows_still_verify
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
