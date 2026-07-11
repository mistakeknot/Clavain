#!/usr/bin/env bats

setup() {
    REPO_ROOT="$(cd "$BATS_TEST_DIRNAME/../.." && pwd)"
    FIXTURE_ROOT="$BATS_TEST_TMPDIR/release-fixture"
    mkdir -p "$FIXTURE_ROOT/scripts" "$FIXTURE_ROOT/cmd/clavain-cli" "$FIXTURE_ROOT/bin" "$FIXTURE_ROOT/fake-bin"
    cp -f "$REPO_ROOT/scripts/build-release.sh" "$FIXTURE_ROOT/scripts/build-release.sh"

    cat >"$FIXTURE_ROOT/fake-bin/go" <<'EOF'
#!/usr/bin/env bash
set -euo pipefail

out=""
trimpath=false
while (($#)); do
    if [[ "$1" == "-trimpath" ]]; then
        trimpath=true
    fi
    if [[ "$1" == "-o" ]]; then
        out="$2"
    fi
    shift
done
[[ -n "$out" ]] || { echo "fake go: missing -o" >&2; exit 2; }
[[ "$trimpath" == true ]] || { echo "fake go: missing -trimpath" >&2; exit 4; }

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
printf '%s\n' "$out" >>"$FAKE_GO_LOG"
EOF
    chmod +x "$FIXTURE_ROOT/fake-bin/go"

    printf '/bin/\n/fake-bin/\n/go.log\n' >"$FIXTURE_ROOT/.gitignore"
    git -C "$FIXTURE_ROOT" init -q
    git -C "$FIXTURE_ROOT" config user.name "Release Test"
    git -C "$FIXTURE_ROOT" config user.email "release-test@example.invalid"
    git -C "$FIXTURE_ROOT" add .gitignore scripts/build-release.sh
    git -C "$FIXTURE_ROOT" commit -q -m "fixture"
}

@test "release builds stay outside the tracked output directory until complete" {
    run env \
        PATH="$FIXTURE_ROOT/fake-bin:$PATH" \
        TMPDIR="$BATS_TEST_TMPDIR" \
        FAKE_RELEASE_OUT_DIR="$FIXTURE_ROOT/bin" \
        FAKE_GO_LOG="$FIXTURE_ROOT/go.log" \
        bash "$FIXTURE_ROOT/scripts/build-release.sh"

    [ "$status" -eq 0 ]
    [ "$(wc -l <"$FIXTURE_ROOT/go.log" | tr -d ' ')" -eq 4 ]
    [ -x "$FIXTURE_ROOT/bin/clavain-cli-go-darwin-arm64" ]
    [ -x "$FIXTURE_ROOT/bin/clavain-cli-go-linux-amd64" ]
    [ -x "$FIXTURE_ROOT/bin/clavain-cli-go-windows-amd64" ]
    [ -x "$FIXTURE_ROOT/bin/clavain-cli-go" ]

    shopt -s nullglob
    stage_dirs=("$BATS_TEST_TMPDIR"/clavain-build-release.*)
    [ "${#stage_dirs[@]}" -eq 0 ]
}

@test "a late cross-build failure leaves existing release artifacts unchanged" {
    for artifact in \
        clavain-cli-go-darwin-arm64 \
        clavain-cli-go-linux-amd64 \
        clavain-cli-go-windows-amd64; do
        printf 'old:%s\n' "$artifact" >"$FIXTURE_ROOT/bin/$artifact"
    done

    run env \
        PATH="$FIXTURE_ROOT/fake-bin:$PATH" \
        TMPDIR="$BATS_TEST_TMPDIR" \
        FAKE_RELEASE_OUT_DIR="$FIXTURE_ROOT/bin" \
        FAKE_GO_LOG="$FIXTURE_ROOT/go.log" \
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

    run env \
        PATH="$FIXTURE_ROOT/fake-bin:$PATH" \
        TMPDIR="$BATS_TEST_TMPDIR" \
        FAKE_RELEASE_OUT_DIR="$FIXTURE_ROOT/bin" \
        FAKE_GO_LOG="$FIXTURE_ROOT/go.log" \
        bash "$FIXTURE_ROOT/scripts/build-release.sh"

    [ "$status" -ne 0 ]
    [ ! -e "$FIXTURE_ROOT/go.log" ]
}
