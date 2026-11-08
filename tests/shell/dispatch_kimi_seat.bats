#!/usr/bin/env bats
# The role-resolved kimi review seat (validation-kimi, the third provider in the
# validation chain) must be able to run a plan's Verification, like the claude
# seat: Bash and read tools allowed, edit tools absent, the plan directory
# readable, and the checkout snapshotted around the run so a run that changes it
# is an error verdict (bead mk-1rbg). A direct `--to kimi` dispatch stays
# toolless, because it may carry untrusted input. Dry-run tests assert on the
# assembled agent file; the run tests put a fake `kimi` on PATH.

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

# $1 = body the fake seat prints; $2 = optional shell to run first (a mutation).
# The fake records the agent file it was given and its argv.
fake_kimi() {
    cat > "$T/bin/kimi" <<EOF
#!/usr/bin/env bash
printf '%s ' "\$@" > "$T/kimi.argv"
while [ \$# -gt 0 ]; do
  if [ "\$1" = --agent-file ]; then cp "\$2" "$T/kimi.agent"; fi
  shift
done
${2:-}
printf '%s\n' "\$FAKE_BODY"
EOF
    chmod +x "$T/bin/kimi"
    export FAKE_BODY="$1"
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

@test "kimi seat: the run is given the tool agent file and the plan directory" {
    fake_kimi $'VERDICT: PASS\nCRITERION: none'
    run governed_kimi --plan "$T/plans/plan.md" -C "$T/repo" -o "$T/out.md" "prompt"
    [ "$status" -eq 0 ]
    grep -q '^tools: \[Bash, Read, Glob, Grep\]$' "$T/kimi.agent"
    grep -q -- "--add-dir $T/plans" "$T/kimi.argv"
}

@test "kimi seat: a run that mutates the checkout is an error verdict and a failed dispatch" {
    fake_kimi $'VERDICT: PASS\nCRITERION: none' "printf 'y\\n' >> \"$T/repo/f.txt\"; : > \"$T/repo/new.txt\""
    run governed_kimi -C "$T/repo" -o "$T/out.md" "prompt"
    [ "$status" -ne 0 ]
    [[ "$output" == *"mutated the checkout"* ]]
    run cat "$T/out.md.verdict"
    [[ "$output" == *"STATUS: error"* ]]
    [[ "$output" == *"f.txt"* ]]
    [[ "$output" == *"new.txt"* ]]
}

@test "kimi seat: a clean run keeps its verdict" {
    fake_kimi $'VERDICT: PASS\nCRITERION: none'
    run governed_kimi -C "$T/repo" -o "$T/out.md" "prompt"
    [ "$status" -eq 0 ]
    [[ "$output" != *"mutated the checkout"* ]]
    run cat "$T/out.md.verdict"
    [[ "$output" == *"pass"* ]]
}

@test "kimi seat: a direct --to kimi run is not snapshotted" {
    fake_kimi $'VERDICT: PASS\nCRITERION: none' ": > \"$T/repo/new.txt\""
    PATH="$T/bin:$PATH" run bash "$DISPATCH" --to kimi --model kimi-code/k3 -C "$T/repo" -o "$T/out.md" "prompt"
    [ "$status" -eq 0 ]
    [[ "$output" != *"mutated the checkout"* ]]
}

@test "kimi seat: narration before the ruling does not hide the verdict" {
    fake_kimi $'• Executing the verification command:\n\n• VERDICT: PASS\n  CRITERION: bash check.sh printed NONCE-1'
    run governed_kimi -C "$T/repo" -o "$T/out.md" "prompt"
    [ "$status" -eq 0 ]
    [ "$(head -1 "$T/out.md")" = "VERDICT: PASS" ]
    run cat "$T/out.md.verdict"
    [[ "$output" == *"STATUS: pass"* ]]
}

@test "kimi seat: output with no ruling message passes through and never reads as pass" {
    fake_kimi $'• I could not run it.'
    run governed_kimi -C "$T/repo" -o "$T/out.md" "prompt"
    run cat "$T/out.md.verdict"
    [[ "$output" != *"STATUS: pass"* ]]
}
