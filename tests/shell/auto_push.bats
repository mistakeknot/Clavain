#!/usr/bin/env bats
# Regression tests for hooks/auto-push.sh: upstream-less worktree
# branches were stranded (silent exit), and branches tracking origin/main
# failed bare `git push` under push.default=simple.
# Opt-outs, protected branches and the push log (mk-ge29k) are covered below.

setup() {
    load test_helper
    export WORK="$BATS_TEST_TMPDIR/work"
    export REMOTE="$BATS_TEST_TMPDIR/remote.git"
    mkdir -p "$WORK"
    git init --bare -q -b main "$REMOTE"
    git init -q -b main "$WORK/repo"
    cd "$WORK/repo"
    git config user.email test@example.com
    git config user.name "Bats Test"
    git config push.default simple
    git remote add origin "$REMOTE"
    export CLAVAIN_AUTO_PUSH_LOG="$BATS_TEST_TMPDIR/auto-push.log"
    unset CLAVAIN_AUTO_PUSH CLAVAIN_AUTO_PUSH_SKIP
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
    git checkout -qb feature
    git push -qu origin feature
    echo more > more.txt
    git add more.txt
    git commit -qm "more on feature"
    run run_hook
    [ "$status" -eq 0 ]
    run git --git-dir="$REMOTE" rev-parse refs/heads/feature
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

commit_on() { # commit_on BRANCH: create BRANCH from main with one commit
    git checkout -qb "$1"
    echo "$1" > "$(echo "$1" | tr / _).txt"
    git add .
    git commit -qm "work on $1"
}

remote_has() { git --git-dir="$REMOTE" rev-parse -q --verify "refs/heads/$1" >/dev/null; }
# seeded_bare NAME DEFAULT: a bare repo whose default branch DEFAULT exists (an empty remote reports no default).
seeded_bare() {
    git init --bare -q -b "$2" "$BATS_TEST_TMPDIR/$1"
    git push -q "$BATS_TEST_TMPDIR/$1" "HEAD:refs/heads/$2"
}
# reject_pushes PATH: make a bare repo refuse every push.
reject_pushes() {
    printf '#!/bin/sh\nexit 1\n' > "$1/hooks/pre-receive"
    chmod +x "$1/hooks/pre-receive"
}
# A bare `! cmd` never trips bats errexit; a function returning 1 does.
not_remote_has() { ! remote_has "$@"; }

@test "auto-push: CLAVAIN_AUTO_PUSH=0 pushes nothing" {
    commit_on feature
    CLAVAIN_AUTO_PUSH=0 run run_hook
    [ "$status" -eq 0 ]
    not_remote_has feature
    grep -q 'event=skipped .*branch=feature .*reason=env:CLAVAIN_AUTO_PUSH=0' "$CLAVAIN_AUTO_PUSH_LOG"
}

@test "auto-push: CLAVAIN_AUTO_PUSH=1 still pushes" {
    commit_on feature
    CLAVAIN_AUTO_PUSH=1 run run_hook
    remote_has feature
}

@test "auto-push: git-dir marker file opts the clone out" {
    commit_on feature
    mkdir -p .git/info
    : > .git/info/no-auto-push
    run run_hook
    [ "$status" -eq 0 ]
    not_remote_has feature
}

@test "auto-push: work tree .no-auto-push opts the repo out" {
    : > .no-auto-push
    commit_on feature
    run run_hook
    not_remote_has feature
}

@test "auto-push: git config clavain.autoPush=false opts out; true does not" {
    commit_on feature
    git config clavain.autoPush false
    run run_hook
    not_remote_has feature
    git config clavain.autoPush true
    run run_hook
    remote_has feature
}

@test "auto-push: default skip pattern wk/* is not pushed, and is logged as skipped" {
    commit_on wk/some-work
    run run_hook
    [ "$status" -eq 0 ]
    not_remote_has wk/some-work
    grep -q 'event=skipped .*branch=wk/some-work .*reason=skip-pattern:wk/\*' "$CLAVAIN_AUTO_PUSH_LOG"
}

@test "auto-push: CLAVAIN_AUTO_PUSH_SKIP replaces the default pattern list" {
    commit_on wk/some-work
    CLAVAIN_AUTO_PUSH_SKIP="tmp/* scratch-*" run run_hook
    remote_has wk/some-work
    commit_on scratch-one
    CLAVAIN_AUTO_PUSH_SKIP="tmp/*,scratch-*" run run_hook
    not_remote_has scratch-one
}

@test "auto-push: git config clavain.autoPushSkip patterns are honoured" {
    git config --add clavain.autoPushSkip 'tmp/*'
    git config --add clavain.autoPushSkip 'draft-*'
    commit_on draft-x
    run run_hook
    not_remote_has draft-x
    commit_on feature
    run run_hook
    remote_has feature
}

@test "auto-push: main with an unpushed commit is never pushed" {
    echo more > more.txt
    git add more.txt
    git commit -qm "more on main"
    before=$(git --git-dir="$REMOTE" rev-parse refs/heads/main)
    run run_hook
    [ "$status" -eq 0 ]
    [ "$(git --git-dir="$REMOTE" rev-parse refs/heads/main)" = "$before" ]
    grep -q 'event=skipped .*branch=main .*reason=protected-branch:main' "$CLAVAIN_AUTO_PUSH_LOG"
}

@test "auto-push: master is never pushed" {
    git checkout -qb master
    echo m > m.txt
    git add m.txt
    git commit -qm "master work"
    run run_hook
    not_remote_has master
}

@test "auto-push: the remote's default branch is never pushed, whatever its name" {
    git --git-dir="$REMOTE" symbolic-ref HEAD refs/heads/trunk
    git checkout -qb trunk
    git push -qu origin trunk
    git remote set-head origin trunk
    echo t > t.txt
    git add t.txt
    git commit -qm "trunk work"
    before=$(git --git-dir="$REMOTE" rev-parse refs/heads/trunk)
    run run_hook
    [ "$(git --git-dir="$REMOTE" rev-parse refs/heads/trunk)" = "$before" ]
    grep -q 'reason=default-branch:origin/trunk' "$CLAVAIN_AUTO_PUSH_LOG"
}

@test "auto-push: a branch tracking origin/main publishes under its own name, not main" {
    git checkout -qb hotfix --track origin/main
    echo fix > fix.txt
    git add fix.txt
    git commit -qm "hotfix"
    before=$(git --git-dir="$REMOTE" rev-parse refs/heads/main)
    run run_hook
    remote_has hotfix
    [ "$(git --git-dir="$REMOTE" rev-parse refs/heads/main)" = "$before" ]
}

@test "auto-push: push.default=matching does not push other branches" {
    git config push.default matching
    commit_on feature
    git push -q origin feature
    git checkout -q main
    echo more > more.txt
    git add more.txt
    git commit -qm "unpushed main"
    git checkout -q feature
    echo f2 > f2.txt
    git add f2.txt
    git commit -qm "feature again"
    before=$(git --git-dir="$REMOTE" rev-parse refs/heads/main)
    run run_hook
    [ "$(git --git-dir="$REMOTE" rev-parse refs/heads/feature)" = "$(git rev-parse HEAD)" ]
    [ "$(git --git-dir="$REMOTE" rev-parse refs/heads/main)" = "$before" ]
}

@test "auto-push: a push is logged with branch, remote, sha and the previous remote sha" {
    commit_on feature
    echo '{"hook_event_name":"SessionEnd","session_id":"sess-123"}' | bash "$HOOKS_DIR/auto-push.sh"
    sha=$(git rev-parse HEAD | cut -c1-12)
    run grep 'event=pushed' "$CLAVAIN_AUTO_PUSH_LOG"
    [ "$status" -eq 0 ]
    [[ "$output" == *"branch=feature"* ]]
    [[ "$output" == *"remote=origin"* ]]
    [[ "$output" == *"urls=$REMOTE "* ]]
    [[ "$output" == *"sha=$sha"* ]]
    [[ "$output" == *"from=none"* ]]
    [[ "$output" == *"session=sess-123"* ]]
    [[ "$output" == *"hook_event=SessionEnd"* ]]
    [[ "$output" == *"ppid="* ]]
}

@test "auto-push: a failed push is logged as push-failed and the hook still exits 0" {
    commit_on feature
    reject_pushes "$REMOTE"
    run run_hook
    [ "$status" -eq 0 ]
    grep -q 'event=push-failed .*branch=feature' "$CLAVAIN_AUTO_PUSH_LOG"
}

@test "auto-push: nothing to push writes no log line" {
    run run_hook
    [ "$status" -eq 0 ]
    [ ! -s "$CLAVAIN_AUTO_PUSH_LOG" ]
}

@test "auto-push: an unwritable log path does not break the push" {
    commit_on feature
    CLAVAIN_AUTO_PUSH_LOG=/proc/nope/auto-push.log run run_hook
    [ "$status" -eq 0 ]
    remote_has feature
}

@test "auto-push: beads push still runs on a skipped branch but not under an explicit opt-out" {
    mkdir -p .beads
    printf '#!/usr/bin/env bash\ntouch "$BATS_TEST_TMPDIR/beads-ran"\n' > .beads/push.sh
    commit_on wk/some-work
    run run_hook
    [ -e "$BATS_TEST_TMPDIR/beads-ran" ]
    rm "$BATS_TEST_TMPDIR/beads-ran"
    CLAVAIN_AUTO_PUSH=0 run run_hook
    [ ! -e "$BATS_TEST_TMPDIR/beads-ran" ]
}

@test "auto-push: the default branch is still refused when refs/remotes/origin/HEAD is unset (resolved from the remote)" {
    git --git-dir="$REMOTE" symbolic-ref HEAD refs/heads/trunk
    git checkout -qb trunk
    git push -qu origin trunk
    git remote set-head origin --delete
    run git symbolic-ref -q refs/remotes/origin/HEAD
    [ "$status" -ne 0 ]
    echo t > t.txt
    git add t.txt
    git commit -qm "trunk work"
    before=$(git --git-dir="$REMOTE" rev-parse refs/heads/trunk)
    run run_hook
    [ "$status" -eq 0 ]
    [ "$(git --git-dir="$REMOTE" rev-parse refs/heads/trunk)" = "$before" ]
    grep -q 'reason=default-branch:origin/trunk' "$CLAVAIN_AUTO_PUSH_LOG"
}

@test "auto-push: an unknowable default branch blocks the push (fails closed)" {
    commit_on feature
    git config remote.origin.pushurl "$BATS_TEST_TMPDIR/does-not-exist.git"
    run run_hook
    [ "$status" -eq 0 ]
    not_remote_has feature
    grep -q 'event=skipped .*reason=default-branch-of-origin-unknown' "$CLAVAIN_AUTO_PUSH_LOG"
    run grep -q 'event=push-failed' "$CLAVAIN_AUTO_PUSH_LOG"
    [ "$status" -eq 1 ]
}

@test "auto-push: a stale origin/HEAD does not permit pushing the remote's new default branch" {
    git checkout -qb trunk
    echo t > t.txt
    git add t.txt
    git commit -qm "trunk work"
    git push -qu origin trunk
    git remote set-head origin main
    git --git-dir="$REMOTE" symbolic-ref HEAD refs/heads/trunk
    echo t2 > t2.txt
    git add t2.txt
    git commit -qm "more trunk"
    before=$(git --git-dir="$REMOTE" rev-parse refs/heads/trunk)
    run run_hook
    [ "$status" -eq 0 ]
    [ "$(git --git-dir="$REMOTE" rev-parse refs/heads/trunk)" = "$before" ]
    grep -q 'reason=default-branch:origin/trunk' "$CLAVAIN_AUTO_PUSH_LOG"
}

@test "auto-push: the default branch of the push URL is checked, not just the fetch URL" {
    git checkout -qb trunk
    seeded_bare pushdest.git trunk
    git config remote.origin.pushurl "$BATS_TEST_TMPDIR/pushdest.git"
    echo t > t.txt
    git add t.txt
    git commit -qm "trunk work"
    before=$(git --git-dir="$BATS_TEST_TMPDIR/pushdest.git" rev-parse refs/heads/trunk)
    run run_hook
    [ "$status" -eq 0 ]
    [ "$(git --git-dir="$BATS_TEST_TMPDIR/pushdest.git" rev-parse refs/heads/trunk)" = "$before" ]
    grep -q 'reason=default-branch:origin/trunk' "$CLAVAIN_AUTO_PUSH_LOG"
}

@test "auto-push: with several push URLs, one default-branch match blocks the whole push" {
    git checkout -qb trunk
    seeded_bare mirror.git trunk
    git remote set-url --add --push origin "$REMOTE"
    git remote set-url --add --push origin "$BATS_TEST_TMPDIR/mirror.git"
    echo t > t.txt
    git add t.txt
    git commit -qm "trunk work"
    before=$(git --git-dir="$BATS_TEST_TMPDIR/mirror.git" rev-parse refs/heads/trunk)
    run run_hook
    [ "$status" -eq 0 ]
    not_remote_has trunk
    [ "$(git --git-dir="$BATS_TEST_TMPDIR/mirror.git" rev-parse refs/heads/trunk)" = "$before" ]
}

@test "auto-push: a chained URL rewrite cannot make the guard inspect a different repository than the push" {
    git checkout -qb trunk
    seeded_bare push.git trunk
    seeded_bare safe.git main
    git config remote.origin.pushurl "review-alias:"
    git config "url.$BATS_TEST_TMPDIR/push.git.insteadOf" "review-alias:"
    git config "url.$BATS_TEST_TMPDIR/safe.git.insteadOf" "$BATS_TEST_TMPDIR/push.git"
    echo t > t.txt
    git add t.txt
    git commit -qm "trunk work"
    before=$(git --git-dir="$BATS_TEST_TMPDIR/push.git" rev-parse refs/heads/trunk)
    run run_hook
    [ "$status" -eq 0 ]
    [ "$(git --git-dir="$BATS_TEST_TMPDIR/push.git" rev-parse refs/heads/trunk)" = "$before" ]
    grep -q 'event=skipped .*reason=default-branch-of-origin-unknown' "$CLAVAIN_AUTO_PUSH_LOG"
}

@test "auto-push: a push URL containing a newline cannot hide behind its truncated path" {
    git checkout -qb trunk
    seeded_bare read.git main
    nl_url="$BATS_TEST_TMPDIR/read.git"$'\n'
    git init --bare -q -b trunk "$nl_url"
    git -C "$nl_url" symbolic-ref HEAD refs/heads/trunk
    git config remote.origin.pushurl "$nl_url"
    echo t > t.txt
    git add t.txt
    git commit -qm "trunk work"
    run run_hook
    [ "$status" -eq 0 ]
    run git --git-dir="$nl_url" rev-parse --verify -q refs/heads/trunk
    [ "$status" -ne 0 ]
    grep -q 'event=skipped .*reason=destination-unverifiable:control-character-in-url-config' "$CLAVAIN_AUTO_PUSH_LOG"
}

@test "auto-push: a custom receive-pack command cannot redirect the push away from the queried repository" {
    git checkout -qb trunk
    seeded_bare read.git main
    seeded_bare write.git trunk
    git config remote.origin.pushurl "$BATS_TEST_TMPDIR/read.git"
    git config remote.origin.receivepack "sh -c 'exec git-receive-pack $BATS_TEST_TMPDIR/write.git'"
    echo t > t.txt
    git add t.txt
    git commit -qm "trunk work"
    before=$(git --git-dir="$BATS_TEST_TMPDIR/write.git" rev-parse refs/heads/trunk)
    run run_hook
    [ "$status" -eq 0 ]
    [ "$(git --git-dir="$BATS_TEST_TMPDIR/write.git" rev-parse refs/heads/trunk)" = "$before" ]
    grep -q 'event=skipped .*reason=destination-unverifiable:remote-command-override' "$CLAVAIN_AUTO_PUSH_LOG"
}

@test "auto-push: a control byte before a newline in a push URL cannot hide the real destination" {
    git checkout -qb trunk
    seeded_bare soh_read main
    soh_url="$BATS_TEST_TMPDIR/soh_read"$'\001\n'
    git init --bare -q -b trunk "$soh_url"
    git -C "$soh_url" symbolic-ref HEAD refs/heads/trunk
    git config remote.origin.pushurl "$soh_url"
    echo t > t.txt
    git add t.txt
    git commit -qm "trunk work"
    run run_hook
    [ "$status" -eq 0 ]
    run git --git-dir="$soh_url" rev-parse --verify -q refs/heads/trunk
    [ "$status" -ne 0 ]
    grep -q 'event=skipped .*reason=destination-unverifiable:control-character-in-url-config' "$CLAVAIN_AUTO_PUSH_LOG"
}

@test "auto-push: a custom ssh command (config or environment) is never trusted to reach the queried repository" {
    commit_on feature
    git config core.sshCommand "sh -c 'exit 1' --"
    run run_hook
    [ "$status" -eq 0 ]
    not_remote_has feature
    grep -q 'event=skipped .*reason=destination-unverifiable:core.sshCommand' "$CLAVAIN_AUTO_PUSH_LOG"
    git config --unset core.sshCommand
    GIT_SSH_COMMAND="sh -c 'exit 1' --" run run_hook
    [ "$status" -eq 0 ]
    not_remote_has feature
    grep -q 'event=skipped .*reason=destination-unverifiable:env:GIT_SSH_COMMAND' "$CLAVAIN_AUTO_PUSH_LOG"
}

@test "auto-push: a push URL that is also a remote's name cannot redirect the default-branch query" {
    git checkout -qb trunk
    seeded_bare read.git main
    seeded_bare write.git trunk
    # relative names, resolved from the work tree root, as in a hostile-but-plausible config
    ln -s "$BATS_TEST_TMPDIR/write.git" write.git
    ln -s "$BATS_TEST_TMPDIR/read.git" read.git
    git config remote.origin.pushurl write.git
    git remote add write.git write.git
    git config remote.write.git.uploadpack "sh -c 'exec git-upload-pack $BATS_TEST_TMPDIR/read.git'"
    echo t > t.txt
    git add t.txt
    git commit -qm "trunk work"
    before=$(git --git-dir="$BATS_TEST_TMPDIR/write.git" rev-parse refs/heads/trunk)
    run run_hook
    [ "$status" -eq 0 ]
    [ "$(git --git-dir="$BATS_TEST_TMPDIR/write.git" rev-parse refs/heads/trunk)" = "$before" ]
    grep -q 'event=skipped .*reason=destination-unverifiable:remote-command-override' "$CLAVAIN_AUTO_PUSH_LOG"
}

@test "auto-push: a push URL equal to another remote's name is treated as an unknown default" {
    git checkout -qb feature
    seeded_bare a.git main
    seeded_bare b.git main
    git remote add alias "$BATS_TEST_TMPDIR/b.git"
    git config remote.origin.pushurl alias
    echo t > t.txt
    git add t.txt
    git commit -qm "feature work"
    run run_hook
    [ "$status" -eq 0 ]
    not_remote_has feature
    grep -q 'event=skipped .*reason=default-branch-of-origin-unknown' "$CLAVAIN_AUTO_PUSH_LOG"
}

@test "auto-push: a submodule branch is never pushed by push.recurseSubmodules" {
    git init --bare -q -b feature "$BATS_TEST_TMPDIR/sub.git"
    git init -q -b feature "$BATS_TEST_TMPDIR/subsrc"
    git -C "$BATS_TEST_TMPDIR/subsrc" -c user.email=t@example.com -c user.name=t commit -q --allow-empty -m sub-base
    git -C "$BATS_TEST_TMPDIR/subsrc" push -q "$BATS_TEST_TMPDIR/sub.git" feature
    git -c protocol.file.allow=always submodule add -q -b feature "$BATS_TEST_TMPDIR/sub.git" sub
    git commit -qm "add submodule"
    git push -q origin main
    git checkout -qb feature
    git -C sub -c user.name=t -c user.email=t@example.invalid commit -q --allow-empty -m "sub work"
    git add sub
    git commit -qm "bump submodule"
    git config push.recurseSubmodules on-demand
    sub_before=$(git --git-dir="$BATS_TEST_TMPDIR/sub.git" rev-parse refs/heads/feature)
    run run_hook
    [ "$status" -eq 0 ]
    remote_has feature
    [ "$(git --git-dir="$BATS_TEST_TMPDIR/sub.git" rev-parse refs/heads/feature)" = "$sub_before" ]
}

@test "auto-push: an ext:: URL produced by a URL rewrite is never queried or pushed to" {
    git checkout -qb trunk
    seeded_bare safe.git main
    seeded_bare write.git trunk
    git config protocol.ext.allow always
    git config remote.origin.pushurl review-alias:
    git config "url.ext::sh -c if% test% %s% =% upload-pack;% then% exec% git-upload-pack% $BATS_TEST_TMPDIR/safe.git;% else% exec% git-receive-pack% $BATS_TEST_TMPDIR/write.git;% fi.insteadOf" review-alias:
    echo t > t.txt
    git add t.txt
    git commit -qm "trunk work"
    before=$(git --git-dir="$BATS_TEST_TMPDIR/write.git" rev-parse refs/heads/trunk)
    run run_hook
    [ "$status" -eq 0 ]
    [ "$(git --git-dir="$BATS_TEST_TMPDIR/write.git" rev-parse refs/heads/trunk)" = "$before" ]
    grep -q 'event=skipped .*reason=destination-unverifiable:helper-transport' "$CLAVAIN_AUTO_PUSH_LOG"
}

@test "auto-push: an ext:: URL is never pushed to" {
    commit_on feature
    git config remote.origin.pushurl "ext::sh -c 'touch $BATS_TEST_TMPDIR/ext-ran'"
    run run_hook
    [ "$status" -eq 0 ]
    [ ! -e "$BATS_TEST_TMPDIR/ext-ran" ]
    grep -q 'event=skipped .*reason=destination-unverifiable:helper-transport' "$CLAVAIN_AUTO_PUSH_LOG"
}

@test "auto-push: an invalid clavain.autoPush value blocks the push (fails closed)" {
    commit_on feature
    git config clavain.autoPush disabled
    run run_hook
    [ "$status" -eq 0 ]
    not_remote_has feature
    grep -q 'event=skipped .*reason=git-config:clavain.autoPush-unreadable' "$CLAVAIN_AUTO_PUSH_LOG"
}

@test "auto-push: a newline or space in the repo path still yields one log line per event" {
    odd="$WORK/$(printf 'odd\nevent=pushed forged=1')"
    mv "$WORK/repo" "$odd"
    cd "$odd"
    commit_on feature
    run run_hook
    [ "$status" -eq 0 ]
    remote_has feature
    [ "$(wc -l < "$CLAVAIN_AUTO_PUSH_LOG")" -eq 1 ]
    run grep -q ' forged=1' "$CLAVAIN_AUTO_PUSH_LOG"
    [ "$status" -eq 1 ]
    grep -q 'repo=.*odd%0Aevent=pushed%20forged=1 ' "$CLAVAIN_AUTO_PUSH_LOG"
}

@test "auto-push: every push URL of the remote is logged" {
    seeded_bare mirror.git main
    git remote set-url --add --push origin "$REMOTE"
    git remote set-url --add --push origin "$BATS_TEST_TMPDIR/mirror.git"
    commit_on feature
    run run_hook
    [ "$status" -eq 0 ]
    remote_has feature
    run git --git-dir="$BATS_TEST_TMPDIR/mirror.git" rev-parse -q --verify refs/heads/feature
    [ "$status" -eq 0 ]
    grep 'event=pushed' "$CLAVAIN_AUTO_PUSH_LOG" | grep -q "urls=$REMOTE,$BATS_TEST_TMPDIR/mirror.git "
}

@test "auto-push: a failed multi-URL push is flagged as possibly partial" {
    seeded_bare mirror.git main
    reject_pushes "$BATS_TEST_TMPDIR/mirror.git"
    git remote set-url --add --push origin "$REMOTE"
    git remote set-url --add --push origin "$BATS_TEST_TMPDIR/mirror.git"
    commit_on feature
    run run_hook
    [ "$status" -eq 0 ]
    grep 'event=push-failed' "$CLAVAIN_AUTO_PUSH_LOG" | grep -q 'note=may-be-partial'
}
