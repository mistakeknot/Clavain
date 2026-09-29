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

@test "shadow and active hand off to the pre_tool claude-code hook" {
  for value in shadow SHADOW active; do
    rm -f "$MARK"
    run env CLAVAIN_SELECTOR_SCRIPT="$STUB" CLAVAIN_SELECTOR_SECURITY_TRIAGE="$value" "$HOOK" <<< "{}"
    [ "$status" -eq 0 ]
    [ "$(cat "$MARK")" = "hook --point pre_tool --host claude-code" ]
  done
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
