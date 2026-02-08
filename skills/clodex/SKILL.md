---
name: clodex
description: Dispatch tasks to Codex CLI agents — single megaprompt for one task, parallel delegation for many. Includes behavioral contract for codex-first mode, structured debate triggers, and Oracle escalation.
version: 0.2.0
---

# Clodex — Codex Dispatch

Dispatch tasks to Codex CLI agents (`codex exec`). Claude acts as orchestrator — planning, dispatching, verifying, and committing. Works for single tasks (megaprompt) and multi-task parallel execution (delegation).

## When to Use

- You have well-scoped implementation work (bug fixes, features, tests, refactoring)
- Each task has clear files, clear success criteria, and can be verified independently
- You want to keep Claude's context window clean for orchestration + review

## When NOT to Use

- Tasks requiring interactive user input mid-execution
- Tasks needing deep cross-file architectural understanding (use Claude subagents)
- Code review (use interpeer instead)
- Tasks where you're unsure what needs to change (research first, then dispatch)

## Prerequisites

1. Codex CLI installed: `which codex`
2. Codex config exists: `~/.codex/config.toml`
3. Project directory has a `.git` root

If Codex is unavailable, suggest falling back to `clavain:subagent-driven-development`.

## Dispatch Routing

Decide which mode to use based on the work:

| Situation | Mode | Why |
|-----------|------|-----|
| Single task | **Megaprompt** | One agent explores + implements + verifies in one shot |
| 2+ independent tasks | **Parallel delegation** | Multiple agents run concurrently |
| Sequential dependent tasks | **Ordered delegation** | Agent N starts after agent N-1 verified |
| Complex decision before implementing | **Debate first** | Get Codex's independent analysis before coding |

## Step 0: Resolve dispatch.sh

`$CLAUDE_PLUGIN_ROOT` is only available during skill loading — it's NOT exported to the Bash environment. Find the absolute path:
```bash
DISPATCH=$(find ~/.claude/plugins/cache -path '*/clavain/*/scripts/dispatch.sh' 2>/dev/null | head -1)
[ -z "$DISPATCH" ] && DISPATCH=$(find ~/projects/Clavain -name dispatch.sh -path '*/scripts/*' 2>/dev/null | head -1)
```

---

## Megaprompt Mode (Single Task)

**Announce:** "Dispatching to Codex agent..."

### Step 1: Craft the Megaprompt

Write a single prompt that tells the Codex agent to explore, implement, AND verify — all in one session:

```markdown
## Goal
[1-2 sentence description of the change]

## Phase 1: Explore
Before making any changes, investigate the code area:
- Read [suspected files/functions/areas]
- Identify the exact file(s) and line(s) that need to change
- Check for existing tests covering this area
- Note the package name, imports, and any callers of modified code
- Print a brief exploration summary before proceeding

## Phase 2: Implement
Make the change:
- [Specific description of what to change]
- [File hints, e.g., "likely in internal/foo/"]
- [Design notes if relevant]

## Phase 3: Verify
After implementing, run ALL of these and report results:
1. Build: `[build command]`
2. Tests: `[SCOPED test command — see below]`
3. Diff: `git diff --stat` (ensure only expected files changed)
4. If build or tests fail: fix and re-verify (up to 2 self-retries)

**CRITICAL — Scope test commands**: Use `-run TestPattern`, `-short`, `-timeout=60s`. NEVER use broad `go test ./... -v`.

## Final Report
```
EXPLORATION: [1-2 sentence summary]
CHANGES: [files modified/created]
BUILD: PASS | FAIL
TESTS: PASS | FAIL [N passed, M failed]
VERDICT: CLEAN | NEEDS_ATTENTION [reason]
```

## Constraints
- Only modify files directly related to the goal
- Do not reformat, realign, or adjust whitespace in code you didn't functionally change
- Do not add comments, docstrings, or type annotations to unchanged code
- Do not refactor or rename anything not directly related to the task
- Keep the change minimal — prefer 5 clean lines over 50 "proper" lines
- Do NOT commit or push any changes
- If GOCACHE permission errors occur, use: GOCACHE=/tmp/go-build-cache
```

Save to: `/tmp/codex-mega-$(date +%s).md`

### Step 2: Dispatch

```bash
bash "$DISPATCH" \
  --prompt-file "$PROMPT_FILE" \
  -C "$PROJECT_DIR" \
  -o "/tmp/codex-result-$(date +%s).md" \
  -s workspace-write \
  --inject-docs
```

Use `timeout: 600000` (10 minutes) on the Bash tool call.

### Step 3: Read Verdict

- `VERDICT: CLEAN` → report success, trust self-verification
- `VERDICT: NEEDS_ATTENTION` → read reason, retry once with tighter prompt
- No verdict / garbled → fall back to Split mode or edit directly

**When to independently verify:**
- First dispatch in a new session (establish trust)
- Changes to critical paths (auth, data integrity, billing)
- Diff mentions unexpected files

### Step 4: Handle Failure (max 1 retry)

1. Read failure details
2. Write tighter follow-up megaprompt with error context
3. Re-dispatch once
4. If still failing:
   ```
   Codex agent failed. Issue: [description]
   Options:
   1. Try Split mode (separate explore/implement/verify agents)
   2. I'll make this change directly
   3. Skip this change
   ```

### Split Mode (Fallback)

When megaprompt fails, dispatch separate read-only explore → workspace-write implement → read-only verify agents. Claude reads summaries between steps.

---

## Parallel Delegation Mode (Multiple Tasks)

### Step 1: Identify and Classify Tasks

| Classification | Executor | Rationale |
|---------------|----------|-----------|
| Independent implementation | Codex agent | Well-scoped, clear files, clear tests |
| Exploratory/research | Claude subagent | Needs deep reasoning |
| Architecture-sensitive | Claude subagent | Needs cross-file understanding |
| Sequential dependency | Codex (ordered) | Must wait for prior task |

Present the classification to the user and get approval before dispatching.

### Step 2: Check for File Overlap

If two tasks might modify the same file:
- **(a) Combine them** into one agent prompt, or
- **(b) Dispatch sequentially** — agent 2 starts only after agent 1 commits

### Step 3: Craft Prompts

Each prompt MUST include:
- **Context**: What the project is, relevant architecture
- **Task**: Exact description of what to change
- **Files**: Specific file paths
- **Success criteria**: SCOPED test commands
- **Constraints**: The standard constraints block (same as megaprompt)

**Prompt template:**
```
You are working on [project name], a [brief description].

## Task
[Detailed description]

## Relevant Files
- [path/to/file1] — [what it does]

## Success Criteria
- [ ] [Build command] succeeds
- [ ] [SCOPED test command] passes
- [ ] [Specific behavior verified]

## Constraints (ALWAYS INCLUDE)
- Only modify listed files unless absolutely necessary
- Do not reformat unchanged code
- Keep it minimal — prefer 5 clean lines over 50 "proper" lines
- Do NOT commit or push

## Environment
- Build: [command]
- Test: [SCOPED command]
```

**CRITICAL — Scope test commands**: `-run TestPattern`, `-short`, `-timeout=60s`. Never `go test ./...` or bare `pytest`.

**Tips:**
- `--inject-docs` prepends CLAUDE.md (Codex reads AGENTS.md natively)
- `--prompt-file` for long prompts (avoids shell escaping)
- `--dry-run` to preview without executing

### Step 4: Dispatch in Parallel

Launch all Bash calls **in a single message** (multiple tool calls). They run concurrently. Set `timeout: 600000` on each.

```bash
# Agent 1
bash $DISPATCH \
  --inject-docs -C /path/to/project \
  --name fix-auth -o /tmp/codex-{name}.md \
  -s workspace-write \
  --prompt-file /tmp/task1-prompt.md

# Agent 2 (parallel)
bash $DISPATCH \
  --inject-docs -C /path/to/project \
  --name add-tests -o /tmp/codex-{name}.md \
  -s workspace-write \
  --prompt-file /tmp/task2-prompt.md
```

Do NOT use `run_in_background: true` — parallel tool calls give the same concurrency without stale notifications.

### Step 5: Verify Each Agent

For EACH completed agent:

```bash
# 1. Read output
cat /tmp/codex-{name}.md

# 2. Build
go build ./relevant/package/...

# 3. Scoped tests
go test ./relevant/package/... -v

# 4. Review diff
git diff -- relevant/files

# 5. Proportionality check
git diff --stat
```

**NEVER skip verification.** Check spec compliance, code quality, integration tests across all changes.

### Step 6: Retry Failed Agents

**Resume** (agent was on right track): `codex exec resume --last "Fix: [error details]"`
**Re-dispatch** (agent went wrong direction): Fresh prompt with tighter constraints

### Step 7: Land the Change

Use `clavain:landing-a-change`:
- Full test suite passes across all changes
- Evidence checklist
- Commit with dual Co-Authored-By

---

## Codex-First Behavioral Contract

When codex-first mode is active (`/clodex-toggle`), these rules apply:

### The Three Rules
1. **Read freely**: Read, Grep, Glob, WebFetch, WebSearch — without restriction
2. **Write via Codex**: All code changes go through dispatch.sh → Codex agents
3. **Bash discipline**: Read-only commands only. File-modifying Bash goes through Codex.

**Exception**: Git operations (add, commit, push) are Claude's responsibility — do them directly.

### Allowed Bash (read-only)
`git status/diff/log/show`, `go build/test`, `make test`, `npm test`, `pytest`, `cat/head/tail/wc/ls/find`, `codex exec resume`

### Must Dispatch via Codex (file-modifying)
File creation/modification/deletion, `sed -i`, package installs

---

## Debate Mode

### When to Suggest

Count complexity signals — if 3+ apply, suggest debate:

| Signal | Example |
|--------|---------|
| Multiple valid approaches | "middleware or decorators" |
| Architectural implications | New patterns, cross-cutting concerns |
| Security-sensitive | Auth, crypto, permissions |
| API contract changes | Public interfaces, protocols |
| Performance-critical | Hot loops, data structures at scale |
| Ambiguous requirements | User intent unclear |

**Always ask the user first.**

### Running a Debate

1. Write position to `/tmp/debate-claude-position-${TOPIC}.md`
2. Dispatch:

```bash
DEBATE_SH=$(find ~/.claude/plugins/cache -path '*/clavain/*/scripts/debate.sh' 2>/dev/null | head -1)
[ -z "$DEBATE_SH" ] && DEBATE_SH=$(find ~/projects/Clavain -name debate.sh -path '*/scripts/*' 2>/dev/null | head -1)

bash $DEBATE_SH -C $PROJECT_DIR -t $TOPIC \
  --claude-position /tmp/debate-claude-position-${TOPIC}.md \
  -o /tmp/debate-output-${TOPIC}.md --rounds 2
```

3. Read output, synthesize, present options to user

### 2-Round Maximum
Capped to prevent debate costing more than implementation.

## Oracle Escalation

Escalate to Oracle (GPT-5.2 Pro) for security, multi-system integration, performance architecture, or irreconcilable Claude↔Codex disagreement:

```bash
DISPLAY=:99 CHROME_PATH=/usr/local/bin/google-chrome-wrapper \
  oracle --wait \
  -p "Review this technical decision. [summary]" \
  -f 'relevant/files/**' \
  --write-output /tmp/oracle-clodex-${TOPIC}.md
```

After Oracle: map all three positions, synthesize, present to user.

---

## Common Issues

| Problem | Solution |
|---------|----------|
| GOCACHE permission denied | Add `GOCACHE=/tmp/go-build-cache` to prompt |
| Agent test hangs | Scope test commands: `-run`, `-short`, `-timeout=60s` |
| Output file empty | Check `~/.codex/sessions/` for transcript |
| Agent over-engineers | Add "keep it minimal" to constraints |
| Agent reformats code | Add "do not reformat unchanged code" |
| Agent touches wrong files | List files explicitly in constraints |
| Two agents conflict | Check file overlap before dispatching |
| Agent commits despite "don't" | Use `workspace-write` sandbox, always `git status` after |

## Codex CLI Quick Reference

| Flag | Purpose |
|------|---------|
| `-C <DIR>` | Working directory (required) |
| `-s <MODE>` | `read-only`, `workspace-write`, `danger-full-access` |
| `-o <FILE>` | Save agent's final message |
| `-m <MODEL>` | Override model |
| `-i <FILE>` | Attach image (repeatable) |
| `--add-dir <DIR>` | Write access to additional directories |
| `--full-auto` | Shortcut for `-s workspace-write` |

**Resume**: `codex exec resume --last "follow-up"` or `codex exec resume <SESSION_ID> "follow-up"`
