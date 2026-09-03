---
name: interserve-engine
description: Internal engine for /clavain:interserve — dispatches tasks to Codex CLI agents with debate triggers and Oracle escalation.
version: 0.5.0
user-invocable: false
---

<!-- compact: SKILL-compact.md — if it exists in this directory, load it instead of following the full instructions below. The compact version contains the same dispatch protocol in a single file. For debate mode, Oracle escalation, or CLI reference, read the references/ directory. -->

# Interserve — Codex Dispatch

Claude acts as orchestrator — planning, dispatching, verifying, committing. Works for single tasks (megaprompt) and multi-task parallel execution (delegation).

## When to Use / Not Use

**Use:** Well-scoped implementation (bug fixes, features, tests, refactoring) with clear files + success criteria.
**Skip:** Interactive user input mid-execution; deep cross-file architectural tasks (use Claude subagents); code review standalone (use interpeer); tasks where scope is unclear (research first).

## Prerequisites

```bash
command -v codex              # Codex CLI installed
[ -f ~/.codex/config.toml ]  # Config exists
git rev-parse --git-dir       # Inside git repo
```
If Codex unavailable, fall back to `clavain:subagent-driven-development`.

## Critical: Always Use dispatch.sh

**NEVER call `codex` directly.** Common wrong forms:
- `codex --approval-mode full-auto` — flag doesn't exist, correct: `codex exec --full-auto`
- `codex --file task.md` — no `--file` flag, use dispatch.sh `--prompt-file`
- Bare `codex "prompt"` — opens interactive mode, always `codex exec "prompt"`

See `references/cli-reference.md` for full flag reference.

## Executor class (Sylveste-d3m phase 1 — shadow wiring)

Every interserve dispatch goes through `--to auto --class <class>` so executor routing sees it:

- `interserve-fast` — read-only, administrative, exploration, verification, quick reviews (the tasks you would send with `--tier fast`)
- `interserve-deep` — implementation, complex reasoning, debates, generative work (`--tier deep`)

Both classes are deliberately UNMAPPED in `config/routing.yaml` (`executor_routing.classes`), so they fall through to `default: [codex]` and behavior is unchanged. What changes: each dispatch appends a row to `~/.clavain/executor-routing-shadow.jsonl` (class, mode, would-route, chosen backend, prompt file). That corpus is the phase-2 parity eval's input; a class is mapped to a cheaper backend only after its eval passes (doctrine: `config/routing.yaml` header). Do not map these classes by hand.

## Step 0: Resolve dispatch.sh

`$CLAUDE_PLUGIN_ROOT` is not exported to Bash. Find the path:
```bash
DISPATCH=$(find ~/.claude/plugins/cache -path '*/clavain/*/scripts/dispatch.sh' 2>/dev/null | head -1)
[ -z "$DISPATCH" ] && DISPATCH=$(find ~/projects/Clavain -name dispatch.sh -path '*/scripts/*' 2>/dev/null | head -1)
```

## Model Tiers

`--tier fast|deep` resolves from `config/routing.yaml` (dispatch section):

| Tier | Model | Use for |
|------|-------|---------|
| fast | `gpt-5.3-codex-spark` | Read-only exploration, verification, quick reviews |
| deep | `gpt-5.3-codex` | Implementation, complex reasoning, debates |

For x-high: set `CLAVAIN_DISPATCH_PROFILE=interserve` when invoking — then fast→`gpt-5.3-codex-spark-xhigh`, deep→`gpt-5.3-codex-xhigh`. `--tier` and `-m` are mutually exclusive. Missing `routing.yaml` degrades gracefully.

## Backend Selection (`--to`)

`dispatch.sh --to <codex|kimi>` picks the dispatch backend. **Codex is the default** — existing invocations are unchanged.

| Backend | Command built | Use for |
|---------|---------------|---------|
| `codex` (default) | `codex exec -s <sandbox> -C <dir> -o <file> "prompt"` | Primary implementation/exploration — full sandbox, JSONL statusline, verdict pipeline |
| `kimi` | `kimi [-m alias] -p "prompt"` | Second opinions from a different model family (Kimi k3 / kimi-for-coding), cross-checking a Codex result, or when Codex is rate-limited |

Kimi specifics:
- **Never** use bare interactive `kimi` or `kimi "prompt"` for dispatch — non-interactive mode is `kimi -p "prompt"` (dispatch.sh builds this for you). Like Codex, there is **no `--file` flag** — use dispatch.sh `--prompt-file`, which inlines the file into `-p`.
- Do **not** add `--auto` or `--yolo` to prompt mode — kimi v0.29 rejects both (`Cannot combine --prompt with --auto`). `kimi -p` is already fully non-interactive.
- Tiers map to kimi model aliases instead of `routing.yaml`: fast→`kimi-code/kimi-for-coding`, deep→`kimi-code/k3`. If the alias isn't defined in `~/.kimi-code/config.toml`, dispatch.sh warns and falls back to the config's `default_model`.
- Codex-only options don't translate: `-s/--sandbox`, `-i/--image`, and codex passthrough flags are dropped with a warning. `-C` is applied via `cd`, `-o` by teeing stdout. No JSONL statusline updates on the kimi path.
- Prereqs for kimi: `command -v kimi` and `~/.kimi-code/config.toml` (dispatch.sh preflights the binary and fails fast if missing).

Example — second opinion on a Codex-produced diff:
```bash
bash "$DISPATCH" --to kimi --tier deep \
  --prompt-file "$REVIEW_TASK" \
  -C "$PROJECT_DIR" \
  -o "/tmp/kimi-review-$(date +%s).md"
```

## Steerable Sessions (`--via zaka`)

`dispatch.sh --via zaka` trades the one-shot headless exec for a **steerable tmux session** driven by zaka: dispatch = `zaka spawn` + `zaka steer <session> <prompt>`. It prints the session name and returns immediately — no verdict sidecars, no output file, no waiting. Use it for long-running or exploratory work where you want to watch, steer mid-task, or kill; use the default one-shot exec for fire-and-forget tasks with a verdict.

- Without `--to`, the adapter defaults to `claude-code` (zaka's most capable adapter — resume support, richest steering). `--to codex` / `--to kimi` / `--to claude-code` map to the same-named zaka adapters (`zaka agents` lists what's installed).
- `-s`, `-i`, `-o`, `--name`, and codex passthrough flags don't apply to an interactive session — dropped with a warning. `-C` becomes `zaka spawn --workdir`, `-m` becomes `--model`.
- After dispatch, drive the session yourself: `zaka steer <session> "..."`, `tmux attach -t <session>`, `zaka kill <session>`. Prereqs: `command -v zaka` and `command -v tmux` (preflighted).

```bash
bash "$DISPATCH" --via zaka --to kimi -C "$PROJECT_DIR" "Long-running refactor — I'll steer as you go"
```

## Dispatch Routing

| Situation | Mode |
|-----------|------|
| Single task | Megaprompt |
| 2+ independent tasks | Parallel delegation |
| Sequential dependent tasks | Ordered delegation |
| Complex decision before implementing | Debate first |

---

## Megaprompt Mode (Single Task)

**Announce:** "Dispatching to Codex agent..."

### Step 1: Write Prompt File

```markdown
Fix the timeout bug in the auth handler.

Files: internal/auth/handler.go, internal/auth/middleware.go

Change timeout from 5s to 30s in handler.go and add retry with exponential backoff.

Build: go build ./internal/auth/...
Test: go test ./internal/auth/... -run TestLogin -short -timeout=60s

When done, report:
VERDICT: CLEAN | NEEDS_ATTENTION [reason]
FILES_CHANGED: [list]
```

Save to `/tmp/codex-task-$(date +%s).md`. **CRITICAL — Scope test commands**: use `-run TestPattern`, `-short`, `-timeout=60s`. NEVER `go test ./... -v`.

### Step 2: Dispatch

```bash
CLAVAIN_DISPATCH_PROFILE=interserve bash "$DISPATCH" \
  --prompt-file "$TASK_FILE" \
  -C "$PROJECT_DIR" \
  -o "/tmp/codex-result-$(date +%s).md" \
  -s workspace-write \
  --to auto --class interserve-deep \
  --tier deep
```
Use `timeout: 600000` on the Bash tool call.

### Step 3: Read Verdict

```bash
cat "/tmp/codex-result-*.md.verdict"
```
- `STATUS: pass` → report success
- `STATUS: warn` + `NEEDS_ATTENTION` → retry once with tighter prompt
- `STATUS: error` or no `.verdict` → read full output; fall back to Split mode or direct edit

Read full output (override verdict) for: first dispatch in new session, critical paths (auth/billing/data), warn/fail status.

### Step 4: Handle Failure (max 1 retry)

Write tighter follow-up prompt with error context → re-dispatch once. If still failing: offer Split mode, direct edit, or skip.

---

## Parallel Delegation Mode (Multiple Tasks)

### Step 1: Classify Tasks

| Classification | Executor |
|---------------|----------|
| Independent implementation (clear files + tests) | Codex agent |
| Exploratory/research | Claude subagent |
| Architecture-sensitive | Claude subagent |
| Sequential dependency | Codex (ordered) |

Present classification table → **AskUserQuestion**: Approve / Edit / Cancel.

### Step 2: Check File Overlap

If two tasks might modify the same file: combine into one prompt, or dispatch sequentially.

### Step 3: Write Prompt Files

One prompt file per task (same format as megaprompt Step 1).

### Step 4: Dispatch in Parallel

Launch all Bash calls **in a single message**. Set `timeout: 600000` on each.

```bash
CLAVAIN_DISPATCH_PROFILE=interserve bash "$DISPATCH" \
  --prompt-file /tmp/task1.md \
  -C "$PROJECT_DIR" \
  --name fix-auth -o /tmp/codex-{name}.md \
  -s workspace-write \
  --to auto --class interserve-deep \
  --tier deep
```

### Step 5: Verify and Land

For each agent: read output → build → run scoped tests → review diff → proportionality check. Use `clavain:landing-a-change` to commit.

---

## References

| Topic | File |
|-------|------|
| Debate mode | `references/debate-mode.md` |
| Oracle escalation | `references/oracle-escalation.md` |
| CLI flags | `references/cli-reference.md` |
| Common issues | `references/troubleshooting.md` |
| Split mode fallback | `references/split-mode.md` |
