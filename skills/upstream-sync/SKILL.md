---
name: upstream-sync
description: Use when checking for updates from upstream tool repos (beads, oracle, superpowers, compound-engineering) or when the /clavain:upstream-sync command is invoked
---

# Upstream Sync

Clavain bundles knowledge from upstream tools. This skill tracks their releases and updates affected skills.

## Upstream Repos

| Tool | Repo | Clavain Skills Affected |
|------|------|------------------------|
| Beads | `steveyegge/beads` | `interphase` companion plugin |
| Oracle | `steipete/oracle` | `interpeer`, `prompterpeer`, `winterpeer`, `splinterpeer` |
| superpowers | `obra/superpowers` | Multiple (founding source) |
| superpowers-lab | `obra/superpowers-lab` | `using-tmux-for-interactive-commands` |
| superpowers-dev | `obra/superpowers-developing-for-claude-code` | `developing-claude-code-plugins`, `working-with-claude-code` |
| compound-engineering | `EveryInc/compound-engineering-plugin` | Multiple (founding source) |

## Automated Pipeline

### Layer 1: Daily GitHub Action
`.github/workflows/upstream-check.yml` runs daily at 08:00 UTC — runs `scripts/upstream-check.sh --json`, compares against `docs/upstream-versions.json`, opens/updates a GitHub issue (label `upstream-sync`) if changes detected. No manual action needed.

### Layer 2: Session-Start Warning
`hooks/session-start.sh` checks age of `docs/upstream-versions.json` on every session. If >7 days old, injects: **"Upstream sync stale (N days). Run `/clavain:upstream-sync`."**

### Layer 3: `/clavain:upstream-sync` Command

**Preferred path** (issues exist):
1. `gh issue list` — fetch open `upstream-sync` issues
2. Read checklist and affected skills from each issue
3. Fetch upstream changelogs; edit affected skills
4. `bash scripts/upstream-check.sh --update` — update baseline
5. Commit changes, close issue

**Manual fallback** (no issues): `bash scripts/upstream-check.sh` directly, then remediate.

### Layer 4: Human Decision Gate

Two PR workflows:
- `.github/workflows/upstream-impact.yml` — posts impact summaries
- `.github/workflows/upstream-decision-gate.yml` — blocks merge until decision record complete

Required: `docs/upstream-decisions/pr-<PR_NUMBER>.md` (template at `docs/templates/upstream-decision-record.md`) with `Gate: approved`, no `TBD`, explicit per-upstream decisions (`adopt-now`/`defer`/`ignore`).

## Manual Remediation

For each repo with new activity, check:
1. **CLI changes** — new commands, renamed/removed flags
2. **MCP tool changes** — new tools, changed parameters, removed tools
3. **Config changes** — new env vars, changed defaults
4. **Conceptual changes** — new features to document

```bash
# Check changelog
gh api repos/{owner}/{repo}/contents/CHANGELOG.md --jq '.content' | base64 -d | head -100

# Check recent README commits
gh api "repos/{owner}/{repo}/commits?path=README.md&per_page=3" \
  --jq '.[] | .sha[:7] + " " + (.commit.message | split("\n")[0])'
```

For each breaking change: read the skill → make minimal edit → verify no phantom references (flags/tools that no longer exist).

After all edits: `bash scripts/upstream-check.sh --update`

## Baseline File

`docs/upstream-versions.json`:
```json
{
  "steveyegge/beads": {
    "synced_release": "v0.49.4",
    "synced_commit": "eb1049b",
    "checked_at": "2026-02-06T20:26:55Z"
  }
}
```

## When to Run Manually

- Session-start warning fires
- A tool misbehaves (upstream may have changed)
- User reports stale docs
- Before major Clavain releases

## Red Flags

- Skill documents a flag that no longer exists
- MCP tool parameters changed (silent failures)
- New upstream feature not documented
- Upstream renamed a concept (stale terminology)
