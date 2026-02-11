# Plan: Audit and apply disable-model-invocation (Clavain-zkds)

## Goal
Reduce plugin context budget usage by marking manual-invocation-only commands and skills with `disable-model-invocation: true`. Prevents silent component exclusion as Clavain grows.

## Steps

### Step 1: Add flag to 13 commands
Add `disable-model-invocation: true` to frontmatter of these commands (8 already have it):

```
lfg.md, brainstorm.md, strategy.md, work.md, smoke-test.md, fixbuild.md,
resolve.md, setup.md, upstream-sync.md, compound.md, model-routing.md,
clodex-toggle.md, debate.md
```

**Do NOT add** to review/auto-discovery commands: quality-gates, plan-review, review, flux-drive, interpeer, repro-first-debugging, migration-safety.

### Step 2: Add flag to 8 skills
Add `disable-model-invocation: true` to frontmatter of these skills (1 already has it):

```
using-clavain/SKILL.md, upstream-sync/SKILL.md, beads-workflow/SKILL.md,
developing-claude-code-plugins/SKILL.md, brainstorming/SKILL.md,
writing-plans/SKILL.md, landing-a-change/SKILL.md, writing-skills/SKILL.md
```

### Step 3: Run structural tests
```bash
uv run --project tests pytest tests/structural/ -q
```
Verify no regressions — the frontmatter tests should still pass since `disable-model-invocation` is a valid optional field.

### Step 4: Commit
Commit message: `perf: add disable-model-invocation to 21 manual commands/skills`

## Verification
- `grep -rl 'disable-model-invocation' commands/ | wc -l` → should be 21 (8 existing + 13 new)
- `grep -rl 'disable-model-invocation' skills/ | wc -l` → should be 9 (1 existing + 8 new)
- Review commands (quality-gates, flux-drive, interpeer, etc.) should NOT have the flag
