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

@test "an interrupt while stdin is still open leaves no event file and frees the slot" {
  export TMPDIR="$TEST_TMP"
  fifo="$TEST_TMP/fifo"
  mkfifo "$fifo"
  env CLAVAIN_SELECTOR_SCRIPT="$STUB" CLAVAIN_SELECTOR_SECURITY_TRIAGE=shadow "$HOOK" < "$fifo" &
  hook_pid=$!
  exec 9> "$fifo"   # open the write end so the hook blocks in cat, never seeing EOF
  for _ in $(seq 1 50); do
    ls "$TEST_TMP"/clavain-triage-event.* >/dev/null 2>&1 && break
    sleep 0.1
  done
  ls "$TEST_TMP"/clavain-triage-event.* >/dev/null 2>&1   # the capture really is in flight
  kill -TERM "$hook_pid"
  wait "$hook_pid" || true
  exec 9>&-
  ! ls "$TEST_TMP"/clavain-triage-event.* >/dev/null 2>&1
  [ -z "$(ls "$TEST_TMP/selector/triage-slots" 2>/dev/null)" ]
}

@test "shadow jobs are bounded: extra edits are dropped, never queued" {
  slow="$TEST_TMP/slow.py"
  printf '#!/usr/bin/env python3\nimport sys, time\nsys.stdin.buffer.read()\nopen("%s", "a").write("x")\ntime.sleep(2)\n' "$MARK" > "$slow"
  chmod +x "$slow"
  for _ in 1 2 3 4 5 6; do
    run env SELECTOR_HOOK_TIMEOUT=10 CLAVAIN_TRIAGE_MAX_JOBS=2 CLAVAIN_SELECTOR_SCRIPT="$slow" CLAVAIN_SELECTOR_SECURITY_TRIAGE=shadow "$HOOK" <<< "{}"
    [ "$status" -eq 0 ]
    [ -z "$output" ]
  done
  sleep 1
  [ "$(wc -c < "$MARK")" -eq 2 ]
}

@test "a stale slot is reaped so measurement resumes" {
  mkdir -p "$CLAVAIN_STATE_DIR/selector/triage-slots/slot.1"
  touch -d '2 minutes ago' "$CLAVAIN_STATE_DIR/selector/triage-slots/slot.1"
  run env CLAVAIN_TRIAGE_MAX_JOBS=1 CLAVAIN_SELECTOR_SCRIPT="$STUB" CLAVAIN_SELECTOR_SECURITY_TRIAGE=shadow "$HOOK" <<< "{}"
  [ "$status" -eq 0 ]
  _await_mark
}
