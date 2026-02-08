---
name: codex-first
description: Toggle codex-first execution mode — all code changes go through Codex agents
allowed-tools:
  - Bash
  - Read
  - Grep
  - Glob
---

# Codex-First Mode Toggle

Toggle codex-first execution mode for this session.

## When Invoked

### 1. Check Current State

```bash
PROJECT_DIR=$(pwd)
FLAG_FILE="$PROJECT_DIR/.claude/autopilot.flag"
```

Check if `$FLAG_FILE` exists.

### 2. Toggle

**If codex-first mode is OFF** (flag file does not exist):
```bash
mkdir -p "$PROJECT_DIR/.claude"
date -Iseconds > "$PROJECT_DIR/.claude/autopilot.flag"
```

Tell the user:
> Codex-first mode: **ON**
>
> - Edit/Write/MultiEdit calls will be blocked by the PreToolUse hook and redirected to Codex agents
> - Read/Grep/Glob still work normally (fast, no delegation)
> - Bash is governed by behavioral contract: use it for read-only commands only
> - Non-code files (*.md, *.json, *.yaml) can still be edited directly
>
> To make code changes, follow the plan→prompt→dispatch→verify cycle.
> Run `/codex-first` (or `/clodex`) again to toggle off.

**If codex-first mode is ON** (flag file exists):
```bash
rm "$PROJECT_DIR/.claude/autopilot.flag"
```

Tell the user:
> Codex-first mode: **OFF**
>
> Direct file editing is restored. Edit/Write/MultiEdit will work normally.

### 3. Behavioral Contract Reminder (when turning ON)

After announcing the toggle, remind yourself of the codex-first behavioral contract:

- **Plan**: Read code freely (Read/Grep/Glob). Identify what needs to change.
- **Prompt**: Write a task description file to `/tmp/codex-task-<name>.md`
- **Dispatch**: dispatch.sh assembles full prompt from template + task description
- **Verify**: Read output, build, test, diff review, proportionality check
- **Bash**: Only for read-only commands (git status, test runs, build checks). Any file-modifying Bash commands should be dispatched through Codex.

**Exception**: Git operations (add, commit, push) are Claude's responsibility — do them directly.

## Codex-First Behavioral Contract

When codex-first mode is ON, follow these rules for the rest of the session:

### MUST NOT (code changes)
- Use `Edit` tool on source code files (*.go, *.py, *.ts, *.js, *.rs, *.java, *.rb, *.c, *.cpp, *.h, *.swift, *.kt, *.sh)
- Use `Write` tool to create source code files
- Use `NotebookEdit` on code cells
- Make code changes through Bash (sed, awk, echo >, cat <<EOF to source files)

### MUST (always allowed)
- Use `Read`, `Grep`, `Glob` freely — reading is always allowed
- Edit non-code files freely: *.md, *.json, *.yaml, *.yml, *.toml, *.txt, config files, documentation
- Plan implementation as detailed Codex prompts
- Dispatch via `clavain:clodex` skill for all code changes
- Verify results (build, test, diff review)
- Commit verified changes (git operations are Claude's responsibility)

### Dispatch Workflow

For every code change (even trivial ones):

```
1. UNDERSTAND — Read relevant code (Grep, Glob, Read, Explore agents)
2. PLAN      — Design the change, identify files, success criteria
3. PROMPT    — Write a detailed Codex prompt to scratchpad
4. DISPATCH  — Use clavain:clodex skill
5. VERIFY    — Read output, build, test, diff review
6. RETRY     — If failed: tighten prompt, re-dispatch (max 2 retries)
7. LAND      — git add, commit (on user request)
```

### Dispatch Granularity
- Single small edit -> single Codex agent
- Multiple independent edits -> parallel Codex agents (multiple dispatch calls in one message)
- Sequential dependent edits -> ordered Codex agents (dispatch after prior verified)

## Hook Enforcement

The PreToolUse hook in `hooks/hooks.json` checks for the flag file at `$PROJECT_DIR/.claude/autopilot.flag`. When the flag exists, Edit/Write/MultiEdit/NotebookEdit calls are denied with a message directing you to use the dispatch cycle. This enforces the behavioral contract at the tool level — you can't accidentally edit source files while codex-first mode is active.

## Notes

- The flag file is at `$PROJECT_DIR/.claude/autopilot.flag` (not in plugin directory)
- The `.claude/` directory may already exist (Claude Code uses it for project settings)
- The flag file contains a timestamp for debugging (when was codex-first enabled?)

## CLAUDE.md Auto-Detection

If the project's CLAUDE.md contains `codex-first: true`, this mode activates automatically at session start without needing to invoke this command. The `/codex-first` command can still toggle it off.
