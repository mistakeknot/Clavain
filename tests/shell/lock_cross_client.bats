#!/usr/bin/env bats
# Opt-in: the bash lock fallback in hooks/lib-intercore.sh and the Go ic binary
# share one on-disk protocol (directory, owner.json, cleaner.json). This checks
# the two clients against each other. It needs an ic built from the intercore
# lock-owner change and is skipped unless IC_CROSS_BIN names that binary.
#
#   IC_CROSS_BIN=/path/to/ic bats tests/shell/lock_cross_client.bats
#
# ic hardcodes its lock directory (/tmp/intercore/locks), so these tests use
# unique lock names there and remove them afterwards.

setup() {
    [ -n "${IC_CROSS_BIN:-}" ] || skip "IC_CROSS_BIN not set"
    [ -x "$IC_CROSS_BIN" ] || skip "IC_CROSS_BIN is not executable"
    load test_helper
    ROOT_DIR="$(cd "$BATS_TEST_DIRNAME/../.." && pwd)"
    REAL_MKDIR="$(command -v mkdir)"
    SHIM_DIR="$BATS_TEST_TMPDIR/shim"
    "$REAL_MKDIR" -p "$SHIM_DIR"
    cat > "$SHIM_DIR/mkdir" <<SHIM
#!/usr/bin/env bash
if [[ \$# -eq 1 && "\$1" != -* && -d "\$1" ]]; then exit 0; fi
exec "$REAL_MKDIR" "\$@"
SHIM
    chmod +x "$SHIM_DIR/mkdir"
    export HOME="$BATS_TEST_TMPDIR"
    export INTERCORE_LOCK_FALLBACK_DIR=/tmp/intercore/locks
    LOCK_NAME="xc-$$-${BATS_TEST_NUMBER}"
    LOCK_SCOPE="scope"
    LOCK_DIR="$INTERCORE_LOCK_FALLBACK_DIR/$LOCK_NAME/$LOCK_SCOPE"
    source "$ROOT_DIR/hooks/lib-intercore.sh"
    intercore_lock_available() { return 1; }
}

teardown() {
    [ -n "${LOCK_NAME:-}" ] && rm -rf "${INTERCORE_LOCK_FALLBACK_DIR:-/nonexistent}/$LOCK_NAME"
    return 0
}

_dead_pid() { sleep 0 & local p=$!; wait "$p"; printf '%d' "$p"; }

@test "cross-client: ic neither cleans nor acquires a lock a live bash holder owns" {
    intercore_lock "$LOCK_NAME" "$LOCK_SCOPE"
    touch -d '2 hours ago' "$LOCK_DIR"
    run "$IC_CROSS_BIN" lock clean --older-than=1s
    [ "$status" -eq 0 ]
    [ -f "$LOCK_DIR/owner.json" ]
    run jq -e '.pid == '"$$" "$LOCK_DIR/owner.json"
    [ "$status" -eq 0 ]
    run "$IC_CROSS_BIN" lock acquire "$LOCK_NAME" "$LOCK_SCOPE" --timeout=300ms
    [ "$status" -eq 1 ]
    [ -f "$LOCK_DIR/owner.json" ]
    intercore_unlock "$LOCK_NAME" "$LOCK_SCOPE"
    [ ! -e "$LOCK_DIR" ]
}

@test "cross-client: bash cannot take a lock ic holds, even when mkdir reports success" {
    run "$IC_CROSS_BIN" lock acquire "$LOCK_NAME" "$LOCK_SCOPE" --timeout=1s
    [ "$status" -eq 0 ]
    [ -f "$LOCK_DIR/owner.json" ]
    PATH="$SHIM_DIR:$PATH" run intercore_lock "$LOCK_NAME" "$LOCK_SCOPE"
    [ "$status" -eq 1 ]
}

@test "cross-client: ic and bash each clean a dead owner's lock that a dead cleaner's claim sits on" {
    local n dead
    for n in ic bash; do
        dead=$(_dead_pid)
        "$REAL_MKDIR" -p "$LOCK_DIR"
        printf '{"pid":%d,"host":"%s","owner":"%d:h","created":1}\n' "$dead" "$(uname -n)" "$dead" > "$LOCK_DIR/owner.json"
        printf '{"pid":%d,"host":"%s","created":1,"token":"gone"}\n' "$dead" "$(uname -n)" > "$LOCK_DIR/cleaner.json"
        touch -d '2 hours ago' "$LOCK_DIR"
        if [ "$n" = ic ]; then
            run "$IC_CROSS_BIN" lock clean --older-than=1s
            [ "$status" -eq 0 ]
        else
            intercore_lock_clean 1s
        fi
        [ ! -e "$LOCK_DIR" ]
    done
}

@test "cross-client: a fresh claim written by bash stops ic from cleaning, and the reverse" {
    local dead; dead=$(_dead_pid)
    "$REAL_MKDIR" -p "$LOCK_DIR"
    printf '{"pid":%d,"host":"h","owner":"%d:h","created":1}\n' "$dead" "$dead" > "$LOCK_DIR/owner.json"
    printf '{"pid":%d,"host":"%s","created":%d,"token":"live"}\n' "$$" "$(uname -n)" "$(date +%s)" > "$LOCK_DIR/cleaner.json"
    touch -d '2 hours ago' "$LOCK_DIR"
    run "$IC_CROSS_BIN" lock clean --older-than=1s
    [ "$status" -eq 0 ]
    [ -f "$LOCK_DIR/owner.json" ]
    intercore_lock_clean 1s
    [ -f "$LOCK_DIR/owner.json" ]
}

@test "cross-client: ic release honours the token of a bash-held lock" {
    intercore_lock "$LOCK_NAME" "$LOCK_SCOPE"
    local owner token
    owner=$(jq -r .owner "$LOCK_DIR/owner.json")
    token=$(jq -r .token "$LOCK_DIR/owner.json")
    run "$IC_CROSS_BIN" lock release "$LOCK_NAME" "$LOCK_SCOPE" --owner="$owner" --token="wrong"
    [ -f "$LOCK_DIR/owner.json" ]
    run "$IC_CROSS_BIN" lock release "$LOCK_NAME" "$LOCK_SCOPE" --owner="$owner" --token="$token"
    [ "$status" -eq 0 ]
    [ ! -e "$LOCK_DIR/owner.json" ]
}

@test "cross-client: mixed bash and ic workers never overlap, with a cleaner running" {
    local log="$BATS_TEST_TMPDIR/log" pids=() i
    : > "$log"
    cat > "$BATS_TEST_TMPDIR/worker.sh" <<'W'
source "$LIB"
intercore_lock_available() { return 1; }
for _ in 1 2 3 4 5; do
    if [ "$KIND" = ic ]; then
        "$IC" lock acquire "$LOCK_NAME" "$LOCK_SCOPE" --timeout=5s --owner="$$:w" --print-token >"$TOKF" 2>/dev/null || continue
        printf 'in %s\n' "$$" >> "$LOG"; sleep 0.02; printf 'out %s\n' "$$" >> "$LOG"
        "$IC" lock release "$LOCK_NAME" "$LOCK_SCOPE" --owner="$$:w" --token="$(tr -d '\n' < "$TOKF")" >/dev/null 2>&1
    else
        intercore_lock "$LOCK_NAME" "$LOCK_SCOPE" || continue
        printf 'in %s\n' "$$" >> "$LOG"; sleep 0.02; printf 'out %s\n' "$$" >> "$LOG"
        intercore_unlock "$LOCK_NAME" "$LOCK_SCOPE"
    fi
done
W
    for i in 1 2 3 4; do
        PATH="$SHIM_DIR:$PATH" KIND=$([ $((i % 2)) -eq 0 ] && echo ic || echo bash) IC="$IC_CROSS_BIN" \
            LIB="$ROOT_DIR/hooks/lib-intercore.sh" LOCK_NAME="$LOCK_NAME" LOCK_SCOPE="$LOCK_SCOPE" \
            LOG="$log" TOKF="$BATS_TEST_TMPDIR/tok$i" bash "$BATS_TEST_TMPDIR/worker.sh" &
        pids+=($!)
    done
    for i in $(seq 1 10); do "$IC_CROSS_BIN" lock clean --older-than=1s >/dev/null; intercore_lock_clean 1s; sleep 0.1; done
    for i in "${pids[@]}"; do wait "$i"; done
    local overlaps
    overlaps=$(awk '$1=="in"{n++; if(n>1)o++} $1=="out"{n--} END{print o+0}' "$log")
    echo "entries=$(grep -c '^in' "$log") overlaps=$overlaps" >&3
    [ "$(grep -c '^in' "$log")" -gt 0 ]
    [ "$overlaps" -eq 0 ]
}
