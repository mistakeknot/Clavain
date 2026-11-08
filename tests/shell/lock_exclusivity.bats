#!/usr/bin/env bats
# Mutual exclusion of the two mkdir-style locks must not depend on the installed
# mkdir failing for an existing directory (uutils mkdir 0.8.0 does not;
# uutils/coreutils#13970). The shim below is that mkdir's worst case: it reports
# success for any single directory that already exists. With it on PATH, a lock
# that trusts mkdir admits every caller at once.
#
#   - hooks/lib-intercore.sh intercore_lock fallback (directory + owner.json,
#     the layout ic uses)                                       (mk-bxfvc)
#   - scripts/collect-zaka.sh per-session collector lock         (mk-htpmr)
#
# Overlap is measured, not inferred: workers append enter/leave records with
# O_APPEND (atomic for short lines) and a read-modify-write counter detects lost
# updates. Requires: bats, jq, awk.

setup() {
    load test_helper
    ROOT_DIR="$(cd "$BATS_TEST_DIRNAME/../.." && pwd)"
    REAL_MKDIR="$(command -v mkdir)"
    SHIM_DIR="$BATS_TEST_TMPDIR/shim"
    "$REAL_MKDIR" -p "$SHIM_DIR"
    cat > "$SHIM_DIR/mkdir" <<EOF
#!/usr/bin/env bash
# Non-exclusive mkdir: success when the one operand is already a directory.
if [[ \$# -eq 1 && "\$1" != -* && -d "\$1" ]]; then exit 0; fi
exec "$REAL_MKDIR" "\$@"
EOF
    chmod +x "$SHIM_DIR/mkdir"
    # Private lock namespace: never the shared production one.
    export INTERCORE_LOCK_FALLBACK_DIR="$BATS_TEST_TMPDIR/locks"
    LOCK_NAME="lockx"
    LOCK_SCOPE="scope"
}

# A failing test must not leave a holder process waiting on its release file.
teardown() {
    if [ -n "${HOLDER_PID:-}" ]; then
        : > "$BATS_TEST_TMPDIR/go"
        kill "$HOLDER_PID" 2>/dev/null || true
        wait "$HOLDER_PID" 2>/dev/null || true
    fi
}

# Prints "<overlaps> <max_depth>" for an enter/leave log.
_overlaps() {
    awk '$1=="enter"{d++; if(d>1)v++; if(d>m)m=d} $1=="leave"{d--} END{print v+0, m+0}' "$1"
}

# _lock_stress <workers> <iterations>  -> sets OVERLAPS, LOST, TOTAL
# Workers use the fallback path of intercore_lock (ic is forced unavailable).
_lock_stress() {
    local workers="$1" iters="$2"
    local log="$BATS_TEST_TMPDIR/cs.log" counter="$BATS_TEST_TMPDIR/counter"
    : > "$log"; echo 0 > "$counter"
    cat > "$BATS_TEST_TMPDIR/worker.sh" <<'EOF'
source "$LIB"
intercore_lock_available() { return 1; }
for ((i = 0; i < ITERS; i++)); do
    until intercore_lock "$LOCK_NAME" "$LOCK_SCOPE"; do :; done
    echo "enter $$" >> "$LOG"
    v=$(cat "$COUNTER"); sleep 0.005; echo $((v + 1)) > "$COUNTER"
    echo "leave $$" >> "$LOG"
    intercore_unlock "$LOCK_NAME" "$LOCK_SCOPE"
done
EOF
    local pids=() w
    for ((w = 0; w < workers; w++)); do
        LIB="$HOOKS_DIR/lib-intercore.sh" ITERS="$iters" LOG="$log" COUNTER="$counter" \
            LOCK_NAME="$LOCK_NAME" LOCK_SCOPE="$LOCK_SCOPE" INTERCORE_LOCK_FALLBACK_DIR="$INTERCORE_LOCK_FALLBACK_DIR" HOME="$BATS_TEST_TMPDIR" \
            bash "$BATS_TEST_TMPDIR/worker.sh" &
        pids+=($!)
    done
    for w in "${pids[@]}"; do wait "$w"; done
    read -r OVERLAPS _ < <(_overlaps "$log")
    TOTAL=$((workers * iters))
    LOST=$((TOTAL - $(cat "$counter")))
    echo "# workers=$workers iterations=$iters overlaps=$OVERLAPS lost_updates=$LOST" >&3
}

@test "intercore_lock fallback: exclusive with the real mkdir (stress)" {
    _lock_stress 6 15
    [ "$OVERLAPS" -eq 0 ]
    [ "$LOST" -eq 0 ]
}

@test "intercore_lock fallback: exclusive when mkdir is non-exclusive (stress)" {
    PATH="$SHIM_DIR:$PATH" _lock_stress 6 15
    [ "$OVERLAPS" -eq 0 ]
    [ "$LOST" -eq 0 ]
    # Every lock was released: nothing left behind for ic lock clean.
    [ ! -e "$INTERCORE_LOCK_FALLBACK_DIR/$LOCK_NAME/$LOCK_SCOPE" ]
}

@test "intercore_lock fallback: a held lock refuses a second caller when mkdir reports success" {
    export HOME="$BATS_TEST_TMPDIR"
    source "$HOOKS_DIR/lib-intercore.sh"
    intercore_lock_available() { return 1; }
    intercore_lock "$LOCK_NAME" "$LOCK_SCOPE"
    PATH="$SHIM_DIR:$PATH" run intercore_lock "$LOCK_NAME" "$LOCK_SCOPE"
    [ "$status" -eq 1 ]
    # The refused caller must not have disturbed the holder's record.
    run jq -e '.pid == '"$$"' and (.owner | startswith("'"$$"':"))' \
        "$INTERCORE_LOCK_FALLBACK_DIR/$LOCK_NAME/$LOCK_SCOPE/owner.json"
    [ "$status" -eq 0 ]
    intercore_unlock "$LOCK_NAME" "$LOCK_SCOPE"
    [ ! -e "$INTERCORE_LOCK_FALLBACK_DIR/$LOCK_NAME/$LOCK_SCOPE" ]
}

@test "intercore_lock fallback: keeps the ic directory + owner.json layout" {
    export HOME="$BATS_TEST_TMPDIR"
    source "$HOOKS_DIR/lib-intercore.sh"
    intercore_lock_available() { return 1; }
    intercore_lock "$LOCK_NAME" "$LOCK_SCOPE"
    dir="$INTERCORE_LOCK_FALLBACK_DIR/$LOCK_NAME/$LOCK_SCOPE"
    [ -d "$dir" ]
    run jq -e '(.pid | type == "number") and (.host | type == "string")
        and (.owner | type == "string") and (.created | type == "number")' "$dir/owner.json"
    [ "$status" -eq 0 ]
    # Only owner.json lives in the directory, as with ic, so rmdir release works.
    [ "$(ls -A "$dir")" = "owner.json" ]
    intercore_unlock "$LOCK_NAME" "$LOCK_SCOPE"
    [ ! -e "$dir" ]
}

# --- lock lifecycle: cleanup and unlock must not hit a live holder -------------

_lib() {
    export HOME="$BATS_TEST_TMPDIR"
    source "$HOOKS_DIR/lib-intercore.sh"
    intercore_lock_available() { return 1; }
    LOCK_DIR="$INTERCORE_LOCK_FALLBACK_DIR/$LOCK_NAME/$LOCK_SCOPE"
}

_age() { touch -d '2 hours ago' "$1"; }

# Holds LOCK_NAME/LOCK_SCOPE in its own process until $GO exists, then unlocks.
_start_holder() {
    export READY="$BATS_TEST_TMPDIR/ready" GO="$BATS_TEST_TMPDIR/go" DONE="$BATS_TEST_TMPDIR/done"
    rm -f "$READY" "$GO" "$DONE"
    cat > "$BATS_TEST_TMPDIR/holder.sh" <<'HOLDER'
source "$LIB"
intercore_lock_available() { return 1; }
intercore_lock "$LOCK_NAME" "$LOCK_SCOPE" || exit 3
: > "$READY"
until [ -e "$GO" ]; do sleep 0.05; done
intercore_unlock "$LOCK_NAME" "$LOCK_SCOPE"
: > "$DONE"
HOLDER
    LIB="$HOOKS_DIR/lib-intercore.sh" LOCK_NAME="$LOCK_NAME" LOCK_SCOPE="$LOCK_SCOPE" \
        HOME="$BATS_TEST_TMPDIR" bash "$BATS_TEST_TMPDIR/holder.sh" &
    HOLDER_PID=$!
    local i
    for i in $(seq 1 100); do [ -e "$READY" ] && return 0; sleep 0.05; done
    return 1
}

_wait_done() {
    local i
    for i in $(seq 1 100); do [ -e "$DONE" ] && return 0; sleep 0.05; done
    return 1
}

@test "intercore_lock_clean fallback: leaves an aged lock whose owner is alive, and it still excludes" {
    _lib
    intercore_lock "$LOCK_NAME" "$LOCK_SCOPE"
    _age "$LOCK_DIR"
    intercore_lock_clean 5s
    [ -d "$LOCK_DIR" ]
    run jq -e '.pid == '"$$" "$LOCK_DIR/owner.json"
    [ "$status" -eq 0 ]
    PATH="$SHIM_DIR:$PATH" run intercore_lock "$LOCK_NAME" "$LOCK_SCOPE"
    [ "$status" -eq 1 ]
    intercore_unlock "$LOCK_NAME" "$LOCK_SCOPE"
    [ ! -e "$LOCK_DIR" ]
}

@test "intercore_lock_clean fallback: removes an aged lock whose owner is dead, and an aged empty directory" {
    _lib
    sleep 0 & local dead=$!; wait "$dead"
    "$REAL_MKDIR" -p "$LOCK_DIR" "$INTERCORE_LOCK_FALLBACK_DIR/ghost/scope"
    printf '{"pid":%d,"host":"h","owner":"%d:h","created":1}\n' "$dead" "$dead" > "$LOCK_DIR/owner.json"
    _age "$LOCK_DIR"; _age "$INTERCORE_LOCK_FALLBACK_DIR/ghost/scope"
    intercore_lock_clean 5s
    [ ! -e "$LOCK_DIR" ]
    [ ! -e "$INTERCORE_LOCK_FALLBACK_DIR/ghost/scope" ]
    # A fresh lock is not touched.
    intercore_lock "$LOCK_NAME" "$LOCK_SCOPE"
    intercore_lock_clean 5s
    [ -f "$LOCK_DIR/owner.json" ]
    intercore_unlock "$LOCK_NAME" "$LOCK_SCOPE"
}

@test "intercore_unlock fallback: cleanup, re-acquire, then a delayed unlock leaves the new holder's lock" {
    _lib
    _start_holder                       # holder A takes the lock in its own process
    _age "$LOCK_DIR"
    # Model a cleaner that wrongly judges A dead (pid reuse, a paused process):
    _intercore_pid_alive() { return 1; }
    intercore_lock_clean 5s
    [ ! -e "$LOCK_DIR" ]
    _lib                                # restore the real liveness check
    intercore_lock "$LOCK_NAME" "$LOCK_SCOPE"    # B takes it
    run jq -e '.pid == '"$$" "$LOCK_DIR/owner.json"
    [ "$status" -eq 0 ]
    : > "$GO"                           # A's delayed unlock
    _wait_done
    wait "$HOLDER_PID"
    # A's unlock did not remove B's lock, and B still excludes others.
    [ -d "$LOCK_DIR" ]
    run jq -e '.pid == '"$$" "$LOCK_DIR/owner.json"
    [ "$status" -eq 0 ]
    PATH="$SHIM_DIR:$PATH" run intercore_lock "$LOCK_NAME" "$LOCK_SCOPE"
    [ "$status" -eq 1 ]
    intercore_unlock "$LOCK_NAME" "$LOCK_SCOPE"
    [ ! -e "$LOCK_DIR" ]
}

@test "intercore_unlock fallback: a record with this pid but another acquire token is not removed" {
    _lib
    intercore_lock "$LOCK_NAME" "$LOCK_SCOPE"
    # Same pid, newer acquisition: the record carries a different token.
    jq -c '.token = "other"' "$LOCK_DIR/owner.json" > "$LOCK_DIR/owner.new"
    mv "$LOCK_DIR/owner.new" "$LOCK_DIR/owner.json"
    intercore_unlock "$LOCK_NAME" "$LOCK_SCOPE"
    [ -f "$LOCK_DIR/owner.json" ]
    run jq -r .token "$LOCK_DIR/owner.json"
    [ "$output" = "other" ]
}

@test "intercore_unlock fallback: never removes a lock held by another process" {
    _lib
    _start_holder
    intercore_unlock "$LOCK_NAME" "$LOCK_SCOPE"   # not ours
    [ -f "$LOCK_DIR/owner.json" ]
    : > "$GO"; _wait_done; wait "$HOLDER_PID"
    [ ! -e "$LOCK_DIR" ]
}

# --- lock lifecycle, round 3: interleavings --------------------------------------
# Each test pauses one actor at the window where the race lives, lets the other
# actors run, then resumes it. Pauses are shell-function overrides inside a child
# process (no sleeps standing in for ordering).

_wait_for() {
    local i
    for i in $(seq 1 200); do [ -e "$1" ] && return 0; sleep 0.05; done
    return 1
}

@test "intercore_lock fallback: a cleaner never takes a record that is still being written" {
    _lib
    export PAUSED="$BATS_TEST_TMPDIR/paused" RESUME="$BATS_TEST_TMPDIR/resume"
    export ACQUIRED="$BATS_TEST_TMPDIR/acquired" FAILED="$BATS_TEST_TMPDIR/failed"
    export GO="$BATS_TEST_TMPDIR/go"
    rm -f "$PAUSED" "$RESUME" "$ACQUIRED" "$FAILED" "$GO"
    cat > "$BATS_TEST_TMPDIR/writer.sh" <<'WRITER'
source "$LIB"
intercore_lock_available() { return 1; }
# Pause the moment the owner record is about to be filled in: whatever file the
# record is being written to has been created (and is empty) by now.
printf() {
    if [[ "$1" == '%s\n' && "$2" == '{"pid"'* ]]; then
        : > "$PAUSED"
        until [[ -e "$RESUME" ]]; do sleep 0.05; done
    fi
    builtin printf "$@"
}
if intercore_lock "$LOCK_NAME" "$LOCK_SCOPE"; then : > "$ACQUIRED"; else : > "$FAILED"; fi
until [[ -e "$GO" ]]; do sleep 0.05; done
WRITER
    LIB="$HOOKS_DIR/lib-intercore.sh" LOCK_NAME="$LOCK_NAME" LOCK_SCOPE="$LOCK_SCOPE" \
        HOME="$BATS_TEST_TMPDIR" bash "$BATS_TEST_TMPDIR/writer.sh" &
    HOLDER_PID=$!
    _wait_for "$PAUSED"
    # The lock directory is old; a cleaner runs while the record is half written.
    _age "$LOCK_DIR"
    intercore_lock_clean 5s
    : > "$RESUME"
    _wait_for "$ACQUIRED"
    # The writer's acquisition is real: the record on disk is complete and names it.
    [ -s "$LOCK_DIR/owner.json" ]
    run jq -e '.pid == '"$HOLDER_PID" "$LOCK_DIR/owner.json"
    [ "$status" -eq 0 ]
    # So nobody else can take the lock, even when mkdir reports success.
    PATH="$SHIM_DIR:$PATH" run intercore_lock "$LOCK_NAME" "$LOCK_SCOPE"
    [ "$status" -eq 1 ]
}

@test "intercore_lock_clean fallback: an empty or unreadable record is left alone, however old" {
    _lib
    "$REAL_MKDIR" -p "$LOCK_DIR"
    : > "$LOCK_DIR/owner.json"
    _age "$LOCK_DIR"
    intercore_lock_clean 5s 2>/dev/null
    [ -e "$LOCK_DIR/owner.json" ]
    PATH="$SHIM_DIR:$PATH" run intercore_lock "$LOCK_NAME" "$LOCK_SCOPE"
    [ "$status" -eq 1 ]
}

@test "intercore_lock_clean fallback: a delayed cleaner never discards a live successor's record" {
    _lib
    export PAUSED="$BATS_TEST_TMPDIR/paused" RESUME="$BATS_TEST_TMPDIR/resume"
    rm -f "$PAUSED" "$RESUME"
    # Dead owner A's lock.
    sleep 0 & local dead=$!; wait "$dead"
    "$REAL_MKDIR" -p "$LOCK_DIR"
    printf '{"pid":%d,"host":"h","owner":"%d:h","created":1}\n' "$dead" "$dead" > "$LOCK_DIR/owner.json"
    _age "$LOCK_DIR"
    # Cleaner 1 examines A, then stalls just after judging A dead.
    cat > "$BATS_TEST_TMPDIR/cleaner.sh" <<'CLEANER'
source "$LIB"
intercore_lock_available() { return 1; }
_intercore_pid_alive() {
    if [[ "$1" == "$DEAD_A" ]]; then
        : > "$PAUSED"
        until [[ -e "$RESUME" ]]; do sleep 0.05; done
        return 1
    fi
    kill -0 "$1" 2>/dev/null
}
# Client C (mkdir reports success for it) takes the lock the instant a record is
# taken away from the pathname, which is the window the race needs.
_c_joins() {
    [[ -z "${C_DONE:-}" && ! -e "$LOCK_DIR/owner.json" ]] || return 0
    C_DONE=1
    PATH="$SHIM_DIR:$PATH" bash -c 'source "$LIB"; intercore_lock_available() { return 1; }; intercore_lock "$LOCK_NAME" "$LOCK_SCOPE"'
}
mv() { command mv "$@"; _c_joins; }
rm() { command rm "$@"; _c_joins; }
ln() { command ln "$@"; _c_joins; }
rmdir() { command rmdir "$@"; _c_joins; }
intercore_lock_clean 5s
CLEANER
    export DEAD_A="$dead" SHIM_DIR LOCK_DIR LIB="$HOOKS_DIR/lib-intercore.sh" LOCK_NAME LOCK_SCOPE
    HOME="$BATS_TEST_TMPDIR" bash "$BATS_TEST_TMPDIR/cleaner.sh" &
    local cleaner=$!
    _wait_for "$PAUSED"
    # Cleaner 2 finishes the job, and live B takes the lock, while cleaner 1 stalls.
    rm -f "$LOCK_DIR/owner.json"; rmdir "$LOCK_DIR"
    _start_holder
    : > "$RESUME"
    wait "$cleaner"
    # B still holds, with its own record; C was never admitted.
    run jq -e '.pid == '"$HOLDER_PID" "$LOCK_DIR/owner.json"
    [ "$status" -eq 0 ]
    PATH="$SHIM_DIR:$PATH" run intercore_lock "$LOCK_NAME" "$LOCK_SCOPE"
    [ "$status" -eq 1 ]
    : > "$GO"; _wait_done; wait "$HOLDER_PID"
    [ ! -e "$LOCK_DIR" ]
}

@test "intercore_lock_clean fallback: a cleaner defers to another cleaner's claim" {
    _lib
    sleep 0 & local dead=$!; wait "$dead"
    "$REAL_MKDIR" -p "$LOCK_DIR"
    printf '{"pid":%d,"host":"h","owner":"%d:h","created":1}\n' "$dead" "$dead" > "$LOCK_DIR/owner.json"
    printf '{"pid":%d,"host":"%s","created":%d,"token":"other"}\n' "$$" "$(uname -n)" "$(date +%s)" > "$LOCK_DIR/cleaner.json"   # a live cleaner is mid-way
    _age "$LOCK_DIR"
    intercore_lock_clean 5s
    [ -e "$LOCK_DIR/owner.json" ]
    [ -e "$LOCK_DIR/cleaner.json" ]
}

# --- cleaner claims: a dead cleaner must not wedge the lock, and a claim is only
# --- ever removed by the process that published it ------------------------------

# _dead_pid: print the pid of a process that has exited.
_dead_pid() { sleep 0 & local p=$!; wait "$p"; printf '%s' "$p"; }

# _seed_dead_lock <dead-pid>: an aged lock whose owner is the dead pid.
_seed_dead_lock() {
    "$REAL_MKDIR" -p "$LOCK_DIR"
    printf '{"pid":%d,"host":"h","owner":"%d:h","created":1}\n' "$1" "$1" > "$LOCK_DIR/owner.json"
    _age "$LOCK_DIR"
}

# _seed_claim <pid> <host> <created>: a cleaner.json in ic's format (directory kept aged).
_seed_claim() {
    printf '{"pid":%d,"host":"%s","created":%d,"token":"seeded"}\n' "$1" "$2" "$3" > "$LOCK_DIR/cleaner.json"
    _age "$LOCK_DIR"   # writing the claim touched the directory
}

@test "intercore_lock_clean fallback: a cleaner that died holding the claim does not wedge the lock" {
    _lib
    local dead cdead; dead=$(_dead_pid); cdead=$(_dead_pid)
    _seed_dead_lock "$dead"
    _seed_claim "$cdead" "$(uname -n)" "$(date +%s)"   # fresh, but its cleaner is gone
    intercore_lock_clean 5s
    [ ! -e "$LOCK_DIR" ]
    # And the lock is acquirable again.
    intercore_lock "$LOCK_NAME" "$LOCK_SCOPE"
    run jq -e '.pid == '"$$" "$LOCK_DIR/owner.json"
    [ "$status" -eq 0 ]
    intercore_unlock "$LOCK_NAME" "$LOCK_SCOPE"
}

@test "intercore_lock_clean fallback: a claim older than the bound is taken over even if its pid looks alive" {
    _lib
    local dead; dead=$(_dead_pid)
    _seed_dead_lock "$dead"
    _seed_claim "$$" "elsewhere" "$(( $(date +%s) - 120 ))"   # a pid reused by a stranger, on another host
    intercore_lock_clean 5s
    [ ! -e "$LOCK_DIR" ]
}

@test "intercore_lock_clean fallback: a fresh claim of a live cleaner is respected, even for a pid that looks dead elsewhere" {
    _lib
    local dead; dead=$(_dead_pid)
    _seed_dead_lock "$dead"
    _seed_claim "$$" "$(uname -n)" "$(date +%s)"
    intercore_lock_clean 5s
    [ -e "$LOCK_DIR/owner.json" ]
    [ -e "$LOCK_DIR/cleaner.json" ]
    # A claim from another host cannot be shown dead from here; only its age abandons it.
    _seed_claim "$dead" "elsewhere" "$(date +%s)"
    intercore_lock_clean 5s
    [ -e "$LOCK_DIR/owner.json" ]
    [ -e "$LOCK_DIR/cleaner.json" ]
}

@test "intercore_lock_clean fallback: an unparsable claim is judged by its age" {
    _lib
    local dead; dead=$(_dead_pid)
    _seed_dead_lock "$dead"
    printf 'not json\n' > "$LOCK_DIR/cleaner.json"
    _age "$LOCK_DIR"
    intercore_lock_clean 5s 2>/dev/null
    [ -e "$LOCK_DIR/owner.json" ]                       # fresh: left alone
    touch -d '2 minutes ago' "$LOCK_DIR/cleaner.json"
    _age "$LOCK_DIR"
    intercore_lock_clean 5s 2>/dev/null
    [ ! -e "$LOCK_DIR" ]                                # old: taken over
}

# _wrap_fn <name>: keep the current definition of <name> as <name>_orig, so a test
# can redefine <name> around it.
_wrap_fn() { eval "$(declare -f "$1" | sed "1s/.*/${1}_orig ()/")"; }

@test "intercore_lock_clean fallback: the claim is published in ic's format and removed when done" {
    _lib
    local dead; dead=$(_dead_pid)
    _seed_dead_lock "$dead"
    export SEEN="$BATS_TEST_TMPDIR/claim-seen"
    rm -f "$SEEN"
    _wrap_fn _intercore_lock_drop_claim
    # Look at the claim while the cleaner still holds it.
    _intercore_lock_drop_claim() { cp "$1/cleaner.json" "$SEEN"; _intercore_lock_drop_claim_orig "$@"; }
    intercore_lock_clean 5s
    [ ! -e "$LOCK_DIR" ]
    run jq -e '.pid == '"$$"' and .host == "'"$(uname -n)"'" and (.created | type == "number") and (.token | length > 0)' "$SEEN"
    [ "$status" -eq 0 ]
}

@test "intercore_lock_clean fallback: only a cleaner's own claim is removed, never a successor's" {
    _lib
    local dead; dead=$(_dead_pid)
    _seed_dead_lock "$dead"
    # The cleaner's claim is taken over by another cleaner while it works.
    _wrap_fn _intercore_lock_take_claim
    _intercore_lock_take_claim() {
        _intercore_lock_take_claim_orig "$@" || return 1
        rm -f "$1/cleaner.json"
        printf '{"pid":%d,"host":"%s","created":%d,"token":"successor"}\n' "$$" "$(uname -n)" "$(date +%s)" > "$1/cleaner.json"
    }
    intercore_lock_clean 5s
    [ -f "$LOCK_DIR/cleaner.json" ]
    run jq -r .token "$LOCK_DIR/cleaner.json"
    [ "$output" = "successor" ]
}

@test "intercore_lock_clean fallback: a directory pinned only by a dead writer's pending file is reclaimed; a live writer's is not" {
    _lib
    local dead; dead=$(_dead_pid)
    "$REAL_MKDIR" -p "$LOCK_DIR"
    printf '{"pid":%d' "$dead" > "$LOCK_DIR/.pending.$dead.1.abc"
    _age "$LOCK_DIR"
    intercore_lock_clean 5s
    [ ! -e "$LOCK_DIR" ]
    # A writer that is alive and recent is mid-publish: hands off.
    "$REAL_MKDIR" -p "$LOCK_DIR"
    printf '{"pid":%d' "$$" > "$LOCK_DIR/.pending.$$.1.abc"
    _age "$LOCK_DIR"
    intercore_lock_clean 5s
    [ -e "$LOCK_DIR/.pending.$$.1.abc" ]
}

@test "intercore_lock_clean fallback: a directory holding only an abandoned claim is reclaimed; a live claim keeps it" {
    _lib
    local dead; dead=$(_dead_pid)
    "$REAL_MKDIR" -p "$LOCK_DIR"
    _seed_claim "$$" "$(uname -n)" "$(date +%s)"
    _age "$LOCK_DIR"
    intercore_lock_clean 5s
    [ -e "$LOCK_DIR/cleaner.json" ]
    _seed_claim "$dead" "$(uname -n)" "$(date +%s)"
    intercore_lock_clean 5s
    [ ! -e "$LOCK_DIR" ]
}

@test "intercore_unlock fallback: release waits on a live cleaner's claim and then leaves the lock in place" {
    _lib
    intercore_lock "$LOCK_NAME" "$LOCK_SCOPE"
    local other; sleep 30 & other=$!
    _seed_claim "$other" "$(uname -n)" "$(date +%s)"   # a live cleaner holds the claim
    run intercore_unlock "$LOCK_NAME" "$LOCK_SCOPE"
    kill "$other" 2>/dev/null || true
    [ "$status" -eq 0 ]
    [[ "$output" == *"busy"* ]]
    [ -f "$LOCK_DIR/owner.json" ]
    [ -f "$LOCK_DIR/cleaner.json" ]
}

@test "intercore_unlock fallback: release takes over a dead cleaner's claim and leaves no claim behind" {
    _lib
    local cdead; cdead=$(_dead_pid)
    intercore_lock "$LOCK_NAME" "$LOCK_SCOPE"
    _seed_claim "$cdead" "$(uname -n)" "$(date +%s)"
    intercore_unlock "$LOCK_NAME" "$LOCK_SCOPE"
    [ ! -e "$LOCK_DIR" ]
}

@test "intercore_unlock fallback: no recorded token means no release, even when the pid matches" {
    _lib
    # A predecessor's abandoned record that happens to carry this shell's pid.
    "$REAL_MKDIR" -p "$LOCK_DIR"
    printf '{"pid":%d,"host":"h","owner":"%d:h","created":1,"token":"predecessor"}\n' "$$" "$$" > "$LOCK_DIR/owner.json"
    run intercore_unlock "$LOCK_NAME" "$LOCK_SCOPE"
    [ "$status" -eq 0 ]
    [[ "$output" == *"not releasing"* ]]
    [ -f "$LOCK_DIR/owner.json" ]
    run jq -r .token "$LOCK_DIR/owner.json"
    [ "$output" = "predecessor" ]
}

# --- scripts/collect-zaka.sh ------------------------------------------------

_collect_fixture() {
    local d="$BATS_TEST_TMPDIR/collect"
    "$REAL_MKDIR" -p "$d/bin" "$d/work"
    COLLECT_DIR="$d"
    EVENTS="$d/events.jsonl"
    cat > "$d/status.json" <<EOF
{"session":"as-123456789012345678901234","transport":"app-server","thread_id":"thread-1",
 "turn_id":"turn-1","phase":"completed","turn_status":"completed","pending_requests":[],
 "event_log":"$EVENTS","updated_at":"2026-09-05T00:00:00Z",
 "config":{"workdir":"$d/work","model":"m1","sandbox":"read-only","metadata":{"schema_version":1,
  "dispatch_id":"dispatch-1","attempt_id":"attempt-1",
  "resolved_route":{"requested_role":"deep-execution"},
  "resolved_profile":{"profile_ref":"p1","profile":{"model":"m1"}}}}}
EOF
    printf '%s\n' '{"direction":"receive","message":{"method":"turn/completed","params":{"turn":{"id":"turn-1","status":"completed"}}}}' > "$EVENTS"
    printf '#!/usr/bin/env bash\ncat "%s/status.json"\n' "$d" > "$d/bin/zaka"
    # ic shim: the work after the collector lock calls `ic route list`; hold the
    # critical section open there and log it so overlap is observable.
    cat > "$d/bin/ic" <<EOF
#!/usr/bin/env bash
case "\$*" in
  *"route list"*) echo "enter \$\$" >> "$d/cs.log"; sleep 0.3; echo "leave \$\$" >> "$d/cs.log"; echo '[]' ;;
  *) exit 0 ;;
esac
EOF
    chmod +x "$d/bin/zaka" "$d/bin/ic"
    : > "$d/cs.log"
}

@test "collect-zaka lock: a held lock blocks a collector even when mkdir reports success" {
    _collect_fixture
    # Held by another collector: a lock file from this version, or a lock
    # directory left by an older mkdir-based collector.
    for kind in file dir; do
        rm -rf "$COLLECT_DIR/.collect.lock" "$COLLECT_DIR/cs.log"; : > "$COLLECT_DIR/cs.log"
        if [ "$kind" = file ]; then echo 4242 > "$(dirname "$EVENTS")/.collect.lock"
        else "$REAL_MKDIR" "$(dirname "$EVENTS")/.collect.lock"; fi
        run env PATH="$SHIM_DIR:$COLLECT_DIR/bin:$PATH" bash "$ROOT_DIR/scripts/collect-zaka.sh" as-123456789012345678901234
        [ "$status" -eq 1 ]
        [[ "$output" == *"another collector or stale collection lock"* ]]
        # The refused collector neither ran the critical section nor removed the holder's lock.
        [ ! -s "$COLLECT_DIR/cs.log" ]
        [ -e "$(dirname "$EVENTS")/.collect.lock" ]
    done
}

@test "collect-zaka lock: concurrent collectors never overlap when mkdir is non-exclusive (stress)" {
    _collect_fixture
    local pids=() i ok=0 refused=0
    for i in 1 2 3 4 5 6; do
        PATH="$SHIM_DIR:$COLLECT_DIR/bin:$PATH" bash "$ROOT_DIR/scripts/collect-zaka.sh" \
            as-123456789012345678901234 >/dev/null 2>&1 &
        pids+=($!)
    done
    for i in "${pids[@]}"; do if wait "$i"; then ok=$((ok + 1)); else refused=$((refused + 1)); fi; done
    read -r overlaps maxd < <(_overlaps "$COLLECT_DIR/cs.log")
    echo "# collectors=6 completed=$ok refused=$refused overlaps=$overlaps max_concurrent=$maxd" >&3
    [ "$overlaps" -eq 0 ]
    [ "$ok" -ge 1 ]
    # The lock is released on exit.
    [ ! -e "$(dirname "$EVENTS")/.collect.lock" ]
}
