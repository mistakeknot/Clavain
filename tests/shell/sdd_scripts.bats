#!/usr/bin/env bats
# Tests for the plan-execution helpers shared by subagent-driven-development and
# executing-plans: sdd-workspace resolves a self-ignoring, per-plan directory
# under .clavain/sdd/; task-brief and review-package write into it; task-start
# and task-done keep the ledger. Ported from superpowers' test-sdd-workspace.sh
# and test-executing-plans-scripts.sh. Scripts run through bash, as the skills
# invoke them, so a stripped exec bit cannot break them.

setup() {
    REPO_ROOT="$(cd "$BATS_TEST_DIRNAME/../.." && pwd)"
    SDD="$REPO_ROOT/skills/subagent-driven-development/scripts"
    EP="$REPO_ROOT/skills/executing-plans/scripts"
    export GIT_AUTHOR_NAME=t GIT_AUTHOR_EMAIL=t@example.com
    export GIT_COMMITTER_NAME=t GIT_COMMITTER_EMAIL=t@example.com
    export GIT_CONFIG_NOSYSTEM=1 GIT_CONFIG_GLOBAL=/dev/null
    git init -q -b main "$BATS_TEST_TMPDIR/repo"
    REPO="$(cd "$BATS_TEST_TMPDIR/repo" && git rev-parse --show-toplevel)"
    cd "$REPO"
    printf '# Plan A\n\n## Task 1: First thing\n\nDo the first thing.\n\n## Task 2: Second\n\nSecond.\n' > plan-a.md
    printf '# Plan B\n\n## Task 1: Other thing\n\nDo the other thing.\n' > plan-b.md
    git add plan-a.md plan-b.md
    git commit -qm fixture
}

commit_file() {
    printf '%s\n' "$1" > "$1.txt"
    git add "$1.txt"
    git commit -qm "$1"
}

@test "sdd-workspace rejects a missing argument or plan file with exit 2" {
    run bash "$SDD/sdd-workspace"
    [ "$status" -eq 2 ]
    run bash "$SDD/sdd-workspace" no-such-plan.md
    [ "$status" -eq 2 ]
}

@test "sdd-workspace gives each plan its own directory under .clavain/sdd" {
    run bash "$SDD/sdd-workspace" plan-a.md
    [ "$status" -eq 0 ]
    [ "$output" = "$REPO/.clavain/sdd/plan-a" ]
    dir_b="$(bash "$SDD/sdd-workspace" plan-b.md)"
    [ "$dir_b" = "$REPO/.clavain/sdd/plan-b" ]
    [ -d "$output" ] && [ -d "$dir_b" ]
    [ "$(cat "$output/plan-path")" = "plan-a.md" ]
}

@test "the workspace is invisible to git status and git add" {
    dir="$(bash "$SDD/sdd-workspace" plan-a.md)"
    [ "$(cat "$REPO/.clavain/sdd/.gitignore")" = "*" ]
    printf 'x\n' > "$dir/artifact.md"
    [ -z "$(git status --porcelain)" ]
    git add -A
    [ -z "$(git diff --cached --name-only)" ]
}

@test "same-basename plans get distinct workspaces and keep both briefs" {
    mkdir -p docs/alpha docs/beta
    printf '# A\n\n## Task 1: Alpha\n\nAlpha-only requirement text.\n' > docs/alpha/plan.md
    printf '# B\n\n## Task 1: Beta\n\nBeta-only requirement text.\n' > docs/beta/plan.md
    dir_alpha="$(bash "$SDD/sdd-workspace" docs/alpha/plan.md)"
    dir_beta="$(bash "$SDD/sdd-workspace" docs/beta/plan.md)"
    [ "$dir_alpha" = "$REPO/.clavain/sdd/plan" ]
    [ "$dir_beta" = "$REPO/.clavain/sdd/plan-beta" ]
    bash "$SDD/task-brief" docs/alpha/plan.md 1 >/dev/null
    bash "$SDD/task-brief" docs/beta/plan.md 1 >/dev/null
    grep -q "Alpha-only requirement text." "$dir_alpha/task-1-brief.md"
    grep -q "Beta-only requirement text." "$dir_beta/task-1-brief.md"
}

@test "relative, absolute and ../ spellings of one plan share a workspace" {
    mkdir -p docs/alpha docs/beta
    printf '# A\n\n## Task 1: Alpha\n\nAlpha.\n' > docs/alpha/plan.md
    rel="$(bash "$SDD/sdd-workspace" docs/alpha/plan.md)"
    abs="$(bash "$SDD/sdd-workspace" "$REPO/docs/alpha/plan.md")"
    dotdot="$(cd docs/beta && bash "$SDD/sdd-workspace" ../alpha/plan.md)"
    [ "$rel" = "$abs" ] && [ "$rel" = "$dotdot" ]
    [ "$(cat "$rel/plan-path")" = "docs/alpha/plan.md" ]
}

@test "a markerless legacy workspace is adopted in place" {
    printf '# Foo\n\n## Task 1: Foo\n\nFoo.\n' > foo.md
    mkdir -p .clavain/sdd/foo
    printf 'ledger\n' > .clavain/sdd/foo/progress.md
    run bash "$SDD/sdd-workspace" foo.md
    [ "$output" = "$REPO/.clavain/sdd/foo" ]
    [ "$(cat .clavain/sdd/foo/progress.md)" = "ledger" ]
    [ "$(cat .clavain/sdd/foo/plan-path)" = "foo.md" ]
}

@test "a workspace owned by another plan is left alone; collisions fall back to a counter" {
    printf '# Bar\n\n## Task 1: Bar\n\nBar.\n' > bar.md
    mkdir -p .clavain/sdd/bar
    printf 'elsewhere/bar.md\n' > .clavain/sdd/bar/plan-path
    printf 'other ledger\n' > .clavain/sdd/bar/progress.md
    run bash "$SDD/sdd-workspace" bar.md
    [ "$output" = "$REPO/.clavain/sdd/bar-repo" ]
    [ "$(cat .clavain/sdd/bar/plan-path)" = "elsewhere/bar.md" ]
    [ "$(cat .clavain/sdd/bar/progress.md)" = "other ledger" ]

    printf '# Baz\n\n## Task 1: Baz\n\nBaz.\n' > baz.md
    mkdir -p .clavain/sdd/baz .clavain/sdd/baz-repo
    printf 'one/baz.md\n' > .clavain/sdd/baz/plan-path
    printf 'two/baz.md\n' > .clavain/sdd/baz-repo/plan-path
    run bash "$SDD/sdd-workspace" baz.md
    [ "$output" = "$REPO/.clavain/sdd/baz-repo-2" ]
    [ "$(cat .clavain/sdd/baz-repo-2/plan-path)" = "baz.md" ]
}

@test "an out-of-repo plan gets a basename slug and an absolute marker" {
    mkdir -p "$BATS_TEST_TMPDIR/outside"
    printf '# R\n\n## Task 1: R\n\nR.\n' > "$BATS_TEST_TMPDIR/outside/remote-plan.md"
    outside="$(cd "$BATS_TEST_TMPDIR/outside" && pwd -P)/remote-plan.md"
    run bash "$SDD/sdd-workspace" "$BATS_TEST_TMPDIR/outside/remote-plan.md"
    [ "$output" = "$REPO/.clavain/sdd/remote-plan" ]
    [ "$(cat "$output/plan-path")" = "$outside" ]
}

@test "a linked worktree resolves its own workspace" {
    main_dir="$(bash "$SDD/sdd-workspace" plan-a.md)"
    git worktree add -q "$BATS_TEST_TMPDIR/wt" -b wt-feature
    wt_root="$(cd "$BATS_TEST_TMPDIR/wt" && git rev-parse --show-toplevel)"
    wt_dir="$(cd "$wt_root" && bash "$SDD/sdd-workspace" plan-a.md)"
    [ "$wt_dir" = "$wt_root/.clavain/sdd/plan-a" ]
    [ "$wt_dir" != "$main_dir" ]
    printf 'y\n' > "$wt_dir/artifact.md"
    [ -z "$(cd "$wt_root" && git status --porcelain)" ]
}

@test "task-brief extracts only the named task and ignores headings inside fences" {
    printf '# P\n\n## Task 1: One\n\n```md\n## Task 2: fenced\n```\n\nOne body.\n\n## Task 10: Ten\n\nTen body.\n' > fenced.md
    run bash "$SDD/task-brief" fenced.md 1
    [ "$status" -eq 0 ]
    [[ "$output" == "wrote $REPO/.clavain/sdd/fenced/task-1-brief.md: "*" lines" ]]
    brief="$REPO/.clavain/sdd/fenced/task-1-brief.md"
    grep -q "One body." "$brief"
    grep -q "## Task 2: fenced" "$brief"
    ! grep -q "Ten body." "$brief"
    run bash "$SDD/task-brief" fenced.md 7
    [ "$status" -eq 3 ]
}

@test "task-brief works when sdd-workspace has lost its exec bit" {
    mkdir -p "$BATS_TEST_TMPDIR/stripped"
    cp "$SDD/sdd-workspace" "$SDD/task-brief" "$BATS_TEST_TMPDIR/stripped/"
    chmod -x "$BATS_TEST_TMPDIR/stripped/"*
    run bash "$BATS_TEST_TMPDIR/stripped/task-brief" plan-b.md 1
    [ "$status" -eq 0 ]
    [ -f "$REPO/.clavain/sdd/plan-b/task-1-brief.md" ]
}

@test "review-package writes a per-range diff under the plan's workspace" {
    commit_file c1
    run bash "$SDD/review-package" plan-a.md HEAD~1 HEAD
    [ "$status" -eq 0 ]
    [[ "$output" == "wrote $REPO/.clavain/sdd/plan-a/review-"*".diff: 1 commit(s), "* ]]
    run bash "$SDD/review-package" plan-a.md HEAD~1 HEAD "$BATS_TEST_TMPDIR/explicit.diff"
    [ "$status" -eq 0 ]
    grep -q "^## Diff" "$BATS_TEST_TMPDIR/explicit.diff"
    run bash "$SDD/review-package" HEAD~1 HEAD
    [ "$status" -eq 2 ]
}

@test "review-package rejects non-descendant and empty ranges with exit 3" {
    commit_file c1
    divergent="$(git commit-tree 'HEAD~1^{tree}' -p HEAD~1 -m divergent)"
    run bash "$SDD/review-package" plan-a.md "$divergent" HEAD
    [ "$status" -eq 3 ]
    [[ "$output" == *"not a descendant"* ]]
    run bash "$SDD/review-package" plan-a.md HEAD HEAD
    [ "$status" -eq 3 ]
    [[ "$output" == *"empty commit range"* ]]
}

@test "task-start prints the brief path and BASE in one call" {
    run bash "$EP/task-start" plan-a.md
    [ "$status" -eq 2 ]
    base="$(git rev-parse HEAD)"
    run bash "$EP/task-start" plan-a.md 1
    [ "$status" -eq 0 ]
    [ "${lines[0]}" = "brief: $REPO/.clavain/sdd/plan-a/task-1-brief.md" ]
    [ "${lines[1]}" = "base: $base" ]
    [ -s "$REPO/.clavain/sdd/plan-a/task-1-brief.md" ]
}

@test "task-done records a passing task with its range and result" {
    base="$(git rev-parse HEAD)"
    commit_file task1
    head="$(git rev-parse HEAD)"
    run bash "$EP/task-done" plan-a.md 1 "$base" -- sh -c 'echo "Ran 3 tests"; echo OK'
    [ "$status" -eq 0 ]
    [[ "$output" == *"OK"* ]]
    ledger="$REPO/.clavain/sdd/plan-a/progress.md"
    [ "$(head -n 1 "$ledger")" = "# SDD ledger — plan: plan-a.md" ]
    grep -qF "Task 1: complete (commits ${base:0:7}..${head:0:7}, tests: sh -c 'echo \"Ran 3 tests\"; echo OK' → OK)" "$ledger"
    [ -s "$REPO/.clavain/sdd/plan-a/task-1-tests.log" ]
}

@test "task-done refuses to record a failing task" {
    base="$(git rev-parse HEAD)"
    run bash "$EP/task-done" plan-a.md 2 "$base" -- sh -c 'echo "FAILED (errors=1)"; exit 1'
    [ "$status" -eq 1 ]
    [[ "$output" == *"FAILED"* ]]
    [[ "$output" == *"NOT recorded"* ]]
    ! grep -qs "Task 2: complete" "$REPO/.clavain/sdd/plan-a/progress.md"
    run bash "$EP/task-done" plan-a.md 2 "$base" sh -c true
    [ "$status" -eq 2 ]
}

@test "task-start and task-done work with stripped exec bits" {
    mkdir -p "$BATS_TEST_TMPDIR/pkg/executing-plans/scripts" "$BATS_TEST_TMPDIR/pkg/subagent-driven-development/scripts"
    cp "$EP/task-start" "$EP/task-done" "$BATS_TEST_TMPDIR/pkg/executing-plans/scripts/"
    cp "$SDD/sdd-workspace" "$SDD/task-brief" "$BATS_TEST_TMPDIR/pkg/subagent-driven-development/scripts/"
    chmod -x "$BATS_TEST_TMPDIR"/pkg/*/scripts/*
    base="$(git rev-parse HEAD)"
    run bash "$BATS_TEST_TMPDIR/pkg/executing-plans/scripts/task-start" plan-b.md 1
    [ "$status" -eq 0 ]
    commit_file t1
    run bash "$BATS_TEST_TMPDIR/pkg/executing-plans/scripts/task-done" plan-b.md 1 "$base" -- true
    [ "$status" -eq 0 ]
    grep -qF "tests: true → exit 0)" "$REPO/.clavain/sdd/plan-b/progress.md"
}
