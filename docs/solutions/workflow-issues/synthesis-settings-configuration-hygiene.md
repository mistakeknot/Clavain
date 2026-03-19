---
title: "Settings and Configuration Hygiene"
category: workflow-issues
tags: [settings-hygiene, heredoc, permissions, mcp, context-budget, disable-model-invocation, orchestration]
date: 2026-03-19
synthesized_from:
  - workflow-issues/settings-heredoc-permission-bloat-20260210.md
  - workflow-issues/duplicate-mcp-server-context-bloat-20260210.md
  - workflow-issues/disable-model-invocation-blocks-lfg-pipeline-clavain-20260211.md
---

# Settings and Configuration Hygiene

Three classes of configuration error silently degrade Claude Code sessions: permission bloat from heredocs, duplicate MCP registrations, and blanket flags that block orchestration.

## Problem 1: Heredoc Permission Bloat

When a user clicks "Allow" on a Bash tool call containing a heredoc, the **entire multi-line command** (including embedded file contents, plans, or prompts) is saved as a literal permission entry in `settings.local.json`. These entries never match future commands and can cause PreToolUse hook parse errors.

**Prevention (enforce in CLAUDE.md):**
- Never use heredocs in Bash tool calls. Write content with the Write tool, reference the file in Bash.
- Never use multi-line for/while loops. Use one-liners.
- Keep Bash commands short with recognizable prefixes so saved permissions work as wildcards.

**Cleanup:** Replace specific command entries with `command-prefix:*` wildcards (e.g., `Bash(npm:*)` instead of `Bash(npm install --no-fund --no-audit 2>&1 | tail -1)`). Remove any entries containing heredocs, shell fragments (`do`, `done`, `fi`), or paths that no longer exist.

## Problem 2: Duplicate MCP Server Registration

An MCP server registered in both a plugin's `plugin.json` AND the user's `~/.claude/settings.json` creates two tool registrations with different prefixes. This wastes ~12K tokens per session on duplicate tools.

**Detection:** `claude doctor` warns when MCP tools context exceeds 25K tokens. Check for tools appearing under both `plugin_<name>_<server>` and bare `<server>` prefixes.

**Fix:** Remove the duplicate from global settings. The plugin registration is canonical -- it ships with the plugin for all users. The global settings entry is typically a leftover from before the plugin existed.

**Rule:** MCP servers that belong to a plugin should ONLY be registered in `plugin.json`, never duplicated in user settings.

## Problem 3: Blanket disable-model-invocation Blocks Orchestration

The `disable-model-invocation: true` frontmatter flag prevents Claude's model from invoking a command via the Skill tool. When applied as a blanket default to all commands, orchestrator commands like `/lfg` that chain sub-commands via Skill tool calls are completely broken.

**Fix:** Evaluate per-command. Only use `disable-model-invocation: true` for commands with real side effects (deploy, delete, send message). Development workflow commands (brainstorm, plan, review) should default to `false`.

**Test:** If command A calls command B via Skill tool, verify B does not have the flag set.

## Configuration Audit Checklist

1. **`settings.local.json` size:** If > 50KB, review for heredoc bloat
2. **`claude doctor` warnings:** Run periodically to catch context budget issues
3. **Duplicate MCP servers:** `grep -r "server-name" ~/.claude/plugins/cache/` vs `~/.claude/settings.json`
4. **Orchestration chains:** After creating orchestrator commands, verify all sub-commands are model-invocable
5. **Permission entries:** Remove any containing embedded file contents, shell fragments, or dead paths
