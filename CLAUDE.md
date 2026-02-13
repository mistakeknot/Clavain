# Clavain

> See `AGENTS.md` for full development guide.

## Overview

General-purpose engineering discipline plugin for Claude Code — 29 skills, 17 agents, 37 commands, 5 hooks, 2 MCP servers. Companion: `interphase` (phase tracking, gates, discovery).

## Quick Commands

```bash
# Test locally
claude --plugin-dir /root/projects/Clavain

# Validate structure
ls skills/*/SKILL.md | wc -l          # Should be 29
ls agents/{review,research,workflow}/*.md | wc -l  # Should be 17
ls commands/*.md | wc -l              # Should be 37
bash -n hooks/lib.sh                   # Syntax check
bash -n hooks/session-start.sh         # Syntax check
bash -n hooks/dotfiles-sync.sh         # Syntax check
bash -n hooks/auto-compound.sh         # Syntax check
bash -n hooks/session-handoff.sh       # Syntax check
bash -n hooks/lib-discovery.sh         # Syntax check (shim → interphase)
bash -n hooks/lib-gates.sh             # Syntax check (shim → interphase)
python3 -c "import json; json.load(open('.claude-plugin/plugin.json'))"  # Manifest check
```

## Design Decisions (Do Not Re-Ask)

- Namespace: `clavain:` (not superpowers, not compound-engineering)
- General-purpose only — no Rails, Ruby gems, Every.to, Figma, Xcode, browser-automation
- 7 core review agents (fd-architecture, fd-safety, fd-correctness, fd-quality, fd-user-product, fd-performance, fd-game-design) — each auto-detects language
- SessionStart hook injects `using-clavain` skill content via `additionalContext` JSON
- 3-layer routing: Stage → Domain → Concern
- Trunk-based development — no branches/worktrees skills
- `docs-sp-reference/` is historical archive from source plugins — don't modify
- **Always publish after pushing** — use `/interpub:release <version>` or `scripts/bump-version.sh <version>` to bump plugin.json + marketplace.json atomically, commit, and push
