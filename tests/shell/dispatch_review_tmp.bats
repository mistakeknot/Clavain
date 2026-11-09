#!/usr/bin/env bats

setup() {
    load test_helper
    DISPATCH="$BATS_TEST_DIRNAME/../../scripts/dispatch.sh"
    T="$(mktemp -d)"
    mkdir -p "$T/repo" "$T/bin"
    cat > "$T/bin/ic" <<'SH'
#!/bin/sh
case "$*" in
  *"route list"*) echo '[]' ;;
  *"route identity"*) echo '{"model_identity":"gpt-6.1-sol"}' ;;
  *"route record"*) exit 0 ;;
  *) exit 3 ;;
esac
SH
    chmod +x "$T/bin/ic"
    git -C "$T/repo" init -q
    export CLAVAIN_CONTEXT_GATEWAY_MODE=off CLAVAIN_BB_DIRECT_POOL=0
}
teardown() { rm -rf "$T"; }

@test "Linux Codex review uses sandbox-private shared memory without a metadata mask" {
    [[ "$(uname -s)" == Linux ]] || skip 'Linux sandbox only'
    run bash "$DISPATCH" --role cross-lab-review --role-resolved --to codex \
        --dry-run -C "$T/repo" -o "$T/out" 'Review it'
    [ "$status" -eq 0 ]
    [[ "$output" == *'sandbox_workspace_write.exclude_tmpdir_env_var=true'* ]]
    [[ "$output" == *'sandbox_workspace_write.exclude_slash_tmp=true'* ]]
    [[ "$output" == *'sandbox-private /dev/shm'* ]]
    [[ "$output" == *'shell_environment_policy.set.TMPDIR='* ]]
}

@test "review refuses launch when the sandbox temp preflight fails" {
    cat > "$T/bin/codex" <<'SH'
#!/bin/sh
case "$1" in
  sandbox) exit 73 ;;
  exec) touch "$0.launched"; exit 0 ;;
  *) echo 'codex-cli 0.167.0' ;;
esac
SH
    chmod +x "$T/bin/codex"
    route="$(jq -n --arg h "$(sha256sum "$BATS_TEST_DIRNAME/../../config/routing.yaml" | cut -d' ' -f1)" '{policy_hash:$h,profile_ref:"primary",profile:{backend:"codex",model:"gpt-6.1-sol",model_identity:"gpt-6.1-sol"}}')"
    CLAVAIN_DISPATCH_FAILURE_FILE="$T/failure" PATH="$T/bin:$PATH" run bash "$DISPATCH" --role cross-lab-review --role-resolved \
        --to codex --resolved-route-json "$route" -C "$T/repo" -o "$T/out" 'Review it'
    [ "$status" -ne 0 ]
    [ "$(cat "$T/failure")" = unsupported_adapter ]
    [[ "$output" == *'review temp isolation preflight failed'* ]]
    [ ! -e "$T/bin/codex.launched" ]
}

@test "dispatch temp root passes the real sandbox ancestor guard" {
    [[ "$(uname -s)" == Linux ]] || skip 'Linux sandbox only'
    mkdir "$T/hosttmp"
    real_codex="$(command -v codex || true)"
    [[ -n "$real_codex" ]] || skip 'codex is not installed'
    cat > "$T/bin/codex" <<SH
#!/usr/bin/env bash
if [[ "\$1" == sandbox ]]; then exec "$real_codex" "\$@"; fi
[[ "\$1" == exec ]] || { echo 'codex-cli 0.167.0'; exit 0; }
[[ "\$TMPDIR" == "$T/hosttmp" ]] || exit 91
cfg=(); wd=''; out=''; tool_tmp=''
while [[ \$# -gt 0 ]]; do
  case "\$1" in
    -c) cfg+=(-c "\$2"); [[ "\$2" == shell_environment_policy.set.TMPDIR=* ]] && tool_tmp=/dev/shm; shift 2 ;;
    -C) wd="\$2"; shift 2 ;;
    -o) out="\$2"; shift 2 ;;
    *) shift ;;
  esac
done
cd "\$wd"
"$real_codex" sandbox -c sandbox_mode=workspace-write "\${cfg[@]}" -- env "TMPDIR=\$tool_tmp" python3 -c '
import pathlib, tempfile
with tempfile.TemporaryDirectory() as d:
    p=pathlib.Path(d)
    assert str(p).startswith("/dev/shm/")
    assert not any((a/".git").exists() for a in [p,*p.parents])
' || exit 1
printf 'VERDICT: PASS\n' > "\$out"
SH
    chmod +x "$T/bin/codex"
    route="$(jq -n --arg h "$(sha256sum "$BATS_TEST_DIRNAME/../../config/routing.yaml" | cut -d' ' -f1)" '{policy_hash:$h,profile_ref:"primary",profile:{backend:"codex",model:"gpt-6.1-sol",model_identity:"gpt-6.1-sol"}}')"
    TMPDIR="$T/hosttmp" PATH="$T/bin:$PATH" run bash "$DISPATCH" --role cross-lab-review --role-resolved \
        --to codex --resolved-route-json "$route" -C "$T/repo" -o "$T/out" 'Review it'
    [ "$status" -eq 0 ]
    [ -s "$T/out" ]
}
