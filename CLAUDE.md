# Clavain

> See `AGENTS.md` for full development guide.

## Overview

General-purpose engineering discipline plugin for Claude Code — 34 skills, 16 agents, 24 commands, 3 hooks, 3 MCP servers.

## Quick Commands

```bash
# Test locally
claude --plugin-dir /root/projects/Clavain

# Validate structure
ls skills/*/SKILL.md | wc -l          # Should be 34
ls agents/{review,research,workflow}/*.md | wc -l  # Should be 16
ls commands/*.md | wc -l              # Should be 24
bash -n hooks/lib.sh                   # Syntax check
bash -n hooks/session-start.sh         # Syntax check
bash -n hooks/agent-mail-register.sh   # Syntax check
bash -n hooks/dotfiles-sync.sh         # Syntax check
bash -n hooks/autopilot.sh             # Syntax check
python3 -c "import json; json.load(open('.claude-plugin/plugin.json'))"  # Manifest check
```

## Design Decisions (Do Not Re-Ask)

- Namespace: `clavain:` (not superpowers, not compound-engineering)
- General-purpose only — no Rails, Ruby gems, Every.to, Figma, Xcode, browser-automation
- 6 core review agents (fd-architecture, fd-safety, fd-correctness, fd-quality, fd-user-product, fd-performance) — each auto-detects language
- SessionStart hook injects `using-clavain` skill content via `additionalContext` JSON
- 3-layer routing: Stage → Domain → Language
- Trunk-based development — no branches/worktrees skills
- `docs-sp-reference/` is historical archive from source plugins — don't modify
- **Always publish after pushing** — use `/interpub:release <version>` or `scripts/bump-version.sh <version>` to bump plugin.json + marketplace.json atomically, commit, and push
