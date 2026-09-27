#!/usr/bin/env bats
# Real tests for selector-hook.sh wrapper script

setup() {
  REPO_ROOT="$(cd "$BATS_TEST_DIRNAME/../.." && pwd)"
  WRAPPER="$REPO_ROOT/hooks/selector-hook.sh"
  TEST_TMP="$(mktemp -d)"
  export CLAVAIN_STATE_DIR="$TEST_TMP/state"
  SCRIPT="$TEST_TMP/script.py"
  mkdir -p "$(dirname "$SCRIPT")"

  # Create a working stub script
  cat > "$SCRIPT" << 'EOF'
#!/usr/bin/env python3
import sys
sys.exit(0)
EOF
  chmod +x "$SCRIPT"
}

teardown() {
  rm -rf "$TEST_TMP"
}

@test "wrapper exits 0 on success" {
  run env CLAVAIN_SELECTOR_SCRIPT="$SCRIPT" "$WRAPPER" pre_tool claude-code <<< "{}"
  [ "$status" -eq 0 ]
}

@test "wrapper exits 0 when script missing" {
  run "$WRAPPER" pre_tool claude-code <<< "{}"
  [ "$status" -eq 0 ]
}

@test "wrapper exits 0 when python is missing" {
  run env CLAVAIN_SELECTOR_SCRIPT="$SCRIPT" CLAVAIN_SELECTOR_PYTHON="$TEST_TMP/no-python" \
    "$WRAPPER" pre_tool claude-code <<< "{}"
  [ "$status" -eq 0 ]
  [ -z "$output" ]
}

@test "wrapper exits 0 when script fails" {
  failing="$TEST_TMP/fail.py"
  cat > "$failing" << 'EOF'
#!/usr/bin/env python3
import sys
sys.exit(1)
EOF
  chmod +x "$failing"

  run env CLAVAIN_SELECTOR_SCRIPT="$failing" "$WRAPPER" pre_tool claude-code <<< "{}"
  [ "$status" -eq 0 ]
}

@test "wrapper exits 0 on malformed stdin" {
  run env CLAVAIN_SELECTOR_SCRIPT="$SCRIPT" "$WRAPPER" pre_tool claude-code <<< "{"
  [ "$status" -eq 0 ]
}

@test "timeout writes bounded telemetry line" {
  hanging="$TEST_TMP/hang.py"
  cat > "$hanging" << 'EOF'
#!/usr/bin/env python3
import time
time.sleep(10)
EOF
  chmod +x "$hanging"

  run env CLAVAIN_SELECTOR_SCRIPT="$hanging" SELECTOR_HOOK_TIMEOUT=0.1 "$WRAPPER" pre_tool claude-code <<< "{}"
  [ "$status" -eq 0 ]

  log="$CLAVAIN_STATE_DIR/selector/wrapper-timeouts.jsonl"
  [ -f "$log" ]
  [ "$(wc -l < "$log")" -eq 1 ]

  # Verify the JSON structure
  run python3 -c "
import json, sys
with open('$log') as f:
  line = f.readline()
  x = json.loads(line)
  assert x['point'] == 'pre_tool', f'point mismatch: {x}'
  assert x['kind'] == 'wrapper_timeout', f'kind mismatch: {x}'
  assert 'at' in x, f'missing at: {x}'
  print('JSON valid')
" 2>&1
  [ "$status" -eq 0 ]
  [[ "$output" == *"valid"* ]]
}

@test "wrapper emits empty stdout for inert operations" {
  run env CLAVAIN_SELECTOR_SCRIPT="$SCRIPT" "$WRAPPER" pre_tool claude-code <<< "{}"
  [ "$status" -eq 0 ]
  [ -z "$output" ]
}

# Fail-closed stdout: the child's bytes reach the host only on exit 0.
_child() {
  local path="$TEST_TMP/$1.py"
  printf '%s\n' '#!/usr/bin/env python3' 'import os, signal, sys, time' "$2" > "$path"
  chmod +x "$path"
  printf '%s' "$path"
}

@test "child exit 1 after valid selection JSON emits nothing" {
  child="$(_child fail_after_json 'sys.stdout.write("{\"hookSpecificOutput\":{\"permissionDecision\":\"allow\"}}\n"); sys.stdout.flush(); sys.exit(1)')"
  CLAVAIN_SELECTOR_SCRIPT="$child" "$WRAPPER" pre_tool claude-code < /dev/null > "$TEST_TMP/out" 2>/dev/null
  status=$?
  [ "$status" -eq 0 ]
  [ ! -s "$TEST_TMP/out" ]
}

@test "child crash after partial JSON emits nothing" {
  child="$(_child crash_partial 'sys.stdout.write("{\"hookSpecificOutput\":{\"perm"); sys.stdout.flush(); os._exit(3)')"
  CLAVAIN_SELECTOR_SCRIPT="$child" "$WRAPPER" pre_tool claude-code < /dev/null > "$TEST_TMP/out" 2>/dev/null
  status=$?
  [ "$status" -eq 0 ]
  [ ! -s "$TEST_TMP/out" ]
}

@test "child killed after partial output emits nothing" {
  child="$(_child killed_partial 'sys.stdout.write("{\"partial\":"); sys.stdout.flush(); os.kill(os.getpid(), signal.SIGKILL)')"
  CLAVAIN_SELECTOR_SCRIPT="$child" "$WRAPPER" pre_tool claude-code < /dev/null > "$TEST_TMP/out" 2>/dev/null
  status=$?
  [ "$status" -eq 0 ]
  [ ! -s "$TEST_TMP/out" ]
}

@test "child exit 0 output is passed through byte for byte" {
  child="$(_child ok_output 'sys.stdout.write("{\"hookSpecificOutput\":{\"permissionDecision\":\"allow\"}}\n\n"); sys.exit(0)')"
  printf '%s\n\n' '{"hookSpecificOutput":{"permissionDecision":"allow"}}' > "$TEST_TMP/expected"
  CLAVAIN_SELECTOR_SCRIPT="$child" "$WRAPPER" pre_tool claude-code < /dev/null > "$TEST_TMP/out" 2>/dev/null
  status=$?
  [ "$status" -eq 0 ]
  cmp "$TEST_TMP/expected" "$TEST_TMP/out"
}

@test "timeout after partial output writes telemetry and emits nothing" {
  child="$(_child hang_partial 'sys.stdout.write("{\"hookSpecificOutput\":"); sys.stdout.flush(); time.sleep(10)')"
  CLAVAIN_SELECTOR_SCRIPT="$child" SELECTOR_HOOK_TIMEOUT=0.2 "$WRAPPER" pre_tool claude-code < /dev/null > "$TEST_TMP/out" 2>/dev/null
  status=$?
  [ "$status" -eq 0 ]
  [ ! -s "$TEST_TMP/out" ]
  log="$CLAVAIN_STATE_DIR/selector/wrapper-timeouts.jsonl"
  [ "$(wc -l < "$log")" -eq 1 ]
  grep -q '"kind":"wrapper_timeout"' "$log"
}
