#!/usr/bin/env bats
# mk-fdj7h: --review-scratch gives a cross-lab-review a private writable
# scratch clone (workspace-write over the clone and a sibling tmp only).

setup() {
    load test_helper
    T="$(mktemp -d)"
    DISPATCH="$BATS_TEST_DIRNAME/../../scripts/dispatch.sh"
    export CLAVAIN_CONTEXT_GATEWAY_MODE=off
    export CLAVAIN_BB_DIRECT_POOL=0
    export LC_ALL=C
    REAL_CODEX="$(command -v codex || true)"
    mkdir -p "$T/bin" "$T/scratchroot" "$T/home"
    export TMPDIR="$T/scratchroot"
    R="$T/repo"; git init -q -b main "$R"
    git -C "$R" config user.email t@t; git -C "$R" config user.name t
    echo a > "$R/a"; git -C "$R" add a; git -C "$R" commit -qm base
    BASE="$(git -C "$R" rev-parse HEAD)"
    echo b > "$R/b"; git -C "$R" add b; git -C "$R" commit -qm head
    HEAD_SHA="$(git -C "$R" rev-parse HEAD)"
    export CLAVAIN_REVIEW_RECEIPT_DIR="$T/reviews"
    # Minimal fake ic: audit persistence succeeds, identity resolves, no history.
    cat > "$T/bin/ic" <<'SH'
#!/usr/bin/env bash
if [[ "$*" == *"route list"* ]]; then echo '[]'
elif [[ "$*" == *"route identity"* ]]; then echo '{"model_identity":"gpt-6.1-sol"}'
elif [[ "$*" == *"route record"* ]]; then exit 0
else exit 3; fi
SH
    chmod +x "$T/bin/ic"
    printf 'Review it.\n' > "$T/prompt.md"
    OUT="$T/out.md"
    POLICY_HASH="$(sha256sum "$BATS_TEST_DIRNAME/../../config/routing.yaml" | cut -d' ' -f1)"
    ROUTE_JSON="$(jq -n --arg h "$POLICY_HASH" \
        '{policy_hash:$h, profile_ref:"primary", profile:{backend:"codex",model:"gpt-6.1-sol",model_identity:"gpt-6.1-sol"}}')"
    RECEIPT_FLAGS=(--repo o/r --repo-id R_abc123 --pr 7 --head "$HEAD_SHA" --base "$BASE")
}

teardown() {
    chmod -R u+rwX "$T" 2>/dev/null || true
    rm -rf "$T"
}

# A codex stand-in. Records argv, then runs a probe script inside the REAL
# `codex sandbox` with the exact -c overrides dispatch passed, in the -C
# directory, so the sandbox rules under test are the real ones.
fake_codex_probe() {
    cat > "$T/bin/codex" <<EOF
#!/usr/bin/env bash
[[ "\$1" == exec ]] || { echo "codex-cli 0.166.0"; exit 0; }
printf '%s\n' "\$@" > "$T/codex.argv"
cat > /dev/null
cfg=(); cd_dir=""; outfile=""
while [[ \$# -gt 0 ]]; do
  case "\$1" in
    -c) cfg+=(-c "\$2"); shift 2 ;;
    -C) cd_dir="\$2"; shift 2 ;;
    -o) outfile="\$2"; shift 2 ;;
    *) shift ;;
  esac
done
echo "\$cd_dir" > "$T/codex.cwd"
echo "\$TMPDIR" > "$T/codex.tmpdir"
cd "\$cd_dir"
"$REAL_CODEX" sandbox -c sandbox_mode=workspace-write "\${cfg[@]}" -- bash "$T/probe.sh" > "$T/probe.out" 2>&1
printf 'Findings: none\n\nVERDICT: PASS\n' > "\$outfile"
exit 0
EOF
    chmod +x "$T/bin/codex"
}

# Plain recorder: no sandbox, just argv and exit.
fake_codex_plain() {
    cat > "$T/bin/codex" <<EOF
#!/usr/bin/env bash
[[ "\$1" == exec ]] || { echo "codex-cli 0.166.0"; exit 0; }
printf '%s\n' "\$@" > "$T/codex.argv"
cat > /dev/null
outfile=""
cd_dir=""
while [[ \$# -gt 0 ]]; do case "\$1" in -o) outfile="\$2"; shift 2 ;; -C) cd_dir="\$2"; shift 2 ;; *) shift ;; esac; done
echo "\$cd_dir" > "$T/codex.cwd"
[[ -d "\$cd_dir/.git" ]] && git -C "\$cd_dir" rev-parse HEAD > "$T/codex.clone_head"
printf 'Findings: none\n\nVERDICT: PASS\n' > "\$outfile"
exit 0
EOF
    chmod +x "$T/bin/codex"
}

run_scratch() {
    PATH="$T/bin:$PATH" run bash "$DISPATCH" --role-resolved --role cross-lab-review \
        --to codex --model gpt-6.1-sol --resolved-route-json "$ROUTE_JSON" \
        --review-scratch --producer-identity claude-sonnet-5-5 "${RECEIPT_FLAGS[@]}" -C "$R" \
        --prompt-file "$T/prompt.md" -o "$OUT" "$@"
}

scratch_dirs() { find "$T/scratchroot" -maxdepth 1 -name 'clavain-review-scratch.*' 2>/dev/null; }

@test "dry run shows the scratch flags and creates nothing" {
    fake_codex_plain
    run_scratch --dry-run
    [ "$status" -eq 0 ]
    [[ "$output" == *"sandbox_workspace_write.writable_roots=\\[\\]"* ]]
    [[ "$output" == *"sandbox_workspace_write.exclude_slash_tmp=true"* ]]
    [[ "$output" == *"sandbox_workspace_write.network_access=false"* ]]
    [[ "$output" == *"review-scratch\\>/repo"* ]]
    [ -z "$(scratch_dirs)" ]
    [ ! -e "$T/codex.argv" ]
}

@test "rejected for a role other than cross-lab-review" {
    fake_codex_plain
    PATH="$T/bin:$PATH" run bash "$DISPATCH" --dry-run --role-resolved --role validation \
        --to codex --model gpt-6.1-sol --resolved-route-json "$ROUTE_JSON" \
        --review-scratch "${RECEIPT_FLAGS[@]}" -C "$R" --prompt-file "$T/prompt.md" -o "$OUT"
    [ "$status" -ne 0 ]
    [[ "$output" == *"cross-lab-review only"* ]]
}

@test "rejected without the receipt flags" {
    fake_codex_plain
    PATH="$T/bin:$PATH" run bash "$DISPATCH" --dry-run --role-resolved --role cross-lab-review \
        --to codex --model gpt-6.1-sol --resolved-route-json "$ROUTE_JSON" \
        --review-scratch -C "$R" --prompt-file "$T/prompt.md" -o "$OUT"
    [ "$status" -ne 0 ]
    [[ "$output" == *"receipt flags"* ]]
}

@test "rejected with a partial set of receipt flags" {
    fake_codex_plain
    PATH="$T/bin:$PATH" run bash "$DISPATCH" --dry-run --role-resolved --role cross-lab-review \
        --to codex --model gpt-6.1-sol --resolved-route-json "$ROUTE_JSON" \
        --review-scratch --repo o/r --pr 7 -C "$R" --prompt-file "$T/prompt.md" -o "$OUT"
    [ "$status" -ne 0 ]
}

@test "rejected without -C and with a wider sandbox" {
    fake_codex_plain
    PATH="$T/bin:$PATH" run bash "$DISPATCH" --dry-run --role-resolved --role cross-lab-review \
        --to codex --model gpt-6.1-sol --resolved-route-json "$ROUTE_JSON" \
        --review-scratch "${RECEIPT_FLAGS[@]}" --prompt-file "$T/prompt.md" -o "$OUT"
    [ "$status" -ne 0 ]
    [[ "$output" == *"-C"* ]]
    run_scratch --dry-run -s danger-full-access
    [ "$status" -ne 0 ]
    [[ "$output" == *"cannot be combined with -s"* ]]
}

@test "a non-codex engine fails closed" {
    printf '#!/usr/bin/env bash\ncat >/dev/null\nexit 0\n' > "$T/bin/claude"; chmod +x "$T/bin/claude"
    local claude_route
    claude_route="$(jq -n --arg h "$POLICY_HASH" \
        '{policy_hash:$h, profile_ref:"primary", profile:{backend:"claude",model:"gpt-6-astra",model_identity:"gpt-6-astra"}}')"
    PATH="$T/bin:$PATH" run bash "$DISPATCH" --dry-run --role-resolved --role cross-lab-review \
        --to claude --model gpt-6-astra --resolved-route-json "$claude_route" \
        --review-scratch "${RECEIPT_FLAGS[@]}" -C "$R" --prompt-file "$T/prompt.md" -o "$OUT"
    [ "$status" -ne 0 ]
    [[ "$output" == *"codex engine only"* ]]
}

@test "a clone whose tree does not match --head fails closed and cleans up" {
    fake_codex_plain
    # Wrong tree: lie about the head's tree through the prepared value by
    # pointing --head at a commit the checkout lacks.
    local missing; missing="$(printf 'b%.0s' {1..40})"
    PATH="$T/bin:$PATH" run bash "$DISPATCH" --role-resolved --role cross-lab-review \
        --to codex --model gpt-6.1-sol --resolved-route-json "$ROUTE_JSON" \
        --review-scratch --repo o/r --repo-id R_abc123 --pr 7 --head "$missing" --base "$BASE" \
        -C "$R" --prompt-file "$T/prompt.md" -o "$OUT"
    [ "$status" -ne 0 ]
    [ ! -e "$T/codex.argv" ]
    [ -z "$(scratch_dirs)" ]
}

@test "setup refuses when the clone tree differs from the --head tree" {
    fake_codex_plain
    # Replace the head commit's tree in the clone's view: a checkout whose
    # object database holds a *different* commit under the same id is not
    # constructible, so exercise the guard directly.
    run bash -c '
        set -euo pipefail
        source <(sed -n "/^_review_scratch_cleanup()/,/^_dispatch_cleanup_state()/p" "$0" | sed "\$d")
        _dispatch_write_failure_class() { :; }
        WORKDIR="$1"; RR_HEAD="$2"; RR_HEAD_TREE="$(printf "c%.0s" {1..40})"
        _review_scratch_setup
    ' "$DISPATCH" "$R" "$HEAD_SHA"
    [ "$status" -ne 0 ]
    [[ "$output" == *"does not match the tree of --head"* ]]
    [ -z "$(scratch_dirs)" ]
}

@test "the receipt records scratch-write and a scratch tree bound to the head" {
    fake_codex_plain
    run_scratch
    [ "$status" -eq 0 ]
    f="$T/reviews/o__r/7-$HEAD_SHA.json"
    [ -f "$f" ]
    [ "$(jq -r .sandbox "$f")" = scratch-write ]
    [ "$(jq -r .scratch_tree "$f")" = "$(git -C "$R" rev-parse "$HEAD_SHA^{tree}")" ]
    [ "$(jq -r .head_sha "$f")" = "$HEAD_SHA" ]
    [ "$(jq -r .verdict "$f")" = PASS ]
    # codex ran inside the scratch clone, which is gone afterwards.
    [[ "$(cat "$T/codex.cwd")" == "$T/scratchroot/clavain-review-scratch."*"/repo" ]]
    [ "$(cat "$T/codex.clone_head")" = "$HEAD_SHA" ]
    [ -z "$(scratch_dirs)" ]
}

@test "a read-only receipt carries no scratch fields" {
    fake_codex_plain
    PATH="$T/bin:$PATH" run bash "$DISPATCH" --role-resolved --role cross-lab-review \
        --to codex --model gpt-6.1-sol --resolved-route-json "$ROUTE_JSON" \
        --producer-identity claude-sonnet-5-5 "${RECEIPT_FLAGS[@]}" -C "$R" --prompt-file "$T/prompt.md" -o "$OUT"
    [ "$status" -eq 0 ]
    f="$T/reviews/o__r/7-$HEAD_SHA.json"
    [ "$(jq -r '.sandbox' "$f")" != scratch-write ]
    [ "$(jq 'has("scratch_tree")' "$f")" = false ]
}

@test "codex args use the scratch clone and an empty writable-roots set" {
    fake_codex_plain
    run_scratch
    [ "$status" -eq 0 ]
    grep -qx 'sandbox_workspace_write.writable_roots=\[\]' "$T/codex.argv"
    grep -qx 'sandbox_workspace_write.exclude_slash_tmp=true' "$T/codex.argv"
    grep -qx 'sandbox_workspace_write.network_access=false' "$T/codex.argv"
    ! grep -q 'uv' "$T/codex.argv"
    grep -qx -- '-C' "$T/codex.argv"
}

@test "in scratch mode mktemp and scratch writes succeed; real repo, HOME and /tmp are denied" {
    [ -n "$REAL_CODEX" ] || skip "codex is not installed"
    cat > "$T/probe.sh" <<EOF
f="\$(mktemp)" && echo "mktemp=ok"
d="\$(mktemp -d)" && echo "mktemp-d=ok"
touch ./scratch-write && echo "scratch-write=ok"
touch "$R/real-write" 2>/dev/null && echo "real-repo=WRITTEN" || echo "real-repo=denied"
touch "$T/home/home-write" 2>/dev/null && echo "home=WRITTEN" || echo "home=denied"
touch "$T/outside-tmp" 2>/dev/null && echo "outside-tmp=WRITTEN" || echo "outside-tmp=denied"
touch "$T/scratchroot/sibling" 2>/dev/null && echo "scratchroot=WRITTEN" || echo "scratchroot=denied"
EOF
    if ! "$REAL_CODEX" sandbox -- true >/dev/null 2>&1; then skip "codex sandbox is unavailable here"; fi
    fake_codex_probe
    HOME="$T/home" run_scratch
    [ "$status" -eq 0 ]
    grep -qx 'mktemp=ok' "$T/probe.out"
    grep -qx 'mktemp-d=ok' "$T/probe.out"
    grep -qx 'scratch-write=ok' "$T/probe.out"
    grep -qx 'real-repo=denied' "$T/probe.out"
    grep -qx 'home=denied' "$T/probe.out"
    grep -qx 'outside-tmp=denied' "$T/probe.out"
    grep -qx 'scratchroot=denied' "$T/probe.out"
    [ ! -e "$R/real-write" ]
    [ ! -e "$T/home/home-write" ]
    [ ! -e "$T/outside-tmp" ]
    [ -z "$(git -C "$R" status --porcelain)" ]
    [ "$(git -C "$R" rev-parse HEAD)" = "$HEAD_SHA" ]
    [ -z "$(scratch_dirs)" ]
}

@test "a reviewer that dirties the real checkout fails the run" {
    fake_codex_plain
    cat > "$T/bin/codex" <<EOF
#!/usr/bin/env bash
[[ "\$1" == exec ]] || { echo "codex-cli 0.166.0"; exit 0; }
cat > /dev/null
outfile=""
while [[ \$# -gt 0 ]]; do case "\$1" in -o) outfile="\$2"; shift 2 ;; *) shift ;; esac; done
echo dirty > "$R/dirty-file"
printf 'Findings: none\n\nVERDICT: PASS\n' > "\$outfile"
exit 0
EOF
    chmod +x "$T/bin/codex"
    run_scratch
    [ "$status" -ne 0 ]
    [[ "$output" == *"real checkout status changed"* ]]
    [ -z "$(scratch_dirs)" ]
}

# ---- Passthrough allowlist (fix round 1, finding 1) -------------------------
# Passthrough flags are appended after the enforced sandbox settings, so any
# authority-changing one must be refused: non-zero exit, codex never run, no
# receipt, nothing left behind.

assert_scratch_refuses() {
    rm -f "$T/codex.argv"
    run_scratch "$@"
    if [ "$status" -eq 0 ]; then
        echo "accepted passthrough: $*" >&2
        return 1
    fi
    [[ "$output" == *"--review-scratch refuses passthrough"* ]] || { echo "wrong error for: $* -> $output" >&2; return 1; }
    [ ! -e "$T/codex.argv" ] || { echo "codex ran for: $*" >&2; return 1; }
    [ ! -e "$T/reviews/o__r/7-$HEAD_SHA.json" ] || { echo "receipt written for: $*" >&2; return 1; }
    [ -z "$(scratch_dirs)" ] || { echo "scratch left behind for: $*" >&2; return 1; }
}

@test "scratch refuses -c / --config passthrough (network, writable roots)" {
    fake_codex_plain
    assert_scratch_refuses -c sandbox_workspace_write.network_access=true
    assert_scratch_refuses --config sandbox_workspace_write.network_access=true
    assert_scratch_refuses -c "sandbox_workspace_write.writable_roots=[\"$HOME\"]"
    assert_scratch_refuses "--config=sandbox_workspace_write.network_access=true"
    assert_scratch_refuses -c sandbox_mode=danger-full-access
}

@test "scratch refuses --profile / -p passthrough" {
    fake_codex_plain
    assert_scratch_refuses --profile wide
    assert_scratch_refuses -p wide
    assert_scratch_refuses --profile=wide
}

@test "scratch refuses --add-dir passthrough" {
    fake_codex_plain
    assert_scratch_refuses --add-dir "$HOME"
    assert_scratch_refuses "--add-dir=$HOME"
}

@test "scratch refuses sandbox overrides passed as passthrough" {
    fake_codex_plain
    assert_scratch_refuses --sandbox=danger-full-access
    assert_scratch_refuses --sandbox=workspace-write
    # The dispatch-level spellings are refused by the existing -s check.
    run_scratch -s danger-full-access
    [ "$status" -ne 0 ]
    run_scratch --sandbox danger-full-access
    [ "$status" -ne 0 ]
    [ ! -e "$T/codex.argv" ]
}

@test "scratch refuses approval and bypass flags" {
    fake_codex_plain
    assert_scratch_refuses -a never
    assert_scratch_refuses --ask-for-approval never
    assert_scratch_refuses --ask-for-approval=never
    assert_scratch_refuses --full-auto
    CLAVAIN_ALLOW_UNSAFE=1 assert_scratch_refuses --dangerously-bypass-approvals-and-sandbox
    CLAVAIN_ALLOW_UNSAFE=1 assert_scratch_refuses --yolo
    # Without the override the parser itself refuses them: still no run, no receipt.
    run_scratch --yolo
    [ "$status" -ne 0 ]
    [ ! -e "$T/codex.argv" ]
    [ ! -e "$T/reviews/o__r/7-$HEAD_SHA.json" ]
}

@test "scratch refuses --cd passthrough spellings" {
    fake_codex_plain
    assert_scratch_refuses "--cd=$HOME"
    assert_scratch_refuses --cd=
}

@test "scratch refuses other authority-adjacent and unknown flags" {
    fake_codex_plain
    assert_scratch_refuses --enable shell_tool
    assert_scratch_refuses --disable sandbox
    assert_scratch_refuses --search
    assert_scratch_refuses --oss
    assert_scratch_refuses --local-provider ollama
    assert_scratch_refuses --not-a-codex-flag
}

@test "scratch refuses a mixed list when one passthrough is unsafe" {
    fake_codex_plain
    assert_scratch_refuses --json --color never --add-dir "$HOME"
}

@test "scratch refusal also applies to a dry run" {
    fake_codex_plain
    run_scratch --dry-run --add-dir "$HOME"
    [ "$status" -ne 0 ]
    [[ "$output" == *"--review-scratch refuses passthrough"* ]]
}

@test "scratch still accepts the inert passthrough flags" {
    fake_codex_plain
    run_scratch --json --skip-git-repo-check --color never --output-schema "$T/schema.json"
    [ "$status" -eq 0 ]
    grep -qx -- '--json' "$T/codex.argv"
    grep -qx -- '--skip-git-repo-check' "$T/codex.argv"
    grep -qx -- 'never' "$T/codex.argv"
    grep -qx 'sandbox_workspace_write.network_access=false' "$T/codex.argv"
}

@test "read-only reviews keep their passthrough behaviour" {
    fake_codex_plain
    PATH="$T/bin:$PATH" run bash "$DISPATCH" --role-resolved --role cross-lab-review \
        --to codex --model gpt-6.1-sol --resolved-route-json "$ROUTE_JSON" \
        --producer-identity claude-sonnet-5-5 "${RECEIPT_FLAGS[@]}" -C "$R" \
        --prompt-file "$T/prompt.md" -o "$OUT" --json -c some.key=value
    [ "$status" -eq 0 ]
    grep -qx 'some.key=value' "$T/codex.argv"
}

# ---- Setup git isolation (fix round 1, finding 2) ---------------------------
# The clone and checkout run outside the codex sandbox, so a hook named by the
# caller's global or system configuration must not run.

make_hook_config() {
    mkdir -p "$T/hooks"
    cat > "$T/hooks/post-checkout" <<EOF
#!/usr/bin/env bash
echo fired > "$T/marker-outside-scratch"
EOF
    chmod +x "$T/hooks/post-checkout"
    git config --file "$T/hostile.gitconfig" core.hooksPath "$T/hooks"
}

# Control: the hostile configuration really does fire the hook on a plain
# clone-and-checkout, so the isolation tests below are not vacuous.
hook_control() {
    local c="$T/control-clone"
    git clone -q --no-checkout "$R" "$c"
    git -C "$c" checkout -q --detach "$HEAD_SHA"
    [ -e "$T/marker-outside-scratch" ]
    rm -f "$T/marker-outside-scratch"
    rm -rf "$c"
}

@test "a global post-checkout hook (GIT_CONFIG_GLOBAL) does not run during setup" {
    fake_codex_plain
    make_hook_config
    export GIT_CONFIG_GLOBAL="$T/hostile.gitconfig"
    hook_control
    run_scratch
    [ "$status" -eq 0 ]
    [ ! -e "$T/marker-outside-scratch" ]
    [ "$(cat "$T/codex.clone_head")" = "$HEAD_SHA" ]
    [ -z "$(scratch_dirs)" ]
}

@test "a hook named in the home-directory git config does not run during setup" {
    fake_codex_plain
    make_hook_config
    cp "$T/hostile.gitconfig" "$T/home/.gitconfig"
    unset GIT_CONFIG_GLOBAL
    export HOME="$T/home" XDG_CONFIG_HOME="$T/home/.config"
    hook_control
    run_scratch
    [ "$status" -eq 0 ]
    [ ! -e "$T/marker-outside-scratch" ]
}

@test "a hook named in the system git config does not run during setup" {
    fake_codex_plain
    make_hook_config
    export GIT_CONFIG_SYSTEM="$T/hostile.gitconfig"
    unset GIT_CONFIG_NOSYSTEM
    hook_control
    run_scratch
    [ "$status" -eq 0 ]
    [ ! -e "$T/marker-outside-scratch" ]
}

@test "a hook injected through GIT_CONFIG_COUNT does not run during setup" {
    fake_codex_plain
    make_hook_config
    export GIT_CONFIG_COUNT=1 GIT_CONFIG_KEY_0=core.hooksPath GIT_CONFIG_VALUE_0="$T/hooks"
    hook_control
    run_scratch
    [ "$status" -eq 0 ]
    [ ! -e "$T/marker-outside-scratch" ]
}

@test "a template directory named by the environment does not run during setup" {
    fake_codex_plain
    mkdir -p "$T/tpl/hooks"
    cat > "$T/tpl/hooks/post-checkout" <<EOF
#!/usr/bin/env bash
echo fired > "$T/marker-outside-scratch"
EOF
    chmod +x "$T/tpl/hooks/post-checkout"
    export GIT_TEMPLATE_DIR="$T/tpl"
    run_scratch
    [ "$status" -eq 0 ]
    [ ! -e "$T/marker-outside-scratch" ]
}

@test "setup git commands name hooks off and ignore global and system config" {
    run grep -n '_review_scratch_git()' -A5 "$DISPATCH"
    [[ "$output" == *"GIT_CONFIG_GLOBAL=/dev/null"* ]]
    [[ "$output" == *"GIT_CONFIG_NOSYSTEM=1"* ]]
    # No bare git call remains in the setup and source-check functions.
    ! sed -n '/^_review_scratch_setup()/,/^_dispatch_cleanup_state()/p' "$DISPATCH" | grep -E '(\$\(|^[[:space:]]+)git (-C|clone)'
}
