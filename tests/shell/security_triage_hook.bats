#!/usr/bin/env bats
# security-triage-hook.sh: flag off costs nothing; on hands off; never blocks.

setup() {
  REPO_ROOT="$(cd "$BATS_TEST_DIRNAME/../.." && pwd)"
  HOOK="$REPO_ROOT/hooks/security-triage-hook.sh"
  TEST_TMP="$(mktemp -d)"
  export CLAVAIN_STATE_DIR="$TEST_TMP/state"
  MARK="$TEST_TMP/invoked"
  STUB="$TEST_TMP/stub.py"
  cat > "$STUB" <<PY
#!/usr/bin/env python3
import sys
open("$MARK", "a").write(" ".join(sys.argv[1:]) + "\n")
sys.stdin.buffer.read()
PY
  chmod +x "$STUB"
  unset CLAVAIN_SELECTOR CLAVAIN_SELECTOR_SECURITY_TRIAGE
}

teardown() {
  rm -rf "$TEST_TMP"
}

@test "flag unset never starts the selector" {
  run env CLAVAIN_SELECTOR_SCRIPT="$STUB" "$HOOK" <<< "{}"
  [ "$status" -eq 0 ]
  [ -z "$output" ]
  [ ! -e "$MARK" ]
}

@test "flag off, junk or kill switch never start the selector" {
  for value in off OFF "" 0 true; do
    run env CLAVAIN_SELECTOR_SCRIPT="$STUB" CLAVAIN_SELECTOR_SECURITY_TRIAGE="$value" "$HOOK" <<< "{}"
    [ "$status" -eq 0 ]
    [ ! -e "$MARK" ]
  done
  run env CLAVAIN_SELECTOR_SCRIPT="$STUB" CLAVAIN_SELECTOR=off CLAVAIN_SELECTOR_SECURITY_TRIAGE=shadow "$HOOK" <<< "{}"
  [ "$status" -eq 0 ]
  [ ! -e "$MARK" ]
}

# Shadow detaches the selector, so its effects land shortly after the hook returns.
_await_mark() {
  for _ in $(seq 1 100); do
    [ -s "$MARK" ] && return 0
    sleep 0.1
  done
  return 1
}

@test "shadow and active hand off to the pre_tool claude-code hook" {
  for value in shadow SHADOW active; do
    rm -f "$MARK"
    run env CLAVAIN_SELECTOR_SCRIPT="$STUB" CLAVAIN_SELECTOR_SECURITY_TRIAGE="$value" "$HOOK" <<< "{}"
    [ "$status" -eq 0 ]
    _await_mark
    [ "$(cat "$MARK")" = "hook --point pre_tool --host claude-code" ]
  done
}

@test "shadow returns at once without waiting for a slow selector and forwards stdin" {
  slow="$TEST_TMP/slow.py"
  cat > "$slow" <<PY
#!/usr/bin/env python3
import sys, time
data = sys.stdin.buffer.read()
time.sleep(2)
open("$MARK", "wb").write(data)
PY
  chmod +x "$slow"
  start=$(date +%s.%N)
  run env SELECTOR_HOOK_TIMEOUT=10 CLAVAIN_SELECTOR_SCRIPT="$slow" CLAVAIN_SELECTOR_SECURITY_TRIAGE=shadow "$HOOK" <<< '{"k":"v"}'
  end=$(date +%s.%N)
  [ "$status" -eq 0 ]
  [ -z "$output" ]
  python3 -c "import sys; sys.exit(0 if float('$end') - float('$start') < 1.0 else 1)"
  for _ in $(seq 1 100); do [ -s "$MARK" ] && break; sleep 0.1; done
  [ "$(cat "$MARK")" = '{"k":"v"}' ]
}

@test "shadow leaves no event file behind" {
  run env TMPDIR="$TEST_TMP" CLAVAIN_SELECTOR_SCRIPT="$STUB" CLAVAIN_SELECTOR_SECURITY_TRIAGE=shadow "$HOOK" <<< "{}"
  [ "$status" -eq 0 ]
  _await_mark
  for _ in $(seq 1 30); do
    ls "$TEST_TMP"/clavain-triage-event.* >/dev/null 2>&1 || break
    sleep 0.1
  done
  ! ls "$TEST_TMP"/clavain-triage-event.* >/dev/null 2>&1
}

@test "a failing selector never blocks and prints nothing" {
  failing="$TEST_TMP/fail.py"
  printf '#!/usr/bin/env python3\nimport sys\nprint("{\\"permissionDecision\\":\\"deny\\"}")\nsys.exit(3)\n' > "$failing"
  chmod +x "$failing"
  run env CLAVAIN_SELECTOR_SCRIPT="$failing" CLAVAIN_SELECTOR_SECURITY_TRIAGE=shadow "$HOOK" <<< "{}"
  [ "$status" -eq 0 ]
  [ -z "$output" ]
}

@test "a missing selector never blocks" {
  run env CLAVAIN_SELECTOR_SCRIPT="$TEST_TMP/nope.py" CLAVAIN_SELECTOR_SECURITY_TRIAGE=shadow "$HOOK" <<< "{}"
  [ "$status" -eq 0 ]
  [ -z "$output" ]
}
