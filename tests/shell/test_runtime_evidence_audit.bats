#!/usr/bin/env bats

bats_require_minimum_version 1.5.0

setup() {
  load test_helper

  REPO_ROOT="$(cd "$BATS_TEST_DIRNAME/../.." && pwd)"
  AUDIT_SCRIPT="$REPO_ROOT/scripts/runtime-evidence-audit.sh"
  TEST_ROOT="$(mktemp -d)"
  BIN_DIR="$TEST_ROOT/bin"
  FIXTURE_DIR="$TEST_ROOT/fixtures"
  STATE_DIR="$FIXTURE_DIR/state"
  mkdir -p "$BIN_DIR" "$STATE_DIR"

  export AUDIT_CALL_LOG="$TEST_ROOT/calls.log"
  export AUDIT_BEADS_JSON="$FIXTURE_DIR/beads.json"
  export AUDIT_FIXTURE_DIR="$FIXTURE_DIR"
  export PATH="$BIN_DIR:$PATH"
  printf '[]\n' > "$AUDIT_BEADS_JSON"

  _write_bd_stub
  _write_ic_stub
  _write_clavain_cli_stub
}

teardown() {
  rm -rf "$TEST_ROOT"
}

_write_bd_stub() {
  cat > "$BIN_DIR/bd" <<'EOF'
#!/usr/bin/env bash
set -euo pipefail
printf 'bd:%s\n' "$*" >> "$AUDIT_CALL_LOG"
if [[ "${1:-}" == "--readonly" ]]; then
  shift
else
  echo "bd audit call was not read-only" >&2
  exit 90
fi
case "${1:-}" in
  list)
    cat "$AUDIT_BEADS_JSON"
    ;;
  state)
    key_file="$AUDIT_FIXTURE_DIR/state/${2}.${3}"
    if [[ -f "$key_file" ]]; then
      cat "$key_file"
    else
      printf '(no %s state set)\n' "${3:-unknown}"
    fi
    ;;
  *)
    echo "unsupported bd call: $*" >&2
    exit 91
    ;;
esac
EOF
  chmod +x "$BIN_DIR/bd"
}

_write_ic_stub() {
  cat > "$BIN_DIR/ic" <<'EOF'
#!/usr/bin/env bash
set -euo pipefail
printf 'ic:%s\n' "$*" >> "$AUDIT_CALL_LOG"
[[ "${1:-}" == "--json" ]] || { echo "ic audit call was not JSON" >&2; exit 92; }
shift
[[ "${1:-}" == "run" ]] || exit 93
case "${2:-}" in
  list)
    scope=""
    for arg in "$@"; do
      [[ "$arg" == --scope=* ]] && scope="${arg#--scope=}"
    done
    fixture="$AUDIT_FIXTURE_DIR/scope-${scope}.json"
    [[ -f "$fixture" ]] && cat "$fixture" || printf '[]\n'
    ;;
  status)
    fixture="$AUDIT_FIXTURE_DIR/run-${3}.json"
    [[ -f "$fixture" ]] || exit 1
    cat "$fixture"
    ;;
  artifact)
    [[ "${3:-}" == "list" ]] || exit 94
    fixture="$AUDIT_FIXTURE_DIR/artifacts-${4}.json"
    [[ -f "$fixture" ]] && cat "$fixture" || printf '[]\n'
    ;;
  *)
    echo "unsupported ic call: $*" >&2
    exit 95
    ;;
esac
EOF
  chmod +x "$BIN_DIR/ic"
}

_write_clavain_cli_stub() {
  cat > "$BIN_DIR/clavain-cli" <<'EOF'
#!/usr/bin/env bash
set -euo pipefail
printf 'clavain-cli:%s\n' "$*" >> "$AUDIT_CALL_LOG"
[[ "${1:-} ${2:-}" == "runtime-evidence verify" ]] || exit 96
fixture="$AUDIT_FIXTURE_DIR/verify-${3}.json"
[[ -f "$fixture" ]] && cat "$fixture"
rc_file="$AUDIT_FIXTURE_DIR/verify-${3}.rc"
[[ -f "$rc_file" ]] && exit "$(cat "$rc_file")"
exit 0
EOF
  chmod +x "$BIN_DIR/clavain-cli"
}

_write_beads() {
  printf '%s\n' "$1" > "$AUDIT_BEADS_JSON"
}

_write_state() {
  printf '%s\n' "$3" > "$STATE_DIR/$1.$2"
}

_write_scope() {
  printf '%s\n' "$2" > "$FIXTURE_DIR/scope-$1.json"
}

_run_fixture() {
  run --separate-stderr "$AUDIT_SCRIPT" --json
}

_assert_finding() {
  local code="$1" bead="$2"
  jq -e --arg code "$code" --arg bead "$bead" \
    '.findings[] | select(.code == $code and .bead_id == $bead)' \
    <<<"$output" >/dev/null
}

_valid_summary() {
  local run_id="$1" verified_at="$2" host_hash="$3"
  jq -cn \
    --arg run_id "$run_id" \
    --arg verified_at "$verified_at" \
    --arg host_hash "$host_hash" \
    '{schema_version:1,proof_hash:("sha256:" + ("a" * 64)),run_id:$run_id,git_head:("b" * 40),verified_at:$verified_at,host_fingerprint:("sha256:" + $host_hash)}'
}

@test "runtime evidence audit reports an active labeled bead with no bound run" {
  _write_beads '[{"id":"bead-missing","status":"in_progress","labels":["close-gate:runtime-evidence"]}]'
  _write_scope "bead-missing" '[]'

  _run_fixture

  [ "$status" -eq 1 ]
  jq -e '.supported == true and .counts.findings == 1' <<<"$output" >/dev/null
  _assert_finding "run_missing" "bead-missing"
  [ "$(grep -Ec '^bd:--readonly (set-state|update|close|label)( |$)' "$AUDIT_CALL_LOG" || true)" -eq 0 ]
}

@test "runtime evidence audit reports conflicting active runs" {
  local metadata
  metadata='{"close_gate":{"requirements":["runtime-evidence/v1"],"bead_id":"bead-conflict"}}'
  _write_beads '[{"id":"bead-conflict","status":"open","labels":["close-gate:runtime-evidence"]}]'
  _write_state "bead-conflict" "ic_run_id" "run-one"
  _write_scope "bead-conflict" "[{
    \"id\":\"run-one\",\"scope_id\":\"bead-conflict\",\"status\":\"active\",\"phase\":\"reflect\",\"project_dir\":\"/remote/one\",\"metadata\":$(jq -Rn --arg v "$metadata" '$v')
  },{
    \"id\":\"run-two\",\"scope_id\":\"bead-conflict\",\"status\":\"active\",\"phase\":\"reflect\",\"project_dir\":\"/remote/two\",\"metadata\":$(jq -Rn --arg v "$metadata" '$v')
  }]"

  _run_fixture

  [ "$status" -eq 1 ]
  _assert_finding "run_conflict" "bead-conflict"
}

@test "runtime evidence audit reports a completed run whose bead remains open" {
  local metadata
  metadata='{"close_gate":{"requirements":["runtime-evidence/v1"],"bead_id":"bead-open"}}'
  _write_beads '[{"id":"bead-open","status":"open","labels":["close-gate:runtime-evidence"]}]'
  _write_state "bead-open" "ic_run_id" "run-done"
  _write_scope "bead-open" "[{
    \"id\":\"run-done\",\"scope_id\":\"bead-open\",\"status\":\"completed\",\"phase\":\"done\",\"project_dir\":\"$TEST_ROOT/local-project\",\"metadata\":$(jq -Rn --arg v "$metadata" '$v')
  }]"

  _run_fixture

  [ "$status" -eq 1 ]
  _assert_finding "bead_open_after_run_completed" "bead-open"
  [ "$(grep -c '^clavain-cli:' "$AUDIT_CALL_LOG" || true)" -eq 0 ]
}

@test "runtime evidence audit reports a current-host active run without a receipt" {
  local metadata
  metadata='{"close_gate":{"requirements":["runtime-evidence/v1"],"bead_id":"bead-local-missing"}}'
  mkdir -p "$TEST_ROOT/local-project"
  _write_beads '[{"id":"bead-local-missing","status":"in_progress","labels":["close-gate:runtime-evidence"]}]'
  _write_state "bead-local-missing" "ic_run_id" "run-local-missing"
  _write_scope "bead-local-missing" "[{
    \"id\":\"run-local-missing\",\"scope_id\":\"bead-local-missing\",\"status\":\"active\",\"phase\":\"reflect\",\"project_dir\":\"$TEST_ROOT/local-project\",\"metadata\":$(jq -Rn --arg v "$metadata" '$v')
  }]"
  printf '[]\n' > "$FIXTURE_DIR/artifacts-run-local-missing.json"

  _run_fixture

  [ "$status" -eq 1 ]
  _assert_finding "receipt_missing" "bead-local-missing"
}

@test "runtime evidence audit reports a current-host active run with an invalid receipt" {
  local metadata receipt
  metadata='{"close_gate":{"requirements":["runtime-evidence/v1"],"bead_id":"bead-local-invalid"}}'
  mkdir -p "$TEST_ROOT/local-project"
  receipt="$TEST_ROOT/receipt.json"
  printf '{"not":"valid"}\n' > "$receipt"
  _write_beads '[{"id":"bead-local-invalid","status":"in_progress","labels":["close-gate:runtime-evidence"]}]'
  _write_state "bead-local-invalid" "ic_run_id" "run-local-invalid"
  _write_scope "bead-local-invalid" "[{
    \"id\":\"run-local-invalid\",\"scope_id\":\"bead-local-invalid\",\"status\":\"active\",\"phase\":\"reflect\",\"project_dir\":\"$TEST_ROOT/local-project\",\"metadata\":$(jq -Rn --arg v "$metadata" '$v')
  }]"
  printf '[{"run_id":"run-local-invalid","type":"runtime-evidence/v1","status":"active","path":"%s","content_hash":"sha256:%064d","created_at":1}]\n' "$receipt" 0 > "$FIXTURE_DIR/artifacts-run-local-invalid.json"
  printf '1\n' > "$FIXTURE_DIR/verify-bead-local-invalid.rc"

  _run_fixture

  [ "$status" -eq 1 ]
  _assert_finding "receipt_invalid" "bead-local-invalid"
  grep -q '^clavain-cli:runtime-evidence verify bead-local-invalid$' "$AUDIT_CALL_LOG"
}

@test "runtime evidence audit reports closed beads with missing or malformed durable summaries" {
  _write_beads '[
    {"id":"bead-closed-missing","status":"closed","labels":["close-gate:runtime-evidence"]},
    {"id":"bead-closed-malformed","status":"closed","labels":["close-gate:runtime-evidence"]}
  ]'
  _write_state "bead-closed-missing" "ic_run_id" "run-closed-missing"
  _write_state "bead-closed-malformed" "ic_run_id" "run-closed-malformed"
  _write_state "bead-closed-malformed" "runtime_evidence_summary" '{"schema_version":1,"run_id":"wrong-run"}'

  _run_fixture

  [ "$status" -eq 1 ]
  _assert_finding "durable_summary_missing" "bead-closed-missing"
  _assert_finding "durable_summary_malformed" "bead-closed-malformed"
  [ "$(grep -c '^ic:' "$AUDIT_CALL_LOG" || true)" -eq 0 ]
  [ "$(grep -c '^clavain-cli:' "$AUDIT_CALL_LOG" || true)" -eq 0 ]
}

@test "runtime evidence audit accepts old local and remote historical summaries without revalidation" {
  local local_summary remote_summary
  local_summary="$(_valid_summary "run-local-history" "2020-01-01T00:00:00Z" "$(printf 'c%.0s' {1..64})")"
  remote_summary="$(_valid_summary "run-remote-history" "2019-01-01T00:00:00Z" "$(printf 'd%.0s' {1..64})")"
  _write_beads '[
    {"id":"bead-local-history","status":"closed","labels":["close-gate:runtime-evidence"]},
    {"id":"bead-remote-history","status":"closed","labels":["close-gate:runtime-evidence"]}
  ]'
  _write_state "bead-local-history" "ic_run_id" "run-local-history"
  _write_state "bead-local-history" "runtime_evidence_summary" "$local_summary"
  _write_state "bead-remote-history" "ic_run_id" "run-remote-history"
  _write_state "bead-remote-history" "runtime_evidence_summary" "$remote_summary"

  _run_fixture

  [ "$status" -eq 0 ]
  jq -e '.supported == true and .counts.beads == 2 and .counts.findings == 0 and .findings == []' <<<"$output" >/dev/null
  [ "$(grep -c '^ic:' "$AUDIT_CALL_LOG" || true)" -eq 0 ]
  [ "$(grep -c '^clavain-cli:' "$AUDIT_CALL_LOG" || true)" -eq 0 ]
}

@test "session start surfaces findings once per six-hour window" {
  local hook_project audit_stub cache_dir first second
  hook_project="$TEST_ROOT/hook-project"
  audit_stub="$TEST_ROOT/audit-stub.sh"
  cache_dir="$TEST_ROOT/cache"
  mkdir -p "$hook_project" "$cache_dir"
  cat > "$audit_stub" <<'EOF'
#!/usr/bin/env bash
printf 'audit\n' >> "$AUDIT_CALL_LOG"
cat <<'JSON'
{"schema_version":1,"supported":true,"counts":{"beads":1,"findings":1},"findings":[{"code":"receipt_missing","bead_id":"bead-hook","message":"Current-host run has no receipt.","action":"Run runtime-evidence collect."}]}
JSON
exit 1
EOF
  chmod +x "$audit_stub"

  first="$(printf '{"source":"startup","session_id":"audit-session-one"}' | \
    HOME="$TEST_ROOT/home" \
    CLAUDE_PROJECT_DIR="$hook_project" \
    CLAVAIN_RUNTIME_EVIDENCE_AUDIT="$audit_stub" \
    CLAVAIN_RUNTIME_AUDIT_CACHE_DIR="$cache_dir" \
    bash "$HOOKS_DIR/session-start.sh")"
  second="$(printf '{"source":"startup","session_id":"audit-session-two"}' | \
    HOME="$TEST_ROOT/home" \
    CLAUDE_PROJECT_DIR="$hook_project" \
    CLAVAIN_RUNTIME_EVIDENCE_AUDIT="$audit_stub" \
    CLAVAIN_RUNTIME_AUDIT_CACHE_DIR="$cache_dir" \
    bash "$HOOKS_DIR/session-start.sh")"

  jq -e '.hookSpecificOutput.additionalContext | contains("bead-hook") and contains("runtime-evidence collect")' <<<"$first" >/dev/null
  [ "$(jq -r '.hookSpecificOutput.additionalContext | contains("bead-hook")' <<<"$second")" = "false" ]
  [ "$(grep -c '^audit$' "$AUDIT_CALL_LOG")" -eq 1 ]
}

@test "session start is quiet for clean and unsupported audits" {
  local hook_project audit_stub cache_dir result
  hook_project="$TEST_ROOT/hook-project"
  audit_stub="$TEST_ROOT/audit-stub.sh"
  cache_dir="$TEST_ROOT/cache"
  mkdir -p "$hook_project" "$cache_dir"
  cat > "$audit_stub" <<'EOF'
#!/usr/bin/env bash
printf '%s\n' "${AUDIT_STUB_JSON}"
EOF
  chmod +x "$audit_stub"

  for fixture in \
    '{"schema_version":1,"supported":true,"counts":{"beads":0,"findings":0},"findings":[]}' \
    '{"schema_version":1,"supported":false,"reason":"no tracker","counts":{"beads":0,"findings":0},"findings":[]}'
  do
    result="$(printf '{"source":"startup","session_id":"audit-clean"}' | \
      HOME="$TEST_ROOT/home" \
      CLAUDE_PROJECT_DIR="$hook_project" \
      AUDIT_STUB_JSON="$fixture" \
      CLAVAIN_RUNTIME_EVIDENCE_AUDIT="$audit_stub" \
      CLAVAIN_RUNTIME_AUDIT_CACHE_DIR="$cache_dir" \
      CLAVAIN_RUNTIME_AUDIT_INTERVAL_SECONDS=0 \
      bash "$HOOKS_DIR/session-start.sh")"
    [ "$(jq -r '.hookSpecificOutput.additionalContext | contains("runtime evidence audit")' <<<"$result")" = "false" ]
  done
}

@test "session audit cadence is scoped per repository" {
  local first_project second_project audit_stub cache_dir
  first_project="$TEST_ROOT/first-project"
  second_project="$TEST_ROOT/second-project"
  audit_stub="$TEST_ROOT/audit-stub.sh"
  cache_dir="$TEST_ROOT/cache"
  mkdir -p "$first_project" "$second_project" "$cache_dir"
  cat > "$audit_stub" <<'EOF'
#!/usr/bin/env bash
printf 'audit:%s\n' "$PWD" >> "$AUDIT_CALL_LOG"
printf '{"schema_version":1,"supported":false,"reason":"no tracker","counts":{"beads":0,"findings":0},"findings":[]}\n'
EOF
  chmod +x "$audit_stub"

  printf '{"source":"startup","session_id":"audit-first"}' | \
    HOME="$TEST_ROOT/home" \
    CLAUDE_PROJECT_DIR="$first_project" \
    CLAVAIN_RUNTIME_EVIDENCE_AUDIT="$audit_stub" \
    CLAVAIN_RUNTIME_AUDIT_CACHE_DIR="$cache_dir" \
    bash "$HOOKS_DIR/session-start.sh" >/dev/null
  printf '{"source":"startup","session_id":"audit-second"}' | \
    HOME="$TEST_ROOT/home" \
    CLAUDE_PROJECT_DIR="$second_project" \
    CLAVAIN_RUNTIME_EVIDENCE_AUDIT="$audit_stub" \
    CLAVAIN_RUNTIME_AUDIT_CACHE_DIR="$cache_dir" \
    bash "$HOOKS_DIR/session-start.sh" >/dev/null

  [ "$(grep -c '^audit:' "$AUDIT_CALL_LOG")" -eq 2 ]
  grep -Fxq "audit:$first_project" "$AUDIT_CALL_LOG"
  grep -Fxq "audit:$second_project" "$AUDIT_CALL_LOG"
}

@test "session start does not enter an existing runtime audit lock" {
  local hook_project audit_stub cache_dir result
  hook_project="$TEST_ROOT/hook-project"
  audit_stub="$TEST_ROOT/audit-stub.sh"
  cache_dir="$TEST_ROOT/cache"
  mkdir -p "$hook_project" "$cache_dir/runtime-evidence-audit-locked.lock"
  cat > "$audit_stub" <<'EOF'
#!/usr/bin/env bash
printf 'audit\n' >> "$AUDIT_CALL_LOG"
printf '{"schema_version":1,"supported":true,"counts":{"beads":0,"findings":0},"findings":[]}\n'
EOF
  chmod +x "$audit_stub"

  result="$(printf '{"source":"startup","session_id":"audit-locked"}' | \
    HOME="$TEST_ROOT/home" \
    CLAUDE_PROJECT_DIR="$hook_project" \
    CLAVAIN_RUNTIME_EVIDENCE_AUDIT="$audit_stub" \
    CLAVAIN_RUNTIME_AUDIT_CACHE_DIR="$cache_dir" \
    CLAVAIN_RUNTIME_AUDIT_SCOPE_KEY=locked \
    bash "$HOOKS_DIR/session-start.sh")"

  jq -e '.hookSpecificOutput.hookEventName == "SessionStart"' <<<"$result" >/dev/null
  [ "$(grep -c '^audit$' "$AUDIT_CALL_LOG" || true)" -eq 0 ]
}
