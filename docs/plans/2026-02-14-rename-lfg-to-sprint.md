# Plan: Rename `/lfg` to `/sprint`

**Brainstorm:** `docs/brainstorms/2026-02-14-rename-lfg-to-sprint.md`

## Summary

Rename the canonical `/lfg` command to `/sprint`. Keep `/lfg` as a backward-compat alias. Update all live references. Command count goes from 36 → 37.

## Steps

### 1. Create `commands/sprint.md` from `commands/lfg.md`

- Copy `commands/lfg.md` → `commands/sprint.md`
- Change frontmatter `name: lfg` → `name: sprint`
- Update self-references in error recovery: "re-invoke `/clavain:lfg`" → "re-invoke `/clavain:sprint`"

### 2. Convert `commands/lfg.md` to backward-compat alias

Replace contents of `commands/lfg.md` with a thin alias (modeled on `full-pipeline.md`):

```yaml
---
name: lfg
description: "Alias for sprint — full autonomous engineering workflow"
argument-hint: "[feature description]"
---

Run `/clavain:sprint $ARGUMENTS`
```

### 3. Update `commands/full-pipeline.md`

- Description: "Alias for lfg" → "Alias for sprint"
- Error recovery line: "re-invoke `/clavain:lfg`" → "re-invoke `/clavain:sprint`"

### 4. Update `commands/help.md`

- Line 14: `/clavain:lfg` → `/clavain:sprint` as primary entry
- Line 23: Aliases section — add `/lfg` = sprint, update `/full-pipeline` = sprint
- Line 42: Execute stage — `/clavain:lfg` → `/clavain:sprint`

### 5. Update `commands/setup.md`

- Line 186: `/clavain:lfg` → `/clavain:sprint`

### 6. Update `skills/using-clavain/SKILL.md`

- Line 18: `/clavain:lfg` → `/clavain:sprint`

### 7. Update `skills/using-clavain/references/routing-tables.md`

- Line 14: `lfg²` → `sprint²`
- Line 61: Footnote — update `/lfg` references to `/sprint`

### 8. Update `skills/writing-plans/SKILL.md`

- Line 183: `/lfg` → `/sprint`

### 9. Update `skills/dispatching-parallel-agents/SKILL.md`

- Line 215: `/lfg` → `/sprint`

### 10. Update `upstreams.json`

- Line 126: fileMap `"commands/lfg.md": "commands/lfg.md"` — keep as-is (upstream source is still `lfg.md`, maps to our alias)
- Line 134: protectedFiles `"commands/lfg.md"` → `"commands/sprint.md"` (protect the real content)
- Line 143: namespaceReplacements `"/deepen-plan": "/clavain:lfg"` → `"/deepen-plan": "/clavain:sprint"`

### 11. Update tests

- `tests/structural/test_commands.py` line 23-24: `36` → `37`
- `tests/structural/test_discovery.py` lines 31-36: `lfg.md` → `sprint.md` in test function name and file path
- `tests/structural/test_clavain_sync/test_config.py` line 27, 48: `commands/lfg.md` → `commands/sprint.md`
- `tests/structural/test_clavain_sync/test_classify.py` lines 10, 14: `commands/lfg.md` → `commands/sprint.md`

### 12. Update top-level docs

- `README.md`: `/lfg` → `/sprint` in daily drivers table, lifecycle section heading, alias line
- `AGENTS.md` line 322: `/lfg` → `/sprint` in feature-dev row
- `docs/PRD.md`: `/lfg` → `/sprint` in overview table, execution row, section 5.1 heading, interphase row
- `docs/roadmap.md`: `/lfg` → `/sprint` in shipped features, analytics, auto-inject lines
- `docs/vision.md` line 133: `lfg pipeline` → `sprint pipeline`
- `docs/catalog.json`: update name and description for both lfg and full-pipeline entries

### 13. Update CLAUDE.md and gen-catalog counts

- `CLAUDE.md` quick commands section: command count comment stays at 36 if we don't adjust, or add sprint.md. Since count goes 36→37, update the comment and the using-clavain SKILL.md count line.
- `skills/using-clavain/SKILL.md` line 14: `36 commands` → `37 commands`
- Any other "36 commands" references in CLAUDE.md, AGENTS.md, PRD.md

### 14. Regenerate `docs/catalog.json`

Run `scripts/gen-catalog.py` to pick up the new sprint command.

### 15. Update auto-memory

Update `MEMORY.md` references from lfg to sprint where applicable.

## Out of Scope

- `docs/research/`, `docs/brainstorms/`, `docs/plans/`, `docs/prds/`, `docs/solutions/` — historical artifacts, leave as-is
- `.beads/` — system-managed, don't touch
- Upstream source files — they keep their `lfg.md` name
- `docs/README.codex.md` — historical, leave as-is

## Verification

```bash
# Command count is now 37
ls commands/*.md | wc -l  # 37

# sprint.md has discovery section
grep "Before Starting" commands/sprint.md

# lfg.md is a thin alias
wc -l commands/lfg.md  # ~8 lines

# No stale /clavain:lfg as primary in live files (should only appear in alias files and historical docs)
grep -r "clavain:lfg" commands/ skills/ | grep -v "Alias"

# Tests pass
cd /root/projects/Clavain && uv run pytest tests/structural/ -x -q
```
