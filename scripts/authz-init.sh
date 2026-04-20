#!/usr/bin/env bash
# authz-init.sh — idempotent bootstrap for Clavain auto-proceed authz v1.5.
#
# Runs 4 steps, each safe to re-run:
#   1. Migrate the per-project intercore DB to the current schema (adds
#      signing columns + cutover marker if missing).
#   2. Install the global policy YAML at ~/.clavain/policy.yaml if absent.
#   3. Generate the project signing keypair at .clavain/keys/authz-project.*
#      if absent. NEVER overwrites an existing key.
#   4. Sign the cutover marker + any unsigned post-cutover rows.
#   5. Sanity-check with `policy audit --verify --json`.
#
# Run from a project root (directory containing .clavain/ or where you want
# .clavain/ created).
#
# Usage: bash os/Clavain/scripts/authz-init.sh [--project-root=<path>]
#        [--policy-example=<path>]

set -euo pipefail

PROJECT_ROOT=""
POLICY_EXAMPLE=""
for arg in "$@"; do
  case "$arg" in
    --project-root=*)   PROJECT_ROOT="${arg#*=}" ;;
    --policy-example=*) POLICY_EXAMPLE="${arg#*=}" ;;
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
    cp "$POLICY_EXAMPLE" "$GLOBAL_POLICY"
    log "installed global policy: $GLOBAL_POLICY"
  fi
else
  log "global policy already present: $GLOBAL_POLICY"
fi

# 3. Init signing key (never overwrites).
KEY_FILE="${PROJECT_ROOT}/.clavain/keys/authz-project.key"
if [[ -f "$KEY_FILE" ]]; then
  log "signing key already present: $KEY_FILE"
else
  log "generating project signing key"
  clavain-cli policy init-key >/dev/null
fi

# 4. Sign cutover marker + any unsigned post-cutover rows.
log "signing unsigned post-cutover rows (covers migration marker)"
if ! clavain-cli policy sign >/dev/null 2>&1; then
  log "WARN: policy sign failed; unsigned rows will remain"
fi

# 5. Sanity check.
log "verifying audit integrity"
if clavain-cli policy audit --verify --json >/tmp/authz-init-verify.json 2>&1; then
  log "policy audit --verify: OK"
else
  log "WARN: policy audit --verify reported failures; details:"
  cat /tmp/authz-init-verify.json >&2 || true
  exit 1
fi

# Emit a one-line summary for wrappers/scripts that parse authz-init output.
if command -v jq >/dev/null 2>&1; then
  summary="$(jq -c '.summary' /tmp/authz-init-verify.json 2>/dev/null || echo '{}')"
  log "summary: ${summary}"
fi
rm -f /tmp/authz-init-verify.json

log "done"
