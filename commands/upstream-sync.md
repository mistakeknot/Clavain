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

## Automated Pipeline

This command integrates with the GitHub Actions daily check:

1. **Daily Action** (`upstream-check.yml`) runs `scripts/upstream-check.sh`, opens/updates GitHub issues labeled `upstream-sync`
2. **Session start hook** warns when `docs/upstream-versions.json` is stale (>7 days)
3. **This command** picks up open issues and applies changes

## Steps

### If GitHub issues exist (preferred path)

1. Check for open upstream-sync issues:
   ```bash
   gh issue list --repo mistakeknot/Clavain --label upstream-sync --state open --json number,title,body
   ```
2. For each issue, read the checklist and affected skills
3. For each affected skill:
   - Fetch the upstream repo's README/CHANGELOG via `gh api`
   - Identify what changed (new flags, renamed commands, new MCP tools)
   - Edit the skill's `SKILL.md` to reflect the change
4. After all skills updated, update the baseline:
   ```bash
   bash scripts/upstream-check.sh --update
   ```
5. Commit changes to `docs/upstream-versions.json` and affected skills
6. Close the GitHub issue with a summary of what was updated

### If no GitHub issues (manual fallback)

1. Run the check script directly:
   ```bash
   bash scripts/upstream-check.sh
   ```
2. If changes detected, follow the `clavain:upstream-sync` skill process:
   - Identify breaking changes from changelogs
   - Generate upgrade checklist
   - Present to user for approval
   - Apply updates and record sync

## Quick Reference

| Tool | GitHub Repo | Clavain Skill |
|------|-------------|---------------|
| Beads | `steveyegge/beads` | `beads-workflow` |
| Oracle | `steipete/oracle` | `interpeer`, `prompterpeer`, `winterpeer`, `splinterpeer` |
| MCP Agent Mail | `Dicklesworthstone/mcp_agent_mail` | `agent-mail-coordination` |
| superpowers | `obra/superpowers` | multiple |
| superpowers-lab | `obra/superpowers-lab` | `using-tmux`, `slack-messaging`, `mcp-cli`, `finding-duplicate-functions` |
| superpowers-dev | `obra/superpowers-developing-for-claude-code` | `developing-claude-code-plugins`, `working-with-claude-code` |
| compound-engineering | `EveryInc/compound-engineering-plugin` | multiple |
