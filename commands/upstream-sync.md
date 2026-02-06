---
name: upstream-sync
description: Check upstream repos (beads, oracle, agent-mail, superpowers, compound-engineering) for updates and generate upgrade checklist
allowed-tools:
  - Bash
  - Read
  - Edit
  - Write
  - Grep
  - Glob
  - WebFetch
  - Task
---

# Upstream Sync

Use the `clavain:upstream-sync` skill. Follow it exactly.

## Quick Reference

Upstream repos to check:

| Tool | GitHub Repo |
|------|-------------|
| Beads | `steveyegge/beads` |
| Oracle | `steipete/oracle` |
| MCP Agent Mail | `Dicklesworthstone/mcp_agent_mail` |
| superpowers | `obra/superpowers` |
| superpowers-lab | `obra/superpowers-lab` |
| superpowers-dev | `obra/superpowers-developing-for-claude-code` |
| compound-engineering | `EveryInc/compound-engineering-plugin` |

## Steps

1. Load the `clavain:upstream-sync` skill
2. Run Step 1: Check latest releases for all 7 repos (use parallel `gh api` calls)
3. Run Step 2: For repos with new activity, identify breaking changes
4. Run Step 3: Generate upgrade checklist as markdown
5. Present checklist to user for approval before making changes
6. If approved, apply updates (Step 4) and record sync (Step 5)
