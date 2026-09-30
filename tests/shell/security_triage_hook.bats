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
  EVENTS="$CLAVAIN_STATE_DIR/selector/triage-events"
  SLOTS="$CLAVAIN_STATE_DIR/selector/triage-slots"
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
  run env CLAVAIN_SELECTOR_SCRIPT="$STUB" CLAVAIN_SELECTOR_SECURITY_TRIAGE=shadow "$HOOK" <<< "{}"
  [ "$status" -eq 0 ]
  _await_mark
  for _ in $(seq 1 30); do
    ls "$EVENTS"/event.* >/dev/null 2>&1 || break
    sleep 0.1
  done
  ! ls "$EVENTS"/event.* >/dev/null 2>&1
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
  fifo="$TEST_TMP/fifo"
  mkfifo "$fifo"
  env CLAVAIN_SELECTOR_SCRIPT="$STUB" CLAVAIN_SELECTOR_SECURITY_TRIAGE=shadow "$HOOK" < "$fifo" &
  hook_pid=$!
  exec 9> "$fifo"   # open the write end so the hook blocks in cat, never seeing EOF
  for _ in $(seq 1 50); do
    ls "$EVENTS"/event.* >/dev/null 2>&1 && break
    sleep 0.1
  done
  ls "$EVENTS"/event.* >/dev/null 2>&1   # the capture really is in flight
  kill -TERM "$hook_pid"
  wait "$hook_pid" || true
  exec 9>&-
  ! ls "$EVENTS"/event.* >/dev/null 2>&1
  flock -n "$SLOTS/slot.1" true   # the interrupted hook released its slot
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

@test "the slot lock dies with its job: a SIGKILLed job never wedges measurement" {
  slow="$TEST_TMP/slow.py"
  printf '#!/usr/bin/env python3\nimport sys, time\nsys.stdin.buffer.read()\nopen("%s", "a").write("x")\ntime.sleep(30)\n' "$MARK" > "$slow"
  chmod +x "$slow"
  run env SELECTOR_HOOK_TIMEOUT=60 CLAVAIN_TRIAGE_MAX_JOBS=1 CLAVAIN_SELECTOR_SCRIPT="$slow" CLAVAIN_SELECTOR_SECURITY_TRIAGE=shadow "$HOOK" <<< "{}"
  [ "$status" -eq 0 ]
  for _ in $(seq 1 50); do [ -s "$MARK" ] && break; sleep 0.1; done
  ! flock -n "$SLOTS/slot.1" true            # busy while the job lives
  pids=$(pgrep -f "$slow" || true)
  [ -n "$pids" ]
  pkill -KILL -f "$slow"; pkill -KILL -f "selector-hook.sh pre_tool" || true
  for _ in $(seq 1 50); do flock -n "$SLOTS/slot.1" true && break; sleep 0.1; done
  flock -n "$SLOTS/slot.1" true               # the kernel released it
}

@test "event files abandoned by a killed job are swept on the next run" {
  mkdir -p "$EVENTS"
  echo "edit text" > "$EVENTS/event.abandoned"
  touch -d '5 minutes ago' "$EVENTS/event.abandoned"
  echo "fresh" > "$EVENTS/event.fresh"
  run env CLAVAIN_SELECTOR_SCRIPT="$STUB" CLAVAIN_SELECTOR_SECURITY_TRIAGE=shadow "$HOOK" <<< "{}"
  [ "$status" -eq 0 ]
  [ ! -e "$EVENTS/event.abandoned" ]
  [ -e "$EVENTS/event.fresh" ]
}

@test "the event directory and files are private" {
  run env CLAVAIN_SELECTOR_SCRIPT="$STUB" CLAVAIN_SELECTOR_SECURITY_TRIAGE=shadow "$HOOK" <<< "{}"
  [ "$(stat -c %a "$EVENTS")" = "700" ]
}

@test "a planted slot symlink is never followed or truncated" {
  mkdir -p "$SLOTS" "$EVENTS"
  echo "precious" > "$TEST_TMP/victim"
  ln -s "$TEST_TMP/victim" "$SLOTS/slot.1"
  run env CLAVAIN_TRIAGE_MAX_JOBS=1 CLAVAIN_SELECTOR_SCRIPT="$STUB" CLAVAIN_SELECTOR_SECURITY_TRIAGE=shadow "$HOOK" <<< "{}"
  [ "$status" -eq 0 ]
  [ "$(cat "$TEST_TMP/victim")" = "precious" ]
  [ ! -e "$MARK" ]   # slot refused, so no measurement ran
}

@test "a symlinked state directory receives nothing" {
  mkdir -p "$TEST_TMP/elsewhere" "$CLAVAIN_STATE_DIR"
  ln -s "$TEST_TMP/elsewhere" "$CLAVAIN_STATE_DIR/selector"
  run env CLAVAIN_SELECTOR_SCRIPT="$STUB" CLAVAIN_SELECTOR_SECURITY_TRIAGE=shadow "$HOOK" <<< "{}"
  [ "$status" -eq 0 ]
  [ -z "$(ls -A "$TEST_TMP/elsewhere")" ]
  [ ! -e "$MARK" ]
}

@test "the default state dir is per-user, not shared /tmp" {
  run env -u CLAVAIN_STATE_DIR HOME="$TEST_TMP/home" CLAVAIN_SELECTOR_SCRIPT="$STUB" CLAVAIN_SELECTOR_SECURITY_TRIAGE=shadow "$HOOK" <<< "{}"
  [ "$status" -eq 0 ]
  [ -d "$TEST_TMP/home/.clavain/selector/triage-slots" ]
}

@test "the stdin reader does not hold the slot lock after the hook is SIGKILLed" {
  fifo="$TEST_TMP/fifo"
  mkfifo "$fifo"
  env CLAVAIN_TRIAGE_MAX_JOBS=1 CLAVAIN_SELECTOR_SCRIPT="$STUB" CLAVAIN_SELECTOR_SECURITY_TRIAGE=shadow "$HOOK" < "$fifo" &
  hook_pid=$!
  exec 9> "$fifo"   # keep stdin open: the reader blocks
  for _ in $(seq 1 50); do ls "$EVENTS"/event.* >/dev/null 2>&1 && break; sleep 0.1; done
  ! flock -n "$SLOTS/slot.1" true      # held while capturing
  kill -KILL "$hook_pid"
  wait "$hook_pid" 2>/dev/null || true
  for _ in $(seq 1 30); do flock -n "$SLOTS/slot.1" true && break; sleep 0.1; done
  flock -n "$SLOTS/slot.1" true        # the orphaned reader must not keep it
  exec 9>&-
}
