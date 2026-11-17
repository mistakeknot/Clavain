#!/usr/bin/env bats
# review-round.sh: judge files are read from the merge base, never the PR head (bead mk-yzi9w).
# A fake dispatch records what the reviewer's checkout (-C) contains.

setup() {
    export R="$BATS_TEST_TMPDIR/repo" OUT="$BATS_TEST_TMPDIR/out" SEEN="$BATS_TEST_TMPDIR/seen"
    git init -q -b main "$R"; cd "$R"
    git config user.email t@e.com; git config user.name t
    mkdir -p apps/x docs
    echo "base rules" > AGENTS.md
    echo "base standards" > apps/x/CODING_STANDARDS.md
    echo "base seats" > docs/seats.md
    echo "extra/*.md" > .review-judge-paths
    mkdir extra; echo "base extra" > extra/rule.md
    echo code > code.txt
    git add -A; git commit -qm base
    git checkout -q -b w
    cat > "$BATS_TEST_TMPDIR/fake-dispatch.sh" <<'FAKE'
#!/usr/bin/env bash
while [ $# -gt 0 ]; do case "$1" in --prompt-file) PF=$2; shift 2;; -C) C=$2; shift 2;; -o) O=$2; shift 2;; *) shift;; esac; done
{
  echo "== $(basename "$PF")"
  for f in AGENTS.md apps/x/CODING_STANDARDS.md docs/seats.md extra/rule.md .review-judge-paths code.txt docs/review-checklist-pr.md sub/CLAUDE.md; do
    if [ -e "$C/$f" ]; then echo "$f: $(cat "$C/$f")"; else echo "$f: <absent>"; fi
  done
  grep -h 'rules files\|Rules files\|separate review' "$PF" || true
} >> "$SEEN"
printf 'ok\nVERDICT: PASS\n' > "$O"
printf -- '--- VERDICT ---\nSTATUS: pass\n---\n' > "$O.verdict"
FAKE
    chmod +x "$BATS_TEST_TMPDIR/fake-dispatch.sh"
    export REVIEW_ROUND_DISPATCH="$BATS_TEST_TMPDIR/fake-dispatch.sh"
    RR="$BATS_TEST_DIRNAME/../../scripts/review-round.sh"
}

run_round() {
    HEAD_SHA=$(git -C "$R" rev-parse HEAD)
    run bash "$RR" --repo "$R" --base main --head "$HEAD_SHA" --producer-identity p --out-dir "$OUT" --prompt-file /dev/null
}

@test "a PR that rewrites its own rules is judged by the merge-base versions" {
    cd "$R"
    echo "weakened rules" > AGENTS.md; echo "weakened standards" > apps/x/CODING_STANDARDS.md
    echo "new code" > code.txt
    git add -A; git commit -qm change
    run_round
    [ "$status" -eq 0 ]
    grep -q 'AGENTS.md: base rules' "$SEEN"
    grep -q 'apps/x/CODING_STANDARDS.md: base standards' "$SEEN"
    ! grep -q 'weakened' "$SEEN"
    grep -q 'code.txt: new code' "$SEEN"
    grep -q 'JUDGE FILES CHANGED (2)' "$OUT/receipt.md"
    grep -qx 'AGENTS.md' "$OUT/judge-files-changed.txt"
}

@test "a judge file added by the PR is absent and one deleted by the PR is present" {
    cd "$R"
    git rm -q docs/seats.md
    mkdir -p docs; echo "pr checklist" > docs/review-checklist-pr.md
    mkdir -p sub; echo "sub rules" > sub/CLAUDE.md
    git add -A; git commit -qm change
    run_round
    [ "$status" -eq 0 ]
    grep -q 'docs/seats.md: base seats' "$SEEN"
    grep -q 'docs/review-checklist-pr.md: <absent>' "$SEEN"
    grep -q 'sub/CLAUDE.md: <absent>' "$SEEN"
    grep -q 'JUDGE FILES CHANGED (3)' "$OUT/receipt.md"
}

@test "a PR cannot widen or narrow the judge list: the merge-base list governs" {
    cd "$R"
    echo "weakened extra" > extra/rule.md
    echo "nothing/*" > .review-judge-paths     # the PR's own list is ignored
    git add -A; git commit -qm change
    run_round
    [ "$status" -eq 0 ]
    grep -q 'extra/rule.md: base extra' "$SEEN"
    grep -q '.review-judge-paths: extra/\*.md' "$SEEN"
}

@test "a PR that touches no judge file is unchanged and reports none" {
    cd "$R"
    echo "new code" > code.txt; git add -A; git commit -qm change
    run_round
    [ "$status" -eq 0 ]
    grep -q 'judge files changed: none' "$OUT/receipt.md"
    [ ! -s "$OUT/judge-files-changed.txt" ]
    ! grep -q 'separate review' "$SEEN"
}

@test "the reviewer prompt names the changed judge files and says the checkout holds the base versions" {
    cd "$R"
    echo "weakened rules" > AGENTS.md; git add -A; git commit -qm change
    run_round
    [ "$status" -eq 0 ]
    grep -q 'merge-base' "$OUT/prompt-general.txt"
    grep -q 'AGENTS.md' "$OUT/prompt-general.txt"
    grep -q 'separate review' "$OUT/prompt-general.txt"
}

@test "a PR that makes a judge file a symlink out of the tree cannot write outside it" {
    cd "$R"
    rm AGENTS.md; ln -s "$BATS_TEST_TMPDIR/victim" AGENTS.md
    git add -A; git commit -qm change
    echo untouched > "$BATS_TEST_TMPDIR/victim"
    run_round
    [ "$status" -eq 0 ]
    [ "$(cat "$BATS_TEST_TMPDIR/victim")" = untouched ]
    grep -q 'AGENTS.md: base rules' "$SEEN"
}

@test "a PR that swaps a parent directory for a symlink cannot make restoration write outside the tree" {
    cd "$R"
    mkdir -p "$BATS_TEST_TMPDIR/outside"; echo untouched > "$BATS_TEST_TMPDIR/outside/seats.md"
    git rm -q -r docs; ln -s "$BATS_TEST_TMPDIR/outside" docs
    git add -A; git commit -qm change
    run_round
    [ "$status" -eq 11 ]
    [ "$(cat "$BATS_TEST_TMPDIR/outside/seats.md")" = untouched ]
}

@test "a judge symlink is pinned: changing only its target does not change what the reviewer reads" {
    cd "$R"
    echo "policy v1" > policy.txt; rm AGENTS.md; ln -s policy.txt AGENTS.md
    git add -A; git commit -qm base2; git branch -f main
    echo "policy v2 weakened" > policy.txt; git add -A; git commit -qm change
    run_round
    [ "$status" -eq 0 ]
    grep -q 'AGENTS.md: policy v1' "$SEEN"
    ! grep -q weakened "$SEEN"
    grep -qx 'AGENTS.md' "$OUT/judge-files-changed.txt"
}

@test "a gate that rewrites an overlaid judge file fails the round" {
    cd "$R"
    echo "weakened" > AGENTS.md; git add -A; git commit -qm change
    HEAD_SHA=$(git rev-parse HEAD)
    run bash "$RR" --repo "$R" --base main --head "$HEAD_SHA" --producer-identity p --out-dir "$OUT" --prompt-file /dev/null --gate-cmd 'echo compromised > AGENTS.md'
    [ "$status" -eq 11 ]
}

@test "the last glob of a manifest without a trailing newline still applies" {
    cd "$R"
    printf 'extra/*.md' > .review-judge-paths; git add -A; git commit -qm base2; git branch -f main
    echo "weakened extra" > extra/rule.md; git add -A; git commit -qm change
    run_round
    [ "$status" -eq 0 ]
    grep -q 'extra/rule.md: base extra' "$SEEN"
}

@test "a directory in place of a judge file fails closed" {
    cd "$R"
    git rm -q docs/seats.md; mkdir -p docs/seats.md; echo x > docs/seats.md/f
    git add -A; git commit -qm change
    run_round
    [ "$status" -eq 11 ]
}

@test "a judge path containing a newline fails closed" {
    cd "$R"
    mkdir -p "$(printf 'a\nb')"; echo x > "$(printf 'a\nb')/AGENTS.md"
    git add -A; git commit -qm change
    run_round
    [ "$status" -eq 11 ]
}

@test "a symlinked manifest at the merge base fails closed" {
    cd "$R"
    echo 'extra/*.md' > manifest.txt; rm .review-judge-paths; ln -s manifest.txt .review-judge-paths
    git add -A; git commit -qm base2; git branch -f main
    echo "weakened extra" > extra/rule.md; git add -A; git commit -qm change
    run_round
    [ "$status" -eq 11 ]
}

@test "a gate cannot hide a change to a file whose name embeds a newline and an overlaid path" {
    cd "$R"
    echo "weakened" > AGENTS.md
    nm="$(printf 'AGENTS.md\nxxxAGENTS.md')"
    echo one > "$nm"; git add -A; git commit -qm change
    HEAD_SHA=$(git rev-parse HEAD)
    run bash "$RR" --repo "$R" --base main --head "$HEAD_SHA" --producer-identity p --out-dir "$OUT" --prompt-file /dev/null --gate-cmd 'echo two > "$(printf "AGENTS.md\nxxxAGENTS.md")"'
    [ "$status" -eq 11 ]
}
