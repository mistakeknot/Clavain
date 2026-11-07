#!/usr/bin/env bats
# mk-kvwc9: a cross-lab-review whose PR diff touches UI files gets the ui-craft
# review standards in its brief. The brief's own verdict rule is unchanged.

setup() {
    load test_helper
    T="$(mktemp -d)"
    DISPATCH="$BATS_TEST_DIRNAME/../../scripts/dispatch.sh"
    # shellcheck disable=SC1090
    source "$BATS_TEST_DIRNAME/../../scripts/lib-ui-review-standards.sh"
    export CLAVAIN_CONTEXT_GATEWAY_MODE=off
    export CLAVAIN_BB_DIRECT_POOL=0
    export LC_ALL=C
    mkdir -p "$T/bin" "$T/home"
    export HOME="$T/home"
    unset CLAVAIN_UI_REVIEW CLAVAIN_UI_REVIEW_STANDARDS CLAVAIN_UI_CRAFT_DIR CLAUDE_CONFIG_DIR

    # A stand-in ui-craft skill directory, with the two companion files.
    SK="$T/skill"; mkdir -p "$SK/references"
    cat > "$SK/references/review-standards.md" <<'EOF'
# Review standards (UI)

**Format precedence.** The brief's own format wins.

## Flag on sight
- STANDARDS-SENTINEL transition: all

Close with exactly one verdict:
- **Block** if a FEEL finding remains.
- **Approve** when none remain.
EOF
    cat > "$SK/references/motion-and-performance.md" <<'EOF'
## 2. Easing
EASING-NOT-EMBEDDED
## 3. Duration budgets
BUDGET-SENTINEL 100-160ms
### 3a. a sub-heading stays inside the section
## 4. Physical correctness
PHYSICAL-NOT-EMBEDDED
EOF
    cat > "$SK/SKILL.md" <<'EOF'
## Other
OTHER-NOT-EMBEDDED
## Never ship: temporary dev code
NEVERSHIP-SENTINEL
## Quick self-check before done
SELFCHECK-NOT-EMBEDDED
EOF
    export CLAVAIN_UI_CRAFT_DIR="$SK"

    R="$T/repo"; git init -q -b main "$R"
    git -C "$R" config user.email t@t; git -C "$R" config user.name t
    echo a > "$R/a"; git -C "$R" add a; git -C "$R" commit -qm base
    BASE="$(git -C "$R" rev-parse HEAD)"

    export CLAVAIN_REVIEW_RECEIPT_DIR="$T/reviews"
    cat > "$T/bin/ic" <<'SH'
#!/usr/bin/env bash
if [[ "$*" == *"route list"* ]]; then echo '[]'
elif [[ "$*" == *"route identity"* ]]; then echo '{"model_identity":"gpt-6.1-sol"}'
elif [[ "$*" == *"route record"* ]]; then exit 0
else exit 3; fi
SH
    chmod +x "$T/bin/ic"
    # Fake codex: keep argv and stdin so the assembled brief can be read back.
    cat > "$T/bin/codex" <<EOF
#!/usr/bin/env bash
[[ "\$1" == exec ]] || { echo "codex-cli 0.166.0"; exit 0; }
printf '%s\n' "\$@" > "$T/codex.argv"
cat > "$T/codex.stdin"
outfile=""
while [[ \$# -gt 0 ]]; do case "\$1" in -o) outfile="\$2"; shift 2 ;; *) shift ;; esac; done
printf 'Findings: none\n\nVERDICT: PASS\n' > "\$outfile"
exit 0
EOF
    chmod +x "$T/bin/codex"
    printf 'Review it.\n' > "$T/prompt.md"
    OUT="$T/out.md"
    POLICY_HASH="$(sha256sum "$BATS_TEST_DIRNAME/../../config/routing.yaml" | cut -d' ' -f1)"
    ROUTE_JSON="$(jq -n --arg h "$POLICY_HASH" \
        '{policy_hash:$h, profile_ref:"primary", profile:{backend:"codex",model:"gpt-6.1-sol",model_identity:"gpt-6.1-sol"}}')"
}

teardown() { rm -rf "$T"; }

# Commits the given paths on top of BASE and sets the receipt flags.
commit_paths() {
    local f
    for f in "$@"; do
        mkdir -p "$R/$(dirname "$f")"; echo x > "$R/$f"; git -C "$R" add "$f"
    done
    git -C "$R" commit -qm head
    HEAD_SHA="$(git -C "$R" rev-parse HEAD)"
    RECEIPT_FLAGS=(--repo o/r --repo-id R_abc123 --pr 7 --head "$HEAD_SHA" --base "$BASE")
}

run_review() {
    PATH="$T/bin:$PATH" run bash "$DISPATCH" --role-resolved --role cross-lab-review \
        --to codex --model gpt-6.1-sol --resolved-route-json "$ROUTE_JSON" \
        --producer-identity claude-sonnet-5-5 "${RECEIPT_FLAGS[@]}" -C "$R" \
        --prompt-file "$T/prompt.md" -o "$OUT" "$@"
}

brief() { cat "$T/codex.argv" "$T/codex.stdin" 2>/dev/null; }

# ── file classification ─────────────────────────────────────────────────────

@test "UI files by extension and by directory are UI" {
    for f in web/Button.tsx a/b.jsx x.vue x.svelte site/app.css s.scss s.sass s.less index.html a.htm a.astro doc.mdx w.xaml \
             src/components/a.ts src/ui/a.js app/styles/a.ts pkg/views/a.mjs \
             App/Views/Home.swift cmd/tui/model.go internal/ui/panel.go game/ui/hud.rs \
             tailwind.config.ts tailwind.config.js src/theme.ts src/tokens.json web/tokens.css icon.svg; do
        run _ui_review_is_ui_file "$f"
        [ "$status" -eq 0 ] || { echo "expected UI: $f"; return 1; }
    done
}

@test "non-UI files, tests, stories, fixtures and vendored files are not UI" {
    for f in lib/util.ts scripts/dispatch.sh server/x.py README.md a.json pkg/model.go \
             src/App.test.tsx src/App.spec.jsx src/Button.stories.tsx src/__tests__/a.tsx \
             tests/fixtures/page.html tests/e2e/login.css node_modules/x/a.css dist/app.css build/a.html \
             vendor/lib/a.scss assets/logo.svg public/assets/a.svg dist/a.svg App/Models/Home.swift; do
        run _ui_review_is_ui_file "$f"
        [ "$status" -ne 0 ] || { echo "expected not UI: $f"; return 1; }
    done
}

# ── the brief ───────────────────────────────────────────────────────────────

@test "UI diff appends the standards, the section 3 table and the never-ship list" {
    commit_paths web/Button.tsx docs/notes.md
    run_review
    [ "$status" -eq 0 ]
    b="$(brief)"
    [[ "$b" == *"UI lens: this change touches user-facing files"* ]]
    [[ "$b" == *"- web/Button.tsx"* ]]
    [[ "$b" != *"- docs/notes.md"* ]]
    [[ "$b" == *"STANDARDS-SENTINEL"* ]]
    [[ "$b" == *"BUDGET-SENTINEL"* ]]
    [[ "$b" == *"a sub-heading stays inside the section"* ]]
    [[ "$b" == *"NEVERSHIP-SENTINEL"* ]]
    [[ "$b" != *"EASING-NOT-EMBEDDED"* ]]
    [[ "$b" != *"PHYSICAL-NOT-EMBEDDED"* ]]
    [[ "$b" != *"OTHER-NOT-EMBEDDED"* ]]
    [[ "$b" != *"SELFCHECK-NOT-EMBEDDED"* ]]
}

@test "the standards sit before the format rules and the brief's VERDICT line stays last" {
    commit_paths web/Button.tsx
    run_review
    [ "$status" -eq 0 ]
    b="$(brief)"
    pre="${b%%STANDARDS-SENTINEL*}"
    post="${b#*STANDARDS-SENTINEL}"
    [[ "$pre" != *"Give each finding its own heading line"* ]]
    [[ "$post" == *"Give each finding its own heading line"* ]]
    # The wrapper maps the standards' own close onto the packaged verdict.
    [[ "$b" == *"is the only verdict"* ]]
    # The unchanged requirement: one of the three verdict words, last line, no other word.
    [[ "$b" == *'exactly one'* ]]
    [[ "$b" == *'"VERDICT: PASS WITH NOTES"'* ]]
    [[ "$b" == *'"VERDICT: FAIL"'* ]]
    [[ "$b" == *"fails the dispatch without a receipt."* ]]
    tail_text="${b##*"fails the dispatch without a receipt."}"
    [[ "$tail_text" != *"STANDARDS-SENTINEL"* ]]
}

@test "the verdict requirement text is identical with and without the UI section" {
    commit_paths web/Button.tsx
    run_review
    ui="$(brief)"
    ui_tail="${ui#*"Give each finding its own heading line"}"
    git -C "$R" checkout -q "$BASE"
    commit_paths server/x.py
    rm -f "$T/codex.argv" "$T/codex.stdin"
    run_review
    non="$(brief)"
    non_tail="${non#*"Give each finding its own heading line"}"
    [ -n "$ui_tail" ]
    [ "$ui_tail" = "$non_tail" ]
}

@test "non-UI diff does not append the standards" {
    commit_paths server/x.py lib/util.ts src/App.test.tsx
    run_review
    [ "$status" -eq 0 ]
    b="$(brief)"
    [[ "$b" != *"UI lens"* ]]
    [[ "$b" != *"STANDARDS-SENTINEL"* ]]
    [[ "$b" == *"Give each finding its own heading line"* ]]
}

@test "a diff of only tests and stories does not append the standards" {
    commit_paths src/Button.stories.tsx src/__tests__/a.tsx
    run_review
    [ "$status" -eq 0 ]
    [[ "$(brief)" != *"UI lens"* ]]
}

@test "CLAVAIN_UI_REVIEW=off skips the section" {
    commit_paths web/Button.tsx
    CLAVAIN_UI_REVIEW=off run_review
    [ "$status" -eq 0 ]
    [[ "$(brief)" != *"UI lens"* ]]
}

@test "missing standards file: the review runs, a notice is printed, the brief says so" {
    commit_paths web/Button.tsx
    export CLAVAIN_UI_REVIEW_STANDARDS="$T/nope/review-standards.md"
    run_review
    [ "$status" -eq 0 ]
    [[ "$output" == *"Notice: this PR touches UI files but the ui-craft review standards were not found at $T/nope/review-standards.md"* ]]
    b="$(brief)"
    [[ "$b" == *"review standards file was not available to dispatch"* ]]
    [[ "$b" != *"STANDARDS-SENTINEL"* ]]
    [[ "$b" == *"Give each finding its own heading line"* ]]
    [ "$(jq -r .verdict "$T/reviews/o__r/7-$HEAD_SHA.json")" = PASS ]
}

@test "an empty standards file is treated as missing" {
    commit_paths web/Button.tsx
    : > "$T/empty.md"
    export CLAVAIN_UI_REVIEW_STANDARDS="$T/empty.md"
    run_review
    [ "$status" -eq 0 ]
    [[ "$output" == *"Notice:"* ]]
}

@test "a missing standards file with a non-UI diff prints no notice" {
    commit_paths server/x.py
    export CLAVAIN_UI_REVIEW_STANDARDS="$T/nope.md"
    run_review
    [ "$status" -eq 0 ]
    [[ "$output" != *"Notice:"* ]]
}

@test "a missing companion file is named in the brief and does not block" {
    commit_paths web/Button.tsx
    rm "$SK/references/motion-and-performance.md" "$SK/SKILL.md"
    run_review
    [ "$status" -eq 0 ]
    b="$(brief)"
    [[ "$b" == *"STANDARDS-SENTINEL"* ]]
    [[ "$b" == *"motion-and-performance.md section 3; that file was not available"* ]]
    [[ "$b" == *"never-ship checklist in the ui-craft SKILL.md; that file was not available"* ]]
}

@test "CLAVAIN_UI_REVIEW_STANDARDS names the file and its skill directory supplies the companions" {
    commit_paths web/Button.tsx
    unset CLAVAIN_UI_CRAFT_DIR
    export CLAVAIN_UI_REVIEW_STANDARDS="$SK/references/review-standards.md"
    run_review
    [ "$status" -eq 0 ]
    b="$(brief)"
    [[ "$b" == *"STANDARDS-SENTINEL"* && "$b" == *"BUDGET-SENTINEL"* && "$b" == *"NEVERSHIP-SENTINEL"* ]]
}

@test "with no variable set the installed skill under the config directory is used" {
    commit_paths web/Button.tsx
    unset CLAVAIN_UI_CRAFT_DIR
    mkdir -p "$T/cfg/skills"; cp -r "$SK" "$T/cfg/skills/ui-craft"
    CLAUDE_CONFIG_DIR="$T/cfg" run_review
    [ "$status" -eq 0 ]
    [[ "$(brief)" == *"STANDARDS-SENTINEL"* ]]
}

@test "a diff over 200 paths says only the first 200 were checked" {
    RR_CHANGED_PATHS_JSON='{"total":450,"paths":["web/a.tsx"]}'
    run _ui_review_section
    [ "$status" -eq 0 ]
    [[ "$output" == *"first 200 of 450 changed paths"* ]]
}

@test "a long UI list is capped at 40 names" {
    RR_CHANGED_PATHS_JSON="$(jq -nc '{total:60, paths:[range(60)|"web/c\(.).tsx"]}')"
    run _ui_review_section
    [ "$status" -eq 0 ]
    [[ "$output" == *"- web/c39.tsx"* ]]
    [[ "$output" != *"- web/c40.tsx"* ]]
    [[ "$output" == *"... and 20 more"* ]]
}

@test "no changed-paths state means no section" {
    RR_CHANGED_PATHS_JSON=""
    run _ui_review_section
    [ "$status" -eq 0 ]
    [ -z "$output" ]
}

@test "the packaged cross-lab brief and the library are wired together" {
    grep -q 'lib-ui-review-standards.sh' "$DISPATCH"
    grep -q '_ui_review_section' "$DISPATCH"
    # The section is added before the format block, so the VERDICT rule stays the last instruction.
    [ "$(grep -n '_ui_review_section' "$DISPATCH" | head -1 | cut -d: -f1)" -lt "$(grep -n 'Give each finding its own heading line' "$DISPATCH" | head -1 | cut -d: -f1)" ]
}
