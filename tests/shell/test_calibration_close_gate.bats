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
  exit "${CALIBRATION_VERIFY_RC:-0}"
fi
if [[ "$1 $2" == "runtime-evidence required" ]]; then
  printf '%s\n' "${RUNTIME_REQUIRED:-false}"
  exit "${RUNTIME_REQUIRED_RC:-0}"
fi
if [[ "$1 $2" == "runtime-evidence verify" ]]; then
  printf '%s\n' "${RUNTIME_SUMMARY:-}"
  exit "${RUNTIME_VERIFY_RC:-0}"
fi
if [[ "$1 $2 $3" == "policy token consume" ]]; then
  exit 0
fi
if [[ "$1" == "policy-check" ]]; then
  printf '{"policy_hash":"h","policy_match":"m"}\n'
fi
EOF
  chmod +x "$BIN_DIR/clavain-cli"

  cat >"$BIN_DIR/ic" <<'EOF'
#!/usr/bin/env bash
printf 'ic:%s\n' "$*" >>"${CALL_LOG}"
if [[ "$1 $2 $3" == "--json run status" ]]; then
  printf '{"id":"%s","status":"%s","phase":"%s"}\n' \
    "$4" "${RUN_STATUS:-completed}" "${RUN_PHASE:-done}"
  exit "${RUN_STATUS_RC:-0}"
fi
exit 1
EOF
  chmod +x "$BIN_DIR/ic"

  export CALL_LOG="$BATS_TEST_TMPDIR/calls"
  export RUNTIME_REQUIRED=false
  export RUNTIME_REQUIRED_RC=0
  export RUNTIME_VERIFY_RC=0
  export RUNTIME_SUMMARY='{"schema_version":1,"proof_hash":"sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa","run_id":"run-proof","git_head":"bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb","verified_at":"2026-07-11T12:00:00Z","host_fingerprint":"sha256:cccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccc"}'
  export RUN_STATUS=completed
  export RUN_PHASE=done
  export RUN_STATUS_RC=0
  : >"$CALL_LOG"
}

@test "labeled close gate rejects before consuming authorization token" {
  export BD_LABEL_JSON='"close-gate:calibration-streak"'
  export CALIBRATION_VERIFY_RC=1
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

@test "runtime proof failure rejects before consuming authorization token" {
  export RUNTIME_REQUIRED=true
  export RUNTIME_VERIFY_RC=1
  export CLAVAIN_AUTHZ_TOKEN=secret-placeholder

  run bash "$TEST_ROOT/scripts/gates/bead-close.sh" runtime-bead shipped

  [ "$status" -ne 0 ]
  grep -q '^clavain-cli:runtime-evidence required runtime-bead$' "$CALL_LOG"
  grep -q '^clavain-cli:runtime-evidence verify runtime-bead$' "$CALL_LOG"
  ! grep -q '^ic:' "$CALL_LOG"
  ! grep -q 'policy token consume' "$CALL_LOG"
  ! grep -q '^bd:set-state ' "$CALL_LOG"
  ! grep -q '^bd:close ' "$CALL_LOG"
}

@test "runtime proof rejects when its bound run is not completed at done" {
  export RUNTIME_REQUIRED=true
  export RUN_STATUS=active
  export RUN_PHASE=reflect
  export CLAVAIN_AUTHZ_TOKEN=secret-placeholder

  run bash "$TEST_ROOT/scripts/gates/bead-close.sh" runtime-bead shipped

  [ "$status" -ne 0 ]
  grep -q '^ic:--json run status run-proof$' "$CALL_LOG"
  ! grep -q 'policy token consume' "$CALL_LOG"
  ! grep -q '^bd:set-state ' "$CALL_LOG"
  ! grep -q '^bd:close ' "$CALL_LOG"
}

@test "valid runtime proof persists a sanitized summary before token consumption" {
  export RUNTIME_REQUIRED=true
  export CLAVAIN_AUTHZ_TOKEN=secret-placeholder

  run bash "$TEST_ROOT/scripts/gates/bead-close.sh" runtime-bead shipped

  [ "$status" -eq 0 ]
  [ "$(grep -c '^bd:set-state runtime-bead runtime_evidence_' "$CALL_LOG")" -eq 6 ]
  grep -q '^bd:set-state runtime-bead runtime_evidence_proof_hash=sha256:a\{64\} ' "$CALL_LOG"
  grep -q '^bd:set-state runtime-bead runtime_evidence_run_id=run-proof ' "$CALL_LOG"
  grep -q '^bd:set-state runtime-bead runtime_evidence_git_head=b\{40\} ' "$CALL_LOG"
  grep -q '^bd:set-state runtime-bead runtime_evidence_verified_at=2026-07-11T12:00:00Z ' "$CALL_LOG"
  grep -q '^bd:set-state runtime-bead runtime_evidence_host_fingerprint=sha256:c\{64\} ' "$CALL_LOG"
  grep -q '^bd:set-state runtime-bead runtime_evidence_schema=1 ' "$CALL_LOG"
  ! grep -q '^bd:set-state runtime-bead runtime_evidence_summary=' "$CALL_LOG"
  while IFS= read -r state_call; do
    state_value="${state_call#bd:set-state runtime-bead }"
    state_value="${state_value%% --reason=*}"
    [ "${#state_value}" -le 200 ]
  done < <(grep '^bd:set-state runtime-bead runtime_evidence_' "$CALL_LOG")
  grep -q '^bd:close runtime-bead --reason=shipped$' "$CALL_LOG"

  required_line=$(grep -n '^clavain-cli:runtime-evidence required runtime-bead$' "$CALL_LOG" | cut -d: -f1)
  verify_line=$(grep -n '^clavain-cli:runtime-evidence verify runtime-bead$' "$CALL_LOG" | cut -d: -f1)
  status_line=$(grep -n '^ic:--json run status run-proof$' "$CALL_LOG" | cut -d: -f1)
  persist_line=$(grep -n '^bd:set-state runtime-bead runtime_evidence_schema=1 ' "$CALL_LOG" | cut -d: -f1)
  consume_line=$(grep -n 'policy token consume' "$CALL_LOG" | cut -d: -f1)
  close_line=$(grep -n '^bd:close runtime-bead --reason=shipped$' "$CALL_LOG" | cut -d: -f1)

  [ "$required_line" -lt "$verify_line" ]
  [ "$verify_line" -lt "$status_line" ]
  [ "$status_line" -lt "$persist_line" ]
  [ "$persist_line" -lt "$consume_line" ]
  [ "$consume_line" -lt "$close_line" ]
}

@test "runtime requirement lookup failure leaves token and bead untouched" {
  export RUNTIME_REQUIRED_RC=1
  export CLAVAIN_AUTHZ_TOKEN=secret-placeholder

  run bash "$TEST_ROOT/scripts/gates/bead-close.sh" runtime-bead shipped

  [ "$status" -ne 0 ]
  ! grep -q 'policy token consume' "$CALL_LOG"
  ! grep -q '^bd:close ' "$CALL_LOG"
}
