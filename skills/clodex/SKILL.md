---
name: clodex
description: Dispatch tasks to Codex CLI agents — single megaprompt for one task, parallel delegation for many. Includes behavioral contract for codex-first mode, structured debate triggers, and Oracle escalation.
version: 0.3.0
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
- Code review as a standalone task (use interpeer instead — flux-drive uses dispatch infrastructure directly for review agents)
- Tasks where you're unsure what needs to change (research first, then dispatch)

## Prerequisites

1. Codex CLI installed: `which codex`
2. Codex config exists: `~/.codex/config.toml`
3. Project directory has a `.git` root

If Codex is unavailable, suggest falling back to `clavain:subagent-driven-development`.

## Dispatch Routing

| Situation | Mode | Why |
|-----------|------|-----|
| Single task | **Megaprompt** | One agent explores + implements + verifies in one shot |
| 2+ independent tasks | **Parallel delegation** | Multiple agents run concurrently |
| Sequential dependent tasks | **Ordered delegation** | Agent N starts after agent N-1 verified |
| Complex decision before implementing | **Debate first** | Get Codex's independent analysis before coding |

## Step 0: Resolve Paths

`$CLAUDE_PLUGIN_ROOT` is only available during skill loading — it's NOT exported to the Bash environment. Find absolute paths:
```bash
DISPATCH=$(find ~/.claude/plugins/cache -path '*/clavain/*/scripts/dispatch.sh' 2>/dev/null | head -1)
[ -z "$DISPATCH" ] && DISPATCH=$(find ~/projects/Clavain -name dispatch.sh -path '*/scripts/*' 2>/dev/null | head -1)

TEMPLATE=$(find ~/.claude/plugins/cache -path '*/clavain/*/skills/clodex/templates/megaprompt.md' 2>/dev/null | head -1)
[ -z "$TEMPLATE" ] && TEMPLATE=$(find ~/projects/Clavain -path '*/skills/clodex/templates/megaprompt.md' 2>/dev/null | head -1)
```

---

## Megaprompt Mode (Single Task)

**Announce:** "Dispatching to Codex agent..."

### Step 1: Write Task Description

Write a short task description file with section headers. Only include sections relevant to the task:

```markdown
GOAL:
Fix the timeout bug in auth handler

EXPLORE_TARGETS:
internal/auth/handler.go, internal/auth/middleware.go

IMPLEMENT:
- Change timeout from 5s to 30s in handler.go
- Add retry with exponential backoff

BUILD_CMD:
go build ./internal/auth/...

TEST_CMD:
go test ./internal/auth/... -run TestLogin -short -timeout=60s
```

Save to: `/tmp/codex-task-$(date +%s).md`

**CRITICAL — Scope test commands**: Use `-run TestPattern`, `-short`, `-timeout=60s`. NEVER use broad `go test ./... -v`.

### Step 2: Dispatch

dispatch.sh assembles the full prompt from the template + task description:

```bash
bash "$DISPATCH" \
  --template "$TEMPLATE" \
  --prompt-file "$TASK_FILE" \
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
2. Write tighter follow-up task description with error context
3. Re-dispatch once
4. If still failing, offer options:
   - Try Split mode (separate explore/implement/verify agents)
   - Make the change directly
   - Skip this change

---

## Parallel Delegation Mode (Multiple Tasks)

### Step 1: Classify Tasks

| Classification | Executor | Rationale |
|---------------|----------|-----------|
| Independent implementation | Codex agent | Well-scoped, clear files, clear tests |
| Exploratory/research | Claude subagent | Needs deep reasoning |
| Architecture-sensitive | Claude subagent | Needs cross-file understanding |
| Sequential dependency | Codex (ordered) | Must wait for prior task |

Present the classification to the user and get approval before dispatching.

### Step 2: Check for File Overlap

If two tasks might modify the same file: **(a) combine them** into one agent prompt, or **(b) dispatch sequentially**.

### Step 3: Write Task Descriptions

For the parallel-task template, resolve its path:
```bash
PAR_TEMPLATE=$(find ~/.claude/plugins/cache -path '*/clavain/*/skills/clodex/templates/parallel-task.md' 2>/dev/null | head -1)
[ -z "$PAR_TEMPLATE" ] && PAR_TEMPLATE=$(find ~/projects/Clavain -path '*/skills/clodex/templates/parallel-task.md' 2>/dev/null | head -1)
```

Each task description uses these sections:
- `PROJECT:` — project name and brief description
- `TASK:` — detailed description of what to change
- `FILES:` — specific file paths with descriptions
- `CRITERIA:` — additional success criteria beyond build/test
- `BUILD_CMD:` — build command
- `TEST_CMD:` — scoped test command

### Step 4: Dispatch in Parallel

Launch all Bash calls **in a single message** (multiple tool calls). Set `timeout: 600000` on each.

```bash
bash "$DISPATCH" \
  --template "$PAR_TEMPLATE" \
  --prompt-file /tmp/task1.md \
  --inject-docs -C "$PROJECT_DIR" \
  --name fix-auth -o /tmp/codex-{name}.md \
  -s workspace-write
```

### Step 5: Verify and Land

For EACH completed agent: read output, build, run scoped tests, review diff, proportionality check. Use `clavain:landing-a-change` to commit.

---

## References

| Topic | File |
|-------|------|
| Codex-first behavioral contract | `references/behavioral-contract.md` |
| Debate mode | `references/debate-mode.md` |
| Oracle escalation | `references/oracle-escalation.md` |
| CLI flags quick reference | `references/cli-reference.md` |
| Common issues | `references/troubleshooting.md` |
| Split mode fallback | `references/split-mode.md` |
