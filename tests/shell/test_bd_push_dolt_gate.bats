#!/usr/bin/env bats

setup() {
  unset CLAVAIN_AUTHZ_TOKEN GATE_AUTHZ_TOKEN
  export TEST_ROOT="$BATS_TEST_TMPDIR/root"
  export BIN_DIR="$BATS_TEST_TMPDIR/bin"
  export CALL_LOG="$BATS_TEST_TMPDIR/calls.log"
  export DB_DIR="$TEST_ROOT/.beads/dolt/Sylveste"
  mkdir -p "$TEST_ROOT/scripts/gates" "$BIN_DIR" "$DB_DIR"
  cp -f "$BATS_TEST_DIRNAME/../../scripts/gates/bd-push-dolt.sh" "$TEST_ROOT/scripts/gates/"
  cp -f "$BATS_TEST_DIRNAME/../../scripts/gates/_common.sh" "$TEST_ROOT/scripts/gates/"

  AUTHZ_REPO_ROOT="$(cd "$TEST_ROOT" && pwd -P)"
  export AUTHZ_REPO_ROOT
  export CLAVAIN_AUTHZ_PROJECT_ROOT="$AUTHZ_REPO_ROOT"
  export SIGNER_SCHEMA=38
  export SIGNER_ROLE=signer
  export SIGNER_DOCTOR_RC=0
  export POLICY_MODE=auto
  export POLICY_RC=0
  export RECORD_SIGNED_RC=0
  export PATH="$BIN_DIR:$PATH"
  export DOLT="$BIN_DIR/dolt"
  : >"$CALL_LOG"

  cat >"$BIN_DIR/clavain-cli" <<'EOF'
#!/usr/bin/env bash
printf 'clavain-cli:%s\n' "$*" >>"$CALL_LOG"
if [[ "$1 $2" == "policy doctor" ]]; then
  if [[ "$SIGNER_DOCTOR_RC" != "0" ]]; then
    printf 'policy doctor: signer required\n' >&2
    exit "$SIGNER_DOCTOR_RC"
  fi
  printf '{"status":"ok","role":"%s","schema":%s,"project_root":"%s","fingerprint":"0123456789abcdef","manifest_sha256":"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"}\n' \
    "$SIGNER_ROLE" "$SIGNER_SCHEMA" "$AUTHZ_REPO_ROOT"
  exit 0
fi
if [[ "$1 $2" == "policy check" ]]; then
  printf '{"schema":1,"mode":"%s","policy_hash":"hash-test","policy_match":"bd-push-dolt#0"}\n' "$POLICY_MODE"
  exit "$POLICY_RC"
fi
if [[ "$1 $2" == "policy record-signed" ]]; then
  if [[ "$RECORD_SIGNED_RC" != "0" ]]; then
    exit "$RECORD_SIGNED_RC"
  fi
  printf '{"status":"ok","id":"row-test","signed":1}\n'
  exit 0
fi
exit 97
EOF

  cat >"$BIN_DIR/dolt" <<'EOF'
#!/usr/bin/env bash
printf 'dolt:%s:%s\n' "$PWD" "$*" >>"$CALL_LOG"
printf 'pushed\n'
EOF
  chmod +x "$BIN_DIR/clavain-cli" "$BIN_DIR/dolt"
}

@test "schema 38 records a signed authorization before Dolt push" {
  run bash "$TEST_ROOT/scripts/gates/bd-push-dolt.sh" "$DB_DIR"

  [ "$status" -eq 0 ]
  [[ "$output" == *"bd-push-dolt: ok"* ]]
  [ "$(wc -l <"$CALL_LOG" | tr -d ' ')" -eq 4 ]
  sed -n '1p' "$CALL_LOG" | grep -Fq "clavain-cli:policy doctor --require-signer --project-root=$AUTHZ_REPO_ROOT"
  sed -n '2p' "$CALL_LOG" | grep -Fq "clavain-cli:policy check bd-push-dolt --project-root=$AUTHZ_REPO_ROOT --target=$DB_DIR"
  sed -n '3p' "$CALL_LOG" | grep -Fq "clavain-cli:policy record-signed --project-root=$AUTHZ_REPO_ROOT --op=bd-push-dolt --target=$DB_DIR"
  [ "$(sed -n '4p' "$CALL_LOG")" = "dolt:$DB_DIR:push origin main" ]
}

@test "unaudited future schema blocks before policy evaluation or Dolt push" {
  export SIGNER_SCHEMA=39

  run bash "$TEST_ROOT/scripts/gates/bd-push-dolt.sh" "$DB_DIR"

  [ "$status" -ne 0 ]
  [ "$(wc -l <"$CALL_LOG" | tr -d ' ')" -eq 1 ]
  grep -Fq 'clavain-cli:policy doctor ' "$CALL_LOG"
  [[ "$output" == *"malformed signer preflight response"* ]]
}

@test "missing signer blocks before policy evaluation or Dolt push" {
  export SIGNER_DOCTOR_RC=1

  run bash "$TEST_ROOT/scripts/gates/bd-push-dolt.sh" "$DB_DIR"

  [ "$status" -ne 0 ]
  [ "$(wc -l <"$CALL_LOG" | tr -d ' ')" -eq 1 ]
  grep -Fq 'clavain-cli:policy doctor ' "$CALL_LOG"
  [[ "$output" == *"signer preflight failed"* ]]
}

@test "blocked policy stops before signed recording or Dolt push" {
  export POLICY_MODE=block
  export POLICY_RC=2

  run bash "$TEST_ROOT/scripts/gates/bd-push-dolt.sh" "$DB_DIR"

  [ "$status" -ne 0 ]
  [ "$(wc -l <"$CALL_LOG" | tr -d ' ')" -eq 2 ]
  sed -n '1p' "$CALL_LOG" | grep -Fq 'clavain-cli:policy doctor '
  sed -n '2p' "$CALL_LOG" | grep -Fq 'clavain-cli:policy check bd-push-dolt '
  [[ "$output" == *"policy: bd-push-dolt blocked"* ]]
}
