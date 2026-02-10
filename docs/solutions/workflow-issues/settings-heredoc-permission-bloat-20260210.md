---
module: System
date: 2026-02-10
problem_type: workflow_issue
component: tooling
symptoms:
  - "settings.local.json contains massive multi-line permission entries"
  - "PreToolUse hook errors when parsing settings file"
  - "claude doctor may show warnings about invalid permission entries"
  - "Permission entries contain entire file contents or plan documents"
root_cause: config_error
resolution_type: config_change
severity: high
tags: [settings-hygiene, heredoc, permissions, bloat, pretooluse-hook]
---

# Troubleshooting: Settings Permission Bloat from Heredoc Bash Commands

## Problem
When Claude Code uses a heredoc or multi-line command in a Bash tool call and the user clicks "Allow", the **entire command text** — including inline file contents, plans, or prompts — is saved as a literal permission entry in `settings.local.json`. These entries never match again (they're too specific) and can cause hook errors.

## Environment
- Module: System (Claude Code permission system)
- Claude Code Version: 2.1.38
- Affected Component: `.claude/settings.local.json` permission entries
- Date: 2026-02-10

## Symptoms
- `settings.local.json` contains a single permission entry with hundreds of lines of embedded markdown/plan content
- PreToolUse:Read hook throws errors (likely struggling to parse the malformed JSON or oversized entries)
- Permission entries like `Bash(/root/projects/Clavain/docs/research/plan-behavioral-layer-implementation.md << 'ENDOFPLAN'\n# Behavioral Layer...` (~500 lines)
- One-off specific commands saved that will never match: `Bash(printf '{\"type\":...}')`

## What Didn't Work

**Direct solution:** The problem was identified and fixed by rewriting the settings file with clean wildcard-based permissions.

## Solution

**Replaced bloated entries with wildcard patterns:**

```json
// BEFORE (broken — 500+ line heredoc as permission entry):
"Bash(/root/projects/.../plan.md << 'ENDOFPLAN'\n# Behavioral Layer...ENDOFPLAN)"
"Bash(printf '{\"type\":\"tool_use\",...}')"
"Bash(npm install:*)"
"Bash(exec bash -c 'cd /root/projects/Clavain && pwd')"

// AFTER (clean wildcards):
"Bash(npm:*)"
"Bash(printf:*)"
"Bash(exec:*)"
"Bash(node:*)"
```

**Full cleanup process:**
1. Read `settings.local.json`
2. Identify entries that are specific commands (not wildcards)
3. Replace with `command-prefix:*` wildcard patterns
4. Remove entries containing heredocs, multi-line content, or paths that no longer exist
5. Write cleaned file

## Why This Works

1. **Root cause:** Claude Code's permission system saves the **exact command text** when users click "Allow". For simple commands like `git status`, this creates a useful wildcard pattern. But for heredocs, the entire multi-line content becomes a literal string that will never match a future command — it's dead weight.

2. **The PreToolUse hook error** occurred because the settings JSON parser had to process a permission array entry containing ~500 lines of embedded markdown with escaped characters, nested code blocks, and JSON-within-JSON. This likely exceeded parsing limits or caused malformed JSON.

3. **Wildcard patterns** like `Bash(npm:*)` match any npm command, which is what the user intended when they approved `npm install --no-fund --no-audit`. The specific command text is never needed.

## Prevention

**Rules for AI agents (enforce in CLAUDE.md):**
- **Never use heredocs in Bash tool calls.** Write content with Write tool first, then reference the file in Bash.
  - Bad: `Bash(cat << 'EOF' ... EOF > file.md)`
  - Good: `Write(file.md)` then `Bash(cat file.md)`
- **Never use multi-line for/while loops.** Each line becomes a separate invalid entry.
  - Bad: `for f in ...; do\n...\ndone`
  - Good: `for f in ...; do ...; done` (one-liner)
- **Never inline long prompts.** Write to temp file, reference in command.
- **Keep Bash commands short.** Every call should start with a recognizable prefix so the saved permission works as a wildcard.

**Periodic maintenance:**
- Review `settings.local.json` files for entries longer than ~100 characters
- Replace specific commands with `command-prefix:*` wildcards
- Remove entries for commands/paths that no longer exist
- Shell fragments (`do`, `done`, `fi`) in settings are always bugs — delete them

## Related Issues

- See also: [duplicate-mcp-server-context-bloat-20260210.md](./duplicate-mcp-server-context-bloat-20260210.md) — another settings hygiene issue discovered in the same session
