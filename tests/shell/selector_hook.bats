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
