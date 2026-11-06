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

@test "setup git commands run under an env -i allowlist with hooks off and global and system config ignored" {
    run grep -n '_review_scratch_git()' -A16 "$DISPATCH"
    [[ "$output" == *"env -i"* ]]
    [[ "$output" == *"GIT_CONFIG_GLOBAL=/dev/null"* ]]
    [[ "$output" == *"GIT_CONFIG_NOSYSTEM=1"* ]]
    # No bare git call remains in the setup and source-check functions.
    ! sed -n '/^_review_scratch_snapshot_in()/,/^_dispatch_cleanup_state()/p' "$DISPATCH" | grep -E '(\$\(|^[[:space:]]+)git (-C|clone)'
}

# ---- Fix round 2: inherited environment and repo-local configuration --------
# Setup, the source fingerprint and the receipt run git outside the codex
# sandbox against the caller's real checkout. (1) No inherited GIT_* variable
# may steer them; (2) nothing executable named by the checkout's own
# configuration or attributes (filters, textconv, external diff, merge drivers,
# fsmonitor, includes) may run.

# A repository whose root commit holds .gitattributes ($1, optional). The base
# and the head diverge from that root and both edit file a, so merging the head
# onto the base is a real content merge and a head-side edit exists to diff.
mk_diverged_repo() {
    R="$T/drepo"; git init -q -b main "$R"
    git -C "$R" config user.email t@t; git -C "$R" config user.name t
    seq 1 10 > "$R/a"
    [ -z "${1:-}" ] || printf '%s\n' "$1" > "$R/.gitattributes"
    git -C "$R" add -A; git -C "$R" commit -qm root
    local root; root="$(git -C "$R" rev-parse HEAD)"
    sed -i '1s/.*/one/' "$R/a"; git -C "$R" commit -qam base-side
    BASE="$(git -C "$R" rev-parse HEAD)"
    git -C "$R" checkout -q -b pr "$root"
    sed -i '10s/.*/ten/' "$R/a"; git -C "$R" commit -qam head-side
    HEAD_SHA="$(git -C "$R" rev-parse HEAD)"
    RECEIPT_FLAGS=(--repo o/r --repo-id R_abc123 --pr 7 --head "$HEAD_SHA" --base "$BASE")
}

# Edit a tracked file without changing its size, so git must read the content
# (and run any clean filter) to learn whether it changed.
dirty_same_size() { printf 'X' | dd of="$R/a" bs=1 count=1 conv=notrunc 2>/dev/null; }

# A hostile helper that proves it ran by touching a marker outside any scratch
# directory. Mode "cat" behaves as a pass-through filter; "none" just exits.
evil_script() {  # name [cat|none]
    {
        printf '#!/usr/bin/env bash\ntouch %q\n' "$T/marker-$1"
        [ "${2:-cat}" = cat ] && printf 'cat\n' || printf 'exit 0\n'
    } > "$T/evil-$1.sh"
    chmod +x "$T/evil-$1.sh"
}

# Control: the same hostile checkout, copied, really fires the route under
# plain git, so the "does not run" assertions below are not vacuous.
assert_fires() {  # marker-name, then the plain command to run in a copy
    local name="$1"; shift
    rm -f "$T/marker-$name"; rm -rf "$T/ctl"; cp -a "$R" "$T/ctl"
    ( cd "$T/ctl" && "$@" ) >/dev/null 2>&1 </dev/null || true
    [ -e "$T/marker-$name" ] || { echo "control did not fire: $name" >&2; return 1; }
    rm -f "$T/marker-$name"; rm -rf "$T/ctl"
}

# Dispatch survives the hostile checkout: succeeds, the route never ran, the
# scratch is gone and the receipt exists.
assert_survives() {  # marker-name
    run_scratch
    [ "$status" -eq 0 ] || { echo "$output" >&2; return 1; }
    [ ! -e "$T/marker-$1" ] || { echo "hostile route ran: $1" >&2; return 1; }
    [ -z "$(scratch_dirs)" ]
    [ -f "$T/reviews/o__r/7-$HEAD_SHA.json" ]
}

@test "an inherited GIT_INDEX_FILE outside scratch is never written" {
    fake_codex_plain
    export GIT_INDEX_FILE="$T/outside.index"
    # Control: plain git does write the external index.
    rm -rf "$T/ctl"
    git clone -q --no-checkout "$R" "$T/ctl"
    git -C "$T/ctl" checkout -q --detach "$HEAD_SHA"
    [ -e "$T/outside.index" ]
    rm -rf "$T/outside.index" "$T/ctl"
    run_scratch
    [ "$status" -eq 0 ]
    [ ! -e "$T/outside.index" ]
    [ "$(cat "$T/codex.clone_head")" = "$HEAD_SHA" ]
    [ -z "$(scratch_dirs)" ]
}

@test "an inherited GIT_DIR and GIT_WORK_TREE cannot redirect setup to another repository" {
    fake_codex_plain
    local d="$T/decoy"; git init -q -b main "$d"
    git -C "$d" config user.email t@t; git -C "$d" config user.name t
    echo z > "$d/z"; git -C "$d" add z; git -C "$d" commit -qm decoy
    local before; before="$(cd "$d" && find . -type f -not -name '*.lock' | LC_ALL=C sort | xargs sha256sum | sha256sum)"
    # Control: plain git is redirected by it.
    [ "$(GIT_DIR="$d/.git" git -C "$R" rev-parse HEAD)" != "$HEAD_SHA" ]
    export GIT_DIR="$d/.git" GIT_WORK_TREE="$d"
    run_scratch
    [ "$status" -eq 0 ]
    [ "$(cat "$T/codex.clone_head")" = "$HEAD_SHA" ]
    [ "$(cd "$d" && find . -type f -not -name '*.lock' | LC_ALL=C sort | xargs sha256sum | sha256sum)" = "$before" ]
    [ -z "$(scratch_dirs)" ]
}

@test "an inherited GIT_OBJECT_DIRECTORY receives no objects from setup or the receipt" {
    fake_codex_plain
    mkdir -p "$T/outobj"
    # Control: plain git writes objects there.
    echo probe | GIT_OBJECT_DIRECTORY="$T/outobj" git -C "$R" hash-object -w --stdin >/dev/null
    [ -n "$(find "$T/outobj" -type f)" ]
    rm -rf "$T/outobj"; mkdir -p "$T/outobj"
    export GIT_OBJECT_DIRECTORY="$T/outobj" GIT_ALTERNATE_OBJECT_DIRECTORIES="$R/.git/objects"
    run_scratch
    [ "$status" -eq 0 ]
    [ -z "$(find "$T/outobj" -type f)" ]
    [ "$(cat "$T/codex.clone_head")" = "$HEAD_SHA" ]
}

@test "the scratch git helper hands git none of the inherited GIT_* or other hostile variables" {
    local names="GIT_SSH GIT_SSH_COMMAND GIT_ASKPASS SSH_ASKPASS GIT_EXTERNAL_DIFF GIT_PAGER GIT_EDITOR GIT_PROXY_COMMAND GIT_DIFF_OPTS GIT_ATTR_SOURCE GIT_INDEX_FILE GIT_OBJECT_DIRECTORY GIT_CONFIG GIT_CONFIG_COUNT GIT_CONFIG_PARAMETERS GIT_TEMPLATE_DIR GIT_TRACE GIT_NAMESPACE"
    local n
    # Control: plain git hands them to an alias subprocess.
    run bash -c 'cd "$1"; shift; for n in "$@"; do export "$n=HOSTILE-$n"; done; unset GIT_CONFIG_COUNT GIT_CONFIG_PARAMETERS GIT_CONFIG GIT_OBJECT_DIRECTORY GIT_INDEX_FILE GIT_TEMPLATE_DIR GIT_TRACE GIT_NAMESPACE; git -c "alias.penv=!env" penv' _ "$T" $names
    [ "$status" -eq 0 ]
    [[ "$output" == *"HOSTILE-GIT_SSH_COMMAND"* ]]
    # The helper: only the allowlist reaches git.
    run bash -c 'cd "$1"; src="$2"; shift 2; source <(sed -n "/^_review_scratch_git()/,/^}/p" "$src")
        for n in "$@"; do export "$n=HOSTILE-$n"; done
        _review_scratch_git -c "alias.penv=!env" penv' _ "$T" "$DISPATCH" $names
    [ "$status" -eq 0 ]
    ! grep -q HOSTILE <<<"$output"
    [[ "$output" == *"GIT_CONFIG_GLOBAL=/dev/null"* ]]
    [[ "$output" == *"GIT_CONFIG_NOSYSTEM=1"* ]]
    [[ "$output" == *"GIT_OPTIONAL_LOCKS=0"* ]]
}

@test "a repo-local clean filter does not run on the real checkout (baseline and final check)" {
    fake_codex_plain
    mk_diverged_repo 'a filter=evil'
    evil_script clean cat
    git -C "$R" config filter.evil.clean "$T/evil-clean.sh"
    dirty_same_size
    assert_fires clean git status --porcelain
    assert_survives clean
}

@test "a clean filter defined through include.path does not run" {
    fake_codex_plain
    mk_diverged_repo 'a filter=evil'
    evil_script inc cat
    git config --file "$T/inc.gitconfig" filter.evil.clean "$T/evil-inc.sh"
    git -C "$R" config include.path "$T/inc.gitconfig"
    dirty_same_size
    assert_fires inc git status --porcelain
    assert_survives inc
}

@test "a repo-local core.fsmonitor does not run on the real checkout" {
    fake_codex_plain
    evil_script fsm none
    git -C "$R" config core.fsmonitor "$T/evil-fsm.sh"
    assert_fires fsm git status --porcelain
    assert_survives fsm
}

@test "a repo-local merge driver does not run in the receipt's merge-tree" {
    fake_codex_plain
    mk_diverged_repo 'a merge=evil'
    printf '#!/usr/bin/env bash\ntouch %q\ncat "$3" > "$2"\n' "$T/marker-merge" > "$T/evil-merge.sh"
    chmod +x "$T/evil-merge.sh"
    git -C "$R" config merge.evil.driver "$T/evil-merge.sh %O %A %B"
    assert_fires merge git merge-tree --write-tree "$BASE" "$HEAD_SHA"
    assert_survives merge
    [[ "$(jq -r .expected_merge_tree "$T/reviews/o__r/7-$HEAD_SHA.json")" =~ ^[0-9a-f]{40}$ ]]
}

@test "a repo-local textconv does not run on a dirty real checkout" {
    fake_codex_plain
    mk_diverged_repo 'a diff=evil'
    evil_script textconv cat
    git -C "$R" config diff.evil.textconv "$T/evil-textconv.sh"
    echo dirty >> "$R/a"
    assert_fires textconv git diff HEAD
    assert_survives textconv
}

@test "a repo-local diff.external does not run on a dirty real checkout" {
    fake_codex_plain
    mk_diverged_repo ''
    evil_script ext none
    git -C "$R" config diff.external "$T/evil-ext.sh"
    echo dirty >> "$R/a"
    assert_fires ext git diff HEAD
    assert_survives ext
}

@test "an inherited GIT_EXTERNAL_DIFF does not run on a dirty real checkout" {
    fake_codex_plain
    mk_diverged_repo ''
    evil_script envext none
    echo dirty >> "$R/a"
    export GIT_EXTERNAL_DIFF="$T/evil-envext.sh"
    assert_fires envext git diff HEAD
    assert_survives envext
}

@test "a repo-local credential helper and core.sshCommand are never reached" {
    fake_codex_plain
    evil_script cred none
    git -C "$R" config credential.helper "!$T/evil-cred.sh"
    git -C "$R" config core.sshCommand "$T/evil-cred.sh"
    assert_survives cred
}

@test "the source's smudge filter is not carried into the scratch clone checkout" {
    fake_codex_plain
    mk_diverged_repo 'a filter=evil'
    evil_script smudge cat
    git -C "$R" config filter.evil.smudge "$T/evil-smudge.sh"
    # Control: a clone that does carry the source configuration fires it.
    rm -f "$T/marker-smudge"; rm -rf "$T/ctl"
    git clone -q --no-checkout "$R" "$T/ctl"
    cp "$R/.git/config" "$T/ctl/.git/config"
    git -C "$T/ctl" checkout -q --detach "$HEAD_SHA"
    [ -e "$T/marker-smudge" ]
    rm -rf "$T/ctl" "$T/marker-smudge"
    assert_survives smudge
}

# ---- Source fingerprint (replaces git status --porcelain) --------------------

# A codex stand-in that runs a shell snippet ($1) before writing its verdict.
fake_codex_runs() {
    cat > "$T/bin/codex" <<EOF
#!/usr/bin/env bash
[[ "\$1" == exec ]] || { echo "codex-cli 0.166.0"; exit 0; }
cat > /dev/null
outfile=""
while [[ \$# -gt 0 ]]; do case "\$1" in -o) outfile="\$2"; shift 2 ;; *) shift ;; esac; done
$1
printf 'Findings: none\n\nVERDICT: PASS\n' > "\$outfile"
exit 0
EOF
    chmod +x "$T/bin/codex"
}

@test "the fingerprint catches a further edit to a file that was already dirty" {
    echo first >> "$R/a"
    fake_codex_runs "echo second >> '$R/a'"
    run_scratch
    [ "$status" -ne 0 ]
    [[ "$output" == *"real checkout status changed"* ]]
}

@test "the fingerprint catches staging, a mode change and a retargeted symlink" {
    ln -s a "$R/lnk"
    git -C "$R" add lnk; git -C "$R" commit -qm lnk
    HEAD_SHA="$(git -C "$R" rev-parse HEAD)"
    RECEIPT_FLAGS=(--repo o/r --repo-id R_abc123 --pr 7 --head "$HEAD_SHA" --base "$BASE")
    echo first >> "$R/a"
    fake_codex_runs "git -C '$R' add a"
    run_scratch; [ "$status" -ne 0 ]; [[ "$output" == *"status changed"* ]]
    git -C "$R" restore --staged a
    fake_codex_runs "chmod +x '$R/b'"
    run_scratch; [ "$status" -ne 0 ]; [[ "$output" == *"status changed"* ]]
    chmod -x "$R/b"
    fake_codex_runs "ln -sfn b '$R/lnk'"
    run_scratch; [ "$status" -ne 0 ]; [[ "$output" == *"status changed"* ]]
}

@test "changes to ignored paths do not fail the run" {
    mkdir -p "$R/.git/info"; echo ignored.log > "$R/.git/info/exclude"
    fake_codex_runs "echo noise > '$R/ignored.log'"
    run_scratch
    [ "$status" -eq 0 ]
}

@test "the fingerprint is stable, works from a subdirectory, and does not hang on a fifo" {
    mkdir -p "$R/sub"; echo s > "$R/sub/f"; mkfifo "$R/pipe"
    run timeout 60 bash -c '
        source <(sed -n "/^_review_scratch_git()/,/^_review_scratch_fail()/p" "$1" | head -n -1)
        a="$(_review_scratch_snapshot "$2")"; b="$(_review_scratch_snapshot "$2")"; c="$(_review_scratch_snapshot "$2/sub")"
        [[ "$a" =~ ^[0-9a-f]{64}$ && "$a" == "$b" && "$a" == "$c" ]] || { echo "a=$a b=$b c=$c"; exit 1; }
        echo changed >> "$2/b"
        d="$(_review_scratch_snapshot "$2")"
        [[ "$d" != "$a" ]]
    ' _ "$DISPATCH" "$R"
    [ "$status" -eq 0 ]
}

@test "scratch mode skips the post-dispatch git diff and status on the real checkout" {
    run sed -n '/^_seat_snapshot()/,/^}/p' "$DISPATCH"
    [[ "$output" == *'REVIEW_SCRATCH:-false}" != true ]] || return 0'* ]]
    run sed -n '/^_post_dispatch_validate()/,/^}/p' "$DISPATCH"
    [[ "$output" == *'REVIEW_SCRATCH:-false}" != true ]] || return 0'* ]]
}

# ---- Failure evidence and signals (fix round 3) -------------------------------
# Failure evidence is written by the dispatcher, outside the codex sandbox. In
# scratch mode it must land in the trusted receipt directory and never in the
# source checkout, and a symlinked .clavain must be refused outright.

fake_codex_http429() {
    cat > "$T/bin/codex" <<EOF
#!/usr/bin/env bash
[[ "\$1" == exec ]] || { echo "codex-cli 0.166.0"; exit 0; }
cat > /dev/null
echo "ERROR: unexpected status 429 Too Many Requests: rate limit exceeded" >&2
exit 1
EOF
    chmod +x "$T/bin/codex"
}

@test "a failed codex run writes its failure evidence to the receipt directory, not the source checkout" {
    fake_codex_http429
    run_scratch
    [ "$status" -ne 0 ]
    [ ! -e "$R/.clavain" ]
    [ -z "$(git -C "$R" status --porcelain --ignored)" ]
    ev="$(find "$T/reviews/intercept" -maxdepth 1 -name '*.json' 2>/dev/null)"
    [ -n "$ev" ]
    [ "$(printf '%s\n' "$ev" | wc -l)" -eq 1 ]
    jq -e '.failure_class != null and .schema_version == 1' "$ev" >/dev/null
    [ -z "$(scratch_dirs)" ]
}

@test "a symlinked .clavain in the source is refused: codex never runs and nothing is written through it" {
    mkdir -p "$T/elsewhere"
    ln -s "$T/elsewhere" "$R/.clavain"
    fake_codex_http429
    rm -f "$T/codex.argv"
    run_scratch
    [ "$status" -ne 0 ]
    [[ "$output" == *"symlinked .clavain"* ]]
    [ -z "$(find "$T/elsewhere" -mindepth 1 2>/dev/null)" ]
    [ -z "$(find "$T/reviews" -mindepth 1 2>/dev/null)" ]
    [ -z "$(scratch_dirs)" ]
}

@test "a symlinked .clavain is refused on a dry run too" {
    mkdir -p "$T/elsewhere"
    ln -s "$T/elsewhere" "$R/.clavain"
    run_scratch --dry-run
    [ "$status" -ne 0 ]
    [[ "$output" == *"symlinked .clavain"* ]]
}

@test "a symlinked .clavain at the repository top is refused when -C is a subdirectory" {
    mkdir -p "$T/elsewhere" "$R/sub"
    ln -s "$T/elsewhere" "$R/.clavain"
    PATH="$T/bin:$PATH" run bash "$DISPATCH" --role-resolved --role cross-lab-review \
        --to codex --model gpt-6.1-sol --resolved-route-json "$ROUTE_JSON" \
        --review-scratch --producer-identity claude-sonnet-5-5 "${RECEIPT_FLAGS[@]}" -C "$R/sub" \
        --prompt-file "$T/prompt.md" -o "$OUT"
    [ "$status" -ne 0 ]
    [[ "$output" == *"symlinked .clavain"* ]]
    [ -z "$(find "$T/elsewhere" -mindepth 1 2>/dev/null)" ]
}

@test "a real .clavain directory with a symlinked intercept is never written through on failure" {
    mkdir -p "$T/elsewhere" "$R/.clavain"
    ln -s "$T/elsewhere" "$R/.clavain/intercept"
    fake_codex_http429
    run_scratch
    [ "$status" -ne 0 ]
    [ -z "$(find "$T/elsewhere" -mindepth 1 2>/dev/null)" ]
    [ -n "$(find "$T/reviews/intercept" -maxdepth 1 -name '*.json' 2>/dev/null)" ]
}

@test "a symlinked evidence directory in the receipt directory fails closed and is not written through" {
    mkdir -p "$T/elsewhere" "$T/reviews"
    ln -s "$T/elsewhere" "$T/reviews/intercept"
    fake_codex_http429
    run_scratch
    [ "$status" -ne 0 ]
    [ -z "$(find "$T/elsewhere" -mindepth 1 2>/dev/null)" ]
    [ ! -e "$R/.clavain" ]
    [ -z "$(scratch_dirs)" ]
}

@test "the scratch state directories are under the receipt directory and refuse symlinks" {
    run bash -c '
        source <(sed -n "/^_review_scratch_state_dir()/,/^}/p" "$1")
        rdir="$2"
        _review_receipt_dir() { printf "%s\n" "$rdir"; }
        d="$(_review_scratch_state_dir capacity)" || exit 1
        [[ "$d" == "$2/capacity" && -d "$d" ]] || exit 2
        mkdir -p "$3"; ln -s "$3" "$2/packets"
        ! _review_scratch_state_dir packets 2>/dev/null
    ' _ "$DISPATCH" "$T/reviews" "$T/elsewhere"
    [ "$status" -eq 0 ]
    [ -z "$(find "$T/elsewhere" -mindepth 1 2>/dev/null)" ]
}

# Runs dispatch in its own process group with a codex that announces itself and
# then hangs, delivers the signal to the whole group (what a terminal ^C or a
# supervising `kill -- -pgid` does) and waits for dispatch to exit.
signal_scratch_run() {
    local sig="$1" pid i
    cat > "$T/bin/codex" <<EOF
#!/usr/bin/env bash
[[ "\$1" == exec ]] || { echo "codex-cli 0.166.0"; exit 0; }
cat > /dev/null
cd_dir=""
while [[ \$# -gt 0 ]]; do case "\$1" in -C) cd_dir="\$2"; shift 2 ;; *) shift ;; esac; done
echo "\$cd_dir" > "$T/codex.cwd"
touch "$T/codex.started"
exec sleep 60
EOF
    chmod +x "$T/bin/codex"
    PATH="$T/bin:$PATH" setsid bash "$DISPATCH" --role-resolved --role cross-lab-review \
        --to codex --model gpt-6.1-sol --resolved-route-json "$ROUTE_JSON" \
        --review-scratch --producer-identity claude-sonnet-5-5 "${RECEIPT_FLAGS[@]}" -C "$R" \
        --prompt-file "$T/prompt.md" -o "$OUT" >"$T/run.out" 2>&1 &
    pid=$!
    for i in $(seq 1 200); do [ -e "$T/codex.started" ] && break; sleep 0.1; done
    [ -e "$T/codex.started" ]
    [ -n "$(scratch_dirs)" ]
    kill -"$sig" -- -"$pid"
    for i in $(seq 1 200); do kill -0 "$pid" 2>/dev/null || break; sleep 0.1; done
    ! kill -0 "$pid" 2>/dev/null
    wait "$pid" && SIG_RC=0 || SIG_RC=$?
}

@test "SIGINT mid-run leaves no scratch directory and writes nothing outside it" {
    signal_scratch_run INT
    [ "$SIG_RC" -ne 0 ]
    [ -z "$(scratch_dirs)" ]
    [ ! -e "$R/.clavain" ]
    [ -z "$(git -C "$R" status --porcelain --ignored)" ]
    [ "$(git -C "$R" rev-parse HEAD)" = "$HEAD_SHA" ]
    [ -z "$(find "$T/home" -mindepth 1 2>/dev/null)" ]
}

@test "SIGTERM mid-run leaves no scratch directory and writes nothing outside it" {
    signal_scratch_run TERM
    [ "$SIG_RC" -ne 0 ]
    [ -z "$(scratch_dirs)" ]
    [ ! -e "$R/.clavain" ]
    [ -z "$(git -C "$R" status --porcelain --ignored)" ]
    [ "$(git -C "$R" rev-parse HEAD)" = "$HEAD_SHA" ]
    [ -z "$(find "$T/home" -mindepth 1 2>/dev/null)" ]
}
