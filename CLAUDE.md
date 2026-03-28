# Clavain

> See `AGENTS.md` for full development guide.

## Overview

Autonomous software agency — orchestrates the full development lifecycle from problem discovery through shipped code. Layer 2 (OS) in the Demarch stack: sits between Intercore (L1 kernel) and Autarch (L3 apps). 17 skills, 6 agents, 51 commands, 10 hooks, 0 MCP servers. Key companions: `interflux` (multi-agent review + research), `interphase` (phase tracking, gates, discovery), `interspect` (profiler, evidence, routing), `interline` (statusline renderer).

## Quick Commands

```bash
# Test locally
claude --plugin-dir /home/mk/projects/Demarch/os/Clavain

# Validate structure
ls skills/*/SKILL.md | wc -l          # Should be 17
ls agents/{review,workflow}/*.md | wc -l  # Should be 6
ls commands/*.md | wc -l              # Should be 51 (47 registered + 1 unregistered bead-sweep)
for f in hooks/*.sh; do bash -n "$f" && echo "$(basename $f) OK"; done  # Syntax check all hooks
python3 -c "import json; json.load(open('.claude-plugin/plugin.json'))"  # Manifest check
python3 -c "import json; json.load(open('hooks/hooks.json'))"           # Hooks JSON check
```

## Work Tracking

All work tracking goes through beads (`bd create`). Never create TODO files with status frontmatter, pending-beads lists, or markdown checklists for tracking work. If beads is unavailable, note items in a single `BLOCKED.md` and convert when it recovers.

## Design Decisions (Do Not Re-Ask)

- Namespace: `clavain:` (not superpowers, not compound-engineering)
- General-purpose only — no Rails, Ruby gems, Every.to, Figma, Xcode, browser-automation
- 7 core review agents live in interflux companion (fd-architecture, fd-safety, fd-correctness, fd-quality, fd-user-product, fd-performance, fd-game-design)
- SessionStart hook injects `using-clavain` skill content via `additionalContext` JSON
- 3-layer routing: Stage → Domain → Concern
- Trunk-based development — no branches/worktrees skills
- `docs-sp-reference/` is historical archive from source plugins — don't modify
- **Always publish after pushing** — documented in `AGENTS.md` under **Release workflow**.

### Release workflow

Publish with `ic publish --patch` (or `ic publish <version>` for exact). The `/interpub:release` command and `scripts/bump-version.sh` both delegate to `ic publish`.
