#!/usr/bin/env bats
# mk-47vtm.5: every hit record is checked against all token values (the default
# variables plus each --token-env) wherever --hits points, and a named
# --token-env adds to the defaults. Dummy values only; counts are asserted,
# never values.

setup() {
    ROOT="$BATS_TEST_DIRNAME/../.."
    SCAN="$ROOT/scripts/token-leak-scan.py"
    T="$(mktemp -d)"
    unset ANTHROPIC_AUTH_TOKEN CODEX_POOL_AUTH_TOKEN
    DEF=dummydefaultvalue0123
    NAMED=dummynamedvalue4567
    export ANTHROPIC_AUTH_TOKEN="$DEF" NAMED_TOK="$NAMED"
    # file whose name carries the default value; content carries both
    printf 'a %s b %s c\n' "$DEF" "$NAMED" > "$T/f-$DEF.txt"
}

teardown() {
    rm -rf "$T"
}

count() { grep -aF -c -- "$1" "$2" || true; }

# assert the dummy values are absent from stdout, stderr and the hits file
assert_clean() {
    for f in "$@"; do
        [ -e "$f" ] || continue
        [ "$(count "$DEF" "$f")" -eq 0 ]
        [ "$(count "$NAMED" "$f")" -eq 0 ]
    done
}

@test "hits to /dev/stdout with an explicit --token-env: no value reaches stdout, stderr or the file" {
    run bash -c 'python3 -I "$0" scan --hits /dev/stdout --token-env NAMED_TOK -- "$1" >"$2" 2>"$3"' \
        "$SCAN" "$T/f-$DEF.txt" "$T/out" "$T/err"
    [ "$status" -eq 3 ]
    assert_clean "$T/out" "$T/err"
    [ "$(count "$DEF" "$T/f-$DEF.txt")" -eq 0 ]
    [ "$(count "$NAMED" "$T/f-$DEF.txt")" -eq 0 ]
}

@test "hits to /dev/stderr: no value reaches stdout or stderr" {
    run bash -c 'python3 -I "$0" scan --hits /dev/stderr --token-env NAMED_TOK -- "$1" >"$2" 2>"$3"' \
        "$SCAN" "$T/f-$DEF.txt" "$T/out" "$T/err"
    [ "$status" -eq 3 ]
    assert_clean "$T/out" "$T/err"
}

@test "hits to a pipe: no value reaches the reader" {
    run bash -c 'python3 -I "$0" scan --hits /dev/stdout --token-env NAMED_TOK -- "$1" 2>"$3" | cat >"$2"' \
        "$SCAN" "$T/f-$DEF.txt" "$T/out" "$T/err"
    assert_clean "$T/out" "$T/err"
}

@test "an explicit --token-env adds to the defaults: a default value alone is redacted" {
    printf 'only %s here\n' "$DEF" > "$T/d.txt"
    run python3 -I "$SCAN" scan --hits "$T/hits" --token-env NAMED_TOK -- "$T/d.txt"
    [ "$status" -eq 3 ]
    [ "$(count "$DEF" "$T/d.txt")" -eq 0 ]
    assert_clean "$T/hits"
}

@test "an unscanned file whose name carries a default value is recorded without it" {
    ln -s "$T/nowhere" "$T/dangling-$DEF"
    run bash -c 'python3 -I "$0" scan --hits /dev/stdout --token-env NAMED_TOK -- "$1" >"$2" 2>"$3"' \
        "$SCAN" "$T/dangling-$DEF" "$T/out" "$T/err"
    [ "$status" -eq 4 ]
    assert_clean "$T/out" "$T/err"
}

@test "report with --token-env: a default value in a hit record never reaches the report" {
    printf '{"file": "%s/g-%s.txt", "count": 2}\n' "$T" "$DEF" > "$T/hits"
    run python3 -I "$SCAN" report --hits "$T/hits" --token-env NAMED_TOK \
        --report "$T/rep.json" --bead b --role r --run-id id
    [ "$status" -eq 0 ]
    [ -e "$T/rep.json" ]
    assert_clean "$T/rep.json"
}

@test "a value that spans a record boundary (newline plus brace) never reaches the hits output" {
    export SPAN_TOK=$'\n{'
    for dest in /dev/stdout /dev/stderr "$T/hits"; do
        printf 'one\n{two\n' > "$T/a.txt"
        printf 'three\n{four\n' > "$T/b.txt"
        : > "$T/hits"; : > "$T/out"; : > "$T/out.err"
        run bash -c 'python3 -I "$0" scan --hits "$4" --token-env SPAN_TOK -- "$1" "$2" >"$3" 2>"$3.err"' \
            "$SCAN" "$T/a.txt" "$T/b.txt" "$T/out" "$dest"
        [ "$status" -eq 3 ]
        # count occurrences of the value in each destination, one string each
        for f in "$T/out" "$T/out.err" "$T/hits"; do
            n="$(python3 -I -c 'import sys; print(open(sys.argv[1], "rb").read().count(b"\n{"))' "$f")"
            [ "$n" -eq 0 ]
        done
    done
}

@test "hits sharing stderr with a diagnostic: a value spanning the two never reaches stderr" {
    export SPAN_TOK=$'\ntoken-leak-scan: could'
    ln -s "$T/nowhere" "$T/dangling"
    run bash -c 'python3 -I "$0" scan --hits /dev/stderr --token-env SPAN_TOK -- "$1" >"$2" 2>>"$2.err"' \
        "$SCAN" "$T/dangling" "$T/out"
    [ "$status" -eq 4 ]
    for f in "$T/out" "$T/out.err"; do
        n="$(python3 -I -c 'import sys; print(open(sys.argv[1], "rb").read().count(b"\ntoken-leak-scan: could"))' "$f")"
        [ "$n" -eq 0 ]
    done
}

@test "two scans appending to one hits file: a value spanning the invocations is never written" {
    export SPAN_TOK=$'\n{'
    : > "$T/hits"
    printf 'one\n{two\n' > "$T/a.txt"
    run python3 -I "$SCAN" scan --hits "$T/hits" --token-env SPAN_TOK -- "$T/a.txt"
    [ "$status" -eq 3 ]
    printf 'three\n{four\n' > "$T/b.txt"
    run python3 -I "$SCAN" scan --hits "$T/hits" --token-env SPAN_TOK -- "$T/b.txt"
    [ "$status" -eq 3 ]
    n="$(python3 -I -c 'import sys; print(open(sys.argv[1], "rb").read().count(b"\n{"))' "$T/hits")"
    [ "$n" -eq 0 ]
}

@test "stdout and stderr on one file: a value spanning hits and a diagnostic never reaches it (hits to /dev/stderr)" {
    export SPAN_TOK=$'true}\ntoken-leak-scan: could'
    ln -s "$T/nowhere" "$T/dangling"
    : > "$T/both"
    run bash -c 'python3 -I "$0" scan --hits /dev/stderr --token-env SPAN_TOK -- "$1" >"$2" 2>&1' \
        "$SCAN" "$T/dangling" "$T/both"
    [ "$status" -eq 4 ]
    n="$(python3 -I -c 'import sys; print(open(sys.argv[1], "rb").read().count(b"true}\ntoken-leak-scan: could"))' "$T/both")"
    [ "$n" -eq 0 ]
}

@test "stdout and stderr on one file: a value spanning hits and a diagnostic never reaches it (hits to /dev/stdout)" {
    export SPAN_TOK=$'true}\ntoken-leak-scan: could'
    ln -s "$T/nowhere" "$T/dangling"
    : > "$T/both"
    run bash -c 'python3 -I "$0" scan --hits /dev/stdout --token-env SPAN_TOK -- "$1" >"$2" 2>&1' \
        "$SCAN" "$T/dangling" "$T/both"
    [ "$status" -eq 4 ]
    n="$(python3 -I -c 'import sys; print(open(sys.argv[1], "rb").read().count(b"true}\ntoken-leak-scan: could"))' "$T/both")"
    [ "$n" -eq 0 ]
}
