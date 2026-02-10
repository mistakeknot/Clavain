---
module: System
date: 2026-02-10
problem_type: workflow_issue
component: tooling
symptoms:
  - "claude doctor warns about large MCP tools context (>25,000 tokens)"
  - "Same MCP tools appear twice with different prefixes (plugin_clavain_mcp-agent-mail and mcp-agent-mail)"
  - "~12K extra tokens consumed per session for duplicate tool registration"
root_cause: config_error
resolution_type: config_change
severity: medium
tags: [mcp, context-budget, duplicate-registration, settings-hygiene, claude-doctor]
---

# Troubleshooting: Duplicate MCP Server Registration Wastes Context Budget

## Problem
An MCP server registered both in a plugin's `plugin.json` AND in the user's global `~/.claude/settings.json` creates two separate tool registrations — doubling the context budget cost with identical tools under different name prefixes.

## Environment
- Module: System (Claude Code MCP configuration)
- Claude Code Version: 2.1.38
- Affected Component: MCP tool context budget
- Date: 2026-02-10

## Symptoms
- `claude doctor` reports: "Large MCP tools context (~26,179 tokens > 25,000)"
- Tool list shows both `plugin_clavain_mcp-agent-mail` (26 tools, ~11,845 tokens) and `mcp-agent-mail` (26 tools, ~11,689 tokens)
- Both point to the same server (`http://127.0.0.1:8765/mcp`)
- `allowedTools` in settings has entries for both `mcp__plugin_clavain_mcp-agent-mail__*` and `mcp__mcp-agent-mail__*`

## What Didn't Work

**Direct solution:** The problem was identified and fixed on the first attempt by tracing both registrations to their sources.

## Solution

**Removed the duplicate from global settings:**

The bare `mcp-agent-mail` was registered in `~/.claude/settings.json` (historical — added before the Clavain plugin existed). The Clavain plugin's `plugin.json` also registers it as `plugin_clavain_mcp-agent-mail`.

**Changes to `~/.claude/settings.json`:**
```json
// REMOVED from mcpServers:
"mcp-agent-mail": {
  "headers": { "Authorization": "Bearer ..." },
  "type": "http",
  "url": "http://127.0.0.1:8765/mcp/"
}

// REMOVED from allowedTools:
"mcp__mcp-agent-mail__*"
```

**Kept:** The plugin registration in Clavain's `plugin.json` (canonical — travels with the plugin for all users).

**Diagnostic approach:**
```bash
# Find all MCP registrations
grep -r "mcp-agent-mail" ~/.claude/settings.json
grep -r "mcp-agent-mail" /path/to/plugin/.claude-plugin/plugin.json

# Check for .mcp.json files that might add duplicates
find ~ -maxdepth 3 -name ".mcp.json" | xargs grep "mcp-agent-mail"
```

## Why This Works

1. **Root cause:** MCP servers can be registered at multiple levels — global settings, project `.mcp.json`, plugin manifests, and local plugin dirs. Claude Code loads ALL of them and creates separate tool namespaces for each. There's no deduplication by URL.

2. **The plugin registration is canonical** because it ships with the plugin — any user who installs Clavain gets the server automatically. The global settings registration was a leftover from before the plugin existed.

3. **Context budget impact:** Each MCP server's tools are serialized into the system prompt. 26 tools with descriptions = ~12K tokens. Duplicating that wastes 6% of a 200K context window on identical tools.

## Prevention

- **Before adding MCP servers to global settings:** Check if any installed plugin already registers the same server (`grep -r "server-name" ~/.claude/plugins/cache/`)
- **Run `claude doctor` periodically** to catch context budget warnings
- **When migrating to plugins:** Remove manual MCP registrations from `settings.json` after the plugin handles it
- **Rule of thumb:** MCP servers that belong to a plugin should ONLY be registered in `plugin.json`, never duplicated in user settings

## Related Issues

- See also: [settings-heredoc-permission-bloat-20260210.md](./settings-heredoc-permission-bloat-20260210.md) — another settings hygiene issue discovered in the same session
