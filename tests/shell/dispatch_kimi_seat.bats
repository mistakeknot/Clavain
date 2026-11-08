#!/usr/bin/env bats
# The role-resolved kimi review seat (validation-kimi, the third provider in the
# validation chain) must be able to run a plan's Verification, like the claude
# seat: Bash and read tools allowed, edit tools absent (bead mk-1rbg). Those
# tool names are a request to kimi, not a barrier, so what these tests pin is
# the containment: the seat runs in a disposable copy of the checkout at HEAD
# with a copy of the plan directory, any change to either copy is an error
# verdict, and the ruling is read only from kimi's final message. A bwrap
# sandbox adds a read-only root where bwrap works; without it nothing stops a
# write outside the copy, and the tests do not claim otherwise. A direct
# `--to kimi` dispatch stays toolless, because it may carry untrusted input.
# Dry-run tests assert on the assembled agent file; the run tests put a fake
# `kimi` on PATH that speaks kimi's stream-json.

setup() {
    load test_helper
    DISPATCH="$BATS_TEST_DIRNAME/../../scripts/dispatch.sh"
    T="$(mktemp -d)"
    mkdir -p "$T/plans" "$T/bin" "$T/repo"
    printf '# plan\n' > "$T/plans/plan.md"
    git -C "$T/repo" init -q
    printf 'x\n' > "$T/repo/f.txt"
    git -C "$T/repo" -c user.name=t -c user.email=t@t add f.txt
    git -C "$T/repo" -c user.name=t -c user.email=t@t commit -q -m base
    printf 'default_model = "kimi-code/k3"\n[models."kimi-code/k3"]\nprovider = "managed:kimi-code"\nmodel = "k3"\n' > "$T/kimi.toml"
    export KIMI_CONFIG="$T/kimi.toml"
    export CLAVAIN_CONTEXT_GATEWAY_MODE=off
    # A governed run needs the policy hash of the shipped policy and an `ic`.
    POLICY_HASH="$(sha256sum "$BATS_TEST_DIRNAME/../../config/routing.yaml" | awk '{print $1}')"
    printf '#!/usr/bin/env bash\nexit 0\n' > "$T/bin/ic"
    chmod +x "$T/bin/ic"
    unset CLAVAIN_BEAD_ID DISPATCH_SESSION_ID
    export CLAVAIN_DISPATCH_RECEIPT_FILE="$T/receipts.jsonl"
    # The fake kimi records into $T and mutates $T/repo, which a read-only root
    # would block; the bwrap test turns the sandbox back on.
    export CLAVAIN_SEAT_BWRAP=0
}

# A real (non-dry-run) governed validation dispatch resolved to the kimi seat.
governed_kimi() {
    PATH="$T/bin:$PATH" bash "$DISPATCH" --role validation --role-resolved --resolved-profile-ref p1 \
        --resolved-route-json "{\"policy_hash\":\"$POLICY_HASH\"}" \
        --resolved-profile-json '{"profile_ref":"p1"}' --producer-identity prod-model \
        --to kimi --model kimi-code/k3 "$@"
}

teardown() {
    rm -rf "$T"
}

# $1 = the fake seat's final message; $2 = optional shell to run first (a
# mutation); $3 = optional narration printed as an earlier assistant message;
# $4 = optional shell to run just after the final message (stream tampering).
# The fake speaks kimi's stream-json, records the agent file it was given, its
# argv and the directory it ran in.
fake_kimi() {
    cat > "$T/bin/kimi" <<EOF
#!/usr/bin/env bash
printf '%s ' "\$@" > "$T/kimi.argv"
pwd -P > "$T/kimi.pwd"
while [ \$# -gt 0 ]; do
  if [ "\$1" = --agent-file ]; then cp "\$2" "$T/kimi.agent"; fi
  shift
done
printf '{"role":"meta","type":"system.version","version":"0.42.0"}\n'
if [ -n "\${FAKE_NARRATION:-}" ]; then
  jq -cn --arg c "\$FAKE_NARRATION" '{role:"assistant",content:\$c,tool_calls:[{type:"function",id:"t1",function:{name:"Bash",arguments:"{}"}}]}'
  printf 'stray tool output\n'
  jq -cn '{role:"tool",tool_call_id:"t1",content:"ok\n"}'
fi
${2:-}
if [ -n "\${FAKE_BODY:-}" ]; then jq -cn --arg c "\$FAKE_BODY" '{role:"assistant",content:\$c}'; fi
${4:-}
printf '{"role":"meta","type":"session.resume_hint","session_id":"s"}\n'
EOF
    chmod +x "$T/bin/kimi"
    export FAKE_BODY="$1"
    export FAKE_NARRATION="${3:-}"
}

# the agent file path the dry-run command names
agent_file_of() {
    printf '%s\n' "$1" | grep -o -- '--agent-file [^ ]*' | head -1 | cut -d' ' -f2
}

@test "kimi seat: a resolved validation seat gets Bash and read tools, no edit tools" {
    run bash "$DISPATCH" --dry-run --role validation --role-resolved --to kimi --model kimi-code/k3 --plan "$T/plans/plan.md" -C "$T/repo" "prompt"
    [ "$status" -eq 0 ]
    f="$(agent_file_of "$output")"
    [ -r "$f" ]
    grep -q '^tools: \[Bash, Read, Glob, Grep\]$' "$f"
    grep -q '^disallowedTools: \[Write, Edit\]$' "$f"
    ! grep -q '^tools: \[\]$' "$f"
    [[ "$output" == *"--add-dir $T/plans"* ]]
    [[ "$output" == *"--output-format stream-json"* ]]
}

@test "kimi seat: cross-lab-review and plan-review seats get the same profile" {
    for role in cross-lab-review plan-review; do
        run bash "$DISPATCH" --dry-run --role "$role" --role-resolved --to kimi --model kimi-code/k3 -C "$T/repo" "prompt"
        [ "$status" -eq 0 ]
        f="$(agent_file_of "$output")"
        grep -q '^tools: \[Bash, Read, Glob, Grep\]$' "$f"
    done
}

@test "kimi seat: a direct --to kimi dispatch stays toolless" {
    run bash "$DISPATCH" --dry-run --to kimi --plan "$T/plans/plan.md" -C "$T/repo" "prompt"
    [ "$status" -eq 0 ]
    f="$(agent_file_of "$output")"
    grep -q '^tools: \[\]$' "$f"
    [[ "$output" != *"--add-dir"* ]]
}

@test "kimi seat: a role that is not a review seat stays toolless" {
    run bash "$DISPATCH" --dry-run --role scout --role-resolved --to kimi --model kimi-code/k3 -C "$T/repo" "prompt"
    [ "$status" -eq 0 ]
    f="$(agent_file_of "$output")"
    grep -q '^tools: \[\]$' "$f"
}

@test "kimi seat: --no-tools still refuses kimi (fails closed)" {
    run bash "$DISPATCH" --dry-run --role validation --role-resolved --to kimi --model kimi-code/k3 --no-tools -C "$T/repo" "prompt"
    [ "$status" -eq 1 ]
    [[ "$output" == *"--no-tools is enforceable only for a direct --to claude seat"* ]]
}

@test "kimi seat: the run is given the tool agent file and a copy of the plan directory, never the original" {
    fake_kimi $'VERDICT: PASS\nCRITERION: none'
    run governed_kimi --plan "$T/plans/plan.md" -C "$T/repo" -o "$T/out.md" "read $T/plans/plan.md"
    [ "$status" -eq 0 ]
    grep -q '^tools: \[Bash, Read, Glob, Grep\]$' "$T/kimi.agent"
    grep -q -- '--output-format stream-json' "$T/kimi.argv"
    ! grep -q -- "--add-dir $T/plans " "$T/kimi.argv"
    copy="$(grep -o -- '--add-dir [^ ]*' "$T/kimi.argv" | cut -d' ' -f2)"
    [[ "$copy" == */clavain-kimi-sandbox.*/plan ]]
    # the prompt's path into the plan directory points at the copy too
    grep -q -- "read $copy/plan.md" "$T/kimi.argv"
    ! grep -q -- "read $T/plans/plan.md" "$T/kimi.argv"
    # the agent file the seat read is a copy that names the plan copy
    grep -q "$copy" "$T/kimi.agent"
}

@test "kimi seat: the seat runs in a copy of the checkout at HEAD, not in the checkout" {
    printf 'dirty\n' > "$T/repo/uncommitted.txt"
    fake_kimi $'VERDICT: PASS\nCRITERION: none' "[ -f f.txt ] && [ ! -e uncommitted.txt ] && git rev-parse HEAD > \"$T/kimi.head\""
    run governed_kimi -C "$T/repo" -o "$T/out.md" "prompt"
    [ "$status" -eq 0 ]
    [[ "$output" == *"uncommitted changes"* ]]
    [[ "$(cat "$T/kimi.pwd")" == */clavain-kimi-sandbox.*/checkout ]]
    [ "$(cat "$T/kimi.head")" = "$(git -C "$T/repo" rev-parse HEAD)" ]
    # the copy is gone after the run
    [ ! -d "$(dirname "$(cat "$T/kimi.pwd")")" ]
}

@test "kimi seat: from a subdirectory the seat starts in the same subdirectory of the copy" {
    mkdir -p "$T/repo/sub" && printf 's\n' > "$T/repo/sub/s.txt"
    git -C "$T/repo" -c user.name=t -c user.email=t@t add sub/s.txt
    git -C "$T/repo" -c user.name=t -c user.email=t@t commit -q -m sub
    fake_kimi $'VERDICT: PASS\nCRITERION: none'
    run governed_kimi -C "$T/repo/sub" -o "$T/out.md" "prompt"
    [ "$status" -eq 0 ]
    [[ "$(cat "$T/kimi.pwd")" == */clavain-kimi-sandbox.*/checkout/sub ]]
}

@test "kimi seat: a run that mutates its copy is an error verdict and a failed dispatch, and the real checkout is untouched" {
    fake_kimi $'VERDICT: PASS\nCRITERION: none' "printf 'y\\n' >> f.txt; : > new.txt"
    run governed_kimi -C "$T/repo" -o "$T/out.md" "prompt"
    [ "$status" -ne 0 ]
    [[ "$output" == *"mutated the checkout"* ]]
    run cat "$T/out.md.verdict"
    [[ "$output" == *"STATUS: error"* ]]
    [[ "$output" == *"f.txt"* ]]
    [[ "$output" == *"new.txt"* ]]
    [ "$(cat "$T/repo/f.txt")" = x ]
    [ ! -e "$T/repo/new.txt" ]
}

@test "kimi seat: writes the old status snapshot could not see are errors too" {
    # content change of an untracked file restored to the same name, an ignored
    # file, a .git internal, a mode change, a symlink
    printf '*.log\n' > "$T/repo/.gitignore"
    git -C "$T/repo" -c user.name=t -c user.email=t@t add .gitignore
    git -C "$T/repo" -c user.name=t -c user.email=t@t commit -q -m ignore
    for body in "echo noise > ignored.log" "echo x > .git/planted" "chmod +x f.txt" "ln -s f.txt link" "mkdir emptydir"; do
        fake_kimi $'VERDICT: PASS\nCRITERION: none' "$body"
        run governed_kimi -C "$T/repo" -o "$T/out.md" "prompt"
        [ "$status" -ne 0 ] || { echo "not caught: $body"; return 1; }
        run cat "$T/out.md.verdict"
        [[ "$output" == *"STATUS: error"* ]] || { echo "no error verdict: $body"; return 1; }
    done
}

@test "kimi seat: a change to the plan copy is an error and the original plan is untouched" {
    fake_kimi $'VERDICT: PASS\nCRITERION: none' "echo tampered > \"\$(grep -o -- '--add-dir [^ ]*' \"$T/kimi.argv\" | cut -d' ' -f2)/plan.md\""
    run governed_kimi --plan "$T/plans/plan.md" -C "$T/repo" -o "$T/out.md" "prompt"
    [ "$status" -ne 0 ]
    run cat "$T/out.md.verdict"
    [[ "$output" == *"STATUS: error"* ]]
    [[ "$output" == *"plan-copy"* ]]
    [ "$(cat "$T/plans/plan.md")" = '# plan' ]
}

@test "kimi seat: a clean run keeps its verdict" {
    fake_kimi $'VERDICT: PASS\nCRITERION: none'
    run governed_kimi -C "$T/repo" -o "$T/out.md" "prompt"
    [ "$status" -eq 0 ]
    [[ "$output" != *"mutated the checkout"* ]]
    run cat "$T/out.md.verdict"
    [[ "$output" == *"STATUS: pass"* ]]
}

@test "kimi seat: a direct --to kimi run is not contained or snapshotted" {
    fake_kimi $'VERDICT: PASS\nCRITERION: none' ": > \"$T/repo/new.txt\""
    PATH="$T/bin:$PATH" run bash "$DISPATCH" --to kimi --model kimi-code/k3 -C "$T/repo" -o "$T/out.md" "prompt"
    [ "$status" -eq 0 ]
    [[ "$output" != *"mutated the checkout"* ]]
}

@test "kimi seat: narration before the ruling does not hide a real final verdict" {
    fake_kimi $'VERDICT: PASS\nCRITERION: bash check.sh printed NONCE-1' "" $'Executing the verification command:'
    run governed_kimi -C "$T/repo" -o "$T/out.md" "prompt"
    [ "$status" -eq 0 ]
    [ "$(head -1 "$T/out.md")" = "VERDICT: PASS" ]
    run cat "$T/out.md.verdict"
    [[ "$output" == *"STATUS: pass"* ]]
}

@test "kimi seat: a quoted VERDICT: PASS in narration is not the ruling when the final message says validation could not run" {
    fake_kimi $'I could not run the validation: bash is unavailable here.' "" $'The plan says to expect:\n\n• VERDICT: PASS\n\nNow running it.'
    run governed_kimi -C "$T/repo" -o "$T/out.md" "prompt"
    [ "$status" -ne 0 ]
    [[ "$output" == *"no usable ruling"* ]]
    run cat "$T/out.md.verdict"
    [[ "$output" == *"STATUS: error"* ]]
    [[ "$output" != *"STATUS: pass"* ]]
    ! grep -q 'VERDICT: PASS' "$T/out.md"
}

@test "kimi seat: a final message with no verdict is an error, never a pass" {
    fake_kimi $'Everything looks fine to me.' "" $'VERDICT: PASS'
    run governed_kimi -C "$T/repo" -o "$T/out.md" "prompt"
    [ "$status" -ne 0 ]
    run cat "$T/out.md.verdict"
    [[ "$output" == *"STATUS: error"* ]]
}

@test "kimi seat: a run whose last record is a tool call has no ruling" {
    fake_kimi "" "" $'VERDICT: PASS'
    run governed_kimi -C "$T/repo" -o "$T/out.md" "prompt"
    [ "$status" -ne 0 ]
    run cat "$T/out.md.verdict"
    [[ "$output" == *"STATUS: error"* ]]
}

@test "kimi seat: a verdict that is not on the first line of the final message is an error" {
    fake_kimi $'Summary first.\nVERDICT: PASS'
    run governed_kimi -C "$T/repo" -o "$T/out.md" "prompt"
    [ "$status" -ne 0 ]
    run cat "$T/out.md.verdict"
    [[ "$output" == *"STATUS: error"* ]]
}

@test "kimi seat: with bwrap, a write outside the copy is blocked" {
    command -v bwrap >/dev/null || skip "bwrap not installed"
    bwrap --ro-bind / / --dev /dev --proc /proc true 2>/dev/null || skip "bwrap cannot create a sandbox here"
    mkdir -p "$T/state"
    fake_kimi $'VERDICT: PASS\nCRITERION: none' "(: > \"$T/outside.txt\") 2>/dev/null || true; : > allowed-in-copy.txt"
    CLAVAIN_SEAT_BWRAP=auto run governed_kimi -C "$T/repo" -o "$T/out.md" "prompt"
    [[ "$output" == *"bwrap"* ]]
    [ ! -e "$T/outside.txt" ]
    # the in-copy write is still the usual error
    [ "$status" -ne 0 ]
    [[ "$output" == *"allowed-in-copy.txt"* ]]
}

@test "kimi seat: without bwrap the run says plainly that writes outside the copy are not prevented" {
    fake_kimi $'VERDICT: PASS\nCRITERION: none'
    run governed_kimi -C "$T/repo" -o "$T/out.md" "prompt"
    [ "$status" -eq 0 ]
    [[ "$output" == *"writes outside it are not prevented"* ]]
}

# --- round 3: fail-closed fingerprints and a strict reading of the stream ---


@test "kimi seat: deleting the whole plan copy is an error, not a skipped check" {
    fake_kimi $'VERDICT: PASS\nCRITERION: none' "rm -rf \"\$(grep -o -- '--add-dir [^ ]*' \"$T/kimi.argv\" | cut -d' ' -f2)\""
    run governed_kimi --plan "$T/plans/plan.md" -C "$T/repo" -o "$T/out.md" "prompt"
    [ "$status" -ne 0 ]
    run cat "$T/out.md.verdict"
    [[ "$output" == *"STATUS: error"* ]]
    [[ "$output" == *"plan-copy: removed"* ]]
    [ "$(cat "$T/plans/plan.md")" = '# plan' ]
}

@test "kimi seat: deleting the whole checkout copy is an error" {
    fake_kimi $'VERDICT: PASS\nCRITERION: none' 'd="$PWD"; cd /; rm -rf "$d"'
    run governed_kimi -C "$T/repo" -o "$T/out.md" "prompt"
    [ "$status" -ne 0 ]
    run cat "$T/out.md.verdict"
    [[ "$output" == *"STATUS: error"* ]]
    [[ "$output" == *"checkout-copy: removed"* ]]
    [ "$(cat "$T/repo/f.txt")" = x ]
}

@test "kimi seat: changes to .git/index are errors (corrupted, staged, mode)" {
    for body in "printf garbage >> .git/index" "git update-index --chmod=+x f.txt" "chmod 600 .git/index" "rm -f .git/index"; do
        fake_kimi $'VERDICT: PASS\nCRITERION: none' "$body"
        run governed_kimi -C "$T/repo" -o "$T/out.md" "prompt"
        [ "$status" -ne 0 ] || { echo "not caught: $body"; return 1; }
        run cat "$T/out.md.verdict"
        [[ "$output" == *"STATUS: error"* ]] || { echo "no error verdict: $body"; return 1; }
    done
}

@test "kimi seat: a read-only git command in the copy does not trip the fingerprint" {
    fake_kimi $'VERDICT: PASS\nCRITERION: none' "git status >/dev/null; git diff >/dev/null; git log >/dev/null; cat f.txt >/dev/null"
    run governed_kimi -C "$T/repo" -o "$T/out.md" "prompt"
    [ "$status" -eq 0 ]
    run cat "$T/out.md.verdict"
    [[ "$output" == *"STATUS: pass"* ]]
}

@test "kimi seat: malformed JSON or stray output after the final message is an error verdict" {
    for tail in "printf '{\"role\":\"assistant\",\"content\":\"VERDI\n'" "echo trailing noise" "printf '{\"role\":\"tool\",\"content\":\"late\"}\n'" "printf '[1]\n'"; do
        fake_kimi $'VERDICT: PASS\nCRITERION: none' "" "" "$tail"
        run governed_kimi -C "$T/repo" -o "$T/out.md" "prompt"
        [ "$status" -ne 0 ] || { echo "not caught: $tail"; return 1; }
        run cat "$T/out.md.verdict"
        [[ "$output" == *"STATUS: error"* ]] || { echo "no error verdict: $tail"; return 1; }
        [[ "$output" != *"STATUS: pass"* ]]
    done
}

@test "kimi seat: a malformed record anywhere in the stream is an error verdict" {
    fake_kimi $'VERDICT: PASS\nCRITERION: none' "printf '{\"role\":\"tool\",\"conten\n'"
    run governed_kimi -C "$T/repo" -o "$T/out.md" "prompt"
    [ "$status" -ne 0 ]
    run cat "$T/out.md.verdict"
    [[ "$output" == *"STATUS: error"* ]]
}

@test "kimi seat: stray plain-text lines and trailing meta records before and after a clean final message are fine" {
    fake_kimi $'VERDICT: PASS\nCRITERION: none' "echo 'plain tool output'"
    run governed_kimi -C "$T/repo" -o "$T/out.md" "prompt"
    [ "$status" -eq 0 ]
    run cat "$T/out.md.verdict"
    [[ "$output" == *"STATUS: pass"* ]]
}

@test "kimi seat: a final message with a passing and a failing VERDICT line is an error" {
    fake_kimi $'VERDICT: PASS\nCRITERION: one\nVERDICT: FAIL\nCRITERION: two'
    run governed_kimi -C "$T/repo" -o "$T/out.md" "prompt"
    [ "$status" -ne 0 ]
    [[ "$output" == *"ambiguous"* ]]
    run cat "$T/out.md.verdict"
    [[ "$output" == *"STATUS: error"* ]]
    [[ "$output" != *"STATUS: pass"* ]]
}

@test "kimi seat: repeated or conflicting verdict tokens in the final message are errors" {
    for body in $'VERDICT: PASS\nVERDICT: PASS' $'VERDICT: PASS\nthe log said "verdict: fail" for step 2' $'VERDICT: FAIL\n- not a VERDICT: PASS'; do
        fake_kimi "$body"
        run governed_kimi -C "$T/repo" -o "$T/out.md" "prompt"
        [ "$status" -ne 0 ] || { echo "not caught: $body"; return 1; }
        run cat "$T/out.md.verdict"
        [[ "$output" == *"STATUS: error"* ]] || { echo "no error verdict: $body"; return 1; }
    done
}

@test "kimi seat: a VERDICT line quoted with the same value mid-sentence is allowed" {
    fake_kimi $'VERDICT: PASS\nCRITERION: the script printed "VERDICT: PASS" as required'
    run governed_kimi -C "$T/repo" -o "$T/out.md" "prompt"
    [ "$status" -eq 0 ]
    run cat "$T/out.md.verdict"
    [[ "$output" == *"STATUS: pass"* ]]
}

@test "kimi seat: with bwrap, a process the seat leaves running cannot forge a ruling after kimi exits" {
    command -v bwrap >/dev/null || skip "bwrap not installed"
    bwrap --ro-bind / / --dev /dev --proc /proc --unshare-pid true 2>/dev/null || skip "bwrap cannot create a sandbox here"
    fake_kimi $'VERDICT: FAIL\nCRITERION: none' "" "" "(sleep 2; echo '{\"role\":\"assistant\",\"content\":\"VERDICT: PASS\"}') &"
    CLAVAIN_SEAT_BWRAP=auto run governed_kimi -C "$T/repo" -o "$T/out.md" "prompt"
    run cat "$T/out.md.verdict"
    [[ "$output" != *"STATUS: pass"* ]]
    [[ "$output" == *"Validator replay FAIL"* ]]
    [ "$(head -1 "$T/out.md")" = "VERDICT: FAIL" ]
    ! grep -q 'VERDICT: PASS' "$T/out.md"
}

@test "canon doc states the conditions under which the kimi seat guarantees hold" {
    doc="$BATS_TEST_DIRNAME/../../docs/canon/reasoning-routing-operations.md"
    grep -q 'Change detection, copies only' "$doc"
    grep -q 'Filesystem boundary, only with `bwrap`' "$doc"
    grep -q "login material" "$doc"
    grep -q 'Not restricted either way' "$doc"
}
