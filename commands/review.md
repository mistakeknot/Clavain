---
name: review
description: Perform exhaustive code reviews using multi-agent analysis and deep inspection
argument-hint: "[PR number, GitHub URL, branch name, or latest]"
---

# Review Command

Perform exhaustive code reviews using multi-agent analysis and deep inspection.

## Review Target

<review_target> #$ARGUMENTS </review_target>

## Prerequisites

- Git repository with GitHub CLI (`gh`) installed and authenticated
- Clean main/master branch
- For document reviews: Path to a markdown file

## Phase 1: Setup

1. Determine review type: PR number (numeric), GitHub URL, file path (.md), or empty (current branch)
2. If on a different branch than the target, checkout with `gh pr checkout` or `git checkout`
3. Fetch PR metadata: `gh pr view --json title,body,files,linkedIssues`

**Protected artifacts** — never flag for deletion:
- `docs/plans/*.md` — living plan documents
- `docs/solutions/*.md` — solution documentation

## Phase 1b: Prepare Output Directory

Set up the file-based output infrastructure before launching agents:

```bash
# Determine review target identifier for output dir
REVIEW_TARGET="current"  # or PR number, branch name
OUTPUT_DIR="${PROJECT_ROOT}/.clavain/reviews/${REVIEW_TARGET}"
mkdir -p "$OUTPUT_DIR"
rm -f "$OUTPUT_DIR"/*.md "$OUTPUT_DIR"/*.md.partial 2>/dev/null

# Write diff to temp file for agent consumption
TS=$(date +%s)
DIFF_FILE="/tmp/review-diff-${TS}.txt"
git diff HEAD > "$DIFF_FILE"
```

## Phase 2: Multi-Agent Review

Launch these core agents in parallel with `run_in_background: true`. Each agent prompt MUST include the file-based output contract:

```
## Output Contract

Write ALL findings to `{OUTPUT_DIR}/{agent-name}.md`.
Do NOT return findings in your response text.
Your response text should be a single line: "Findings written to {OUTPUT_DIR}/{agent-name}.md"

File structure:

### Findings Index
- SEVERITY | ID | "Section" | Title
Verdict: safe|needs-changes|risky

### Summary
[3-5 lines]

### Issues Found
[ID. SEVERITY: Title — 1-2 sentences with evidence. Reference file:line.]

### Improvements
[ID. Title — 1 sentence with rationale]

Zero findings: empty index + verdict: safe.
```

Each agent should Read the diff file (`{DIFF_FILE}`) as their first action instead of receiving the diff inline.

**Core agents:**
1. Task interflux:review:fd-architecture — structural review
2. Task interflux:review:fd-safety — security scan
3. Task interflux:review:fd-quality — naming, conventions, idioms
4. Task interflux:research:git-history-analyzer — historical context
5. Task intercraft:review:agent-native-reviewer — agent-native parity

**Risk-specific reviewers** (conditional):
- Async/concurrent code or data changes → Task interflux:review:fd-correctness
- Database migrations → Task data-migration-expert

**Polling for completion** (after dispatch):
1. Check `{OUTPUT_DIR}/` every 30 seconds for `.md` files
2. Report progress: `[3/5 agents complete]`
3. After 5 minutes, report any agents still pending

## Phase 3: Cross-AI Review (Oracle, Optional)

If Oracle is available (SessionStart hook reports it), run a GPT-5.2 Pro review in background:

```bash
DISPLAY=:99 CHROME_PATH=/usr/local/bin/google-chrome-wrapper \
  oracle --wait -p "Review this PR for issues a Claude-based reviewer might miss. Focus on: security blind spots, architectural concerns, edge cases. Number each finding with severity (P1/P2/P3)." \
  -f "<changed-files>" \
  --write-output "${OUTPUT_DIR}/oracle-council.md"
```

Oracle output goes to the output directory alongside agent findings.

## Phase 4: Synthesis via Subagent

**Do NOT read agent output files yourself.** Delegate synthesis to a subagent so agent prose never enters the host context.

Launch the **intersynth synthesis agent** (foreground, not background — you need its result):

```
Task(intersynth:synthesize-review):
  prompt: |
    OUTPUT_DIR={OUTPUT_DIR}
    VERDICT_LIB={CLAUDE_PLUGIN_ROOT}/hooks/lib-verdict.sh
    MODE=review
    CONTEXT="PR #{pr_number} — {title}"
    PROTECTED_PATHS=docs/plans/*.md, docs/solutions/*.md
```

The intersynth agent reads all agent output files, validates structure, deduplicates findings, writes verdict JSON files, and returns a compact summary.

After the synthesis subagent returns:
1. Read `{OUTPUT_DIR}/synthesis.md` and present it to the user (~30-50 lines)
2. If FAIL, list P1 findings prominently — they block merge
3. If `.beads/` exists and findings > 3, ask user about filing beads issues

**P1 findings block merge** — must be resolved before accepting the PR.
