---
name: upstream-sync
description: Use when checking for updates from upstream tool repos (beads, oracle, superpowers, compound-engineering) or when the /clavain:upstream-sync command is invoked
---

# Upstream Sync

## Overview

Clavain bundles knowledge from several upstream tools. This skill tracks their releases and surfaces changes that affect Clavain's skills, commands, and documentation.

**Core principle:** Check upstream periodically, surface breaking changes, update affected skills.

## Upstream Repos

| Tool | Repo | Clavain Skills Affected |
|------|------|------------------------|
| Beads | `steveyegge/beads` | `interphase` companion plugin |
| Oracle | `steipete/oracle` | `interpeer`, `prompterpeer`, `winterpeer`, `splinterpeer` |
| superpowers | `obra/superpowers` | Multiple (founding source) |
| superpowers-lab | `obra/superpowers-lab` | `using-tmux-for-interactive-commands`, `slack-messaging`, `mcp-cli`, `finding-duplicate-functions` |
| superpowers-dev | `obra/superpowers-developing-for-claude-code` | `developing-claude-code-plugins`, `working-with-claude-code` |
| compound-engineering | `EveryInc/compound-engineering-plugin` | Multiple (founding source) |

## Automated Pipeline

Upstream sync runs in three layers — background data collection, session-start notification, and on-demand remediation.

### Layer 1: Daily GitHub Action

A GitHub Actions workflow (`.github/workflows/upstream-check.yml`) runs daily at 08:00 UTC:

1. Executes `scripts/upstream-check.sh --json` against all 7 upstream repos
2. Compares current releases/commits to the baseline in `docs/upstream-versions.json`
3. If changes detected: opens a GitHub issue (label `upstream-sync`) with per-repo checklists, or comments on existing open issue
4. If no changes: exits silently

**No manual action needed.** Issues appear automatically.

### Layer 2: Session-Start Warning

The `hooks/session-start.sh` hook checks the age of `docs/upstream-versions.json` on every session start. If the file is older than 7 days, it injects a warning:

> **Upstream sync stale** (N days since last check). Run `/clavain:upstream-sync` to check for updates.

This catches cases where the GitHub Action hasn't run (e.g., repo not pushed, Action disabled).

### Layer 3: `/clavain:upstream-sync` Command

The command integrates with the pipeline. See `commands/upstream-sync.md` for the full workflow.

**Preferred path** (GitHub issues exist):
1. Fetch open `upstream-sync` issues via `gh issue list`
2. For each issue, read the checklist and affected skills
3. Fetch upstream changelogs to understand what changed
4. Edit affected Clavain skills to reflect changes
5. Update baseline: `bash scripts/upstream-check.sh --update`
6. Commit changes and close the issue

### Layer 4: Human Decision Gate (upstream-sync PRs)

Two PR workflows enforce meaningful adaptation decisions:

1. `.github/workflows/upstream-impact.yml` posts impact summaries (commit/file churn + mapped impact)
2. `.github/workflows/upstream-decision-gate.yml` blocks merge until decision record is complete

Required decision record per PR:

- Path: `docs/upstream-decisions/pr-<PR_NUMBER>.md`
- Template: `docs/templates/upstream-decision-record.md`
- Gate criteria:
  - `Gate: approved`
  - no `TBD` placeholders
  - explicit per-upstream decisions (`adopt-now`, `defer`, `ignore`)
  - explicit base-workflow intervention decisions when applicable

**Manual fallback** (no issues):
1. Run `bash scripts/upstream-check.sh` directly
2. If changes detected, follow the remediation process below

## Manual Remediation Process

When applying upstream changes (whether from an issue checklist or manual check):

### Identify Breaking Changes

For each repo with new activity, check:

1. **CLI changes** — new commands, renamed flags, removed options
2. **MCP tool changes** — new tools, changed parameters, removed tools
3. **Configuration changes** — new env vars, changed defaults, new config files
4. **Conceptual changes** — new features that Clavain's skills should document

```bash
# Check changelogs
gh api repos/{owner}/{repo}/contents/CHANGELOG.md --jq '.content' | base64 -d | head -100

# Check recent README changes
gh api "repos/{owner}/{repo}/commits?path=README.md&per_page=3" \
  --jq '.[] | .sha[:7] + " " + (.commit.message | split("\n")[0])'
```

### Apply Updates

For each breaking change:
1. Read the relevant Clavain skill file
2. Make the minimal edit to reflect the upstream change
3. Verify no phantom references introduced (flags/tools that no longer exist)

### Update Baseline

After all skills are updated:

```bash
bash scripts/upstream-check.sh --update
```

This writes the current release/commit for all repos to `docs/upstream-versions.json`.

## Baseline File

`docs/upstream-versions.json` stores the last-synced state:

```json
{
  "steveyegge/beads": {
    "synced_release": "v0.49.4",
    "synced_commit": "eb1049b",
    "checked_at": "2026-02-06T20:26:55Z"
  }
}
```

Fields: `synced_release` (latest tag or `"none"`), `synced_commit` (short SHA of HEAD), `checked_at` (ISO timestamp).

## When Manual Sync is Needed

- **Session-start warning fires** — baseline is stale, run the command
- **Tool misbehaves** — upstream may have changed something Clavain's docs don't reflect
- **User reports stale docs** — specific tool's skill may be out of date
- **Before major Clavain releases** — ensure all bundled knowledge is current

## Red Flags

- **Skill documents a flag that no longer exists** — user gets confusing errors
- **MCP tool parameters changed** — function calls fail silently or with cryptic errors
- **New feature not documented** — users miss capabilities
- **Upstream renamed a concept** — Clavain uses old terminology

## Integration

**Pairs with:**
- `interphase` companion plugin — Primary consumer of beads upstream changes
- `interpeer`, `prompterpeer`, `winterpeer`, `splinterpeer` — Primary consumers of oracle upstream changes
- `developing-claude-code-plugins` — Upstream plugin patterns may evolve
