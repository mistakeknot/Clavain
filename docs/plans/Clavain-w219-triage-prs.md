# Plan: Add /triage-prs command (Clavain-w219)

## Goal
Add repo-wide PR backlog management. Complement existing `/triage` (internal findings) and `/resolve` (fix feedback) with `/triage-prs` (assess open PRs).

## Context
- Upstream compound-engineering has a 10-step triage-prs command
- Clavain's `/triage` is for code review findings, not PRs
- Clavain's `/resolve` fixes review feedback, not triaging what to work on

## Steps

### Step 1: Create `commands/triage-prs.md`
Adapt upstream's approach with Clavain's fd-* agents:

1. Detect repo context (`gh repo view`, branch, recent merges)
2. Gather PRs + issues in parallel (`gh pr list`, `gh issue list`)
3. Batch PRs by theme (bugs, features, docs, stale)
4. Spawn parallel fd-* agents per batch — fd-quality for code PRs, fd-architecture for structural PRs
5. Cross-reference `Fixes #X` / `Closes #X`
6. Generate triage report (markdown table: PR, description, priority, action, related issues)
7. Walk through each PR: merge / comment / close / skip

Add `disable-model-invocation: true` (manual workflow command).

### Step 2: Update counts (28→29 commands)
Update: CLAUDE.md, AGENTS.md, README.md (table + count), plugin.json, test_commands.py

### Step 3: Run tests
```bash
uv run --project tests pytest tests/structural/ -q
```

### Step 4: Commit
Commit message: `feat: add /triage-prs command for repo-wide PR backlog management`

## Verification
- `ls commands/*.md | wc -l` → 29
- Command frontmatter has name, description, disable-model-invocation
