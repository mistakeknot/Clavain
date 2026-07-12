#!/usr/bin/env bats

setup() {
    REPO_ROOT="$(cd "$BATS_TEST_DIRNAME/../.." && pwd)"
    FIXTURE_ROOT="$BATS_TEST_TMPDIR/release-fixture"
    INTERCORE_ROOT="$BATS_TEST_TMPDIR/intercore-fixture"
    mkdir -p "$FIXTURE_ROOT/scripts" "$FIXTURE_ROOT/cmd/clavain-cli" "$FIXTURE_ROOT/bin" "$FIXTURE_ROOT/fake-bin"
    cp -f "$REPO_ROOT/scripts/build-release.sh" "$FIXTURE_ROOT/scripts/build-release.sh"
    cp -f "$REPO_ROOT/scripts/verify-release-binaries.sh" "$FIXTURE_ROOT/scripts/verify-release-binaries.sh"

    cat >"$FIXTURE_ROOT/fake-bin/go" <<'EOF'
#!/usr/bin/env bash
set -euo pipefail

require_sanitized_go_env() {
    [[ "${GOWORK:-}" == "off" && -z "${GOFLAGS:-}" ]] || {
        echo "fake go: unsanitized GOWORK/GOFLAGS" >&2
        exit 11
    }
}
require_sanitized_go_env

if [[ "${1:-}" == "version" && "${2:-}" != "-m" ]]; then
    echo "go version go1.26.4 test/arch"
    exit 0
fi

if [[ "${1:-}" == "version" && "${2:-}" == "-m" ]]; then
    artifact="$3"
    platform="$(basename "$artifact" | sed 's/^clavain-cli-go-//')"
    goos="${platform%%-*}"
    goarch="${platform#*-}"
    source_revision="$(sed -n 's/^source://p' "$artifact")"
    printf '%s: go1.26.4\n' "$artifact"
    printf '\tpath\tgithub.com/mistakeknot/clavain-cli\n'
    printf '\tbuild\t-trimpath=true\n'
    sed -n 's/^tag:/\tbuild\t-tags=/p' "$artifact"
    printf '\tbuild\tGOOS=%s\n' "$goos"
    printf '\tbuild\tGOARCH=%s\n' "$goarch"
    printf '\tbuild\tvcs.revision=%s\n' "$source_revision"
    printf '\tbuild\tvcs.modified=false\n'
    exit 0
fi

if [[ " $* " == *" list -m "* ]]; then
    printf '%s\n' "$FAKE_INTERCORE_ROOT"
    exit 0
fi

out=""
trimpath=false
tags=""
source_dir=""
while (($#)); do
    if [[ "$1" == "-C" ]]; then
        source_dir="$2"
    fi
    if [[ "$1" == "-trimpath" ]]; then
        trimpath=true
    fi
    if [[ "$1" == "-tags" ]]; then
        tags="$2"
    fi
    if [[ "$1" == "-o" ]]; then
        out="$2"
    fi
    shift
done
[[ -n "$out" ]] || { echo "fake go: missing -o" >&2; exit 2; }
[[ "$trimpath" == true ]] || { echo "fake go: missing -trimpath" >&2; exit 4; }
[[ "$tags" =~ ^intercore_rev_[0-9a-f]{40}$ ]] || {
    echo "fake go: missing Intercore build tag" >&2
    exit 6
}
if [[ "$source_dir" == *clavain-build-release.* ]]; then
    snapshot_root="$(cd "$source_dir/../../../.." && pwd)"
    [[ -d "$snapshot_root/os/Clavain/.git" ]] || exit 7
    [[ -d "$snapshot_root/core/intercore/.git" ]] || exit 8
    [[ "$(git -C "$snapshot_root/os/Clavain" rev-parse HEAD)" == "$(git -C "$FAKE_RELEASE_ROOT" rev-parse HEAD)" ]] || exit 9
    [[ "$(git -C "$snapshot_root/core/intercore" rev-parse HEAD)" == "$(git -C "$FAKE_INTERCORE_ROOT" rev-parse HEAD)" ]] || exit 10
fi

if [[ "${FAKE_ALLOW_EXISTING_OUTPUTS:-}" != 1 ]] &&
   find "$FAKE_RELEASE_OUT_DIR" -type f -print -quit | grep -q .; then
    echo "fake go: release output changed before all builds completed" >&2
    exit 3
fi
if [[ -n "${FAKE_FAIL_GOOS:-}" && "${GOOS:-native}" == "$FAKE_FAIL_GOOS" ]]; then
    echo "fake go: injected ${GOOS} failure" >&2
    exit 5
fi

mkdir -p "$(dirname "$out")"
printf 'artifact:%s/%s\n' "${GOOS:-native}" "${GOARCH:-native}" >"$out"
printf 'tag:%s\n' "$tags" >>"$out"
printf 'source:%s\n' "$(git -C "$source_dir" rev-parse HEAD)" >>"$out"
printf '%s\t%s\n' "$source_dir" "$out" >>"$FAKE_GO_LOG"
EOF
    chmod +x "$FIXTURE_ROOT/fake-bin/go"

    printf '/bin/\n/fake-bin/\n/go.log\n' >"$FIXTURE_ROOT/.gitignore"
    git -C "$FIXTURE_ROOT" init -q
    git -C "$FIXTURE_ROOT" config user.name "Release Test"
    git -C "$FIXTURE_ROOT" config user.email "release-test@example.invalid"
    cat >"$FIXTURE_ROOT/cmd/clavain-cli/go.mod" <<'EOF'
module github.com/mistakeknot/clavain-cli

go 1.26

replace github.com/mistakeknot/intercore => ../../../../core/intercore
EOF
    git -C "$FIXTURE_ROOT" add .gitignore scripts/build-release.sh scripts/verify-release-binaries.sh cmd/clavain-cli/go.mod
    git -C "$FIXTURE_ROOT" commit -q -m "fixture"

    mkdir -p "$INTERCORE_ROOT"
    git -C "$INTERCORE_ROOT" init -q
    git -C "$INTERCORE_ROOT" config user.name "Intercore Test"
    git -C "$INTERCORE_ROOT" config user.email "intercore-test@example.invalid"
    printf 'module github.com/mistakeknot/intercore\n' >"$INTERCORE_ROOT/go.mod"
    git -C "$INTERCORE_ROOT" add go.mod
    git -C "$INTERCORE_ROOT" commit -q -m "fixture"
}

release_env() {
    env \
        PATH="$FIXTURE_ROOT/fake-bin:$PATH" \
        TMPDIR="$BATS_TEST_TMPDIR" \
        FAKE_RELEASE_ROOT="$FIXTURE_ROOT" \
        FAKE_INTERCORE_ROOT="$INTERCORE_ROOT" \
        FAKE_RELEASE_OUT_DIR="$FIXTURE_ROOT/bin" \
        FAKE_GO_LOG="$FIXTURE_ROOT/go.log" \
        "$@"
}

hash_file() {
    shasum -a 256 "$1" | awk '{print $1}'
}

write_release_fixture() {
    local source_revision intercore_revision platform artifact
    source_revision="$(git -C "$FIXTURE_ROOT" rev-parse HEAD)"
    intercore_revision="$(git -C "$INTERCORE_ROOT" rev-parse HEAD)"

    for platform in darwin-arm64 linux-amd64 windows-amd64; do
        artifact="$FIXTURE_ROOT/bin/clavain-cli-go-$platform"
        printf 'artifact:%s\ntag:intercore_rev_%s\nsource:%s\n' \
            "$platform" "$intercore_revision" "$source_revision" >"$artifact"
        chmod +x "$artifact"
    done

    jq -n \
        --arg source_revision "$source_revision" \
        --arg intercore_revision "$intercore_revision" \
        --arg darwin_sha "$(hash_file "$FIXTURE_ROOT/bin/clavain-cli-go-darwin-arm64")" \
        --arg linux_sha "$(hash_file "$FIXTURE_ROOT/bin/clavain-cli-go-linux-amd64")" \
        --arg windows_sha "$(hash_file "$FIXTURE_ROOT/bin/clavain-cli-go-windows-amd64")" \
        '{
          schema_version: 1,
          source_revision: $source_revision,
          intercore_revision: $intercore_revision,
          go_version: "go1.26.4",
          artifacts: {
            "darwin-arm64": {path:"bin/clavain-cli-go-darwin-arm64", sha256:$darwin_sha, goos:"darwin", goarch:"arm64"},
            "linux-amd64": {path:"bin/clavain-cli-go-linux-amd64", sha256:$linux_sha, goos:"linux", goarch:"amd64"},
            "windows-amd64": {path:"bin/clavain-cli-go-windows-amd64", sha256:$windows_sha, goos:"windows", goarch:"amd64"}
          }
        }' >"$FIXTURE_ROOT/bin/release-manifest.json"
}

@test "release builds stay outside the tracked output directory until complete" {
    run release_env bash "$FIXTURE_ROOT/scripts/build-release.sh"

    [ "$status" -eq 0 ]
    [ "$(wc -l <"$FIXTURE_ROOT/go.log" | tr -d ' ')" -eq 4 ]
    [ -x "$FIXTURE_ROOT/bin/clavain-cli-go-darwin-arm64" ]
    [ -x "$FIXTURE_ROOT/bin/clavain-cli-go-linux-amd64" ]
    [ -x "$FIXTURE_ROOT/bin/clavain-cli-go-windows-amd64" ]
    [ -x "$FIXTURE_ROOT/bin/clavain-cli-go" ]
    [ -f "$FIXTURE_ROOT/bin/release-manifest.json" ]
    [ ! -e "$FIXTURE_ROOT/.git/clavain-build-release.lock" ]

    shopt -s nullglob
    stage_dirs=("$BATS_TEST_TMPDIR"/clavain-build-release.*)
    [ "${#stage_dirs[@]}" -eq 0 ]
}

@test "release build records the exact clean Intercore revision in manifest and artifacts" {
    run release_env bash "$FIXTURE_ROOT/scripts/build-release.sh"

    [ "$status" -eq 0 ]
    expected_revision="$(git -C "$INTERCORE_ROOT" rev-parse HEAD)"
    [ "$(jq -r '.intercore_revision' "$FIXTURE_ROOT/bin/release-manifest.json")" = "$expected_revision" ]
    [ "$(jq -r '.source_revision' "$FIXTURE_ROOT/bin/release-manifest.json")" = "$(git -C "$FIXTURE_ROOT" rev-parse HEAD)" ]
    [ "$(jq -r '.go_version' "$FIXTURE_ROOT/bin/release-manifest.json")" = "go1.26.4" ]
    release_env env GOWORK=off GOFLAGS= go version -m "$FIXTURE_ROOT/bin/clavain-cli-go-linux-amd64" | \
        grep -F $'\tbuild\t-tags=intercore_rev_'"$expected_revision" >/dev/null

    run release_env bash "$FIXTURE_ROOT/scripts/verify-release-binaries.sh"
    [ "$status" -eq 0 ]
}

@test "release build compiles from immutable detached source snapshots" {
    run release_env bash "$FIXTURE_ROOT/scripts/build-release.sh"

    [ "$status" -eq 0 ]
    while IFS=$'\t' read -r source_dir _; do
        [ "$source_dir" != "$FIXTURE_ROOT/cmd/clavain-cli" ]
        [[ "$source_dir" == "$BATS_TEST_TMPDIR"/clavain-build-release.*/source/os/Clavain/cmd/clavain-cli ]]
    done <"$FIXTURE_ROOT/go.log"
}

@test "release build sanitizes inherited Go workspace and overlay flags" {
    run release_env env \
        GOWORK="$BATS_TEST_TMPDIR/hostile.work" \
        GOFLAGS="-overlay=$BATS_TEST_TMPDIR/hostile-overlay.json" \
        bash "$FIXTURE_ROOT/scripts/build-release.sh"

    [ "$status" -eq 0 ]
}

@test "release build refuses a contended repository release lock" {
    lock_dir="$FIXTURE_ROOT/.git/clavain-build-release.lock"
    mkdir -p "$lock_dir"

    run release_env bash "$FIXTURE_ROOT/scripts/build-release.sh"

    [ "$status" -ne 0 ]
    [[ "$output" == *"another release build holds"* ]]
}

@test "a late cross-build failure leaves existing release artifacts unchanged" {
    for artifact in \
        clavain-cli-go-darwin-arm64 \
        clavain-cli-go-linux-amd64 \
        clavain-cli-go-windows-amd64; do
        printf 'old:%s\n' "$artifact" >"$FIXTURE_ROOT/bin/$artifact"
    done

    run release_env env \
        FAKE_ALLOW_EXISTING_OUTPUTS=1 \
        FAKE_FAIL_GOOS=linux \
        bash "$FIXTURE_ROOT/scripts/build-release.sh"

    [ "$status" -ne 0 ]
    for artifact in \
        clavain-cli-go-darwin-arm64 \
        clavain-cli-go-linux-amd64 \
        clavain-cli-go-windows-amd64; do
        [ "$(cat "$FIXTURE_ROOT/bin/$artifact")" = "old:$artifact" ]
    done
    [ ! -e "$FIXTURE_ROOT/bin/clavain-cli-go" ]
}

@test "release build refuses tracked source changes before invoking go" {
    printf '\n# dirty\n' >>"$FIXTURE_ROOT/scripts/build-release.sh"

    run release_env bash "$FIXTURE_ROOT/scripts/build-release.sh"

    [ "$status" -ne 0 ]
    [ ! -e "$FIXTURE_ROOT/go.log" ]
}

@test "release build refuses dirty Intercore source before invoking a compiler" {
    printf '\n// dirty\n' >>"$INTERCORE_ROOT/go.mod"

    run release_env bash "$FIXTURE_ROOT/scripts/build-release.sh"

    [ "$status" -ne 0 ]
    [[ "$output" == *"Intercore worktree is not clean"* ]]
    [ ! -e "$FIXTURE_ROOT/go.log" ]
}

@test "release build aborts when artifact hashing fails" {
    cat >"$FIXTURE_ROOT/fake-bin/sha256sum" <<'EOF'
#!/usr/bin/env bash
exit 9
EOF
    cat >"$FIXTURE_ROOT/fake-bin/shasum" <<'EOF'
#!/usr/bin/env bash
exit 9
EOF
    chmod +x "$FIXTURE_ROOT/fake-bin/sha256sum" "$FIXTURE_ROOT/fake-bin/shasum"

    run release_env bash "$FIXTURE_ROOT/scripts/build-release.sh"

    [ "$status" -ne 0 ]
    [ ! -e "$FIXTURE_ROOT/bin/release-manifest.json" ]
}

@test "release verification rejects a handwritten Intercore revision mismatch" {
    write_release_fixture
    jq '.intercore_revision = "0000000000000000000000000000000000000000"' \
        "$FIXTURE_ROOT/bin/release-manifest.json" >"$FIXTURE_ROOT/bin/release-manifest.json.tmp"
    mv -f "$FIXTURE_ROOT/bin/release-manifest.json.tmp" "$FIXTURE_ROOT/bin/release-manifest.json"

    run release_env bash "$FIXTURE_ROOT/scripts/verify-release-binaries.sh"

    [ "$status" -ne 0 ]
    [[ "$output" == *"Intercore revision mismatch"* ]]
}

@test "release verification accepts matching checkout and artifact provenance" {
    write_release_fixture

    run release_env bash "$FIXTURE_ROOT/scripts/verify-release-binaries.sh"

    [ "$status" -eq 0 ]
    echo "$output" | jq -e \
        --arg revision "$(git -C "$INTERCORE_ROOT" rev-parse HEAD)" \
        '.verified == true and .intercore_revision == $revision and .artifact_count == 3' >/dev/null
}

@test "release verification rejects descendant CLI source changes" {
    write_release_fixture
    printf 'package main\n' >"$FIXTURE_ROOT/cmd/clavain-cli/main.go"
    git -C "$FIXTURE_ROOT" add cmd/clavain-cli/main.go
    git -C "$FIXTURE_ROOT" commit -q -m "change CLI source"

    run release_env bash "$FIXTURE_ROOT/scripts/verify-release-binaries.sh"

    [ "$status" -ne 0 ]
    [[ "$output" == *"CLI source changed after release build"* ]]
}

@test "release verification rejects malformed artifact objects instead of checking zero rows" {
    write_release_fixture
    jq '.artifacts["darwin-arm64"] = "not-an-artifact"' \
        "$FIXTURE_ROOT/bin/release-manifest.json" >"$FIXTURE_ROOT/bin/release-manifest.json.tmp"
    mv -f "$FIXTURE_ROOT/bin/release-manifest.json.tmp" "$FIXTURE_ROOT/bin/release-manifest.json"

    run release_env bash "$FIXTURE_ROOT/scripts/verify-release-binaries.sh"

    [ "$status" -ne 0 ]
    [[ "$output" == *"manifest schema is invalid"* ]]
}

@test "release verification rejects non-exact artifact platform metadata" {
    write_release_fixture
    jq '.artifacts["darwin-arm64"].goos = ""' \
        "$FIXTURE_ROOT/bin/release-manifest.json" >"$FIXTURE_ROOT/bin/release-manifest.json.tmp"
    mv -f "$FIXTURE_ROOT/bin/release-manifest.json.tmp" "$FIXTURE_ROOT/bin/release-manifest.json"

    run release_env bash "$FIXTURE_ROOT/scripts/verify-release-binaries.sh"

    [ "$status" -ne 0 ]
    [[ "$output" == *"manifest schema is invalid"* ]]
}

@test "release verification rejects a manifest toolchain mismatch" {
    write_release_fixture
    jq '.go_version = "go0.0.0"' \
        "$FIXTURE_ROOT/bin/release-manifest.json" >"$FIXTURE_ROOT/bin/release-manifest.json.tmp"
    mv -f "$FIXTURE_ROOT/bin/release-manifest.json.tmp" "$FIXTURE_ROOT/bin/release-manifest.json"

    run release_env bash "$FIXTURE_ROOT/scripts/verify-release-binaries.sh"

    [ "$status" -ne 0 ]
    [[ "$output" == *"darwin-arm64 Go version mismatch"* ]]
}

@test "release verification rejects an artifact built from another Intercore revision" {
    write_release_fixture
    artifact="$FIXTURE_ROOT/bin/clavain-cli-go-darwin-arm64"
    sed -i.bak 's/^tag:.*/tag:intercore_rev_0000000000000000000000000000000000000000/' "$artifact"
    rm -f "$artifact.bak"
    digest="$(hash_file "$artifact")"
    jq --arg digest "$digest" '.artifacts["darwin-arm64"].sha256 = $digest' \
        "$FIXTURE_ROOT/bin/release-manifest.json" >"$FIXTURE_ROOT/bin/release-manifest.json.tmp"
    mv -f "$FIXTURE_ROOT/bin/release-manifest.json.tmp" "$FIXTURE_ROOT/bin/release-manifest.json"

    run release_env bash "$FIXTURE_ROOT/scripts/verify-release-binaries.sh"

    [ "$status" -ne 0 ]
    [[ "$output" == *"darwin-arm64 Intercore revision mismatch"* ]]
}
