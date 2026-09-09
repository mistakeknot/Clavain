#!/usr/bin/env bats
#
# next-goal-candidates.sh exists to stop one specific conflation: a bead root
# that could not be queried must never look like a bead root with nothing
# ready. Both produce zero candidates; only one of them is a fact about the
# backlog. The first three tests are that distinction, held apart deliberately.

bats_require_minimum_version 1.5.0

setup() {
    load test_helper

    SCRIPT_UNDER_TEST="$BATS_TEST_DIRNAME/../../scripts/next-goal-candidates.sh"
    TEST_DIR="$(mktemp -d)"

    # A stub bd. `where` always resolves (the roots under test have .beads/);
    # `ready` behaves per-root according to a marker file, so one run can mix
    # reachable and unreachable roots the way a real session does.
    BD_STUB="$TEST_DIR/bd"
    cat > "$BD_STUB" <<'EOF'
#!/usr/bin/env bash
if [[ "$1" == "where" ]]; then
    echo "$PWD/.beads"
    echo "  prefix: $(basename "$PWD")"
    echo "  database: $(cat "$PWD/.beads/dbpath" 2>/dev/null || echo "$PWD/.beads/dolt")"
    exit 0
fi
if [[ -f "$PWD/.beads/fail" ]]; then
    cat "$PWD/.beads/fail" >&2
    exit 1
fi
cat "$PWD/.beads/ready.json" 2>/dev/null || echo "[]"
EOF
    chmod +x "$BD_STUB"
    export CLAVAIN_NEXT_GOAL_BD="$BD_STUB"
}

teardown() {
    rm -rf "$TEST_DIR"
}

# Build a root that answers with the given ready-JSON.
make_root() {
    local name="$1" ready="${2:-[]}"
    mkdir -p "$TEST_DIR/$name/.beads"
    printf '%s' "$ready" > "$TEST_DIR/$name/.beads/ready.json"
    printf '%s' "$TEST_DIR/$name/.beads/dolt" > "$TEST_DIR/$name/.beads/dbpath"
    echo "$TEST_DIR/$name"
}

# Build a root whose tracker cannot be queried at all.
make_broken_root() {
    local name="$1" message="${2:-Error: no beads database found}"
    mkdir -p "$TEST_DIR/$name/.beads"
    printf '%s' "$message" > "$TEST_DIR/$name/.beads/fail"
    printf '%s' "$TEST_DIR/$name/.beads/dolt" > "$TEST_DIR/$name/.beads/dbpath"
    echo "$TEST_DIR/$name"
}

run_helper() {
    CLAVAIN_NEXT_GOAL_ROOTS="$1" run --separate-stderr bash "$SCRIPT_UNDER_TEST"
    [ "$status" -eq 0 ]
}

# --------------------------------------------------------- the three-way split

@test "no-database root reports unreachable, not an empty backlog" {
    root="$(make_broken_root broken)"
    run_helper "$root"

    [ "$(jq -r '.roots[0].status' <<<"$output")" = "unreachable" ]
    [ "$(jq -r '.tracker_reachable' <<<"$output")" = "false" ]
    [ "$(jq '.lookup_failures | length' <<<"$output")" -eq 1 ]
    # The reason must survive to the caller — "we could not look" is only
    # actionable if it says which lookup failed.
    [[ "$(jq -r '.lookup_failures[0].reason' <<<"$output")" == *"no beads database found"* ]]
}

@test "reachable root with nothing ready reports empty, and no lookup failure" {
    root="$(make_root quiet '[]')"
    run_helper "$root"

    [ "$(jq -r '.roots[0].status' <<<"$output")" = "empty" ]
    [ "$(jq -r '.tracker_reachable' <<<"$output")" = "true" ]
    [ "$(jq '.lookup_failures | length' <<<"$output")" -eq 0 ]
}

@test "empty and unreachable are distinguishable despite both yielding zero candidates" {
    broken="$(make_broken_root broken)"
    quiet="$(make_root quiet '[]')"

    run_helper "$broken"
    broken_out="$output"
    run_helper "$quiet"
    quiet_out="$output"

    # Identical on the surface the old inline bash looked at...
    [ "$(jq '.candidates | length' <<<"$broken_out")" -eq 0 ]
    [ "$(jq '.candidates | length' <<<"$quiet_out")" -eq 0 ]
    # ...and different on the axis that decides whether the block may be
    # improvised in silence.
    [ "$(jq -r '.tracker_reachable' <<<"$broken_out")" != "$(jq -r '.tracker_reachable' <<<"$quiet_out")" ]
}

# --------------------------------------------------------------- multi-root

@test "candidates merge across multiple reachable roots" {
    a="$(make_root alpha '[{"id":"alpha-1","title":"A"},{"id":"alpha-2","title":"B"}]')"
    b="$(make_root beta  '[{"id":"beta-1","title":"C"}]')"
    run_helper "$a:$b"

    [ "$(jq '.roots | length' <<<"$output")" -eq 2 ]
    [ "$(jq '.candidates | length' <<<"$output")" -eq 3 ]
    # Provenance must ride along: a merged list is unusable if you cannot tell
    # which tracker to file against.
    [ "$(jq -r '[.candidates[]._root] | unique | length' <<<"$output")" -eq 2 ]
}

@test "a partial outage still yields the roots that answered, and still reports the one that did not" {
    good="$(make_root alpha '[{"id":"alpha-1","title":"A"}]')"
    bad="$(make_broken_root beta)"
    run_helper "$good:$bad"

    [ "$(jq '.candidates | length' <<<"$output")" -eq 1 ]
    [ "$(jq '.lookup_failures | length' <<<"$output")" -eq 1 ]
    # One healthy root is enough to make the block tracker-backed, but the
    # failure must not vanish just because something else answered.
    [ "$(jq -r '.tracker_reachable' <<<"$output")" = "true" ]
}

@test "roots resolving to the same database are counted once" {
    a="$(make_root alpha '[{"id":"shared-1","title":"A"}]')"
    b="$(make_root beta  '[{"id":"shared-1","title":"A"}]')"
    # Both directories resolve to one tracker — the real shape of
    # ~/projects and ~/, which bd resolves to the same mk database.
    printf '%s' "$TEST_DIR/shared/.beads/dolt" > "$a/.beads/dbpath"
    printf '%s' "$TEST_DIR/shared/.beads/dolt" > "$b/.beads/dbpath"
    run_helper "$a:$b"

    [ "$(jq '.roots | length' <<<"$output")" -eq 1 ]
    [ "$(jq '.candidates | length' <<<"$output")" -eq 1 ]
}

@test "bd exiting zero with unparseable output is unreachable, not empty" {
    mkdir -p "$TEST_DIR/garbled/.beads"
    printf '%s' "$TEST_DIR/garbled/.beads/dolt" > "$TEST_DIR/garbled/.beads/dbpath"
    printf 'not json at all' > "$TEST_DIR/garbled/.beads/ready.json"
    run_helper "$TEST_DIR/garbled"

    [ "$(jq -r '.roots[0].status' <<<"$output")" = "unreachable" ]
    [ "$(jq -r '.tracker_reachable' <<<"$output")" = "false" ]
}

# ----------------------------------------------------------------- roadmap

@test "roadmap freshness is judged on generated_at, not mtime" {
    root="$(make_root alpha '[]')"
    mkdir -p "$root/docs"
    # Content generated 25 days ago; file touched just now. This is the exact
    # shape of Sylveste's roadmap.json on 2026-08-07 (mtime 07-21,
    # generated_at 07-13), which any mtime-based check calls fresh.
    old="$(python3 -c "
from datetime import datetime, timedelta, timezone
print((datetime.now(timezone.utc) - timedelta(days=25)).strftime('%Y-%m-%dT%H:%M:%SZ'))")"
    jq -n --arg t "$old" '{generated_at: $t, open_beads: 62, module_count: 85}' > "$root/docs/roadmap.json"
    touch "$root/docs/roadmap.json"

    run_helper "$root"
    [ "$(jq -r '.roadmap.status' <<<"$output")" = "stale" ]
    [ "$(jq -r '.roadmap.age_days >= 24' <<<"$output")" = "true" ]
}

@test "a recently generated roadmap reads fresh" {
    root="$(make_root alpha '[]')"
    mkdir -p "$root/docs"
    now="$(python3 -c "
from datetime import datetime, timezone
print(datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ'))")"
    jq -n --arg t "$now" '{generated_at: $t, open_beads: 3}' > "$root/docs/roadmap.json"

    run_helper "$root"
    [ "$(jq -r '.roadmap.status' <<<"$output")" = "fresh" ]
}

@test "a roadmap with no generated_at is undated, never fresh" {
    root="$(make_root alpha '[]')"
    mkdir -p "$root/docs"
    jq -n '{open_beads: 3}' > "$root/docs/roadmap.json"

    run_helper "$root"
    # Unknown freshness is its own state. Defaulting it to fresh would be the
    # same "unmeasured reads as healthy" bug one layer down.
    [ "$(jq -r '.roadmap.status' <<<"$output")" = "undated" ]
}

@test "a missing roadmap is reported as missing" {
    root="$(make_root alpha '[]')"
    run_helper "$root"
    [ "$(jq -r '.roadmap.status' <<<"$output")" = "missing" ]
}

@test "the stale threshold is configurable and bounds the verdict" {
    root="$(make_root alpha '[]')"
    mkdir -p "$root/docs"
    old="$(python3 -c "
from datetime import datetime, timedelta, timezone
print((datetime.now(timezone.utc) - timedelta(days=10)).strftime('%Y-%m-%dT%H:%M:%SZ'))")"
    jq -n --arg t "$old" '{generated_at: $t}' > "$root/docs/roadmap.json"

    CLAVAIN_ROADMAP_STALE_DAYS=30 run_helper "$root"
    [ "$(jq -r '.roadmap.status' <<<"$output")" = "fresh" ]

    CLAVAIN_ROADMAP_STALE_DAYS=7 run_helper "$root"
    [ "$(jq -r '.roadmap.status' <<<"$output")" = "stale" ]
}

@test "the newer of the cache and repo roadmap copies wins, and names its source" {
    root="$(make_root alpha '[]')"
    mkdir -p "$root/docs"
    stamp() { python3 -c "
from datetime import datetime, timedelta, timezone
import sys
print((datetime.now(timezone.utc) - timedelta(days=int(sys.argv[1]))).strftime('%Y-%m-%dT%H:%M:%SZ'))" "$1"; }

    # Repo copy is the committed snapshot and goes stale between deliberate
    # regenerations; the cache copy is what the scheduler maintains.
    jq -n --arg t "$(stamp 25)" '{generated_at: $t, open_beads: 62}'  > "$root/docs/roadmap.json"
    jq -n --arg t "$(stamp 0)"  '{generated_at: $t, open_beads: 481}' > "$TEST_DIR/cached.json"

    CLAVAIN_ROADMAP_CACHE="$TEST_DIR/cached.json" run_helper "$root"
    [ "$(jq -r '.roadmap.source' <<<"$output")" = "cache" ]
    [ "$(jq -r '.roadmap.status' <<<"$output")" = "fresh" ]
    [ "$(jq -r '.roadmap.open_beads' <<<"$output")" = "481" ]

    # ...and the preference is by generated_at, not by which file is the cache:
    # a stale cache must not shadow a freshly committed repo copy.
    jq -n --arg t "$(stamp 40)" '{generated_at: $t, open_beads: 9}' > "$TEST_DIR/cached.json"
    jq -n --arg t "$(stamp 1)"  '{generated_at: $t, open_beads: 77}' > "$root/docs/roadmap.json"
    CLAVAIN_ROADMAP_CACHE="$TEST_DIR/cached.json" run_helper "$root"
    [ "$(jq -r '.roadmap.source' <<<"$output")" = "repo" ]
    [ "$(jq -r '.roadmap.open_beads' <<<"$output")" = "77" ]
}

@test "a cache copy alone is enough when the repo has no roadmap" {
    root="$(make_root alpha '[]')"
    now="$(python3 -c "
from datetime import datetime, timezone
print(datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ'))")"
    jq -n --arg t "$now" '{generated_at: $t, open_beads: 5}' > "$TEST_DIR/cached.json"

    CLAVAIN_ROADMAP_CACHE="$TEST_DIR/cached.json" run_helper "$root"
    [ "$(jq -r '.roadmap.source' <<<"$output")" = "cache" ]
    [ "$(jq -r '.roadmap.status' <<<"$output")" = "fresh" ]
}

@test "output is well-formed JSON carrying its schema version" {
    root="$(make_root alpha '[{"id":"alpha-1","title":"A"}]')"
    run_helper "$root"
    [ "$(jq -r '.schema_version' <<<"$output")" = "clavain.next-goal-candidates/v1" ]
    [ "$(jq -r '.available' <<<"$output")" = "true" ]
}

# ------------------------------------------------------------- backlog signal
#
# Derived from roadmap.json, not from docs/backlog.md: the markdown is a
# filtered rendering of the same JSON, so parsing it would add a parser and
# lose precision. Gated on the same freshness rule, because the signal rides
# inside the roadmap object rather than beside it.

# One root whose roadmap carries a mix of statuses: open, blocked, deferred,
# and closed. Every assertion below turns on keeping those four apart.
make_backlog_root() {
    local stamp="$1"
    local root
    root="$(make_root backlog '[]')"
    mkdir -p "$root/docs"
    jq -n --arg t "$stamp" '{
      project: "demo", generated_at: $t, open_beads: 4, blocked: 1, module_count: 2,
      roadmap: {
        now:  [{id:"d-1",title:"a",module:"core",priority:"P1",status:"open"}],
        next: [{id:"d-2",title:"b",module:"core",priority:"P2",status:"blocked"},
               {id:"d-3",title:"c",module:"edge",priority:"P2",status:"open"}],
        later:[{id:"d-4",title:"d",module:"core",priority:"P3",status:"deferred"},
               {id:"d-5",title:"e",module:"edge",priority:"P3",status:"closed"}]
      }}' > "$root/docs/roadmap.json"
    echo "$root"
}

@test "backlog: deferred beads are counted and named" {
    root="$(make_backlog_root "$(date -u +%Y-%m-%dT%H:%M:%SZ)")"
    run_helper "$root"
    [ "$(jq -r '.roadmap.status' <<<"$output")" = "fresh" ]
    [ "$(jq -r '.roadmap.backlog.deferred' <<<"$output")" = "1" ]
    [ "$(jq -r '.roadmap.backlog.deferred_ids[0]' <<<"$output")" = "d-4" ]
}

@test "backlog: a deferred bead does not inflate module load" {
    root="$(make_backlog_root "$(date -u +%Y-%m-%dT%H:%M:%SZ)")"
    run_helper "$root"
    # core holds d-1 and d-2 live plus d-4 parked. Counting the parked one
    # would make a module nobody is working make look like the busiest.
    core="$(jq -r '.roadmap.backlog.module_load[] | select(.module=="core") | .open' <<<"$output")"
    [ "$core" = "2" ]
}

@test "backlog: closed items are excluded from every count" {
    root="$(make_backlog_root "$(date -u +%Y-%m-%dT%H:%M:%SZ)")"
    run_helper "$root"
    total="$(jq -r '[.roadmap.backlog.by_priority | to_entries[] | .value] | add' <<<"$output")"
    [ "$total" = "3" ]
    edge="$(jq -r '.roadmap.backlog.module_load[] | select(.module=="edge") | .open' <<<"$output")"
    [ "$edge" = "1" ]
}

@test "backlog: blocked ids are named, not just counted" {
    root="$(make_backlog_root "$(date -u +%Y-%m-%dT%H:%M:%SZ)")"
    run_helper "$root"
    [ "$(jq -r '.roadmap.backlog.blocked' <<<"$output")" = "1" ]
    [ "$(jq -r '.roadmap.backlog.blocked_ids[0]' <<<"$output")" = "d-2" ]
}

@test "backlog: one freshness gate, shared with the roadmap" {
    # A stale roadmap must not yield a backlog the caller treats as current.
    # The gate is .roadmap.status — a second gate that could disagree with it
    # would recreate the ambiguity this helper exists to remove.
    root="$(make_backlog_root "2020-01-01T00:00:00Z")"
    run_helper "$root"
    [ "$(jq -r '.roadmap.status' <<<"$output")" = "stale" ]
}

# ------------------------------------------------------------------- worktrees
#
# A linked git worktree (git worktree add, bd worktree create) carries its own
# .beads copy that nothing syncs. From inside one, the main checkout's beads
# are "no such bead" and its ready list is whatever was copied at creation.
# Observed 2026-09-04: two days of improvised blocks from a nested worktree.

@test "worktree: a .beads inside a linked worktree resolves to the main checkout, once" {
    command -v git >/dev/null || skip "git not installed"
    local main
    main="$(make_root main '[{"id":"m-1","title":"from main","status":"open","priority":1}]')"
    git -C "$TEST_DIR" init -q main
    git -C "$main" -c user.email=t@t -c user.name=t commit -q --allow-empty -m init
    git -C "$main" worktree add -q "$main/wt" -b wt
    mkdir -p "$main/wt/.beads"
    printf '[]' > "$main/wt/.beads/ready.json"
    printf '%s' "$main/wt/.beads/stale-copy" > "$main/wt/.beads/dbpath"
    unset CLAVAIN_NEXT_GOAL_ROOTS
    pushd "$main/wt" >/dev/null
    HOME="$TEST_DIR" run --separate-stderr bash "$SCRIPT_UNDER_TEST"
    popd >/dev/null
    [ "$status" -eq 0 ]
    [ "$(jq -r '.roots | length' <<<"$output")" -eq 1 ]
    [ "$(jq -r '.roots[0].root' <<<"$output")" = "$(cd "$main" && pwd -P)" ]
    [ "$(jq -r '.candidates | length' <<<"$output")" -eq 1 ]
    [ "$(jq -r '.candidates[0].id' <<<"$output")" = "m-1" ]
}

@test "worktree: the main checkout itself is unaffected" {
    command -v git >/dev/null || skip "git not installed"
    local main
    main="$(make_root main '[{"id":"m-1","title":"from main","status":"open","priority":1}]')"
    git -C "$TEST_DIR" init -q main
    unset CLAVAIN_NEXT_GOAL_ROOTS
    pushd "$main" >/dev/null
    HOME="$TEST_DIR" run --separate-stderr bash "$SCRIPT_UNDER_TEST"
    popd >/dev/null
    [ "$status" -eq 0 ]
    [ "$(jq -r '.roots[0].root' <<<"$output")" = "$(cd "$main" && pwd -P)" ]
}
