# Clavain

> See `AGENTS.md` for full development guide.

## Overview

General-purpose engineering discipline plugin for Claude Code — 34 skills, 26 agents, 24 commands, 3 hooks, 3 MCP servers.

## Quick Commands

```bash
# Test locally
claude --plugin-dir /root/projects/Clavain

# Validate structure
ls skills/*/SKILL.md | wc -l          # Should be 34
ls agents/{review,research,workflow}/*.md | wc -l  # Should be 24
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
- Language-specific reviewers: Go, Python, TypeScript, Shell, Rust (no Ruby/Rails)
- SessionStart hook injects `using-clavain` skill content via `additionalContext` JSON
- 3-layer routing: Stage → Domain → Language
- Trunk-based development — no branches/worktrees skills
- `docs-sp-reference/` is historical archive from source plugins — don't modify
- **Always publish after pushing** — after every `git push`, run: `claude plugin marketplace update interagency-marketplace && claude plugin update clavain@interagency-marketplace` (bump version in plugin.json first if needed)
