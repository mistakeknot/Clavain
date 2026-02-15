# Clavain

> See `AGENTS.md` for full development guide.

## Overview

Recursively self-improving multi-agent rig — brainstorm to ship. 23 skills, 4 agents, 38 commands, 12 hooks, 1 MCP server. Companions: `interphase` (phase tracking, gates, discovery), `interline` (statusline renderer), `interflux` (multi-agent review + research engine), `interpath` (product artifact generation), `interwatch` (doc freshness monitoring), `interlock` (multi-agent coordination), `interslack` (Slack integration), `interform` (design patterns), `intercraft` (agent-native architecture), `interdev` (developer tooling).

## Quick Commands

```bash
# Test locally
claude --plugin-dir /root/projects/Interverse/hub/clavain

# Validate structure
ls skills/*/SKILL.md | wc -l          # Should be 23
ls agents/{review,workflow}/*.md | wc -l  # Should be 4
ls commands/*.md | wc -l              # Should be 38
bash -n hooks/lib.sh                   # Syntax check
bash -n hooks/session-start.sh         # Syntax check
bash -n hooks/dotfiles-sync.sh         # Syntax check
bash -n hooks/auto-compound.sh         # Syntax check
bash -n hooks/auto-drift-check.sh      # Syntax check
bash -n hooks/lib-signals.sh           # Syntax check
bash -n hooks/session-handoff.sh       # Syntax check
bash -n hooks/auto-publish.sh          # Syntax check
bash -n hooks/bead-agent-bind.sh       # Syntax check
bash -n hooks/catalog-reminder.sh      # Syntax check
bash -n hooks/clodex-audit.sh          # Syntax check
bash -n hooks/sprint-scan.sh           # Syntax check (utility, not a hook binding)
bash -n hooks/lib-sprint.sh            # Syntax check (sprint state library)
bash -n hooks/lib-discovery.sh         # Syntax check (shim → interphase)
bash -n hooks/lib-gates.sh             # Syntax check (shim → interphase)
bash -n hooks/lib-interspect.sh        # Syntax check (interspect shared library)
bash -n hooks/interspect-evidence.sh   # Syntax check (interspect evidence hook)
bash -n hooks/interspect-session.sh    # Syntax check (interspect session start)
bash -n hooks/interspect-session-end.sh # Syntax check (interspect session end)
bash -n scripts/clodex-toggle.sh       # Syntax check
python3 -c "import json; json.load(open('.claude-plugin/plugin.json'))"  # Manifest check
```

## Design Decisions (Do Not Re-Ask)

- Namespace: `clavain:` (not superpowers, not compound-engineering)
- General-purpose only — no Rails, Ruby gems, Every.to, Figma, Xcode, browser-automation
- 7 core review agents live in interflux companion (fd-architecture, fd-safety, fd-correctness, fd-quality, fd-user-product, fd-performance, fd-game-design)
- SessionStart hook injects `using-clavain` skill content via `additionalContext` JSON
- 3-layer routing: Stage → Domain → Concern
- Trunk-based development — no branches/worktrees skills
- `docs-sp-reference/` is historical archive from source plugins — don't modify
- **Always publish after pushing** — use `/interpub:release <version>` or `scripts/bump-version.sh <version>` to bump plugin.json + marketplace.json atomically, commit, and push
