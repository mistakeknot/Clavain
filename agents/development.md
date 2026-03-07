# Clavain — Development Workflow

## Release Workflow

- Run `scripts/bump-version.sh <version>` (or `/interpub:release <version>` in Claude Code) for any released changes.
- The bump updates these files atomically:
  - `.claude-plugin/plugin.json`
  - `infra/marketplace/.claude-plugin/marketplace.json`
  - other discovered versioned artifacts
- The command commits and pushes both plugin and marketplace repos.
- For routine updates, use patch bumps (`0.6.x -> 0.6.x+1`).

## Validation Checklist

When making changes, verify:

- [ ] Skill `name` in frontmatter matches directory name
- [ ] All `clavain:` references point to existing skills/commands (no phantom references)
- [ ] Agent `description` includes `<example>` blocks with `<commentary>`
- [ ] Command `name` in frontmatter matches filename (minus `.md`)
- [ ] `hooks/hooks.json` is valid JSON
- [ ] All hook scripts pass `bash -n` syntax check
- [ ] No references to dropped namespaces (`superpowers:`, `compound-engineering:`)
- [ ] No references to dropped components (Rails, Ruby, Every.to, Figma, Xcode)
- [ ] Routing table in `using-clavain/SKILL.md` is consistent with actual components

Quick validation:
```bash
# Count components
echo "Skills: $(ls skills/*/SKILL.md | wc -l)"      # Should be 16
echo "Agents: $(ls agents/{review,workflow}/*.md | wc -l)"  # Should be 4
echo "Commands: $(ls commands/*.md | wc -l)"        # Should be 45

# Check for phantom namespace references
grep -r 'superpowers:' skills/ agents/ commands/ hooks/ || echo "Clean"
grep -r 'compound-engineering:' skills/ agents/ commands/ hooks/ || echo "Clean"

# Validate JSON
python3 -c "import json; json.load(open('.claude-plugin/plugin.json')); print('Manifest OK')"
python3 -c "import json; json.load(open('hooks/hooks.json')); print('Hooks OK')"

# Syntax check all hook scripts
for f in hooks/*.sh; do bash -n "$f" && echo "$(basename $f) OK"; done

# Run structural tests
uv run -m pytest tests/structural/ -v
```

## Known Constraints

- **No build step** — pure markdown/JSON/bash plugin, nothing to compile (except optional `cmd/clavain-cli/` Go binary)
- **3-tier test suite** — structural (pytest), shell (bats-core), smoke (Claude Code subagents). Run via `tests/run-tests.sh`
- **General-purpose only** — no domain-specific components (Rails, Ruby gems, Every.to, Figma, Xcode, browser-automation)
- **Trunk-based** — no branch/worktree skills; commit directly to `main`

## Bulk Audit to Bead Creation

When creating beads from review findings, **verify each finding before creating a bead**: check `git log` for recent fixes, `bd list` for duplicates, and read current code for staleness.

## Upstream Tracking

6 upstreams tracked: superpowers, superpowers-lab, superpowers-dev, compound-engineering, beads, oracle. Two systems keep them in sync:

- **Check:** `upstream-check.yml` (daily cron) + `scripts/upstream-check.sh` (local). State in `docs/upstream-versions.json`.
- **Sync:** `sync.yml` (weekly cron) + `upstreams.json` (file mappings). Work dir: `.upstream-work/` (gitignored).

```bash
bash scripts/upstream-check.sh        # Local check (no file changes)
gh workflow run sync.yml               # Trigger auto-merge (creates PR)
```
