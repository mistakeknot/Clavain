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
