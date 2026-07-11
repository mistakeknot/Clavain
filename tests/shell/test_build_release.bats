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
while (($#)); do
    if [[ "$1" == "-o" ]]; then
        out="$2"
        break
    fi
    shift
done
[[ -n "$out" ]] || { echo "fake go: missing -o" >&2; exit 2; }

if find "$FAKE_RELEASE_OUT_DIR" -type f -print -quit | grep -q .; then
    echo "fake go: release output changed before all builds completed" >&2
    exit 3
fi

mkdir -p "$(dirname "$out")"
printf 'artifact:%s/%s\n' "${GOOS:-native}" "${GOARCH:-native}" >"$out"
printf '%s\n' "$out" >>"$FAKE_GO_LOG"
EOF
    chmod +x "$FIXTURE_ROOT/fake-bin/go"
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
