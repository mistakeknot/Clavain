---
name: upstream-sync
description: Use when checking for updates from upstream tool repos (beads, oracle, mcp_agent_mail, superpowers, compound-engineering) or when the /clavain:upstream-sync command is invoked
---

# Upstream Sync

## Overview

Clavain bundles knowledge from several upstream tools. This skill tracks their releases and surfaces changes that affect Clavain's skills, commands, and documentation.

**Core principle:** Check upstream periodically, surface breaking changes, update affected skills.

## Upstream Repos

| Tool | Repo | Clavain Skills Affected |
|------|------|------------------------|
| Beads | `steveyegge/beads` | `beads-workflow` |
| Oracle | `steipete/oracle` | `oracle-review` |
| MCP Agent Mail | `Dicklesworthstone/mcp_agent_mail` | `agent-mail-coordination` |
| superpowers | `obra/superpowers` | Multiple (founding source) |
| superpowers-lab | `obra/superpowers-lab` | `using-tmux-for-interactive-commands`, `slack-messaging`, `mcp-cli`, `finding-duplicate-functions` |
| superpowers-dev | `obra/superpowers-developing-for-claude-code` | `developing-claude-code-plugins`, `working-with-claude-code` |
| compound-engineering | `EveryInc/compound-engineering-plugin` | Multiple (founding source) |

## The Process

### Step 1: Check Latest Releases

For each upstream repo, check the latest release/tag and recent commits:

```bash
# Latest release
gh api repos/{owner}/{repo}/releases/latest --jq '.tag_name + " (" + .published_at + ")"' 2>/dev/null || echo "No releases"

# Recent commits (last 30 days)
gh api "repos/{owner}/{repo}/commits?since=$(date -d '30 days ago' -Iseconds)&per_page=5" \
  --jq '.[] | .sha[:7] + " " + (.commit.message | split("\n")[0])'
```

### Step 2: Identify Breaking Changes

For each repo with new activity, check:

1. **CLI changes** — new commands, renamed flags, removed options
2. **MCP tool changes** — new tools, changed parameters, removed tools
3. **Configuration changes** — new env vars, changed defaults, new config files
4. **Conceptual changes** — new features that Clavain's skills should document

**What to look for:**
```bash
# Check changelogs
gh api repos/{owner}/{repo}/contents/CHANGELOG.md --jq '.content' | base64 -d | head -100

# Check recent README changes
gh api "repos/{owner}/{repo}/commits?path=README.md&per_page=3" \
  --jq '.[] | .sha[:7] + " " + (.commit.message | split("\n")[0])'
```

### Step 3: Generate Upgrade Checklist

For each upstream change that affects Clavain, create an actionable item:

```markdown
## Upstream Changes Detected

### Beads (steveyegge/beads)
- **v1.2.0** (2026-02-01): Added `bd archive` command
  - [ ] Add `bd archive` to `beads-workflow` skill Essential Commands section
  - [ ] Check if memory compaction section needs update

### Oracle (steipete/oracle)
- **v0.9.0** (2026-01-28): Added `--search` flag for provider web search
  - [ ] Add `--search` to `oracle-review` skill flags table
  - [ ] Note: API mode only

### MCP Agent Mail (Dicklesworthstone/mcp_agent_mail)
- No changes since last sync
```

### Step 4: Apply Updates

For each checklist item:
1. Read the relevant Clavain skill file
2. Make the minimal edit to reflect the upstream change
3. Verify no phantom references introduced

### Step 5: Record Sync

After applying updates, record what was synced:

```bash
# Create or update sync record
cat > /root/projects/Clavain/docs/upstream-sync-log.md << 'EOF'
# Upstream Sync Log

## Latest Sync: YYYY-MM-DD

| Repo | Version Checked | Changes Applied |
|------|----------------|-----------------|
| beads | v1.2.0 | Added bd archive to beads-workflow |
| oracle | v0.9.0 | Added --search flag docs |
| mcp_agent_mail | v0.5.3 | No changes needed |
| superpowers | v4.2.0 | No changes (founding source) |
| compound-engineering | v2.30.0 | No changes (founding source) |
EOF
```

## When to Sync

- **Monthly**: Routine check for all upstreams
- **Before major Clavain releases**: Ensure all bundled knowledge is current
- **When a tool misbehaves**: Check if upstream changed something Clavain's docs don't reflect
- **When user reports stale docs**: Specific tool's docs may be out of date

## Red Flags

- **Skill documents a flag that no longer exists** — user gets confusing errors
- **MCP tool parameters changed** — function calls fail silently or with cryptic errors
- **New feature not documented** — users miss capabilities
- **Upstream renamed a concept** — Clavain uses old terminology

## Integration

**Pairs with:**
- `beads-workflow` — Primary consumer of beads upstream changes
- `oracle-review` — Primary consumer of oracle upstream changes
- `agent-mail-coordination` — Primary consumer of agent-mail upstream changes
- `developing-claude-code-plugins` — Upstream plugin patterns may evolve
