# Brainstorm: Rename `/lfg` to `/sprint`

## Problem Statement

The `/lfg` command name ("let's fucking go") is the central orchestration hub for Clavain's 9-step autonomous engineering workflow. While energetic, the name:

1. **Doesn't communicate what it does** — new users see `/lfg` and have no idea it's a full pipeline orchestrator
2. **Contains profanity** — awkward in professional/enterprise contexts, screen shares, demos
3. **Doesn't match the mental model** — the workflow IS an "agent sprint": discover work, plan, execute, review, ship

## Proposed Name: `/sprint`

**Why "sprint":**
- Matches the mental model: it's a full sprint cycle from ideation to shipping
- Professional and self-documenting
- Pairs naturally with existing commands: `/sprint-status` already exists
- "Agent sprint" conveys autonomous multi-step execution

## Scope Analysis

### Files to Rename (primary)
- `commands/lfg.md` → `commands/sprint.md` (rename file + update frontmatter `name: sprint`)

### Files to Create
- `commands/lfg.md` — backward-compat alias pointing to `/clavain:sprint` (like `full-pipeline.md` does today)

### Files to Update (references)

**Commands:**
- `commands/full-pipeline.md` — update alias target from lfg to sprint
- `commands/help.md` — update all `/clavain:lfg` references, aliases section

**Skills:**
- `skills/using-clavain/SKILL.md` — quick router table row
- `skills/using-clavain/references/routing-tables.md` — Execute stage row + footnote 2
- `skills/writing-plans/SKILL.md` — if it references `/lfg`
- `skills/dispatching-parallel-agents/SKILL.md` — if it references `/lfg`

**Documentation:**
- `CLAUDE.md` — if it references lfg
- `AGENTS.md` — agent routing references
- `README.md` — primary workflow documentation
- `docs/PRD.md` — feature references
- `docs/vision.md` — vision alignment
- `docs/roadmap.md` — future planning references

**Configuration:**
- `upstreams.json` — fileMap entry `commands/lfg.md`, protectedFiles, namespaceReplacements `/deepen-plan` target

**Tests:**
- `tests/structural/` — any test counting commands or referencing lfg by name

**Memory (auto-memory):**
- Update MEMORY.md references

### Alias Strategy

Keep backward compatibility:
- `/clavain:sprint` — **primary** command (the full 190-line workflow)
- `/clavain:lfg` — **alias** → delegates to `/clavain:sprint` (small file, like full-pipeline.md)
- `/clavain:full-pipeline` — **alias** → update to point to sprint instead of lfg

This means:
- Existing muscle memory for `/lfg` still works
- New users see `/sprint` as the recommended way
- Help/routing tables promote `/sprint` as primary

## Decision Points

1. **Should `/lfg` remain as a backward-compat alias?** YES — no reason to break existing muscle memory
2. **Should `/full-pipeline` also remain?** YES — it's a separate entry point with no discovery mode
3. **Should error recovery text say "re-invoke `/clavain:sprint`"?** YES — all self-references should use the new canonical name
4. **Upstream sync:** Update `upstreams.json` protectedFiles from `commands/lfg.md` to `commands/sprint.md`, and namespace replacement target from `/clavain:lfg` to `/clavain:sprint`

## Implementation Estimate

~15-25 files to touch, but each change is a simple string replacement. No logic changes. The command content is identical — only the filename and name in frontmatter change.

## Risks

- **Low risk:** All changes are string replacements in markdown files and JSON config
- **Test suite:** Command count stays at 36 (adding sprint.md, keeping lfg.md as alias = net zero if we count aliases, or +1 if sprint is new and lfg stays)
  - Actually: lfg.md exists today. We rename it to sprint.md and create a NEW lfg.md alias. Count stays at 36.
  - Wait — we currently have 36 commands. `lfg.md` is one of them. If we rename `lfg.md` → `sprint.md` and create a new `lfg.md` (alias), we go to 37 commands.
  - **Decision needed:** Do we want 37 commands (add sprint, keep lfg alias), or do we want to convert the existing lfg.md in-place to sprint.md and make lfg.md a thin alias? Either way count goes to 37 unless we remove full-pipeline.md.
  - **Recommendation:** Accept 37 commands. Three aliases (`lfg`, `full-pipeline`, `deep-review`, `cross-review`) all serve discoverability.
  - Actually, looking at the current 36: `full-pipeline` is already one of them. So current state is 36 with `lfg` + `full-pipeline` both counted. Renaming `lfg.md` → `sprint.md` and creating a new `lfg.md` alias = 37 total. Update test count from 36 → 37.

## Out of Scope

- Renaming the upstream source file (compound-engineering's `lfg.md` is their name, we just remap)
- Changing other command names
- Modifying workflow logic
