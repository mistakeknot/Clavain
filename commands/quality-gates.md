---
name: quality-gates
description: Auto-select and run the right reviewer agents based on what changed — one command for comprehensive quality review
argument-hint: "[optional: specific files or 'all' for full diff]"
---

# Quality Gates

Run the right set of reviewer agents automatically based on change risk. This command analyzes what changed and invokes the appropriate specialists.

## Input

<review_target> #$ARGUMENTS </review_target>

If no arguments provided, analyze the current unstaged + staged changes (`git diff` + `git diff --cached`).

## Execution Flow

### Phase 1: Analyze Changes

```bash
# Get changed files
git diff --name-only HEAD
git diff --cached --name-only
```

Classify each changed file by:
- **Language**: .go → Go, .py → Python, .ts/.tsx → TypeScript, .sh → Shell
- **Risk domain**: auth/crypto/secrets → Security, migration/schema → Data, hot-path/cache/query → Performance, goroutine/async/channel → Concurrency

### Phase 2: Select Reviewers

Based on analysis, invoke the appropriate agents in parallel:

**Always run:**
- `code-simplicity-reviewer` — every change benefits from simplicity check

**Language-specific (based on file extensions):**
- `.go` files → `go-reviewer`
- `.py` files → `python-reviewer`
- `.ts/.tsx` files → `typescript-reviewer`
- `.sh/.bash` files → `shell-reviewer`
- `.rs` files → `rust-reviewer`

**Risk-based (based on file paths and content):**
- Auth/crypto/input handling/secrets → `security-sentinel`
- Database/migration/schema/backfill → `data-integrity-reviewer` + `data-migration-expert`
- Performance-critical paths → `performance-oracle`
- Concurrent/async code → `concurrency-reviewer`
- Architecture/new modules/interfaces → `architecture-strategist`

**Threshold:** Don't run more than 5 agents total. Prioritize by risk.

### Phase 3: Gather Context for Agents

Before launching agents, gather the diff context they will review:

```bash
# Unified diff (staged + unstaged)
git diff HEAD > /tmp/qg-diff.txt
git diff --cached >> /tmp/qg-diff.txt

# Changed file list with reasons for agent selection
git diff --name-only HEAD
git diff --cached --name-only
```

### Phase 4: Run Agents in Parallel

Launch selected agents using the Task tool with `run_in_background: true`. Each agent prompt MUST include:

1. **The unified diff** — paste the content of `/tmp/qg-diff.txt` (or inline the diff if small)
2. **Changed file list** — with why each file was selected for this agent
3. **Relevant config files** — if any were touched (e.g., go.mod, tsconfig.json, Cargo.toml)

Ask agents to **reference diff hunks** in findings (file:line or hunk header like `@@ -10,5 +10,7 @@`).

```
Task(code-simplicity-reviewer): "Review this diff for unnecessary complexity. [paste diff]. Reference specific hunks."
Task(go-reviewer): "Review Go changes in this diff. [paste diff]. Reference file:line."
Task(security-sentinel): "Scan this diff for security vulnerabilities. [paste diff]. Reference specific hunks."
```

### Phase 5: Synthesize Results

Collect all agent findings and present:

```markdown
## Quality Gates Report

### Changes Analyzed
- X files changed across Y languages
- Risk domains detected: [security, data, performance, etc.]

### Agents Invoked
1. code-simplicity-reviewer — [pass/findings]
2. go-reviewer — [pass/findings]
3. security-sentinel — [pass/findings]

### Findings Summary
- 🔴 CRITICAL (P1): [count] — must fix
- 🟡 IMPORTANT (P2): [count] — should fix
- 🔵 NICE-TO-HAVE (P3): [count] — optional

### Gate Result: [PASS / FAIL]

[If FAIL: list P1 items that must be addressed]
```

## Important

- **Don't over-review small changes.** If the diff is under 20 lines and touches one file, only run `code-simplicity-reviewer` + the language reviewer.
- **Run after tests pass.** Quality gates complement testing, not replace it.
- **P1 findings block shipping.** Present them prominently and ensure resolution.
