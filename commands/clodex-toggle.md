---
name: clodex-toggle
description: Toggle clodex execution mode — source code changes go through Codex agents, non-code files remain directly editable
allowed-tools:
  - Bash
  - Read
  - Grep
  - Glob
---

# Clodex Mode Toggle

Toggle clodex execution mode for this session.

## When Invoked

### 1. Check Current State

```bash
PROJECT_DIR=$(pwd)
FLAG_FILE="$PROJECT_DIR/.claude/clodex-toggle.flag"
```

Check if `$FLAG_FILE` exists.

### 2. Toggle

**If clodex mode is OFF** (flag file does not exist):
```bash
mkdir -p "$PROJECT_DIR/.claude"
date -Iseconds > "$PROJECT_DIR/.claude/clodex-toggle.flag"
```

Tell the user:
> Clodex mode: **ON**
>
> - Edit/Write calls to **source code files** will be blocked by the PreToolUse hook
> - **Non-code files** (*.md, *.json, *.yaml, *.toml, *.txt, etc.) are still directly editable
> - **Temp files** (/tmp/*) are still writable (needed for dispatch prompts)
> - Read/Grep/Glob still work normally
> - Git operations are Claude's responsibility — do them directly
>
> To make source code changes, use the `/clodex` dispatch skill.
> Run `/clodex-toggle` again to toggle off.

**If clodex mode is ON** (flag file exists):
```bash
rm "$PROJECT_DIR/.claude/clodex-toggle.flag"
```

Tell the user:
> Clodex mode: **OFF**
>
> Direct file editing is restored. Edit/Write will work normally for all files.

### 3. Behavioral Contract Reminder (when turning ON)

After announcing the toggle, remind yourself of the clodex behavioral contract:

- **Plan**: Read code freely (Read/Grep/Glob). Identify what needs to change.
- **Prompt**: Write a task description file to `/tmp/codex-task-<name>.md`
- **Dispatch**: Use `/clodex` skill to send to Codex agents
- **Verify**: Read output, build, test, diff review
- **Bash**: Only for read-only commands (git status, test runs, build checks). File-modifying Bash should be dispatched through Codex.

**Exception**: Git operations (add, commit, push) are Claude's responsibility — do them directly.

## What Gets Blocked vs Allowed

| Target | Blocked? | Why |
|--------|----------|-----|
| `*.go`, `*.py`, `*.ts`, `*.rs`, etc. | Yes | Source code — dispatch through Codex |
| `*.md`, `*.json`, `*.yaml`, `*.toml` | No | Non-code — safe to edit directly |
| `/tmp/*` | No | Temp files needed for dispatch prompts |
| Dotfiles (`.gitignore`, `.env`, etc.) | No | Config — safe to edit directly |

## Hook Enforcement

The PreToolUse hook in `hooks/hooks.json` checks for the flag file at `$PROJECT_DIR/.claude/clodex-toggle.flag`. When the flag exists, Edit/Write/MultiEdit/NotebookEdit calls are checked against an allowlist:
- `/tmp/*` paths → allowed
- Non-code extensions (`.md`, `.json`, `.yaml`, `.yml`, `.toml`, `.txt`, `.csv`, `.xml`, `.html`, `.css`, `.svg`, `.lock`, `.cfg`, `.ini`, `.conf`, `.env`) → allowed
- Dotfiles → allowed
- Everything else → denied with dispatch instructions

## Notes

- The flag file is at `$PROJECT_DIR/.claude/clodex-toggle.flag` (not in plugin directory)
- The `.claude/` directory may already exist (Claude Code uses it for project settings)
- The flag file contains a timestamp for debugging (when was clodex mode enabled?)
