# PRD: .clavain/ Agent Memory Filesystem Contract

**Bead:** Clavain-d4ao
**Status:** Draft
**Source:** [Brainstorm](../brainstorms/2026-02-13-clavain-memory-filesystem-brainstorm.md)

## Problem

Clavain scatters agent memory across 5 locations (global knowledge, root HANDOFF.md, docs/solutions/, .claude/flux-drive.yaml, .beads/) with no unified per-project contract. This causes:
- **Root pollution**: HANDOFF.md clutters the project root
- **No cross-session continuity**: Sessions start cold without manual bead consultation
- **No project-local learnings**: Compound knowledge is global (plugin), not project-specific
- **No extension point**: Downstream features (scenarios, pipelines) have nowhere to live

## Solution

Define a `.clavain/` directory convention for per-project agent memory. Implement `/clavain:init` to scaffold it. Update existing hooks to use it when present.

## Scope

### In Scope (this PRD)
1. Directory structure specification with gitignore contract
2. `/clavain:init` command to scaffold `.clavain/`
3. Update `session-handoff.sh` to write to `.clavain/scratch/handoff.md` when available
4. Update `session-start.sh` to read `.clavain/scratch/handoff.md` for continuity
5. YAML schema for learnings entries (matching existing `config/flux-drive/knowledge/` format)

### Out of Scope (deferred)
- `/index:update` and `/genrefy` commands (Phase 2)
- auto-compound writing to `.clavain/learnings/` (Phase 3)
- fd-* agents reading `.clavain/learnings/` (Phase 4)
- scenarios, pipelines, CXDB-lite, provenance (downstream beads)

## Design Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Opt-in vs. auto-create | Opt-in via `/clavain:init` | Discipline over magic; don't surprise users |
| Compound writes | Project-local when `.clavain/` exists, global fallback otherwise | Different purposes: project gotchas vs. plugin review patterns |
| Index generation | Deferred to Phase 2 | Agents already have Grep/Glob; indexes add complexity without proven value |
| Non-git repos | Not supported in v1 | All target projects use git |

## Directory Specification

```
.clavain/
├── learnings/              # Curated durable knowledge (committed)
│   └── *.md                # YAML frontmatter + markdown body
├── scratch/                # Ephemeral state (gitignored)
│   ├── handoff.md          # Session handoff context
│   └── runs/               # Future: run manifests
├── contracts/              # API contracts, invariants (committed)
│   └── *.md                # Contract documents
└── weather.md              # Model routing preferences (committed)
```

### Gitignore Contract
```gitignore
.clavain/scratch/
```

### Learnings Format
```yaml
---
title: "Description of the learning"
category: correctness|safety|performance|architecture|quality
severity: low|medium|high|critical
provenance: independent|primed
date: YYYY-MM-DD
project: <project-name>
---

## Evidence
<what happened, why it was surprising>

## Pattern
<the reusable insight>

## Fix
<what to do when this comes up>
```

## Features

### F1: `/clavain:init` Command
- Creates `.clavain/` directory tree
- Adds `.clavain/scratch/` to project's `.gitignore` (appends if not present)
- Creates starter `weather.md` with sensible defaults
- Creates empty `learnings/` and `contracts/` directories
- Idempotent — safe to re-run (doesn't overwrite existing files)

### F2: Session Handoff Integration
- `session-handoff.sh`: When `.clavain/` exists, write to `.clavain/scratch/handoff.md` instead of root `HANDOFF.md`
- `session-start.sh`: When `.clavain/scratch/handoff.md` exists, inject its content into `additionalContext` as "Previous session context"
- Fallback: If `.clavain/` doesn't exist, current behavior (root HANDOFF.md) is unchanged

### F3: Doctor Check
- Add `.clavain/` health check to `/clavain:doctor`
- Verify: scratch/ is gitignored, no stale handoffs (>7 days), learnings format valid

## Success Criteria

- [ ] `/clavain:init` creates correct structure in any git repo
- [ ] Session handoff uses `.clavain/scratch/` when available
- [ ] Session start reads handoff context from `.clavain/scratch/`
- [ ] Doctor reports `.clavain/` health
- [ ] Existing behavior unchanged when `.clavain/` doesn't exist
- [ ] Directory is extensible — downstream beads can add subdirs without contract changes

## Implementation Estimate

3 files modified (session-handoff.sh, session-start.sh, doctor.md), 1 file created (init.md command), total ~120 lines changed.
