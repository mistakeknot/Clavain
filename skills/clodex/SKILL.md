---
name: clodex
description: Dispatch tasks to Codex CLI agents — single megaprompt for one task, parallel delegation for many. Includes structured debate triggers and Oracle escalation.
version: 0.4.0
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

## Critical: Always Use dispatch.sh

**NEVER call `codex` directly.** Always use `dispatch.sh` which wraps `codex exec` with correct flags. Common mistakes when calling codex directly:
- `codex --approval-mode full-auto` — **wrong**, this flag doesn't exist. The correct form is `codex exec --full-auto`
- `codex --file task.md` — **wrong**, no `--file` flag. Use dispatch.sh `--prompt-file`
- Bare `codex "prompt"` — **wrong**, opens interactive mode. Always `codex exec "prompt"`

See `references/cli-reference.md` for the full flag reference and `references/troubleshooting.md` for common errors.

## Model Tiers

dispatch.sh supports `--tier fast|deep` to resolve model names from `config/dispatch/tiers.yaml`:

| Tier | Model | Use for |
|------|-------|---------|
| **fast** | `gpt-5.3-codex-spark` | Read-only exploration, verification, quick reviews |
| **deep** | `gpt-5.3-codex` | Implementation, complex reasoning, debates |

- `--tier` and `-m` are mutually exclusive — `-m` is the escape hatch for one-off overrides
- If `tiers.yaml` is missing, `--tier` degrades gracefully (warning, uses config.toml default)
- Change model names in one place (`tiers.yaml`) when new models ship

## Dispatch Routing

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

### Step 1: Write the Prompt

Write a concise prompt file with the goal, relevant files, and build/test commands. Write it as natural language — Codex handles exploration, implementation, and verification on its own.

```markdown
Fix the timeout bug in the auth handler.

Files: internal/auth/handler.go, internal/auth/middleware.go

Change the timeout from 5s to 30s in handler.go and add retry with exponential backoff.

Build: go build ./internal/auth/...
Test: go test ./internal/auth/... -run TestLogin -short -timeout=60s

When done, report:
VERDICT: CLEAN | NEEDS_ATTENTION [reason]
FILES_CHANGED: [list]
```

Save to: `/tmp/codex-task-$(date +%s).md`

**CRITICAL — Scope test commands**: Use `-run TestPattern`, `-short`, `-timeout=60s`. NEVER use broad `go test ./... -v`.

### Step 2: Dispatch

```bash
bash "$DISPATCH" \
  --prompt-file "$TASK_FILE" \
  -C "$PROJECT_DIR" \
  -o "/tmp/codex-result-$(date +%s).md" \
  -s workspace-write \
  --tier deep
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
2. Write tighter follow-up prompt with error context
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

Present the classification table, then use **AskUserQuestion** to get approval:

```
AskUserQuestion:
  question: "Dispatch N tasks to Codex agents as classified above?"
  options:
    - label: "Approve"
      description: "Dispatch all tasks as classified"
    - label: "Edit"
      description: "Reclassify or adjust tasks first"
    - label: "Cancel"
      description: "Don't dispatch"
```

### Step 2: Check for File Overlap

If two tasks might modify the same file: **(a) combine them** into one agent prompt, or **(b) dispatch sequentially**.

### Step 3: Write Prompt Files

Write one prompt file per task (same format as megaprompt Step 1). Each should include the goal, relevant files, build/test commands, and the verdict suffix.

### Step 4: Dispatch in Parallel

Launch all Bash calls **in a single message** (multiple tool calls). Set `timeout: 600000` on each.

```bash
bash "$DISPATCH" \
  --prompt-file /tmp/task1.md \
  -C "$PROJECT_DIR" \
  --name fix-auth -o /tmp/codex-{name}.md \
  -s workspace-write \
  --tier deep
```

### Step 5: Verify and Land

For EACH completed agent: read output, build, run scoped tests, review diff, proportionality check. Use `clavain:landing-a-change` to commit.

---

## References

| Topic | File |
|-------|------|
| Debate mode | `references/debate-mode.md` |
| Oracle escalation | `references/oracle-escalation.md` |
| CLI flags quick reference | `references/cli-reference.md` |
| Common issues | `references/troubleshooting.md` |
| Split mode fallback | `references/split-mode.md` |
