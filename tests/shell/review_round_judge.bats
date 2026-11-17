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
