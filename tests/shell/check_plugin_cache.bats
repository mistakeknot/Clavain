#!/usr/bin/env bats
# Tests for scripts/check-plugin-cache.sh (mk-i3u8)
#
# The load-bearing case is the symlink LOOP: on 2026-09-01 the clavain cache
# held 0.6.300 -> 0.6.302 and 0.6.302 -> 0.6.300 with no directory behind
# either, installed_plugins.json pointed at 0.6.302, and every Clavain hook
# failed to start for weeks with nothing reporting it. `-d` is false on a loop
# and `readlink -f` fails, so the check must land in FAIL, not in "no manifest".

setup() {
    load test_helper
    SCRIPT="$BATS_TEST_DIRNAME/../../scripts/check-plugin-cache.sh"
    ROOT="$(mktemp -d)"
    CACHE="$ROOT/plugins/cache/mkt"
    REGISTRY="$ROOT/plugins/installed_plugins.json"
    mkdir -p "$CACHE"
}

teardown() {
    rm -rf "$ROOT"
}

# $1 = plugin name, $2 = version dir, $3 = manifest version ("" = no manifest,
# "-" = manifest without a version field)
make_plugin() {
    local d="$CACHE/$1/$2"
    mkdir -p "$d/.claude-plugin" "$d/hooks"
    printf '#!/usr/bin/env bash\nexit 0\n' > "$d/hooks/session-start.sh"
    printf 'x\n' > "$d/README.md"
    printf 'y\n' > "$d/LICENSE"
    case "$3" in
        "")  rmdir "$d/.claude-plugin" ;;
        "-") printf '{"name":"%s"}\n' "$1" > "$d/.claude-plugin/plugin.json" ;;
        *)   printf '{"name":"%s","version":"%s"}\n' "$1" "$3" > "$d/.claude-plugin/plugin.json" ;;
    esac
}

# $@ = "name version installPath" triples, one per line
write_registry() {
    {
        echo '{"version":2,"plugins":{'
        local first=1
        while read -r name version path; do
            [[ -n "$name" ]] || continue
            [[ $first -eq 1 ]] || echo ','
            first=0
            printf '"%s@mkt":[{"scope":"user","version":"%s","installPath":"%s"}]' "$name" "$version" "$path"
        done
        echo '}}'
    } > "$REGISTRY"
}

@test "a healthy plugin passes" {
    make_plugin good 1.0.0 1.0.0
    write_registry <<<"good 1.0.0 $CACHE/good/1.0.0"
    run bash "$SCRIPT" --registry "$REGISTRY"
    [ "$status" -eq 0 ]
    [[ "$output" == *"good@mkt 1.0.0: PASS"* ]]
    [[ "$output" == *"plugin cache: PASS"* ]]
}

@test "a symlink loop is FAIL and says so — the 2026-09-01 shape" {
    ln -s 0.6.302 "$CACHE/clavain-0.6.300"; mkdir -p "$CACHE/clavain"
    ln -s 0.6.302 "$CACHE/clavain/0.6.300"
    ln -s 0.6.300 "$CACHE/clavain/0.6.302"
    write_registry <<<"clavain 0.6.302 $CACHE/clavain/0.6.302"
    run bash "$SCRIPT" --registry "$REGISTRY"
    [ "$status" -eq 1 ]
    [[ "$output" == *"clavain@mkt 0.6.302: FAIL"* ]]
    [[ "$output" == *"symlink LOOP"* ]]
    [[ "$output" == *"plugin cache: FAIL"* ]]
}

@test "a dangling symlink is FAIL, distinct from a loop" {
    mkdir -p "$CACHE/p"
    ln -s 9.9.9 "$CACHE/p/1.0.0"
    write_registry <<<"p 1.0.0 $CACHE/p/1.0.0"
    run bash "$SCRIPT" --registry "$REGISTRY"
    [ "$status" -eq 1 ]
    [[ "$output" == *"dangling symlink"* ]]
}

@test "a missing installPath is FAIL" {
    write_registry <<<"ghost 1.0.0 $CACHE/ghost/1.0.0"
    run bash "$SCRIPT" --registry "$REGISTRY"
    [ "$status" -eq 1 ]
    [[ "$output" == *"does not exist"* ]]
}

@test "a symlink to a real directory passes — it can run hooks" {
    make_plugin real 1.0.0 1.0.0
    ln -s 1.0.0 "$CACHE/real/1.0.1"
    write_registry <<<"real 1.0.0 $CACHE/real/1.0.1"
    run bash "$SCRIPT" --registry "$REGISTRY"
    [ "$status" -eq 0 ]
    [[ "$output" == *"real@mkt 1.0.0: PASS"* ]]
}

@test "no manifest is a WARN, not a FAIL — lsp-only plugins ship none" {
    make_plugin lsp 1.0.0 ""
    write_registry <<<"lsp 1.0.0 $CACHE/lsp/1.0.0"
    run bash "$SCRIPT" --registry "$REGISTRY"
    [ "$status" -eq 0 ]
    [[ "$output" == *"lsp@mkt 1.0.0: WARN"* ]]
    [[ "$output" == *"no .claude-plugin/plugin.json"* ]]
}

@test "a manifest without a version is not compared — official plugins record a sha" {
    make_plugin official 0e3f501d0f4a "-"
    write_registry <<<"official 0e3f501d0f4a $CACHE/official/0e3f501d0f4a"
    run bash "$SCRIPT" --registry "$REGISTRY"
    [ "$status" -eq 0 ]
    [[ "$output" == *"official@mkt 0e3f501d0f4a: PASS"* ]]
}

@test "a manifest version that disagrees with the registry is WARN" {
    make_plugin drift 2.0.0 1.9.0
    write_registry <<<"drift 2.0.0 $CACHE/drift/2.0.0"
    run bash "$SCRIPT" --registry "$REGISTRY"
    [ "$status" -eq 0 ]
    [[ "$output" == *"drift@mkt 2.0.0: WARN"* ]]
    [[ "$output" == *"1.9.0 != registry version 2.0.0"* ]]
}

@test "verdicts are per plugin: one loop does not hide a healthy neighbour" {
    make_plugin good 1.0.0 1.0.0
    mkdir -p "$CACHE/bad"; ln -s 2 "$CACHE/bad/1"; ln -s 1 "$CACHE/bad/2"
    write_registry <<EOF2
good 1.0.0 $CACHE/good/1.0.0
bad 1 $CACHE/bad/1
EOF2
    run bash "$SCRIPT" --registry "$REGISTRY" --json
    [ "$status" -eq 1 ]
    [ "$(jq -r '.plugins[] | select(.plugin=="good@mkt") | .verdict' <<<"$output")" = "PASS" ]
    [ "$(jq -r '.plugins[] | select(.plugin=="bad@mkt") | .verdict' <<<"$output")" = "FAIL" ]
    [ "$(jq -r '.ok' <<<"$output")" = "false" ]
}

@test "installer leftovers are counted, never scored" {
    make_plugin good 1.0.0 1.0.0
    mkdir -p "$ROOT/plugins/cache/temp_git_123_abc" "$ROOT/plugins/cache/temp_git_456_def"
    write_registry <<<"good 1.0.0 $CACHE/good/1.0.0"
    run bash "$SCRIPT" --registry "$REGISTRY" --json
    [ "$status" -eq 0 ]
    [ "$(jq -r '.temp_git_leftovers' <<<"$output")" = "2" ]
}

@test "an unreadable registry is 'could not evaluate' (exit 2), never PASS" {
    run bash "$SCRIPT" --registry "$ROOT/nope.json"
    [ "$status" -eq 2 ]
    [[ "$output" != *"PASS"* ]]
}
