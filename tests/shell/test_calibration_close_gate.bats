#!/usr/bin/env bats

setup() {
  unset CLAVAIN_AUTHZ_PROJECT_ROOT GATE_AUTHZ_TOKEN
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
if [[ "$1 $2" == "context --json" ]]; then
  printf '{"repo_root":"%s","beads_dir":"%s/.beads"}\n' "${AUTHZ_REPO_ROOT}" "${AUTHZ_REPO_ROOT}"
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
	if [[ "${TOKEN_CONSUME_MALFORMED:-0}" == "1" ]]; then
		printf 'malformed-success\n'
	else
		op=""; target=""
		for arg in "$@"; do
			case "$arg" in
				--expect-op=*) op="${arg#*=}" ;;
				--expect-target=*) target="${arg#*=}" ;;
			esac
		done
		printf '# authz-receipt {"schema":1,"status":"consumed","op":"%s","target":"%s","audit_id":"row-token","signed":true}\n' "$op" "$target"
		printf '# authz-unset-begin\nunset CLAVAIN_AUTHZ_TOKEN\n# authz-unset-end\n'
	fi
  exit 0
fi
if [[ "$1 $2" == "policy doctor" ]]; then
	if [[ "${SIGNER_DOCTOR_RC:-0}" != "0" ]]; then
		exit "$SIGNER_DOCTOR_RC"
	fi
	printf '{"status":"ok","role":"signer","schema":35,"project_root":"%s","fingerprint":"0123456789abcdef"}\n' "$AUTHZ_REPO_ROOT"
	exit 0
fi
if [[ "$1 $2" == "policy check" ]]; then
  printf '{"schema":1,"mode":"auto","policy_hash":"h","policy_match":"m"}\n'
  exit 0
fi
if [[ "$1 $2" == "policy record-signed" ]]; then
  if [[ "${RECORD_SIGNED_RC:-0}" != "0" ]]; then
    exit "$RECORD_SIGNED_RC"
  fi
  printf '{"status":"ok","id":"row-test","signed":1}\n'
  exit 0
fi
if [[ "$1" == "policy-check" ]]; then
  exit 99
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
  export AUTHZ_REPO_ROOT="$(cd "$TEST_ROOT" && pwd -P)"
  export SIGNER_DOCTOR_RC=0
  export RECORD_SIGNED_RC=0
  : >"$CALL_LOG"
}

@test "missing signer blocks before proof checks, token consumption, or close" {
  export SIGNER_DOCTOR_RC=1
  export RUNTIME_REQUIRED=true
  export CLAVAIN_AUTHZ_TOKEN=secret-placeholder

  run bash "$TEST_ROOT/scripts/gates/bead-close.sh" signerless-bead shipped

  [ "$status" -ne 0 ]
  grep -q '^clavain-cli:policy doctor --require-signer' "$CALL_LOG"
  ! grep -q 'runtime-evidence' "$CALL_LOG"
  ! grep -q 'policy token consume' "$CALL_LOG"
  ! grep -q '^bd:set-state ' "$CALL_LOG"
  ! grep -q '^bd:close ' "$CALL_LOG"
}

@test "authorization fallback uses the authz policy namespace" {
  run bash "$TEST_ROOT/scripts/gates/bead-close.sh" ordinary-bead shipped

  [ "$status" -eq 0 ]
  grep -q '^clavain-cli:policy check bead-close ' "$CALL_LOG"
  ! grep -q '^clavain-cli:policy-check ' "$CALL_LOG"
}

@test "signed authorization failure blocks before close" {
  export RECORD_SIGNED_RC=1

  run bash "$TEST_ROOT/scripts/gates/bead-close.sh" ordinary-bead shipped

  [ "$status" -ne 0 ]
  grep -q '^clavain-cli:policy record-signed ' "$CALL_LOG"
  ! grep -q '^bd:close ' "$CALL_LOG"
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

@test "malformed token success receipt blocks before close" {
	export TOKEN_CONSUME_MALFORMED=1
	export CLAVAIN_AUTHZ_TOKEN=secret-placeholder

	run bash "$TEST_ROOT/scripts/gates/bead-close.sh" malformed-receipt shipped

	[ "$status" -ne 0 ]
	! grep -q '^bd:close malformed-receipt ' "$CALL_LOG"
}

@test "missing JSON parser blocks before policy or close" {
	cat >"$BIN_DIR/jq" <<'EOF'
#!/usr/bin/env bash
exit 127
EOF
	chmod +x "$BIN_DIR/jq"

	run bash "$TEST_ROOT/scripts/gates/bead-close.sh" no-json-parser shipped

	[ "$status" -ne 0 ]
	! grep -q '^bd:close no-json-parser ' "$CALL_LOG"
}
