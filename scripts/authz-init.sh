#!/usr/bin/env bash
# authz-init.sh — idempotent bootstrap for Clavain auto-proceed authz v1.5.
#
# Runs 6 steps, each safe to re-run:
#   1. Migrate the per-project intercore DB to the current schema (adds
#      signing columns + cutover marker if missing).
#   2. Install the global policy YAML at ~/.clavain/policy.yaml if absent.
#   3. Generate the project signing keypair at .clavain/keys/authz-project.*
#      if absent. NEVER overwrites an existing key.
#   4. Sign the cutover marker + any unsigned post-cutover rows.
#   5. Create an explicit empty legacy anchor for a fresh ledger. Nonempty
#      legacy history stops for operator review; it is never auto-anchored.
#   6. Sanity-check with `policy audit --verify --json`.
#
# Run from a project root (directory containing .clavain/ or where you want
# .clavain/ created).
#
# Usage: bash os/Clavain/scripts/authz-init.sh [--project-root=<path>]
#        [--policy-example=<path>]

set -euo pipefail

PROJECT_ROOT=""
POLICY_EXAMPLE=""
WITH_TOKEN_DEMO=0
for arg in "$@"; do
  case "$arg" in
    --project-root=*)   PROJECT_ROOT="${arg#*=}" ;;
    --policy-example=*) POLICY_EXAMPLE="${arg#*=}" ;;
    --with-token-demo)  WITH_TOKEN_DEMO=1 ;;
    -h|--help)
      sed -n '1,20p' "$0" | sed 's/^# \{0,1\}//'
      exit 0
      ;;
    *) echo "authz-init: unknown arg: $arg" >&2; exit 2 ;;
  esac
done

if [[ -z "$PROJECT_ROOT" ]]; then
  PROJECT_ROOT="$PWD"
fi
PROJECT_ROOT="$(cd "$PROJECT_ROOT" && pwd)"

# Default policy example location: this script's ../config/policy.yaml.example.
if [[ -z "$POLICY_EXAMPLE" ]]; then
  SELF_DIR="$(cd "$(dirname "$0")" && pwd)"
  POLICY_EXAMPLE="${SELF_DIR}/../config/policy.yaml.example"
fi

log() { printf '[authz-init] %s\n' "$*"; }

need() {
  command -v "$1" >/dev/null 2>&1 || { echo "authz-init: required binary not on PATH: $1" >&2; exit 1; }
}
need clavain-cli
need ic

mkdir -p "${PROJECT_ROOT}/.clavain"
cd "${PROJECT_ROOT}"

# 1. Migrate DB to the current schema (idempotent).
log "migrating .clavain/intercore.db to current schema"
ic init --db=.clavain/intercore.db >/dev/null

# 2. Install global policy if missing (never overwrites).
GLOBAL_POLICY="${HOME}/.clavain/policy.yaml"
if [[ ! -f "$GLOBAL_POLICY" ]]; then
  if [[ ! -f "$POLICY_EXAMPLE" ]]; then
    log "WARN: policy example not found at $POLICY_EXAMPLE; skipping global install"
  else
    mkdir -p "${HOME}/.clavain"
    cp -f "$POLICY_EXAMPLE" "$GLOBAL_POLICY"
    chmod 0644 "$GLOBAL_POLICY"
    log "installed global policy: $GLOBAL_POLICY"
  fi
else
  log "global policy already present: $GLOBAL_POLICY"
fi

# 3. Init signing key (never overwrites).
KEY_FILE="${PROJECT_ROOT}/.clavain/keys/authz-project.key"
PUB_FILE="${PROJECT_ROOT}/.clavain/keys/authz-project.pub"
IS_SIGNER=0
if [[ -f "$KEY_FILE" && -f "$PUB_FILE" ]]; then
  log "signing key already present: $KEY_FILE"
  IS_SIGNER=1
elif [[ -f "$KEY_FILE" ]]; then
  echo "authz-init: private key exists without the trusted public key: $KEY_FILE" >&2
  exit 1
elif [[ -f "$PUB_FILE" ]]; then
  log "public key present without private key; configuring verifier-only checkout"
else
  log "generating project signing key"
  clavain-cli policy init-key --project-root="$PROJECT_ROOT" >/dev/null
  IS_SIGNER=1
fi

# 4. Sign cutover marker + any unsigned post-cutover rows, then establish the
# schema-36 legacy anchor before doctor is allowed to report readiness.
MANIFEST_FILE="${PROJECT_ROOT}/.clavain/keys/authz-legacy-manifest.json"
if [[ "$IS_SIGNER" == "1" ]]; then
	log "signing unsigned post-cutover rows (covers migration marker)"
	clavain-cli policy sign --project-root="$PROJECT_ROOT" >/dev/null
	if [[ ! -f "$MANIFEST_FILE" ]]; then
		log "creating explicit empty legacy anchor for a fresh ledger"
		ANCHOR_ERROR="$(mktemp "${TMPDIR:-/tmp}/authz-init-anchor.XXXXXX")"
		if ! clavain-cli policy anchor-legacy --project-root="$PROJECT_ROOT" --expect-empty >/dev/null 2>"$ANCHOR_ERROR"; then
			log "ERROR: legacy authorization history requires operator review; no manifest was created"
			cat "$ANCHOR_ERROR" >&2 || true
			echo "Inspect the immutable proposal:" >&2
			echo "  clavain-cli policy anchor-legacy --inspect --project-root=\"$PROJECT_ROOT\"" >&2
			rm -f "$ANCHOR_ERROR"
			exit 1
		fi
		rm -f "$ANCHOR_ERROR"
	else
		log "legacy anchor already present: $MANIFEST_FILE"
	fi
	log "checking signer readiness"
	clavain-cli policy doctor --project-root="$PROJECT_ROOT" --require-signer >/dev/null
else
	log "checking verifier readiness"
	clavain-cli policy doctor --project-root="$PROJECT_ROOT" >/dev/null
	log "verifier-only checkout: skipping signing"
fi

# 6. Sanity check.
log "verifying audit integrity"
VERIFY_FILE="$(mktemp "${TMPDIR:-/tmp}/authz-init-verify.XXXXXX")"
trap 'rm -f "$VERIFY_FILE"' EXIT
if clavain-cli policy audit --verify --json --project-root="$PROJECT_ROOT" >"$VERIFY_FILE" 2>&1; then
  log "policy audit --verify: OK"
else
  log "WARN: policy audit --verify reported failures; details:"
  cat "$VERIFY_FILE" >&2 || true
  exit 1
fi

# Emit a one-line summary for wrappers/scripts that parse authz-init output.
if command -v jq >/dev/null 2>&1; then
  summary="$(jq -c '.summary' "$VERIFY_FILE" 2>/dev/null || echo '{}')"
  log "summary: ${summary}"
fi
rm -f "$VERIFY_FILE"
trap - EXIT

# Optional: issue a demo bead-close token to validate v2 end-to-end.
if [[ "$WITH_TOKEN_DEMO" == "1" ]]; then
  AGENT_ID="${CLAVAIN_AGENT_ID:-demo-agent}"
  TARGET="demo-$(date +%s)"
  if [[ "$IS_SIGNER" != "1" ]]; then
    log "WARN: verifier-only checkout cannot issue a demo token"
  elif TOKEN="$(CLAVAIN_AGENT_ID="$AGENT_ID" clavain-cli policy token issue --project-root="$PROJECT_ROOT" --op=bead-close --target="$TARGET" --for="$AGENT_ID" --ttl=5m 2>/tmp/authz-init-demo.err)"; then
    echo "Demo token issued: $TOKEN"
    echo "Use with (one-shot, preferred):"
    echo "  CLAVAIN_AUTHZ_TOKEN=$TOKEN bead-close some-bead-id"
    echo "Verify (no consume):"
    echo "  clavain-cli policy token verify --token=$TOKEN"
    echo "(Do NOT 'export' the token — keep it scoped to one command.)"
  else
    log "WARN: demo token issue failed:"
    cat /tmp/authz-init-demo.err >&2 || true
  fi
  rm -f /tmp/authz-init-demo.err
fi

log "done"
