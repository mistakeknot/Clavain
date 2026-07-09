#!/usr/bin/env bats
# Regression tests for hooks/auto-push.sh (mk-667): upstream-less worktree
# branches were stranded (silent exit), and branches tracking origin/main
# failed bare `git push` under push.default=simple.

setup() {
    load test_helper
    export WORK="$BATS_TEST_TMPDIR/work"
    export REMOTE="$BATS_TEST_TMPDIR/remote.git"
    mkdir -p "$WORK"
    git init --bare -q "$REMOTE"
    git init -q -b main "$WORK/repo"
    cd "$WORK/repo"
    git config user.email test@example.com
    git config user.name "Bats Test"
    git config push.default simple
    git remote add origin "$REMOTE"
    echo base > base.txt
    git add base.txt
    git commit -qm "base"
    git push -qu origin main
}

run_hook() {
    echo '{}' | bash "$HOOKS_DIR/auto-push.sh"
}

@test "auto-push: upstream-less branch with commits gets pushed with -u (regression: stranded worktree branches)" {
    git checkout -qb wt-feature
    echo change > change.txt
    git add change.txt
    git commit -qm "worktree work"

    run run_hook
    [ "$status" -eq 0 ]

    # commit reached the remote under the branch's own name
    run git --git-dir="$REMOTE" rev-parse refs/heads/wt-feature
    [ "$status" -eq 0 ]
    [ "$output" = "$(git rev-parse HEAD)" ]
    # and the branch adopted origin/wt-feature as upstream
    run git rev-parse --abbrev-ref wt-feature@{upstream}
    [ "$output" = "origin/wt-feature" ]
}

@test "auto-push: branch tracking origin/main pushes under push.default=simple (regression: bare push refused)" {
    git checkout -qb hotfix --track origin/main
    echo fix > fix.txt
    git add fix.txt
    git commit -qm "hotfix work"

    run run_hook
    [ "$status" -eq 0 ]

    run git --git-dir="$REMOTE" rev-parse refs/heads/hotfix
    [ "$status" -eq 0 ]
    [ "$output" = "$(git rev-parse HEAD)" ]
    # upstream moved off origin/main to the branch's own name
    run git rev-parse --abbrev-ref hotfix@{upstream}
    [ "$output" = "origin/hotfix" ]
}

@test "auto-push: upstream-less branch with NO unique commits is not published" {
    git checkout -qb dup-of-main # same tip as origin/main
    run run_hook
    [ "$status" -eq 0 ]
    run git --git-dir="$REMOTE" rev-parse refs/heads/dup-of-main
    [ "$status" -ne 0 ]
}

@test "auto-push: same-name upstream ahead pushes plainly" {
    echo more > more.txt
    git add more.txt
    git commit -qm "more on main"
    run run_hook
    [ "$status" -eq 0 ]
    run git --git-dir="$REMOTE" rev-parse refs/heads/main
    [ "$output" = "$(git rev-parse HEAD)" ]
}

@test "auto-push: detached HEAD exits cleanly without pushing" {
    git checkout -q --detach HEAD
    echo stray > stray.txt
    git add stray.txt
    git commit -qm "detached work"
    run run_hook
    [ "$status" -eq 0 ]
}
