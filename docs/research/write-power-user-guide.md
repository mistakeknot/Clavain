# Research: Write Power User Guide

**Date:** 2026-02-23
**Task:** Create `/home/mk/projects/Demarch/docs/guide-power-user.md`

## Analysis

### Target Audience
Claude Code users who already have Claude Code installed and want to add Clavain to their workflow. This is a "quick start" guide, not a comprehensive reference.

### Content Decisions

1. **Install path**: Uses `curl | bash` from GitHub raw URL. No `install.sh` exists at the repo root yet — this is aspirational/planned. The guide references it as the intended install mechanism.

2. **Companion plugins**: The `/clavain:setup` command installs 12+ companion plugins from the Interverse ecosystem. These include interflux (review), interphase (phase tracking), interwatch (doc freshness), interlock (file coordination), intermap (code mapping), intermux (agent monitoring), interline (statusline), interfluence (voice profiles), interkasten (Notion sync), and others.

3. **Sprint lifecycle**: The guide documents 6 phases: Brainstorm, Strategize, Plan, Execute, Review, Ship. Each maps to a specific slash command.

4. **Beads integration**: Beads (`bd` CLI) is the git-native issue tracker. The guide shows the most common commands.

5. **Multi-agent review**: Quality gates dispatch 7 specialized agents (fd-architecture, fd-safety, fd-correctness, fd-quality, fd-user-product, fd-performance, fd-game-design).

6. **File location**: Written to `/home/mk/projects/Demarch/docs/guide-power-user.md` — top-level docs directory alongside existing guides in `docs/guides/`.

### Key Findings

- No existing `guide-*.md` files exist in `/home/mk/projects/Demarch/docs/` — this is the first user-facing guide at this path convention.
- The `docs/guides/` subdirectory contains operational/internal guides, not user-facing ones.
- No `install.sh` exists at the Demarch repo root — the guide references a planned installation script.
- The content was provided verbatim by the user and written as-is.

### Files Written

- `/home/mk/projects/Demarch/docs/guide-power-user.md` — the power user guide (exact content as specified)
