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

## Phase 2: Multi-Agent Review

Launch these core agents in parallel with `run_in_background: true` to prevent agent output from flooding the main conversation context:

1. Task pattern-recognition-specialist(PR content)
2. Task architecture-strategist(PR content)
3. Task security-sentinel(PR content)
4. Task performance-oracle(PR content)
5. Task git-history-analyzer(PR content)
6. Task agent-native-reviewer(PR content)

**Language-specific reviewers** (based on file extensions):
- `.go` files → Task go-reviewer
- `.py` files → Task python-reviewer
- `.ts/.tsx` files → Task typescript-reviewer
- `.sh` files → Task shell-reviewer
- `.rs` files → Task rust-reviewer

**Risk-specific reviewers** (conditional):
- Async/concurrent code → Task concurrency-reviewer
- Data changes → Task data-integrity-reviewer
- Database migrations → Task data-migration-expert + Task deployment-verification-agent

## Phase 3: Simplification Pass

Run Task code-simplicity-reviewer on the PR content.

## Phase 3.5: Cross-AI Review (Oracle, Optional)

If Oracle is available (SessionStart hook reports it), run a GPT-5.2 Pro review in background:

```bash
DISPLAY=:99 CHROME_PATH=/usr/local/bin/google-chrome-wrapper \
  oracle --wait -p "Review this PR for issues a Claude-based reviewer might miss. Focus on: security blind spots, architectural concerns, edge cases. Number each finding with severity (P1/P2/P3)." \
  -f "<changed-files>"
```

Include Oracle findings in Phase 4 synthesis alongside Clavain agent results.

## Phase 4: Synthesis

1. Collect all agent findings. Discard any that flag `docs/plans/` or `docs/solutions/` files.
2. Categorize: P1 (critical/blocks merge), P2 (important/should fix), P3 (nice-to-have)
3. Remove duplicates across agents
4. Create beads issues for each finding using `bd create`
5. Run project tests if applicable

Present summary:

```
## Review Complete

**Target:** PR #XXXX - [Title]
**Findings:** X total (Y P1, Z P2, W P3)

P1 (blocks merge):
- [finding] — [file:line]

P2 (should fix):
- [finding] — [file:line]

P3 (nice-to-have):
- [finding] — [file:line]

Agents used: [list]
```

**P1 findings block merge** — must be resolved before accepting the PR.
