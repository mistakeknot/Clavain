#!/usr/bin/env bats

# Tests for toolchain preflight in dispatch.sh (sylveste-aglf).
# Sources the _preflight_toolchains function and exercises it against
# fixture project trees with synthetic markers + PATH manipulation.

setup() {
    load test_helper

    DISPATCH_SCRIPT="$BATS_TEST_DIRNAME/../../scripts/dispatch.sh"
    TMPDIR_T="$(mktemp -d)"
    WORKDIR="$TMPDIR_T/proj"
    mkdir -p "$WORKDIR"

    # Fake-bin holds stub tools we "discover" or hide
    FAKE_BIN="$TMPDIR_T/fakebin"
    mkdir -p "$FAKE_BIN"
    ORIGINAL_PATH="$PATH"

    HELPERS="$TMPDIR_T/preflight.sh"
    awk '
        /^_preflight_toolchains\(\)[[:space:]]*\{/ { emit=1 }
        emit {
            print
            if ($0 ~ /^}[[:space:]]*$/) { emit=0 }
        }
    ' "$DISPATCH_SCRIPT" > "$HELPERS"
}

teardown() {
    rm -rf "$TMPDIR_T"
    export PATH="$ORIGINAL_PATH"
}

_load() {
    # shellcheck disable=SC1090
    source "$HELPERS"
}

# Helper: make a stub executable for a given tool name
_make_stub() {
    local tool="$1"
    cat > "$FAKE_BIN/$tool" <<EOF
#!/bin/sh
echo "$tool stub"
EOF
    chmod +x "$FAKE_BIN/$tool"
}

@test "preflight: empty workdir → no warning" {
    _load
    export PATH="$FAKE_BIN:/usr/bin:/bin"
    run _preflight_toolchains "$WORKDIR"
    [ "$status" -eq 0 ]
    [ -z "$output" ]
}

@test "preflight: go.mod present + go on PATH → silent pass" {
    _load
    echo "module foo" > "$WORKDIR/go.mod"
    _make_stub go
    export PATH="$FAKE_BIN:/usr/bin:/bin"
    run _preflight_toolchains "$WORKDIR"
    [ "$status" -eq 0 ]
    [[ "$output" != *"Warning:"* ]]
}

@test "preflight: go.mod present + go missing → warns but returns 0" {
    _load
    echo "module foo" > "$WORKDIR/go.mod"
    export PATH="$FAKE_BIN:/usr/bin:/bin"   # go intentionally NOT in FAKE_BIN
    run _preflight_toolchains "$WORKDIR"
    [ "$status" -eq 0 ]
    [[ "$output" == *"Warning: preflight"* ]]
    [[ "$output" == *"go"* ]]
    [[ "$output" == *"go.mod"* ]]
}

@test "preflight: strict mode + missing tool → exits 1" {
    _load
    echo "module foo" > "$WORKDIR/go.mod"
    export PATH="$FAKE_BIN:/usr/bin:/bin"
    export CLAVAIN_STRICT_PREFLIGHT=1
    run _preflight_toolchains "$WORKDIR"
    [ "$status" -eq 1 ]
    [[ "$output" == *"preflight failed"* ]]
    unset CLAVAIN_STRICT_PREFLIGHT
}

@test "preflight: PATH injection finds go in fake /usr/local/go/bin" {
    _load
    echo "module foo" > "$WORKDIR/go.mod"
    # Shadow /usr/local/go/bin by setting HOME to a dir that has the tool
    local HOME_GO="$TMPDIR_T/home/go/bin"
    mkdir -p "$HOME_GO"
    cat > "$HOME_GO/go" <<'EOF'
#!/bin/sh
echo "home go"
EOF
    chmod +x "$HOME_GO/go"
    export PATH="$FAKE_BIN:/usr/bin:/bin"
    export HOME="$TMPDIR_T/home"
    export CLAVAIN_PREFLIGHT_INJECT_PATH=1
    run _preflight_toolchains "$WORKDIR"
    [ "$status" -eq 0 ]
    [[ "$output" == *"injected"* ]]
    [[ "$output" == *"go"* ]]
    unset CLAVAIN_PREFLIGHT_INJECT_PATH
}

@test "preflight: multiple markers dedupe by tool (java)" {
    _load
    echo "<project/>" > "$WORKDIR/pom.xml"
    echo "plugins {}" > "$WORKDIR/build.gradle"
    echo "plugins {}" > "$WORKDIR/build.gradle.kts"
    # Stay with FAKE_BIN-only: java is definitely absent here.
    export PATH="$FAKE_BIN"
    # Use bash-only iteration so this test doesn't depend on external grep.
    local line hits=0
    while IFS= read -r line; do
        [[ "$line" == *"required toolchain not on PATH — java"* ]] && hits=$((hits+1))
    done < <(_preflight_toolchains "$WORKDIR" 2>&1)
    [ "$hits" -eq 1 ]
}

@test "preflight: no workdir → no-op" {
    _load
    run _preflight_toolchains ""
    [ "$status" -eq 0 ]
    [ -z "$output" ]
}

@test "preflight: nonexistent workdir → no-op" {
    _load
    run _preflight_toolchains "$TMPDIR_T/does-not-exist"
    [ "$status" -eq 0 ]
    [ -z "$output" ]
}
