#!/usr/bin/env bats

setup() {
  export TEST_ROOT="$BATS_TEST_TMPDIR/root"
  export BIN_DIR="$BATS_TEST_TMPDIR/bin"
  mkdir -p "$TEST_ROOT/scripts/gates" "$BIN_DIR"
  cp "$BATS_TEST_DIRNAME/../../scripts/gates/bead-close.sh" "$TEST_ROOT/scripts/gates/"
  cp "$BATS_TEST_DIRNAME/../../scripts/gates/_common.sh" "$TEST_ROOT/scripts/gates/"
  export PATH="$BIN_DIR:$PATH"

  cat >"$BIN_DIR/bd" <<'EOF'
#!/usr/bin/env bash
if [[ "$1" == "show" ]]; then
  printf '[{"id":"%s","labels":[%s]}]\n' "$2" "${BD_LABEL_JSON:-}"
  exit 0
fi
printf 'bd:%s\n' "$*" >>"${CALL_LOG}"
EOF
  chmod +x "$BIN_DIR/bd"

  cat >"$BIN_DIR/clavain-cli" <<'EOF'
#!/usr/bin/env bash
printf 'clavain-cli:%s\n' "$*" >>"${CALL_LOG}"
if [[ "$1 $2" == "calibration-streak verify" ]]; then
  exit "${VERIFY_RC:-0}"
fi
if [[ "$1 $2 $3" == "policy token consume" ]]; then
  exit 0
fi
if [[ "$1" == "policy-check" ]]; then
  printf '{"policy_hash":"h","policy_match":"m"}\n'
fi
EOF
  chmod +x "$BIN_DIR/clavain-cli"

  export CALL_LOG="$BATS_TEST_TMPDIR/calls"
  : >"$CALL_LOG"
}

@test "labeled close gate rejects before consuming authorization token" {
  export BD_LABEL_JSON='"close-gate:calibration-streak"'
  export VERIFY_RC=1
  export CLAVAIN_AUTHZ_TOKEN=secret-placeholder

  run bash "$TEST_ROOT/scripts/gates/bead-close.sh" proof-bead shipped

  [ "$status" -ne 0 ]
  grep -q '^clavain-cli:calibration-streak verify --target=10$' "$CALL_LOG"
  ! grep -q 'policy token consume' "$CALL_LOG"
  ! grep -q '^bd:close ' "$CALL_LOG"
}

@test "unlabeled bead follows existing authorization path without proof verification" {
  export BD_LABEL_JSON='"ordinary"'
  export CLAVAIN_AUTHZ_TOKEN=secret-placeholder

  run bash "$TEST_ROOT/scripts/gates/bead-close.sh" ordinary-bead shipped

  [ "$status" -eq 0 ]
  ! grep -q 'calibration-streak verify' "$CALL_LOG"
  grep -q 'policy token consume' "$CALL_LOG"
  grep -q '^bd:close ordinary-bead --reason=shipped$' "$CALL_LOG"
}
