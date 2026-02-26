# Clavain

> See `AGENTS.md` for full development guide.

## Overview

Autonomous software agency — orchestrates the full development lifecycle from problem discovery through shipped code. Layer 2 (OS) in the Demarch stack: sits between Intercore (L1 kernel) and Autarch (L3 apps). 16 skills, 4 agents, 46 commands, 7 hooks, 1 MCP server. Key companions: `interflux` (multi-agent review + research), `interphase` (phase tracking, gates, discovery), `interspect` (profiler, evidence, routing), `interline` (statusline renderer).

## Quick Commands

```bash
# Test locally
claude --plugin-dir /home/mk/projects/Demarch/os/clavain

# Validate structure
ls skills/*/SKILL.md | wc -l          # Should be 16
ls agents/{review,workflow}/*.md | wc -l  # Should be 4
ls commands/*.md | wc -l              # Should be 46
for f in hooks/*.sh; do bash -n "$f" && echo "$(basename $f) OK"; done  # Syntax check all hooks
python3 -c "import json; json.load(open('.claude-plugin/plugin.json'))"  # Manifest check
python3 -c "import json; json.load(open('hooks/hooks.json'))"           # Hooks JSON check
```

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

For publishing a release, use `scripts/bump-version.sh <version>` (or `/interpub:release <version>` in Claude Code).
