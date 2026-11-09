#!/usr/bin/env bats
# mk-ouz83: Claude-backed dispatch keeps ANTHROPIC_AUTH_TOKEN and scans every
# artifact for it afterwards; other backends lose it; two other bearer tokens
# never reach any child. Only a dummy token value is used here.

setup() {
    load test_helper
    ROOT="$BATS_TEST_DIRNAME/../.."
    DISPATCH="$ROOT/scripts/dispatch.sh"
    T="$(mktemp -d)"
    DUMMY=sk-test-dummy-0123456789abcdef
    mkdir -p "$T/bin" "$T/repo"
    git -C "$T/repo" init -q
    printf 'x\n' > "$T/repo/f.txt"
    git -C "$T/repo" -c user.name=t -c user.email=t@t add f.txt
    git -C "$T/repo" -c user.name=t -c user.email=t@t commit -q -m base
    printf 'prompt\n' > "$T/prompt.md"
    printf '{"decision":"x"}\n' > "$T/ctx.json"
    POLICY_HASH="$(sha256sum "$ROOT/config/routing.yaml" | awk '{print $1}')"
    printf '#!/usr/bin/env bash\nexit 0\n' > "$T/bin/ic"
    # Fake backends record which of the three token variables are present
    # (names only, never values) and can leak the dummy value on demand.
    cat > "$T/bin/claude" <<'FAKE'
#!/usr/bin/env bash
cat > /dev/null
{
  echo "anthropic:${ANTHROPIC_AUTH_TOKEN+set}"
  echo "bbparent:${BB_ACCOUNT_POOL_PARENT_TOKEN+set}"
  echo "message:${CLAUDE_CODE_MESSAGING_TOKEN+set}"
} > "$FAKE_ENV_LOG"
body="${BODY:-clean answer}"
[[ "${LEAK:-}" != *out* ]] || body="answer with ${ANTHROPIC_AUTH_TOKEN} inside"
[[ "${LEAK:-}" != *err* ]] || echo "auth detail ${ANTHROPIC_AUTH_TOKEN}" >&2
[[ "${LEAK:-}" != *event* ]] || jq -cn --arg t "${ANTHROPIC_AUTH_TOKEN}" '{type:"system",note:$t}'
if [[ -n "${SLOW:-}" ]]; then : > "$SLOW"; sleep 3; fi
jq -cn --arg body "$body" '{type:"result",subtype:"success",is_error:false,result:$body}'
FAKE
    cat > "$T/bin/kimi" <<'FAKE'
#!/usr/bin/env bash
{
  echo "anthropic:${ANTHROPIC_AUTH_TOKEN+set}"
  echo "bbparent:${BB_ACCOUNT_POOL_PARENT_TOKEN+set}"
  echo "message:${CLAUDE_CODE_MESSAGING_TOKEN+set}"
} > "$FAKE_ENV_LOG"
[[ "${LEAK:-}" != *err* ]] || echo "auth detail ${LEAKVAL}" >&2
echo "kimi answer ${LEAKVAL:-}"
FAKE
    cat > "$T/bin/codex" <<'FAKE'
#!/usr/bin/env bash
if [[ "${1:-}" == --version ]]; then echo "codex-cli 9.9.9"; exit 0; fi
{
  echo "anthropic:${ANTHROPIC_AUTH_TOKEN+set}"
  echo "bbparent:${BB_ACCOUNT_POOL_PARENT_TOKEN+set}"
  echo "message:${CLAUDE_CODE_MESSAGING_TOKEN+set}"
} > "$FAKE_ENV_LOG"
[[ "${LEAK:-}" != *err* ]] || echo "auth detail ${LEAKVAL}" >&2
[[ "${LEAK:-}" != *event* ]] || jq -cn --arg t "${LEAKVAL:-}" '{type:"note",note:$t}'
echo '{"type":"turn.completed"}'
FAKE
    # Leak hook: records its arguments and never sees the token.
    cat > "$T/bin/hook" <<'FAKE'
#!/usr/bin/env bash
{ echo "argc=$#"; echo "arg1=$1"; echo "token=${ANTHROPIC_AUTH_TOKEN+set}"
  echo "codex=${CODEX_POOL_AUTH_TOKEN+set}"; echo "parent=${BB_ACCOUNT_POOL_PARENT_TOKEN+set}"
  echo "message=${CLAUDE_CODE_MESSAGING_TOKEN+set}"; } > "$HOOK_LOG"
FAKE
    chmod +x "$T"/bin/*
    export PATH="$T/bin:$PATH"
    export FAKE_ENV_LOG="$T/env.log" HOOK_LOG="$T/hook.log"
    export CLAVAIN_CONTEXT_GATEWAY_MODE=off CLAVAIN_BB_DIRECT_POOL=0
    export CLAVAIN_DISPATCH_RECEIPT_FILE="$T/state/receipts.jsonl"
    export ANTHROPIC_AUTH_TOKEN="$DUMMY"
    export BB_ACCOUNT_POOL_PARENT_TOKEN=dummy-parent-value CLAUDE_CODE_MESSAGING_TOKEN=dummy-message-value
    unset CLAVAIN_BEAD_ID BB_THREAD_ID BB_SERVER_URL ANTHROPIC_BASE_URL CLAUDE_SESSION_ID CODEX_THREAD_ID \
        DISPATCH_SESSION_ID CLAVAIN_TOKEN_LEAK_HOOK CODEX_POOL_AUTH_TOKEN
}

teardown() { rm -rf "$T"; }

governed() { _governed bash "$@"; }
governed_exec() { _governed exec "$@"; }
_governed() {
    "$1" "$DISPATCH" --role validation --role-resolved --resolved-profile-ref p1 \
        --resolved-route-json "{\"policy_hash\":\"$POLICY_HASH\"}" \
        --resolved-profile-json '{"profile_ref":"p1"}' --producer-identity prod-model \
        --to claude --model m1 --reasoning-effort high -C "$T/repo" \
        --prompt-file "$T/prompt.md" -o "$T/out.md" "${@:2}"
}

# ---- environment handling ---------------------------------------------------

@test "claude backend keeps the pooled token; the other two bearer tokens are unset" {
    run governed
    [ "$status" -eq 0 ]
    grep -qx 'anthropic:set' "$T/env.log"
    grep -qx 'bbparent:' "$T/env.log"
    grep -qx 'message:' "$T/env.log"
}

@test "kimi backend loses all three tokens" {
    printf '[models."k"]\nmodel = "k"\n' > "$T/kimi.toml"
    KIMI_CONFIG="$T/kimi.toml" run bash "$DISPATCH" --to kimi -C "$T/repo" --prompt-file "$T/prompt.md" -o "$T/out.md"
    [ "$status" -eq 0 ]
    grep -qx 'anthropic:' "$T/env.log"
    grep -qx 'bbparent:' "$T/env.log"
    grep -qx 'message:' "$T/env.log"
}

@test "codex backend loses all three tokens" {
    run bash "$DISPATCH" --to codex -C "$T/repo" --prompt-file "$T/prompt.md" -o "$T/out.md"
    [ "$status" -eq 0 ]
    grep -qx 'anthropic:' "$T/env.log"
    grep -qx 'bbparent:' "$T/env.log"
    grep -qx 'message:' "$T/env.log"
}

# ---- leak scan --------------------------------------------------------------

@test "no leak: exit 0, no report, output unchanged, receipt completed" {
    run governed
    [ "$status" -eq 0 ]
    [ "$(cat "$T/out.md")" = "clean answer" ]
    [ ! -e "$T/out.md.token-leak.json" ]
    [ "$(jq -r .outcome "$T/state/receipts.jsonl")" = completed ]
    [[ "$output" != *"token leak"* ]]
}

@test "token in the output file fails the run and is redacted in place" {
    LEAK=out run governed
    [ "$status" -ne 0 ]
    ! grep -qF "$DUMMY" "$T/out.md"
    grep -qF '[REDACTED:anthropic-token]' "$T/out.md"
    [ "$(jq -r .outcome "$T/state/receipts.jsonl")" = failed ]
    grep -q '^STATUS: error' "$T/out.md.verdict"
    ! grep -qiE 'STATUS: *(pass|clean)' "$T/out.md.verdict"
}

@test "token in a provider-events sidecar is found and redacted" {
    LEAK=event run governed
    [ "$status" -ne 0 ]
    # the output itself was clean; only the events file carried the value
    [ "$(cat "$T/out.md")" = "clean answer" ]
    ev="$(ls "$T"/out.md.provider-events.*.jsonl)"
    ! grep -qF "$DUMMY" "$ev"
    grep -qF '[REDACTED:anthropic-token]' "$ev"
    jq -e --arg f "$ev" '.files | map(.path) | index($f) != null' "$T/out.md.token-leak.json" >/dev/null
}

@test "token in captured stderr is redacted before it is mirrored and fails the run" {
    LEAK=err run governed
    [ "$status" -ne 0 ]
    [[ "$output" != *"$DUMMY"* ]]
    [[ "$output" == *"leak report: $T/out.md.token-leak.json"* ]]
    # the mirror has its own sanitizer, so prove the dispatch scan itself caught it
    jq -e '.files | map(select(.path | endswith(".stderr"))) | length == 1' "$T/out.md.token-leak.json" >/dev/null
}

@test "a hit writes a report without the value and names it in one error line" {
    CLAVAIN_BEAD_ID=mk-test LEAK=out,event run governed
    [ "$status" -ne 0 ]
    rep="$T/out.md.token-leak.json"
    [ -f "$rep" ]
    ! grep -qF "$DUMMY" "$rep"
    [ "$(jq -r .kind "$rep")" = anthropic-token-leak ]
    [ "$(jq -r .bead "$rep")" = mk-test ]
    [ "$(jq -r .role "$rep")" = validation ]
    jq -e '.run_id | length > 0' "$rep" >/dev/null
    jq -e '.timestamp | test("^[0-9]{4}-.*Z$")' "$rep" >/dev/null
    jq -e '.files | length >= 2' "$rep" >/dev/null
    jq -e '.total_count >= 2' "$rep" >/dev/null
    [ "$(printf '%s\n' "$output" | grep -c 'leak report:')" -eq 1 ]
}

@test "the leak hook runs with the report path as its only argument and no token" {
    CLAVAIN_TOKEN_LEAK_HOOK="$T/bin/hook" LEAK=out run governed
    [ "$status" -ne 0 ]
    grep -qx 'argc=1' "$T/hook.log"
    grep -qx "arg1=$T/out.md.token-leak.json" "$T/hook.log"
    grep -qx 'token=' "$T/hook.log"
    grep -qx 'codex=' "$T/hook.log"
    grep -qx 'parent=' "$T/hook.log"
    grep -qx 'message=' "$T/hook.log"
}

@test "a hook that is not executable is ignored" {
    printf '#!/usr/bin/env bash\ntouch "$HOOK_LOG"\n' > "$T/nohook"
    CLAVAIN_TOKEN_LEAK_HOOK="$T/nohook" LEAK=out run governed
    [ "$status" -ne 0 ]
    [ ! -e "$T/hook.log" ]
}

@test "the token value never reaches any child command line" {
    export PATH="$T/spy:$PATH"
    mkdir -p "$T/spy"
    real_py="$(command -v python3)"
    cat > "$T/spy/python3" <<SPY
#!/usr/bin/env bash
printf '%s\\0' "\$@" >> "$T/argv.log"
exec "$real_py" "\$@"
SPY
    chmod +x "$T/spy/python3"
    LEAK=out run governed
    [ "$status" -ne 0 ]
    [ -s "$T/argv.log" ]
    grep -aq 'token-leak-scan.py' "$T/argv.log"
    ! grep -aqF "$DUMMY" "$T/argv.log"
}

@test "unset token: scan skipped with a logged note, run unaffected" {
    unset ANTHROPIC_AUTH_TOKEN
    run governed
    [ "$status" -eq 0 ]
    [[ "$output" == *"token leak scan skipped"* ]]
    [ ! -e "$T/out.md.token-leak.json" ]
}

@test "a short token is scanned and redacted" {
    export ANTHROPIC_AUTH_TOKEN=abc12
    LEAK=out run governed
    [ "$status" -ne 0 ]
    ! grep -qF abc12 "$T/out.md"
    grep -qF '[REDACTED:anthropic-token]' "$T/out.md"
    [ -f "$T/out.md.token-leak.json" ]
}

# ---- helper -----------------------------------------------------------------

@test "helper redacts the JSON-escaped form too and keeps file mode" {
    export ANTHROPIC_AUTH_TOKEN='sk-test-dummy-"quoted"-0123456789'
    printf '{"k":"sk-test-dummy-\\"quoted\\"-0123456789"}\n' > "$T/ev.jsonl"
    chmod 640 "$T/ev.jsonl"
    run python3 "$ROOT/scripts/token-leak-scan.py" scan --hits "$T/hits" -- "$T/ev.jsonl" "$T/missing"
    [ "$status" -eq 3 ]
    grep -qF '[REDACTED:anthropic-token]' "$T/ev.jsonl"
    ! grep -qF 'quoted' "$T/ev.jsonl"
    [ "$(stat -c %a "$T/ev.jsonl")" = 640 ]
}

# ---- every engine is scanned -----------------------------------------------

codex_run() { bash "$DISPATCH" --to codex -C "$T/repo" --prompt-file "$T/prompt.md" -o "$T/out.md" "$@"; }

@test "codex (direct): a leak in stderr or events fails the run and is redacted" {
    export LEAKVAL="$DUMMY"
    LEAK=err,event run codex_run
    [ "$status" -ne 0 ]
    [[ "$output" != *"$DUMMY"* ]]
    [ -f "$T/out.md.token-leak.json" ]
    ! grep -rqF "$DUMMY" "$T" --exclude=env.log --exclude=hook.log --exclude-dir=bin
}

@test "codex (pooled alias): the pool token value is scanned when only it is set" {
    unset ANTHROPIC_AUTH_TOKEN
    export CODEX_POOL_AUTH_TOKEN="$DUMMY" LEAKVAL="$DUMMY"
    LEAK=err run codex_run
    [ "$status" -ne 0 ]
    [[ "$output" != *"$DUMMY"* ]]
    [ -f "$T/out.md.token-leak.json" ]
}

@test "kimi: a leak in the output fails the run and is redacted" {
    printf '[models."k"]\nmodel = "k"\n' > "$T/kimi.toml"
    export LEAKVAL="$DUMMY"
    KIMI_CONFIG="$T/kimi.toml" run bash "$DISPATCH" --to kimi -C "$T/repo" --prompt-file "$T/prompt.md" -o "$T/out.md"
    [ "$status" -ne 0 ]
    ! grep -qF "$DUMMY" "$T/out.md"
    [ -f "$T/out.md.token-leak.json" ]
}

mock_scripts() {
    # a private copy of scripts/ whose flere worker and bb seat worker are stubs
    mkdir -p "$T/mock"
    cp -r "$ROOT/scripts" "$T/mock/scripts"
    local d
    for d in config .claude-plugin docs hooks; do
        [[ ! -e "$ROOT/$d" ]] || ln -s "$ROOT/$d" "$T/mock/$d"
    done
    cat > "$T/mock/scripts/flere-worker.py" <<'W'
import sys
out = sys.argv[sys.argv.index("--output") + 1]
open(out, "w").write("worker wrote " + __import__("os").environ["LEAKVAL"] + "\n")
W
    MOCK_DISPATCH="$T/mock/scripts/dispatch.sh"
}

@test "flere: the output is scanned after the worker and a hit fails the run" {
    mock_scripts
    mkdir -p "$T/project" "$T/profile"
    printf '{}\n' > "$T/profile/models.json"
    export CLAVAIN_FLERE_BIN=/usr/bin/true CLAVAIN_FLERE_PROFILE="$T/profile"
    export IC_DISPATCH_ID=d IC_RUN_ID=r IC_PROMPT_HASH=h LEAKVAL="$DUMMY"
    run bash "$MOCK_DISPATCH" --to flere -C "$T/project" -o "$T/out.md" -m provider/model "inspect"
    [ "$status" -ne 0 ]
    ! grep -qF "$DUMMY" "$T/out.md"
    grep -qF '[REDACTED:anthropic-token]' "$T/out.md"
    [ -f "$T/out.md.token-leak.json" ]
}

flere_setup() {
    mock_scripts
    mkdir -p "$T/project" "$T/profile"
    printf '{}\n' > "$T/profile/models.json"
    export CLAVAIN_FLERE_BIN=/usr/bin/true CLAVAIN_FLERE_PROFILE="$T/profile"
    export IC_DISPATCH_ID=d IC_RUN_ID=r IC_PROMPT_HASH=h LEAKVAL="$DUMMY"
}

# a stub worker that writes the dummy value only under <output>.attempt
flere_attempt_worker() {
    cat > "$T/mock/scripts/flere-worker.py" <<'W'
import os, sys, time
out = sys.argv[sys.argv.index("--output") + 1]
att = out + ".attempt"
os.makedirs(att + "/session/nested")
open(att + "/prompt.txt", "w").write("prompt\n")
open(att + "/rpc.jsonl", "w").write("event " + os.environ["LEAKVAL"] + "\n")
open(att + "/session/nested/s.jsonl", "w").write("deep " + os.environ["LEAKVAL"] + "\n")
open(out, "w").write("clean worker output\n")
if os.environ.get("SLOW"):
    open(os.environ["SLOW"], "w").close()
    time.sleep(3)
W
}

@test "flere: a value written only under the attempt directory fails the run and is redacted" {
    flere_setup
    flere_attempt_worker
    run bash "$MOCK_DISPATCH" --to flere -C "$T/project" -o "$T/out.md" -m provider/model "inspect"
    [ "$status" -ne 0 ]
    ! grep -rqF "$DUMMY" "$T/out.md.attempt"
    grep -qF '[REDACTED:anthropic-token]' "$T/out.md.attempt/rpc.jsonl"
    grep -qF '[REDACTED:anthropic-token]' "$T/out.md.attempt/session/nested/s.jsonl"
    ! grep -qF "$DUMMY" "$T/out.md.token-leak.json"
    jq -e '.files | length == 2' "$T/out.md.token-leak.json" >/dev/null
}

@test "flere: a clean attempt directory passes" {
    flere_setup
    flere_attempt_worker
    export LEAKVAL=clean-value-not-the-token
    run bash "$MOCK_DISPATCH" --to flere -C "$T/project" -o "$T/out.md" -m provider/model "inspect"
    [ "$status" -eq 0 ]
    [ ! -e "$T/out.md.token-leak.json" ]
}

@test "flere: a signal still scans the output and the attempt directory from the exit trap" {
    flere_setup
    flere_attempt_worker
    export SLOW="$T/slow.flag"
    exec_flere() {
        exec bash "$MOCK_DISPATCH" --to flere -C "$T/project" -o "$T/out.md" -m provider/model "inspect"
    }
    exec_flere > "$T/run.out" 2>&1 &
    pid=$!
    for _ in $(seq 1 100); do [ -e "$T/slow.flag" ] && break; sleep 0.1; done
    [ -e "$T/slow.flag" ]
    kill -TERM "$pid"
    rc=0
    wait "$pid" || rc=$?
    [ "$rc" -ne 0 ]
    ! grep -rqF "$DUMMY" "$T/out.md.attempt"
    grep -qF '[REDACTED:anthropic-token]' "$T/out.md.attempt/rpc.jsonl"
    pkill -f "$T/mock/scripts/flere-worker.py" || true
}

@test "flere: a symlink under the attempt directory pointing outside the roots is not followed" {
    flere_setup
    flere_attempt_worker
    OUTSIDE_DIR="$(mktemp -d)"
    printf 'outside %s\n' "$DUMMY" > "$OUTSIDE_DIR/other.txt"
    cat >> "$T/mock/scripts/flere-worker.py" <<'W'
os.symlink(os.environ["OUTSIDE"], att + "/link.txt")
W
    OUTSIDE="$OUTSIDE_DIR/other.txt" run bash "$MOCK_DISPATCH" --to flere -C "$T/project" -o "$T/out.md" -m provider/model "inspect"
    [ "$status" -ne 0 ]
    grep -qF "$DUMMY" "$OUTSIDE_DIR/other.txt"
    rm -rf "$OUTSIDE_DIR"
}

@test "bb seat: the output and its receipt are scanned and a hit fails the run" {
    mock_scripts
    printf 'import sys\nsys.exit(0)\n' > "$T/mock/scripts/bb-host.py"
    cat > "$T/mock/scripts/bb-seat.py" <<'W'
import os, sys
out = sys.argv[sys.argv.index("--output") + 1]
open(out, "w").write("seat wrote " + os.environ["LEAKVAL"] + "\n")
open(out + ".receipt.json", "w").write('{"note":"' + os.environ["LEAKVAL"] + '"}\n')
W
    export LEAKVAL="$DUMMY"
    run bash "$MOCK_DISPATCH" --role validation --role-resolved --resolved-profile-ref p1 \
        --resolved-route-json "{\"policy_hash\":\"$POLICY_HASH\"}" \
        --resolved-profile-json '{"profile_ref":"p1"}' --producer-identity prod-model \
        --to claude --via bb --model m1 --reasoning-effort high -C "$T/repo" \
        --prompt-file "$T/prompt.md" -o "$T/out.md"
    [ "$status" -ne 0 ]
    ! grep -qF "$DUMMY" "$T/out.md" "$T/out.md.receipt.json"
    [ -f "$T/out.md.token-leak.json" ]
}

# ---- scan after the last write ---------------------------------------------

review() {
    bash "$DISPATCH" --role cross-lab-review --role-resolved --resolved-profile-ref p1 \
        --resolved-route-json "{\"policy_hash\":\"$POLICY_HASH\"}" \
        --resolved-profile-json '{"profile_ref":"p1"}' --producer-identity gpt-6.1-sol \
        --to claude --model claude-opus-5-5 --reasoning-effort high -C "$T/repo" \
        --prompt-file "$T/prompt.md" -o "$T/out.md" \
        --repo o/r --repo-id R_x --pr 7 --head "$HEADSHA" --base "$BASESHA" "$@"
}

review_setup() {
    BASESHA="$(git -C "$T/repo" rev-parse HEAD)"
    printf 'y\n' > "$T/repo/f-$DUMMY.txt"
    git -C "$T/repo" -c user.name=t -c user.email=t@t add .
    git -C "$T/repo" -c user.name=t -c user.email=t@t commit -q -m two
    HEADSHA="$(git -C "$T/repo" rev-parse HEAD)"
    export CLAVAIN_REVIEW_RECEIPT_DIR="$T/reviews"
    export BODY=$'Findings: none\n\nVERDICT: PASS'
}

@test "the review receipt directory is scanned after the receipt is written" {
    review_setup
    run review
    [ "$status" -ne 0 ]
    rec="$(ls "$T"/reviews/o__r/7-*.json | head -1)"
    ! grep -qF "$DUMMY" "$rec"
    grep -qF '[REDACTED:anthropic-token]' "$rec"
    [ -f "$T/out.md.token-leak.json" ]
}

@test "the run receipt is scanned after it is appended" {
    review_setup
    run review
    [ "$status" -ne 0 ]
    ! grep -qF "$DUMMY" "$T/state/receipts.jsonl"
}

@test "a token-bearing artifact path never reaches the report, hook argument, hits file or stderr" {
    LEAK=event TMPDIR="$T" CLAVAIN_TOKEN_LEAK_HOOK="$T/bin/hook" run governed -o "$T/o-$DUMMY.md"
    [ "$status" -ne 0 ]
    [[ "$output" != *"$DUMMY"* ]]
    ! grep -qF "$DUMMY" "$HOOK_LOG"
    # the report fell back to a neutral path and carries no value
    rep="$(ls "$T"/clavain-token-leak-*.json)"
    [ -f "$rep" ]
    ! grep -qF "$DUMMY" "$rep"
    grep -qx "arg1=$rep" "$HOOK_LOG"
    jq -e '.files | length >= 1' "$rep" >/dev/null
}

# ---- symlinks ---------------------------------------------------------------

@test "a run that writes through a symlinked output has the target scanned" {
    printf 'old\n' > "$T/real.md"
    ln -s real.md "$T/out.md"
    LEAK=out run governed
    [ "$status" -ne 0 ]
    [ -L "$T/out.md" ]
    ! grep -qF "$DUMMY" "$T/real.md"
    grep -qF '[REDACTED:anthropic-token]' "$T/real.md"
}

@test "a symlink that cannot be resolved to a file is reported and fails closed" {
    ln -s "$T/does-not-exist" "$T/out.md.provider-events.zz.jsonl"
    run governed
    [ "$status" -ne 0 ]
    [[ "$output" == *"could not scan"* ]]
    jq -e '.unscanned | length == 1' "$T/out.md.token-leak.json" >/dev/null
    ! grep -qF "$DUMMY" "$T/out.md.token-leak.json"
}

@test "a symlinked artifact pointing outside the run roots is not opened or modified, and fails the run" {
    OUTSIDE_DIR="$(mktemp -d)"
    printf 'outside %s\n' "$DUMMY" > "$OUTSIDE_DIR/other.txt"
    before="$(sha256sum "$OUTSIDE_DIR/other.txt")"
    ln -s "$OUTSIDE_DIR/other.txt" "$T/out.md.provider-events.zz.jsonl"
    run governed
    [ "$status" -ne 0 ]
    [[ "$output" == *"could not scan"* ]]
    [ "$(sha256sum "$OUTSIDE_DIR/other.txt")" = "$before" ]
    rm -rf "$OUTSIDE_DIR"
    jq -e '.unscanned | length == 1' "$T/out.md.token-leak.json" >/dev/null
    ! grep -qF "$DUMMY" "$T/out.md.token-leak.json"
}

@test "scanner: a symlink is followed only into a given root" {
    export ANTHROPIC_AUTH_TOKEN=abc12
    mkdir "$T/in" "$T/out"
    printf 'x abc12 y\n' > "$T/in/real.txt"
    printf 'x abc12 y\n' > "$T/out/other.txt"
    ln -s "$T/in/real.txt" "$T/in/ok-link"
    ln -s "$T/out/other.txt" "$T/in/bad-link"
    run python3 -I "$ROOT/scripts/token-leak-scan.py" scan --hits "$T/hits" --root "$T/in" "$T/in/bad-link"
    [ "$status" -eq 4 ]
    grep -q abc12 "$T/out/other.txt"
    run python3 -I "$ROOT/scripts/token-leak-scan.py" scan --hits "$T/hits" "$T/in/ok-link"
    [ "$status" -eq 4 ]
    grep -q abc12 "$T/in/real.txt"
    run python3 -I "$ROOT/scripts/token-leak-scan.py" scan --hits "$T/hits" --root "$T/in" "$T/in/ok-link"
    [ "$status" -eq 3 ]
    ! grep -q abc12 "$T/in/real.txt"
}

@test "scanner: a symlinked parent directory pointing outside the root is not read or rewritten" {
    export ANTHROPIC_AUTH_TOKEN=abc12
    mkdir "$T/in" "$T/out"
    printf 'x abc12 y\n' > "$T/out/other.txt"
    before="$(sha256sum "$T/out/other.txt")"
    ln -s "$T/out" "$T/in/dir-link"
    run python3 -I "$ROOT/scripts/token-leak-scan.py" scan --hits "$T/hits" --root "$T/in" "$T/in/dir-link/other.txt"
    [ "$status" -eq 4 ]
    [ "$(sha256sum "$T/out/other.txt")" = "$before" ]
    # a symlinked parent that stays inside the root is still scanned
    mkdir "$T/in/real"
    printf 'x abc12 y\n' > "$T/in/real/f.txt"
    ln -s "$T/in/real" "$T/in/ok-dir"
    run python3 -I "$ROOT/scripts/token-leak-scan.py" scan --hits "$T/hits" --root "$T/in" "$T/in/ok-dir/f.txt"
    [ "$status" -eq 3 ]
    run grep -q abc12 "$T/in/real/f.txt"
    [ "$status" -eq 1 ]
}

@test "scanner: a value that matches a fixed key of the hit record never reaches the hits file" {
    for tok in count file unscanned; do
        export ANTHROPIC_AUTH_TOKEN="$tok"
        printf 'x %s y\n' "$tok" > "$T/m.txt"
        : > "$T/hits"
        run python3 -I "$ROOT/scripts/token-leak-scan.py" scan --hits "$T/hits" "$T/m.txt"
        [ "$status" -eq 3 ]
        run grep -q "$tok" "$T/hits"
        [ "$status" -eq 1 ]
        run grep -q "$tok" "$T/m.txt"
        [ "$status" -eq 1 ]
    done
}

@test "a fallback report path that carries a value is not used, passed to the hook or printed" {
    export ANTHROPIC_AUTH_TOKEN=token-leak
    LEAK=event TMPDIR="$T" CLAVAIN_TOKEN_LEAK_HOOK="$T/bin/hook" run governed -o "$T/o-token-leak.md"
    [ "$status" -ne 0 ]
    [[ "$output" != *token-leak* ]]
    [[ "$output" == *"no value-free path"* ]]
    [ ! -e "$T/hook.log" ]
    run ls "$T"/clavain-token-leak-*.json
    [ "$status" -ne 0 ]
}

# ---- signals ---------------------------------------------------------------

@test "a signal still runs the scan from the exit trap" {
    export SLOW="$T/slow.flag" LEAK=event
    governed_exec > "$T/run.out" 2>&1 &
    pid=$!
    for _ in $(seq 1 100); do [ -e "$T/slow.flag" ] && break; sleep 0.1; done
    [ -e "$T/slow.flag" ]
    kill -TERM "$pid"
    wait "$pid" || true
    ev="$(ls "$T"/out.md.provider-events.*.jsonl)"
    ! grep -qF "$DUMMY" "$ev"
    grep -qF '[REDACTED:anthropic-token]' "$ev"
    pkill -f "$T/bin/claude" || true
}

# ---- hook isolation ----------------------------------------------------------

@test "the hook sees none of the four tokens, including the pooled alias" {
    export CODEX_POOL_AUTH_TOKEN="$DUMMY"
    CLAVAIN_TOKEN_LEAK_HOOK="$T/bin/hook" LEAK=out run governed
    [ "$status" -ne 0 ]
    grep -qx 'token=' "$T/hook.log"
    grep -qx 'codex=' "$T/hook.log"
    grep -qx 'parent=' "$T/hook.log"
    grep -qx 'message=' "$T/hook.log"
}

# ---- zaka and preflight ------------------------------------------------------

@test "zaka --to claude keeps the token for both claude names; other agents lose it" {
    mkdir -p "$T/zbin"
    cat > "$T/zbin/zaka" <<'Z'
#!/usr/bin/env bash
echo "agent=$3 token=${ANTHROPIC_AUTH_TOKEN+set}" >> "$ZAKA_LOG"
echo session-1
Z
    printf '#!/usr/bin/env bash\nexit 0\n' > "$T/zbin/tmux"
    chmod +x "$T/zbin/zaka" "$T/zbin/tmux"
    for to in claude claude-code kimi; do
        export ZAKA_LOG="$T/zaka-$to.log"
        PATH="$T/zbin:$PATH" run bash "$DISPATCH" --via zaka --to "$to" -C "$T/repo" "hello"
        [ -s "$ZAKA_LOG" ]
    done
    grep -q 'token=set' "$T/zaka-claude.log"
    grep -q 'token=set' "$T/zaka-claude-code.log"
    ! grep -q 'token=set' "$T/zaka-kimi.log"
}

@test "the codex version preflight runs without the claude bearer token" {
    cat > "$T/bin/codex" <<'FAKE'
#!/usr/bin/env bash
if [[ "${1:-}" == --version ]]; then
  echo "version:${ANTHROPIC_AUTH_TOKEN+set}" >> "$FAKE_ENV_LOG.version"
  echo "codex-cli 9.9.9"; exit 0
fi
echo '{"type":"turn.completed"}'
FAKE
    # The direct codex path unsets the token first; the profile-fallback loops
    # call the preflight while a Claude-backed run still holds it, so exercise
    # the function itself with the token present.
    export ANTHROPIC_AUTH_TOKEN="$DUMMY"
    export FAKE_ENV_LOG="$T/env.log" PATH="$T/bin:$PATH"
    sed -n '/^_codex_version_at_least() {/,/^}/p' "$DISPATCH" > "$T/fn.sh"
    [ -s "$T/fn.sh" ]
    run bash -c 'source "$1"; _codex_version_at_least 1.0.0' _ "$T/fn.sh"
    [ "$status" -eq 0 ]
    [ -s "$T/env.log.version" ]
    ! grep -q 'set' "$T/env.log.version"
}

# ---- the scanner itself -------------------------------------------------------

@test "scanner runs under python3 -OO" {
    export ANTHROPIC_AUTH_TOKEN=abc12
    printf 'x abc12 y\n' > "$T/a.txt"
    run python3 -I -OO "$ROOT/scripts/token-leak-scan.py" scan --hits "$T/hits" "$T/a.txt"
    [ "$status" -eq 3 ]
    ! grep -q abc12 "$T/a.txt"
    run python3 -I -OO "$ROOT/scripts/token-leak-scan.py" --help
    [ "$status" -eq 0 ]
}

@test "scanner: an internal error prints only a fixed message" {
    export ANTHROPIC_AUTH_TOKEN=abc12
    # a hits path whose directory is missing forces an exception that names the path
    run python3 -I "$ROOT/scripts/token-leak-scan.py" scan --hits "$T/abc12-missing-dir/hits" "$T/a.txt"
    [ "$status" -eq 4 ]
    [ "$output" = "token-leak-scan: internal error (details withheld)" ]
    run python3 -I "$ROOT/scripts/token-leak-scan.py" scan --hits "$T/h" --bogus-abc12
    [ "$status" -eq 2 ]
    [[ "$output" != *abc12* ]]
}

@test "scanner: a dangling symlink and a token-bearing name are handled without leaking" {
    export ANTHROPIC_AUTH_TOKEN=abc12
    ln -s "$T/nowhere" "$T/dangling-abc12"
    run python3 -I "$ROOT/scripts/token-leak-scan.py" scan --hits "$T/hits" "$T/dangling-abc12"
    [ "$status" -eq 4 ]
    [[ "$output" != *abc12* ]]
    ! grep -q abc12 "$T/hits"
}

@test "scanner: a value that is part of the default marker is still fully redacted" {
    for tok in token e '[' REDACTED anthropic ':'; do
        export ANTHROPIC_AUTH_TOKEN="$tok"
        printf 'x %s y\n' "$tok" > "$T/m.txt"
        : > "$T/hits"
        run python3 -I "$ROOT/scripts/token-leak-scan.py" scan --hits "$T/hits" "$T/m.txt"
        [ "$status" -eq 3 ]
        run python3 -I -c 'import sys; sys.exit(0 if sys.argv[1].encode() in open(sys.argv[2], "rb").read() else 1)' "$tok" "$T/m.txt"
        [ "$status" -eq 1 ]
    done
}

@test "scanner: a marker-colliding value is absent from the hits file and the sanitized file names" {
    for tok in token e '[' REDACTED; do
        export ANTHROPIC_AUTH_TOKEN="$tok"
        d="$T/d-$RANDOM"; mkdir -p "$d"
        printf 'x %s y\n' "$tok" > "$d/$tok-name.txt"
        : > "$T/hits"
        run python3 -I "$ROOT/scripts/token-leak-scan.py" scan --hits "$T/hits" "$d/$tok-name.txt"
        [ "$status" -eq 3 ]
        run python3 -I -c 'import json, sys
tok = sys.argv[1]
for line in open(sys.argv[2]):
    rec = json.loads(line)
    assert tok not in rec["file"], "value in sanitized name"' "$tok" "$T/hits"
        [ "$status" -eq 0 ]
    done
}

@test "scanner: the report never contains a colliding value; a report that cannot be made value-free is not written" {
    export ANTHROPIC_AUTH_TOKEN=REDACTED
    printf '{"file":"a/REDACTED/b","count":1}\n' > "$T/hits"
    run python3 -I "$ROOT/scripts/token-leak-scan.py" report --hits "$T/hits" --report "$T/r.json" --bead fixture-bead
    [ "$status" -eq 0 ]
    ! grep -q REDACTED "$T/r.json"
    # a value that is also in the fixed report text cannot be removed from it
    export ANTHROPIC_AUTH_TOKEN=files
    rm -f "$T/r.json"
    run python3 -I "$ROOT/scripts/token-leak-scan.py" report --hits "$T/hits" --report "$T/r.json"
    [ "$status" -eq 4 ]
    [ "$output" = "token-leak-scan: internal error (details withheld)" ]
    [ ! -e "$T/r.json" ]
}

@test "scanner: when no marker can be verified the file is left alone and the run fails closed" {
    python3 -I - "$ROOT/scripts/token-leak-scan.py" "$T" <<'PY'
import os, subprocess, sys
script, tmp = sys.argv[1], sys.argv[2]
# every ASCII character is itself a value, so no character is free for a marker
path = os.path.join(tmp, "all.txt")
open(path, "wb").write(b"abc XYZ [REDACTED]")
env = {b"PATH": os.environb.get(b"PATH", b"")}
cmd = [sys.executable.encode(), b"-I", script.encode(), b"scan", b"--hits",
       os.path.join(tmp, "h").encode()]
for code in range(1, 128):
    name = b"CLAVAIN_LEAK_TOKEN_%d" % code
    env[name] = bytes([code])
    cmd += [b"--token-env", name]
cmd.append(path.encode())
r = subprocess.run(cmd, env=env, capture_output=True)
assert r.returncode == 4, r.returncode
assert open(path, "rb").read() == b"abc XYZ [REDACTED]"
PY
}

@test "scanner: an import-time failure prints only the fixed message" {
    # make an import of json fail inside the interpreter before main runs
    run python3 -I -c 'import sys, runpy
sys.modules["json"] = None
runpy.run_path(sys.argv[1], run_name="__main__")' "$ROOT/scripts/token-leak-scan.py" scan --hits "$T/h"
    [ "$status" -eq 4 ]
    [ "$output" = "token-leak-scan: internal error (details withheld)" ]
}

# mk-47vtm.4: every scanner message goes through one checked printer, so a
# token that occurs in a fixed message (here a single ':' or a word of it) is
# never echoed. Dummy values only.
_scan_no_echo() {
    # $1 dummy value; remaining args: scanner arguments. Sets $status, $output.
    local value="$1"; shift
    ANTHROPIC_AUTH_TOKEN="$value" run python3 -I "$ROOT/scripts/token-leak-scan.py" "$@"
}

@test "scanner: the internal-error message is never printed when a value occurs in it" {
    local v
    for v in ':' 'internal' 'withheld' 'e'; do
        _scan_no_echo "$v" scan --hits "$T/missing-dir/hits" "$T/a.txt"
        [ "$status" -eq 4 ]
        [[ "$output" != *"$v"* ]]
    done
}

@test "scanner: the invalid-arguments message is never printed when a value occurs in it" {
    local v
    for v in ':' 'invalid' 'arguments'; do
        _scan_no_echo "$v" scan --hits "$T/h" --bogus
        [ "$status" -eq 2 ]
        [[ "$output" != *"$v"* ]]
    done
}

@test "scanner: the could-not-scan message is never printed when a value occurs in it" {
    local v
    ln -s "$T/nowhere" "$T/dangling"
    for v in ':' 'closed' 'failing'; do
        _scan_no_echo "$v" scan --hits "$T/hits" "$T/dangling"
        [ "$status" -eq 4 ]
        [[ "$output" != *"$v"* ]]
    done
}

@test "scanner: usage and --help text never contain a value" {
    local v
    for v in ':' 'Post-run' 'usage'; do
        _scan_no_echo "$v" --help
        [ "$status" -eq 0 ]
        [[ "$output" != *"$v"* ]]
    done
}

@test "scanner: an import-time failure prints nothing when a value occurs in the message" {
    local v
    for v in ':' 'internal'; do
        ANTHROPIC_AUTH_TOKEN="$v" run python3 -I -c 'import sys, runpy
sys.modules["json"] = None
runpy.run_path(sys.argv[1], run_name="__main__")' "$ROOT/scripts/token-leak-scan.py" scan --hits "$T/h"
        [ "$status" -eq 4 ]
        [[ "$output" != *"$v"* ]]
    done
}

@test "scanner: a value from a --token-env variable is checked too" {
    CUSTOM_TOK=':' run python3 -I "$ROOT/scripts/token-leak-scan.py" scan --token-env CUSTOM_TOK --hits "$T/missing-dir/hits" "$T/a.txt"
    [ "$status" -eq 4 ]
    [[ "$output" != *:* ]]
}

@test "scanner: a message with no value in it is still printed" {
    _scan_no_echo 'zzzz' scan --hits "$T/missing-dir/hits" "$T/a.txt"
    [ "$status" -eq 4 ]
    [ "$output" = "token-leak-scan: internal error (details withheld)" ]
}
