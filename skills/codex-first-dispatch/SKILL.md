---
name: codex-first-dispatch
description: Streamlined single-task Codex dispatch for codex-first mode. Lighter than interclode:delegate — skips multi-task planning and file overlap checks.
---

# Codex-First Dispatch

Streamlined single-task dispatch to a Codex agent. This is the execution primitive for codex-first mode — every code change, no matter how small, flows through here.

**Announce at start:** "Dispatching to Codex agent..."

## Prerequisites

1. Codex CLI installed: `which codex`
2. Interclode dispatch script available: find it at the interclode plugin's `scripts/dispatch.sh`
3. Project directory has a `.git` root

If Codex is unavailable, tell the user and ask if they want to fall back to direct editing.

## Dispatch Modes

Choose the mode based on how much context Claude already has:

| Mode | When to use | Agents dispatched |
|------|------------|-------------------|
| **Full** | Claude has little/no context on the code area | EXPLORE → IMPLEMENT → VERIFY |
| **Standard** | Claude already read the relevant code | IMPLEMENT → VERIFY |
| **Minimal** | Trivial change + Claude already verified similar code this session | IMPLEMENT only (Claude verifies) |

**Default to Full** for the first task in a code area. **Drop to Standard** when Claude has already explored the area (e.g., second task touching the same files). **Use Minimal** only for follow-up fixes where the pattern is established.

## Step 0: Resolve dispatch.sh

Find the interclode dispatch script. Check in order:
1. `~/.claude/plugins/cache/interagency-marketplace/interclode/*/scripts/dispatch.sh`
2. `/root/projects/interclode/scripts/dispatch.sh` (local dev)

Store the resolved path as `$DISPATCH`.

## Step 1: EXPLORE (Full mode only)

**Goal:** Get a structured summary of the code area so Claude can write a precise prompt without reading raw source.

Write an explore prompt to the scratchpad:

```markdown
## Task
Analyze the following code area and produce a structured summary.

## Target
- File(s): [paths Claude knows or suspects]
- Function/type: [name if known]
- Area: [description if name unknown, e.g., "the overlay rendering code in the TUI"]

## Report Format
Produce a summary with these sections:
1. **Location**: Exact file:line for the target function/type
2. **Signature**: Full function/method signature
3. **Imports**: Only the imports used by this code (package paths)
4. **Package**: The Go/Python/TS package name
5. **Logic summary**: 3-5 bullet points on what the code does
6. **Callers**: Where this function is called from (file:line, max 5)
7. **Test coverage**: Existing test file + test function names, or "none"
8. **Adjacent context**: Nearby types/functions that the implementation interacts with

## Constraints
- Do NOT modify any files
- Keep the report under 80 lines
- Use exact line numbers
- If GOCACHE permission errors occur, use: GOCACHE=/tmp/go-build-cache
```

Dispatch with `-s read-only`:

```bash
bash "$DISPATCH" \
  --prompt-file "$EXPLORE_PROMPT" \
  -C "$PROJECT_DIR" \
  -o "$SCRATCHPAD/codex-explore-$(date +%s).md" \
  -s read-only \
  --inject-docs
```

Read the output summary. Use it to inform Steps 2-3 instead of reading source files directly.

**Claude tokens saved:** ~5-10K per task (avoids reading raw source + imports + tests + callers).

## Step 2: Write IMPLEMENT Prompt

Write the Codex prompt to the scratchpad directory. Use this template:

```markdown
## Task
[Clear description of what to change]

## Relevant Files
- `path/to/file.go` — [what this file contains, what to change]
- `path/to/other.go` — [if applicable]

## Success Criteria
- [Build command] succeeds (e.g., `go build ./internal/foo/...`)
- [Test command] passes (e.g., `go test ./internal/foo/... -v`)
- [Behavioral check if applicable]

## Constraints
- Only modify files listed in "Relevant Files" unless absolutely necessary
- Do not reformat, realign, or adjust whitespace in code you didn't functionally change
- Do not add comments, docstrings, or type annotations to unchanged code
- Do not refactor or rename anything not directly related to the task
- Keep the fix minimal — prefer 5 clean lines over 50 "proper" lines
- Do NOT commit or push any changes
- If GOCACHE permission errors occur, use: GOCACHE=/tmp/go-build-cache
```

Save to: `$SCRATCHPAD/codex-prompt-$(date +%s).md`

## Step 3: Dispatch IMPLEMENT

```bash
bash "$DISPATCH" \
  --prompt-file "$PROMPT_FILE" \
  -C "$PROJECT_DIR" \
  -o "$SCRATCHPAD/codex-output-$(date +%s).md" \
  -s workspace-write \
  --inject-docs
```

Use `timeout: 600000` (10 minutes) on the Bash tool call.

For **parallel independent changes**, issue multiple Bash tool calls in a single message, each dispatching a separate Codex agent with its own prompt file and output file.

## Step 4: VERIFY

### Full/Standard mode — Dispatch a VERIFY agent

Write a verify prompt:

```markdown
## Task
Verify the changes made by a previous Codex agent. Run ALL checks and report results.

## Checks
1. Build: `[build command, e.g., go build ./internal/foo/...]`
2. Tests: `[test command, e.g., go test ./internal/foo/... -v]`
3. Diff review: `git diff -- [relevant files]`
4. Proportionality: `git diff --stat` (flag unexpected files)
5. Lint: `[lint command if available]`

## Report Format
```
BUILD:  PASS | FAIL (error excerpt if fail)
TESTS:  PASS | FAIL (failing test names + error if fail)
DIFF:   [1-3 sentence summary of what changed]
FILES:  [list of files modified, with +/- line counts]
ISSUES: [any concerns — unexpected files, excessive changes, style problems]
VERDICT: CLEAN | NEEDS_ATTENTION
```

## Constraints
- Do NOT modify any files
- Do NOT commit or push
- If GOCACHE permission errors occur, use: GOCACHE=/tmp/go-build-cache
```

Dispatch with `-s read-only`:

```bash
bash "$DISPATCH" \
  --prompt-file "$VERIFY_PROMPT" \
  -C "$PROJECT_DIR" \
  -o "$SCRATCHPAD/codex-verify-$(date +%s).md" \
  -s read-only \
  --inject-docs
```

Read the VERIFY report. If `VERDICT: CLEAN`, report success to user. If `NEEDS_ATTENTION`, Claude reads the issues and decides whether to retry or escalate.

**Claude tokens saved:** ~3-5K per task (avoids reading test output + diff + stat).

### Minimal mode — Claude verifies directly

Run build, test, and diff commands via Bash tool calls. Review output. This is the fallback when dispatching a VERIFY agent isn't worth the latency.

## Step 5: Handle Result

### On Success
Report to the user:
```
Codex agent completed successfully.
Changes: [brief summary from VERIFY report or Claude's review]
Build: PASS
Tests: PASS
```

The changes are now in the working tree, ready for Claude to commit when the user asks.

### On Failure (max 2 retries)
1. Read the agent output (or VERIFY report) to understand what went wrong
2. Tighten the prompt — add more context, be more specific about the fix
3. Re-dispatch with the improved prompt (skip EXPLORE on retry — context is established)
4. If still failing after 2 retries, escalate to the user:
   ```
   Codex agent failed after 2 attempts. Issue: [description]
   Options:
   1. I'll make this change directly (exit codex-first for this edit)
   2. Provide more context for another attempt
   3. Skip this change
   ```

## Notes

- This skill is for **single-task dispatch**. For multi-task parallel execution from a plan, use `clavain:codex-delegation` which wraps `interclode:delegate`.
- Every invocation is independent — no session state between dispatches.
- Claude orchestrates; Codex reads, writes, and verifies. Claude's role is judgment — choosing what to build, crafting prompts, deciding if results are acceptable.
- EXPLORE and VERIFY agents use `-s read-only` sandbox — they cannot modify files.
- Total agents per Full dispatch: 3 (explore + implement + verify). Typical wall time: ~2 minutes.
