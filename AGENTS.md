# Clavain — Development Guide

## Canonical References
1. [`PHILOSOPHY.md`](../../PHILOSOPHY.md) — direction for ideation and planning decisions.
2. `CLAUDE.md` — implementation details, architecture, testing, and release workflow.

## Philosophy Alignment Protocol
Review [`PHILOSOPHY.md`](../../PHILOSOPHY.md) during:
- Intake/scoping
- Brainstorming
- Planning
- Execution kickoff
- Review/gates
- Handoff/retrospective

For brainstorming/planning outputs, add two short lines:
- **Alignment:** one sentence on how the proposal supports the module's purpose within Demarch's philosophy.
- **Conflict/Risk:** one sentence on any tension with philosophy (or 'none').

If a high-value change conflicts with philosophy, either:
- adjust the plan to align, or
- create follow-up work to update `PHILOSOPHY.md` explicitly.


Autonomous software agency — orchestrates the full development lifecycle from problem discovery through shipped code using heterogeneous AI models. Layer 2 (OS) in the Demarch stack: sits between Intercore (L1 kernel) for state management and Autarch (L3 apps) for TUI rendering. Originated from [superpowers](https://github.com/obra/superpowers), [superpowers-lab](https://github.com/obra/superpowers-lab), [superpowers-developing-for-claude-code](https://github.com/obra/superpowers-developing-for-claude-code), and [compound-engineering](https://github.com/EveryInc/compound-engineering-plugin).

## Quick Reference

| Item | Value |
|------|-------|
| Repo | `https://github.com/mistakeknot/Clavain` |
| Namespace | `clavain:` |
| Manifest | `.claude-plugin/plugin.json` |
| Components | 17 skills, 6 agents, 50 commands, 10 hooks, 0 MCP servers |
| License | MIT |
| Layer | L2 (OS) — depends on Intercore (L1), consumed by Autarch (L3) |

### North Star for New Work

- Improve at least one frontier axis: orchestration, reasoning quality, or token efficiency.
- Avoid measurable regressions on the other two axes unless offset by a larger quantified gain.
- Prefer changes with observable signals in routing, review precision, or resource-to-outcome ratio.

## Topic Guides

| Topic | File | Covers |
|-------|------|--------|
| Architecture | [agents/architecture.md](agents/architecture.md) | Directory structure, routing system, component types, factory substrate, CXDB |
| Skills & Agents | [agents/skills-reference.md](agents/skills-reference.md) | Skill conventions, agent conventions, adding/renaming components |
| Commands | [agents/commands-reference.md](agents/commands-reference.md) | Command conventions, adding commands and MCP servers |
| Hooks | [agents/hooks-reference.md](agents/hooks-reference.md) | Hook catalog, hook libraries, event types |
| Development | [agents/development.md](agents/development.md) | Release workflow, validation checklist, constraints, upstream tracking |
| Codex & Plugins | [agents/codex-integration.md](agents/codex-integration.md) | Codex setup, interserve dispatch, modpack companion plugins |

## Prior Art Pipeline

Brainstorm, strategy, and write-plan commands all enforce a prior art check before building new infrastructure. The pipeline:

1. `grep -ril "<keywords>" docs/research/assess-*.md` — check for prior verdicts
2. `bd search "<keywords>"` + `ls interverse/*/CLAUDE.md | xargs grep -li "<keywords>"` — check existing work
3. Conditional web search — only when creating new systems from scratch
4. Clone to `research/` for deep evaluation — write `docs/research/assess-<repo>.md` with verdict

See `agents/operational-guides.md` in the Demarch root for the full protocol.

## Quick Validation

```bash
echo "Skills: $(ls skills/*/SKILL.md | wc -l)"      # Should be 17
echo "Commands: $(ls commands/*.md | wc -l)"        # Should be 50
```

See [agents/development.md](agents/development.md) for the full validation checklist.

## Session Completion

See root `Demarch/AGENTS.md` -> "Landing the Plane" for the mandatory push workflow.
