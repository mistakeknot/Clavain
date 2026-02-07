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

Print the current mode status and toggle it:

### If codex-first mode was OFF (or first invocation):

```
Codex-first mode: ON

All code changes will be dispatched to Codex agents.
Claude's role: read, plan, prompt, dispatch, verify, commit.

Use /clodex (or /codex-first) again to toggle off.
```

Then follow the **Codex-First Behavioral Contract** below for the rest of the session.

### If codex-first mode was already ON:

```
Codex-first mode: OFF

Claude will make code changes directly using Edit/Write tools.
Normal execution mode restored.
```

Stop following the behavioral contract.

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
- Dispatch via `clavain:codex-first-dispatch` skill for all code changes
- Verify results (build, test, diff review)
- Commit verified changes (git operations are Claude's responsibility)

### Dispatch Workflow

For every code change (even trivial ones):

```
1. UNDERSTAND — Read relevant code (Grep, Glob, Read, Explore agents)
2. PLAN      — Design the change, identify files, success criteria
3. PROMPT    — Write a detailed Codex prompt to scratchpad
4. DISPATCH  — Use clavain:codex-first-dispatch skill
5. VERIFY    — Read output, build, test, diff review
6. RETRY     — If failed: tighten prompt, re-dispatch (max 2 retries)
7. LAND      — git add, commit (on user request)
```

### Dispatch Granularity
- Single small edit -> single Codex agent
- Multiple independent edits -> parallel Codex agents (multiple dispatch calls in one message)
- Sequential dependent edits -> ordered Codex agents (dispatch after prior verified)

## CLAUDE.md Auto-Detection

If the project's CLAUDE.md contains `codex-first: true`, this mode activates automatically at session start without needing to invoke this command. The `/codex-first` command can still toggle it off.
