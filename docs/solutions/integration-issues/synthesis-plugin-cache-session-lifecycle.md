---
title: "Plugin Cache and Session Lifecycle Pitfalls"
category: integration-issues
tags: [plugin-cache, session-lifecycle, hooks, mcp, node-modules, symlink, agents]
date: 2026-03-19
synthesized_from:
  - integration-issues/stop-hooks-break-after-mid-session-publish-20260212.md
  - integration-issues/new-agents-not-available-until-restart-20260210.md
  - integration-issues/mcp-plugin-missing-node-modules-20260210.md
---

# Plugin Cache and Session Lifecycle Pitfalls

Claude Code's plugin system loads state at session start and does not fully refresh mid-session. Three recurring problems stem from this design: hooks break after publish, new agents are invisible, and MCP servers arrive without dependencies.

## Core Invariant

**Session-start state is immutable.** Agent registries, hook paths, and MCP tool lists are snapshots taken at session initialization. Any mid-session change to the plugin cache (publish, new agent files, npm install) is invisible to the running session.

## Problem 1: Stop Hooks Break After Mid-Session Publish

When `bump-version.sh` publishes a new version, Claude Code downloads it to a new cache directory and **deletes the old one**. But the running session still references the old path. Every stop hook fails with "No such file or directory" for the rest of the session.

**Fix:** Create compatibility symlinks from old version to new:
- `bump-version.sh` creates a symlink for the immediate predecessor (`0.4.48 -> 0.4.49`)
- `session-start.sh` replaces any older version directories with symlinks to current, bridging multi-hop gaps (e.g., a session loaded from 0.4.45 when current is 0.4.49)

**Emergency repair:** `ln -sf <new_version> ~/.claude/plugins/cache/interagency-marketplace/clavain/<old_version>`

## Problem 2: New Agents Not Available Until Restart

Agent `.md` files created mid-session exist on disk but are not in the Task tool's `subagent_type` list. The registry is a static snapshot from session start.

**Workaround:** Use `subagent_type: general-purpose` and paste the agent's full system prompt into the task prompt.

**Proper fix:** Commit, push, publish, restart session. Then the new agents appear.

## Problem 3: MCP Plugins Missing node_modules

The plugin marketplace downloads source/dist files but does **not** run `npm install`. Node.js MCP servers fail with `ERR_MODULE_NOT_FOUND` on first start.

**Fix:** Use a bootstrap wrapper script (`scripts/start.sh`) that:
1. Checks for `node_modules/`, runs `npm install` if missing
2. Handles native module system deps (`libgif-dev` for canvas, etc.)
3. Sends all bootstrap output to stderr (protects MCP JSON-RPC on stdout)
4. Uses `exec node` to replace the shell process for correct signal handling

Point `.mcp.json` at the wrapper script instead of `node dist/index.js`.

## Rules of Thumb

1. **Never test new agents in the session that created them.** Commit, publish, restart first.
2. **Always publish through `bump-version.sh`** which auto-creates symlinks for running sessions.
3. **For MCP plugins with Node.js deps**, always use a wrapper script entry point -- never assume `node_modules/` exists in cache.
4. **If hooks break mid-session**, create a manual symlink or restart. The errors are non-blocking but hooks silently stop running.
5. **Budget for the restart tax.** Plugin development requires frequent session restarts. Plan publish-restart cycles rather than trying to test in-session.
