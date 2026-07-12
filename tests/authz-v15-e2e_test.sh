#!/usr/bin/env bash
# End-to-end test for the auto-proceed authz v1.5 stack.
#
# Covers:
#   1. Fresh sandbox bootstrap via authz-init.sh (migrate → policy → key →
#      sign marker → verify). Assert exit 0 + 0 failed rows.
#   2. Gate wrapper (bead-close) runs, produces a signed audit row. Assert
#      signature length = 64 and `policy audit --verify` exits 0.
#   3. Bootstrap cannot sign an injected sig_version=1 row, and direct-SQL
#      downgrade/tampering flips verification even through display filters.
#   4. `policy rotate-key` refuses to invalidate signed history; the active
#      fingerprint remains unchanged and the retained ledger still verifies.
#
# Scenarios 4-6 from the plan (ic-publish freshness / marker fallback) are
# covered by Go tests in internal/publish/approval_test.go — the shell
# path only tests what uniquely requires shell execution.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../../.." && pwd)"
CLAVAIN_ROOT="${ROOT}/os/Clavain"
SANDBOX="$(mktemp -d)"
cleanup() { rm -rf "$SANDBOX"; }
trap cleanup EXIT
unset CLAVAIN_AUTHZ_PROJECT_ROOT GATE_AUTHZ_TOKEN
export GOCACHE="${SANDBOX}/go-build-cache"


mkdir -p "${SANDBOX}/real-bin"
CLI_BIN="${SANDBOX}/real-bin/clavain-cli"
IC_BIN="${SANDBOX}/real-bin/ic"
(cd "${CLAVAIN_ROOT}/cmd/clavain-cli" && PATH="/usr/local/go/bin:$PATH" GOTOOLCHAIN=local go build -o "$CLI_BIN" .)
(cd "${ROOT}/core/intercore" && PATH="/usr/local/go/bin:$PATH" GOTOOLCHAIN=local go build -o "$IC_BIN" ./cmd/ic)

STUB_BIN="${SANDBOX}/bin"
mkdir -p "$STUB_BIN"
cat > "${STUB_BIN}/bd" <<'STUB'
#!/usr/bin/env bash
if [[ "${1:-}" == "show" ]]; then
  printf '[{"id":"%s","labels":[]}]\n' "${2:-unknown}"
  exit 0
fi
printf 'bd %s\n' "$*" >> "$BD_CALL_LOG"
STUB
cat > "${STUB_BIN}/clavain-cli" <<STUB
#!/usr/bin/env bash
exec "${CLI_BIN}" "\$@"
STUB
cat > "${STUB_BIN}/ic" <<STUB
#!/usr/bin/env bash
exec "${IC_BIN}" "\$@"
STUB
chmod +x "${STUB_BIN}/bd" "${STUB_BIN}/clavain-cli" "${STUB_BIN}/ic"

export PATH="${STUB_BIN}:${PATH}"
export BD_CALL_LOG="${SANDBOX}/bd-calls.log"
: > "$BD_CALL_LOG"
export HOME="${SANDBOX}/fakehome"
mkdir -p "$HOME"

# v2-behavior assertion: this test covers the v1.5 legacy path. With v2
# rolled in, $CLAVAIN_AUTHZ_TOKEN MUST be empty so gate_token_consume
# returns immediately and the legacy gate_check path runs. If it's set by
# the caller's environment we explicitly clear it — any regression where
# v1.5 silently stops working with tokens absent would fail scenario 2.
unset CLAVAIN_AUTHZ_TOKEN

cd "$SANDBOX"

# ─── Scenario 1: bootstrap ────────────────────────────────────────────
bash "${CLAVAIN_ROOT}/scripts/authz-init.sh" >/dev/null 2>&1 || {
  echo "FAIL scenario 1: authz-init.sh bootstrap did not complete"
  bash "${CLAVAIN_ROOT}/scripts/authz-init.sh"
  exit 1
}
if [[ ! -f "${SANDBOX}/.clavain/keys/authz-project.key" ]]; then
  echo "FAIL scenario 1: signing key not created"
  exit 1
fi
if [[ ! -f "${SANDBOX}/.clavain/keys/authz-legacy-manifest.json" ]]; then
  echo "FAIL scenario 1: signed empty legacy manifest not created"
  exit 1
fi
if [[ "$(uname -s)" == "Darwin" ]]; then
  perms="$(stat -f '%Lp' "${SANDBOX}/.clavain/keys/authz-project.key")"
else
  perms="$(stat -c '%a' "${SANDBOX}/.clavain/keys/authz-project.key")"
fi
[[ "$perms" == "400" ]] || { echo "FAIL scenario 1: key perms=$perms, want 400"; exit 1; }
clavain-cli policy audit --verify >/dev/null 2>&1 || {
  echo "FAIL scenario 1: audit --verify did not pass after bootstrap"
  exit 1
}
echo "PASS scenario 1: bootstrap (authz-init.sh) — key 0400, marker signed, verify OK"

# Explicit --project-root must outrank an ambient root for every init step.
EXPLICIT_ROOT="${SANDBOX}/explicit-root"
mkdir -p "$EXPLICIT_ROOT"
CLAVAIN_AUTHZ_PROJECT_ROOT="$SANDBOX" \
  bash "${CLAVAIN_ROOT}/scripts/authz-init.sh" --project-root="$EXPLICIT_ROOT" >/dev/null
[[ -f "$EXPLICIT_ROOT/.clavain/intercore.db" ]] || { echo "FAIL scenario 1a: explicit DB missing"; exit 1; }
[[ -f "$EXPLICIT_ROOT/.clavain/keys/authz-project.key" ]] || { echo "FAIL scenario 1a: explicit key missing"; exit 1; }
clavain-cli policy doctor --project-root="$EXPLICIT_ROOT" --require-signer >/dev/null \
  || { echo "FAIL scenario 1a: explicit signer doctor failed"; exit 1; }
echo "PASS scenario 1a: explicit project root outranks ambient root"

# An existing signer with unsafe private-key permissions must fail bootstrap
# even when every current authorization row is already signed.
chmod 0600 "$EXPLICIT_ROOT/.clavain/keys/authz-project.key"
if bash "${CLAVAIN_ROOT}/scripts/authz-init.sh" --project-root="$EXPLICIT_ROOT" >/dev/null 2>&1; then
  echo "FAIL scenario 1b: authz-init accepted unsafe signer permissions"
  exit 1
fi
chmod 0400 "$EXPLICIT_ROOT/.clavain/keys/authz-project.key"
echo "PASS scenario 1b: existing signer requires a healthy doctor preflight"

# A checkout containing only the tracked public key is verifier-only and must
# never mint or overwrite a private identity.
VERIFIER_ROOT="${SANDBOX}/verifier-root"
mkdir -p "$VERIFIER_ROOT/.clavain/keys"
cp -f "$SANDBOX/.clavain/keys/authz-project.pub" "$VERIFIER_ROOT/.clavain/keys/authz-project.pub"
cp -f "$SANDBOX/.clavain/keys/authz-legacy-manifest.json" "$VERIFIER_ROOT/.clavain/keys/authz-legacy-manifest.json"
cp -f "$SANDBOX/.clavain/intercore.db" "$VERIFIER_ROOT/.clavain/intercore.db"
bash "${CLAVAIN_ROOT}/scripts/authz-init.sh" --project-root="$VERIFIER_ROOT" >/dev/null
[[ ! -e "$VERIFIER_ROOT/.clavain/keys/authz-project.key" ]] \
  || { echo "FAIL scenario 1c: verifier checkout minted a private key"; exit 1; }
clavain-cli policy doctor --project-root="$VERIFIER_ROOT" >/dev/null \
  || { echo "FAIL scenario 1c: verifier doctor failed"; exit 1; }
echo "PASS scenario 1c: public-only checkout remains verifier-only"

# A nonempty legacy set must stop for explicit operator review. Bootstrap may
# create an empty anchor, but it must never snapshot existing vintage rows.
LEGACY_ROOT="${SANDBOX}/legacy-review-root"
mkdir -p "$LEGACY_ROOT"
(cd "$LEGACY_ROOT" && ic init --db=.clavain/intercore.db >/dev/null)
clavain-cli policy init-key --project-root="$LEGACY_ROOT" >/dev/null
clavain-cli policy sign --project-root="$LEGACY_ROOT" >/dev/null
python3 - <<PY
import sqlite3
db = sqlite3.connect("${LEGACY_ROOT}/.clavain/intercore.db")
db.execute("INSERT INTO authorizations (id,op_type,target,agent_id,mode,created_at,sig_version) VALUES ('review-required','bead-close','legacy','legacy-agent','auto',1,0)")
db.execute("PRAGMA user_version=35")
db.commit()
PY
if bash "${CLAVAIN_ROOT}/scripts/authz-init.sh" --project-root="$LEGACY_ROOT" >/dev/null 2>&1; then
  echo "FAIL scenario 1d: authz-init silently anchored nonempty legacy history"
  exit 1
fi
[[ ! -e "$LEGACY_ROOT/.clavain/keys/authz-legacy-manifest.json" ]] \
  || { echo "FAIL scenario 1d: bootstrap created an unreviewed manifest"; exit 1; }
legacy_schema="$(python3 -c "import sqlite3; db=sqlite3.connect('${LEGACY_ROOT}/.clavain/intercore.db'); print(db.execute('PRAGMA user_version').fetchone()[0])")"
[[ "$legacy_schema" == "35" ]] \
  || { echo "FAIL scenario 1d: refusal advanced schema to $legacy_schema, want 35"; exit 1; }
echo "PASS scenario 1d: nonempty legacy history requires operator review"

# A schema-35 public-only verifier cannot create the manifest and must receive
# the canonical schema-36 snapshot plus signed artifact from the signer.
LEGACY_VERIFIER_ROOT="${SANDBOX}/legacy-verifier-root"
mkdir -p "$LEGACY_VERIFIER_ROOT/.clavain/keys"
cp -f "$LEGACY_ROOT/.clavain/keys/authz-project.pub" "$LEGACY_VERIFIER_ROOT/.clavain/keys/authz-project.pub"
cp -f "$LEGACY_ROOT/.clavain/intercore.db" "$LEGACY_VERIFIER_ROOT/.clavain/intercore.db"
if bash "${CLAVAIN_ROOT}/scripts/authz-init.sh" --project-root="$LEGACY_VERIFIER_ROOT" >/dev/null 2>&1; then
  echo "FAIL scenario 1e: schema-35 verifier bootstrap should require canonical signer artifacts"
  exit 1
fi
verifier_schema="$(python3 -c "import sqlite3; db=sqlite3.connect('${LEGACY_VERIFIER_ROOT}/.clavain/intercore.db'); print(db.execute('PRAGMA user_version').fetchone()[0])")"
[[ "$verifier_schema" == "35" ]] \
  || { echo "FAIL scenario 1e: verifier refusal advanced schema to $verifier_schema, want 35"; exit 1; }
[[ ! -e "$LEGACY_VERIFIER_ROOT/.clavain/keys/authz-project.key" ]] \
  || { echo "FAIL scenario 1e: verifier minted a private key"; exit 1; }
echo "PASS scenario 1e: schema-35 verifier remains unchanged"

# authz-init installed the full production policy globally (with strict
# `requires` on bead-close — including vetted_sha_matches_head). Init a
# throwaway git repo so there's a real HEAD SHA to match against.
git init -q
git config user.email "v15-e2e@example.com"
git config user.name "v15-e2e"
git config commit.gpgsign false
touch marker
git add marker
git commit -q -m "init"
HEAD_SHA="$(git rev-parse HEAD)"

export CLAVAIN_AGENT_ID=v15-e2e
export CLAVAIN_VETTED_AT="$(date +%s)"
export CLAVAIN_VETTED_SHA="$HEAD_SHA"
export CLAVAIN_TESTS_PASSED=1
export CLAVAIN_SPRINT_OR_WORK=1

# ─── Scenario 2: gate wrapper produces signed row ─────────────────────
bash "${CLAVAIN_ROOT}/scripts/gates/bead-close.sh" iv-v15-1 shipped
grep -q "bd close iv-v15-1" "$BD_CALL_LOG" || {
  echo "FAIL scenario 2: bd close not invoked"
  exit 1
}
sig_len="$(python3 -c "
import sqlite3
db = sqlite3.connect('${SANDBOX}/.clavain/intercore.db')
r = db.execute(\"SELECT length(signature) FROM authorizations WHERE op_type='bead-close'\").fetchone()
print(r[0] if r and r[0] is not None else 0)
")"
[[ "$sig_len" == "64" ]] || { echo "FAIL scenario 2: signature length=$sig_len, want 64"; exit 1; }
clavain-cli policy audit --verify >/dev/null 2>&1 || {
  echo "FAIL scenario 2: verify failed after legitimate gate run"
  exit 1
}
echo "PASS scenario 2: gate wrapper → signed row → verify OK"

# Rerunning bootstrap against an established anchor must inspect before any
# mutation. An injected unsigned sig_version=1 row is evidence of corruption,
# never backlog for the bootstrap signer.
python3 - <<PY
import sqlite3
db = sqlite3.connect("${SANDBOX}/.clavain/intercore.db")
db.execute("INSERT INTO authorizations (id,op_type,target,agent_id,mode,created_at,sig_version) VALUES ('bootstrap-signing-oracle','bead-close','injected','attacker','auto',2,1)")
db.commit()
PY
if bash "${CLAVAIN_ROOT}/scripts/authz-init.sh" --project-root="$SANDBOX" >/dev/null 2>&1; then
  echo "FAIL scenario 2a: bootstrap signed an injected post-anchor row"
  exit 1
fi
injected_sig_state="$(python3 -c "import sqlite3; db=sqlite3.connect('${SANDBOX}/.clavain/intercore.db'); r=db.execute(\"SELECT signature,signed_at FROM authorizations WHERE id='bootstrap-signing-oracle'\").fetchone(); print('null' if r == (None, None) else 'mutated')")"
[[ "$injected_sig_state" == "null" ]] \
  || { echo "FAIL scenario 2a: bootstrap mutated injected signing fields"; exit 1; }
python3 - <<PY
import sqlite3
db = sqlite3.connect("${SANDBOX}/.clavain/intercore.db")
db.execute("DELETE FROM authorizations WHERE id='bootstrap-signing-oracle'")
db.commit()
PY
clavain-cli policy audit --verify >/dev/null 2>&1 \
  || { echo "FAIL scenario 2a: cleanup did not restore verification"; exit 1; }
echo "PASS scenario 2a: bootstrap refuses injected sig_version=1 history"

# ─── Scenario 2b: sig_version downgrade is globally rejected ──────────
python3 - <<PY
import sqlite3
db = sqlite3.connect("${SANDBOX}/.clavain/intercore.db")
db.execute("UPDATE authorizations SET sig_version=0 WHERE op_type='bead-close'")
db.commit()
PY
if clavain-cli policy audit --verify --op=git-push-main >/dev/null 2>&1; then
  echo "FAIL scenario 2b: filtered audit accepted a signed row downgraded to sig_version=0"
  exit 1
fi
python3 - <<PY
import sqlite3
db = sqlite3.connect("${SANDBOX}/.clavain/intercore.db")
db.execute("UPDATE authorizations SET sig_version=1 WHERE op_type='bead-close'")
db.commit()
PY
clavain-cli policy audit --verify >/dev/null 2>&1 \
  || { echo "FAIL scenario 2b: restoring sig_version did not restore verification"; exit 1; }
echo "PASS scenario 2b: filtered audit rejects sig_version downgrade"

# ─── Scenario 3: tamper detection ─────────────────────────────────────
python3 - <<PY
import sqlite3
db = sqlite3.connect("${SANDBOX}/.clavain/intercore.db")
db.execute("UPDATE authorizations SET policy_match='TAMPERED' WHERE op_type='bead-close'")
db.commit()
PY

verify_json="$(clavain-cli policy audit --verify 2>&1 || true)"
if clavain-cli policy audit --verify >/dev/null 2>&1; then
  echo "FAIL scenario 3: verify unexpectedly passed after tampering"
  echo "$verify_json"
  exit 1
fi
if ! grep -q '"valid":false' <<<"$verify_json"; then
  echo "FAIL scenario 3: tampered row not flagged invalid in report"
  echo "$verify_json"
  exit 1
fi
if ! grep -q '"signature invalid' <<<"$verify_json"; then
  echo "FAIL scenario 3: verify reason did not cite signature invalidity"
  echo "$verify_json"
  exit 1
fi
echo "PASS scenario 3: direct-SQL tamper detected by verify"

# Un-tamper for downstream scenarios.
python3 - <<PY
import sqlite3
db = sqlite3.connect("${SANDBOX}/.clavain/intercore.db")
db.execute("UPDATE authorizations SET policy_match='bead-close#0' WHERE op_type='bead-close'")
db.commit()
PY
# Re-sign the restored row so it verifies again.
python3 - <<PY
import sqlite3
db = sqlite3.connect("${SANDBOX}/.clavain/intercore.db")
db.execute("UPDATE authorizations SET signature=NULL, signed_at=NULL WHERE op_type='bead-close'")
db.commit()
PY
clavain-cli policy sign >/dev/null
clavain-cli policy audit --verify >/dev/null 2>&1 || {
  echo "FAIL scenario 3 post-cleanup: verify should pass after re-sign"
  exit 1
}

# ─── Scenario 4: rotate-key refuses signed history ─────────────────────
old_fp="$({ clavain-cli policy verify --json 2>/dev/null || true; } | python3 -c "
import json,sys
r = json.load(sys.stdin)
print(r.get('fingerprint',''))
")"
[[ -n "$old_fp" ]] || { echo "FAIL scenario 4: could not read current fingerprint"; exit 1; }

if clavain-cli policy rotate-key >/dev/null 2>&1; then
  echo "FAIL scenario 4: rotate-key should refuse signed history"
  exit 1
fi
new_fp="$({ clavain-cli policy verify --json 2>/dev/null || true; } | python3 -c "
import json,sys
r = json.load(sys.stdin)
print(r.get('fingerprint',''))
")"
[[ -n "$new_fp" && "$new_fp" == "$old_fp" ]] || {
  echo "FAIL scenario 4: fingerprint changed after refused rotation ($old_fp -> $new_fp)"
  exit 1
}
clavain-cli policy audit --verify >/dev/null 2>&1 || {
  echo "FAIL scenario 4: verify should still pass after refused rotation"
  exit 1
}
echo "PASS scenario 4: rotate-key refuses signed history without changing trust"

echo ""
echo "PASS: authz-v15-e2e (all 4 scenarios)"
