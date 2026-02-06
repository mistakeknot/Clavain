# Clavain

> See `AGENTS.md` for full development guide.

## Overview

General-purpose engineering discipline plugin for Claude Code — 31 skills, 23 agents, 22 commands, 2 hooks, 2 MCP servers.

## Quick Commands

```bash
# Test locally
claude --plugin-dir /root/projects/Clavain

# Validate structure
ls skills/*/SKILL.md | wc -l          # Should be 31
ls agents/{review,research,workflow}/*.md | wc -l  # Should be 23
ls commands/*.md | wc -l              # Should be 22
bash -n hooks/session-start.sh        # Syntax check
python3 -c "import json; json.load(open('.claude-plugin/plugin.json'))"  # Manifest check
```

## Design Decisions (Do Not Re-Ask)

- Namespace: `clavain:` (not superpowers, not compound-engineering)
- General-purpose only — no Rails, Ruby gems, Every.to, Figma, Xcode, browser-automation
- Language-specific reviewers: Go, Python, TypeScript, Shell (no Ruby/Rails)
- SessionStart hook injects `using-clavain` skill content via `additionalContext` JSON
- 3-layer routing: Stage → Domain → Language
- Trunk-based development — no branches/worktrees skills
- `docs-sp-reference/` is historical archive from source plugins — don't modify
