---
name: landing-a-change
description: Use when implementation is complete and tests pass — verify, document, and land on trunk.
---

<!-- compact: SKILL-compact.md — if it exists in this directory, load it instead of following the full instructions below. The compact version contains the same verify → review → document → commit → confirm process. -->

# Landing a Change

Verify → Review evidence → Document → Commit → Confirm.

**Announce:** "I'm using the landing-a-change skill to complete this work."

## Step 1: Verify Tests

**Artifact-cached skip:** If inside a sprint (`CLAVAIN_BEAD_ID` set), check whether tests already passed at current HEAD:

```bash
BEAD_ID="${CLAVAIN_BEAD_ID:-}"
if [[ -n "$BEAD_ID" ]]; then
    test_sha=$(clavain-cli get-artifact "$BEAD_ID" "test-pass-sha" 2>/dev/null) || test_sha=""
    current_sha=$(git rev-parse HEAD)
    if [[ "$test_sha" == "$current_sha" ]]; then
        echo "Tests verified at $test_sha (current HEAD). Skipping re-run."
        # Skip to Step 2
    fi
fi
```

If HEAD moved since the last recorded test pass, or no test-pass-sha artifact exists, or not in a sprint: run the full test suite (`go test ./...` / `npm test` / `pytest` / `cargo test`). If tests fail, stop and fix. Do not proceed.

## Step 2: Verify Plan Compliance

- Were all plan checkboxes checked?
- Any unresolved TODO comments?
- Implementation matches agreed scope?

If a plan existed, invoke `verification-before-completion` skill. Otherwise proceed.

## Step 3: Evidence Checklist

- [ ] Tests pass
- [ ] Plan checkpoints complete (if plan exists)
- [ ] No unresolved TODOs in changed files
- [ ] No debug artifacts (`console.log`, `fmt.Println`, etc.)
- [ ] Changes in logical commits with descriptive messages
- [ ] Deploy verification plan exists (if deploy-relevant)

If deploy-relevant, consider invoking `fd-safety`.

## Step 4: Present Options (AskUserQuestion)

```
question: "Implementation verified. How would you like to land this?"
options:
  - Commit and push
  - Commit locally
  - Changelog first (runs /clavain:changelog)
  - Review first (show git diff, return to this step)
```

## Step 5: Execute

**Commit and push / Commit locally:**
```bash
bd close <issue-ids>          # if .beads/ exists
git add <specific files>      # NOT git add .
git commit -m "feat(scope): description

Co-Authored-By: Claude <noreply@anthropic.com>"
git push                      # skip if "locally" chosen
```

**Changelog first:** Run `/clavain:changelog`, then commit.

**Review first:** Show `git diff --stat && git diff`, return to Step 4.

## Step 5.5: Post-Push Canary (rsj.1.2)

After push succeeds and inside a sprint (`CLAVAIN_BEAD_ID` set), run a lightweight canary check on the merged state:

```bash
if [[ -n "${CLAVAIN_BEAD_ID:-}" ]] && [[ "${CLAVAIN_SKIP_CANARY:-}" != "true" ]]; then
    source "${CLAUDE_PLUGIN_ROOT}/hooks/lib-sprint.sh" 2>/dev/null || true
    if ! sprint_canary_check "$CLAVAIN_BEAD_ID"; then
        echo "⚠ Post-merge canary FAILED. Sprint NOT recorded as successful."
        echo "  Fix the issue and re-run, or set CLAVAIN_SKIP_CANARY=true to override."
        # Do NOT close the bead or record success
    fi
fi
```

If canary fails: warn user, emit `quality_failure` event to Interspect, do NOT record sprint as successful. If canary passes: normal flow continues.

## Step 6: Capture Learnings (Optional)

Run `/clavain:compound` or note insights in project memory files.

## Red Flags

- Never push without verified tests
- Never `git add .` — stage specific files
- Never auto-push without user selecting Option 1
- Never skip the evidence checklist
