---
name: codex-first-dispatch
description: Streamlined single-task Codex dispatch for codex-first mode. Lighter than interclode:delegate — skips multi-task planning and file overlap checks.
---

# Codex-First Dispatch

Single-agent dispatch for codex-first mode. One Codex agent explores, implements, and verifies in a single invocation. Claude's role: craft the megaprompt, dispatch once, read the verdict, commit.

**Announce at start:** "Dispatching to Codex agent..."

## Prerequisites

1. Codex CLI installed: `which codex`
2. Interclode dispatch script available: find it at the interclode plugin's `scripts/dispatch.sh`
3. Project directory has a `.git` root

If Codex is unavailable, tell the user and ask if they want to fall back to direct editing.

## Dispatch Modes

| Mode | When | Claude tokens | Latency |
|------|------|--------------|---------|
| **Megaprompt** (default) | All tasks | ~6K | ~60-90s |
| **Split** (fallback) | Megaprompt failed or task is unusually complex | ~12K | ~120s |

**Always start with Megaprompt.** Only fall back to Split if the megaprompt agent fails and you need finer-grained control over exploration vs implementation.

## Step 0: Resolve dispatch.sh

Find the interclode dispatch script. Check in order:
1. `~/.claude/plugins/cache/interagency-marketplace/interclode/*/scripts/dispatch.sh`
2. `/root/projects/interclode/scripts/dispatch.sh` (local dev)

Store the resolved path as `$DISPATCH`.

---

## Megaprompt Mode (Default)

### Step 1: Craft the Megaprompt

Write a single prompt to the scratchpad that tells the Codex agent to explore, implement, AND verify — all in one session. Use this template:

```markdown
## Goal
[1-2 sentence description of the change, from the user's request]

## Phase 1: Explore
Before making any changes, investigate the code area:
- Read [suspected files/functions/areas]
- Identify the exact file(s) and line(s) that need to change
- Check for existing tests covering this area
- Note the package name, imports, and any callers of modified code
- Print a brief exploration summary before proceeding to implementation

## Phase 2: Implement
Make the change:
- [Specific description of what to change]
- [File hints if Claude has any, e.g., "likely in internal/foo/"]
- [Design notes if relevant, e.g., "use table-driven tests"]

## Phase 3: Verify
After implementing, run ALL of these and report results:
1. Build: `[build command, e.g., go build ./internal/foo/...]`
2. Tests: `[SCOPED test command — see below]`
3. Diff: `git diff --stat` (ensure only expected files changed)
4. If build or tests fail: fix the issue and re-verify (up to 2 self-retries)

**CRITICAL — Scope test commands**: Use `-run TestPattern` to target tests related to the change, `-short` to skip integration tests, and `-timeout=60s` to prevent hangs. Example: `go test ./internal/tui/... -run TestGurgeh -v -short -timeout=60s`. NEVER use broad `go test ./... -v` — integration tests that need live services will hang and consume the entire timeout.

## Final Report
At the end, print a structured verdict:
```
EXPLORATION: [1-2 sentence summary of what you found]
CHANGES: [list files modified/created with brief description]
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

**Key principles for the megaprompt:**
- Give the agent *freedom to explore* — don't over-specify file paths if you're not sure. Say "likely in internal/foo/" not "exactly at internal/foo/bar.go:42"
- Include build AND **scoped** test commands — the agent should self-verify. Always use `-run`, `-short`, `-timeout` to avoid integration test hangs
- Ask for a structured verdict so Claude can parse the result quickly
- Include self-retry: "if tests fail, fix and re-verify (up to 2 retries)"

Save to: `$SCRATCHPAD/codex-mega-$(date +%s).md`

### Step 2: Dispatch

```bash
bash "$DISPATCH" \
  --prompt-file "$PROMPT_FILE" \
  -C "$PROJECT_DIR" \
  -o "$SCRATCHPAD/codex-result-$(date +%s).md" \
  -s workspace-write \
  --inject-docs
```

Use `timeout: 600000` (10 minutes) on the Bash tool call.

For **parallel independent changes**, issue multiple Bash tool calls in a single message, each dispatching a separate megaprompt agent.

### Step 3: Read Verdict

Read the output file. Look for the structured verdict block:
- `VERDICT: CLEAN` → report success to user
- `VERDICT: NEEDS_ATTENTION` → read the reason, decide whether to retry or escalate
- No verdict / garbled output → fall back to Split mode

**Claude does NOT need to independently re-run build/test/diff if the verdict is CLEAN.** Trust the agent's self-verification unless you have reason to doubt it (e.g., past experience with this code area being tricky, or the agent's output looks suspicious).

**When to independently verify anyway:**
- First dispatch in a new session (establish trust)
- Changes to critical paths (auth, data integrity, billing)
- Agent reports CLEAN but the diff summary mentions unexpected files

### Step 4: Handle Result

**On CLEAN verdict:**
```
Codex agent completed successfully.
Exploration: [from report]
Changes: [from report]
Build: PASS | Tests: PASS
```

Changes are in the working tree, ready for Claude to commit on user request.

**On NEEDS_ATTENTION or failure (max 1 retry as megaprompt):**
1. Read the failure details from the agent's output
2. Write a tighter follow-up megaprompt with the error context
3. Re-dispatch once
4. If still failing, fall back to Split mode or escalate:
   ```
   Codex agent failed. Issue: [description]
   Options:
   1. Try Split mode (separate explore/implement/verify agents)
   2. I'll make this change directly (exit codex-first for this edit)
   3. Skip this change
   ```

---

## Split Mode (Fallback)

Use when megaprompt fails or for tasks requiring separate exploration and implementation control.

### Split Step 1: EXPLORE

Dispatch a read-only agent to investigate:

```bash
bash "$DISPATCH" \
  --prompt-file "$EXPLORE_PROMPT" \
  -C "$PROJECT_DIR" \
  -o "$SCRATCHPAD/codex-explore-$(date +%s).md" \
  -s read-only \
  --inject-docs
```

The explore prompt asks for: location, signature, imports, package, logic summary, callers, test coverage, adjacent context. Same as the megaprompt's Phase 1 but as a standalone agent.

### Split Step 2: IMPLEMENT

Write a focused implementation prompt using the explore output, dispatch with `-s workspace-write`.

### Split Step 3: VERIFY

Dispatch a read-only agent to run build, test, diff, and report a structured verdict.

Each step uses its own dispatch call. Claude reads summaries between steps rather than raw source.

---

## Notes

- **Megaprompt is the default.** It uses ~40-60K Codex tokens but only ~6K Claude tokens per task.
- **Self-retry is built into the megaprompt.** The agent fixes its own build/test failures before reporting. Claude only sees the final verdict.
- **Parallel dispatch works.** Multiple independent megaprompt agents can run simultaneously in a single Bash tool call message.
- For multi-task parallel execution from a plan, use `clavain:codex-delegation` which wraps `interclode:delegate`.
- Claude's only essential jobs: craft the prompt, dispatch, read the verdict, decide if it's acceptable, commit.
