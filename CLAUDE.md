# Clavain

> See `AGENTS.md` for full development guide.

## Overview

Autonomous software agency — orchestrates the full development lifecycle from problem discovery through shipped code. Runs on Autarch TUI, backed by Intercore kernel (Layer 1) and Interspect profiler. 16 skills, 4 agents, 46 commands, 8 hooks, 1 MCP server. 32 companion plugins as drivers (Layer 3). Key companions: `interflux` (multi-agent review + research), `interphase` (phase tracking, gates, discovery), `interspect` (profiler, evidence, routing), `interlock` (multi-agent coordination), `interpeer` (cross-AI review), `intertest` (quality disciplines).

## Quick Commands

```bash
# Test locally
claude --plugin-dir /home/mk/projects/Demarch/os/clavain

# Validate structure
ls skills/*/SKILL.md | wc -l          # Should be 16
ls agents/{review,workflow}/*.md | wc -l  # Should be 4
ls commands/*.md | wc -l              # Should be 58
bash -n hooks/lib.sh                   # Syntax check
bash -n hooks/session-start.sh         # Syntax check
bash -n hooks/dotfiles-sync.sh         # Syntax check
bash -n hooks/auto-stop-actions.sh     # Syntax check (compound + drift, merged)
bash -n hooks/lib-signals.sh           # Syntax check
bash -n hooks/session-handoff.sh       # Syntax check
bash -n hooks/auto-publish.sh          # Syntax check
bash -n hooks/bead-agent-bind.sh       # Syntax check
bash -n scripts/bead-land.sh           # Syntax check (close orphaned beads)
bash -n hooks/catalog-reminder.sh      # Syntax check
bash -n hooks/interserve-audit.sh       # Syntax check
bash -n hooks/sprint-scan.sh           # Syntax check (utility, not a hook binding)
bash -n hooks/lib-sprint.sh            # Syntax check (sprint state library)
bash -n hooks/lib-discovery.sh         # Syntax check (shim → interphase)
bash -n hooks/lib-gates.sh             # Syntax check (shim → interphase)
bash -n hooks/session-end-handoff.sh  # Syntax check (SessionEnd backup handoff)
bash -n scripts/clodex-toggle.sh   # Syntax check
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
- **Always publish after pushing** — documented in `AGENTS.md` under **Release workflow**.

### Release workflow

For publishing a release, use `scripts/bump-version.sh <version>` (or `/interpub:release <version>` in Claude Code).
