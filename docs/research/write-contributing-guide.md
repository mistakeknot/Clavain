# Research: Write Contributing Guide

## Task

Create `/home/mk/projects/Demarch/docs/guide-contributing.md` with the exact content specified by the user.

## Analysis

### Pre-existing State
- The `docs/` directory already existed with subdirectories for brainstorms, guides, plans, PRDs, etc.
- No `guide-*.md` files existed at the `docs/` root level -- this is the first guide placed there (as opposed to `docs/guides/` which contains operational reference docs).
- The guide references two sibling files that don't yet exist: `guide-full-setup.md` and `guide-power-user.md`. These are expected to be created separately.

### Content Review
The contributing guide covers:
1. **Monorepo cloning** -- emphasizes that subprojects keep their own `.git` repos
2. **Project structure** -- L1/L2/L3 layer architecture with all top-level directories
3. **Development workflow** -- trunk-based development (commit to main), bead-tracked work, Clavain routing
4. **Testing** -- Go test commands with `-race`, plugin syntax checking, structural validation
5. **Code review** -- 7-agent quality gates + cross-AI review via interpeer/Oracle
6. **Plugin development** -- local testing, plugin structure, publishing, naming conventions
7. **Key files** -- CLAUDE.md, AGENTS.md, plugin.json, agent-rig.json, .beads/

### Consistency with Project Conventions
- Naming conventions match `CLAUDE.md` at `/home/mk/projects/Demarch/CLAUDE.md` (lowercase modules, proper noun exceptions)
- Trunk-based development matches global `~/.claude/CLAUDE.md` git workflow rules
- Layer descriptions (L1/L2/L3) match the Demarch CLAUDE.md design decisions
- Testing conventions (`-race` flag) match autarch/intermute project standards from MEMORY.md

### File Placement
Written to `/home/mk/projects/Demarch/docs/guide-contributing.md` -- at the docs root alongside `architecture.md`, `glossary.md`, and other top-level reference docs. This is distinct from `docs/guides/` which holds operational/troubleshooting docs.

## Outcome

File written successfully with all specified content.
