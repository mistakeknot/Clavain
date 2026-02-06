---
name: migration-safety
description: Orchestrate database migration and data-risk work with consistent safety checks — combines data integrity, migration, and deployment verification agents
argument-hint: "[migration file, PR number, or description of data change]"
---

# Migration Safety

Orchestrate DB/data-risk work with consistent checks. Runs 3 specialized agents in parallel to produce a comprehensive safety assessment.

## Migration Context

<migration_context> #$ARGUMENTS </migration_context>

**If empty:** Ask the user: "What data change are you making? Include: migration files, affected tables/columns, and whether this touches production data."

## Execution Flow

### Phase 1: Gather Context

1. Read the migration files or data change description
2. Identify:
   - Which tables/columns are affected?
   - Is this a schema change, data backfill, or both?
   - Is there production data at risk?
   - Is this reversible?

### Phase 2: Run Safety Agents in Parallel

Launch all 3 agents simultaneously:

```
Task(data-migration-expert): "Review this migration for safety: <context>. Check for: ID mapping correctness, swapped values, orphaned associations, dual-write patterns. Produce validation queries."

Task(data-integrity-reviewer): "Review this data change for integrity: <context>. Check for: referential integrity, transaction boundaries, privacy compliance, constraint violations. Identify invariants that must hold."

Task(deployment-verification-agent): "Create a Go/No-Go deployment checklist for: <context>. Include: pre-deploy verification queries, post-deploy checks, rollback procedure, monitoring plan."
```

### Phase 3: Synthesize Results

Combine all 3 agent reports into a single safety assessment:

```markdown
## Migration Safety Assessment

### Summary
- **Migration:** [description]
- **Risk Level:** [LOW / MEDIUM / HIGH / CRITICAL]
- **Reversible:** [yes / no / partial]

### Data Migration Expert Findings
- [ID mapping validation results]
- [Swapped value checks]
- [Verification queries to run]

### Data Integrity Review
- [Invariants that must hold]
- [Transaction boundary assessment]
- [Privacy compliance check]

### Deployment Checklist

#### Pre-Deploy
- [ ] [verification query 1]
- [ ] [verification query 2]
- [ ] [backup/snapshot taken]

#### Deploy
- [ ] [migration command]
- [ ] [monitoring check]

#### Post-Deploy
- [ ] [verification query 1]
- [ ] [verification query 2]
- [ ] [data count comparison]

#### Rollback (if needed)
- [ ] [rollback step 1]
- [ ] [rollback step 2]

### Go/No-Go Decision
- 🔴 **NO-GO** if: [conditions that block deployment]
- 🟢 **GO** if: [all pre-deploy checks pass]
```

### Phase 4: Present to User

Present the synthesized report and ask:

```
Migration safety assessment complete.
Risk level: [HIGH/MEDIUM/LOW]

1. Proceed with deployment (all checks pass)
2. Fix issues first (P1 findings need resolution)
3. I need to review the full report
```

## When to Use This Command

- Any database schema migration
- Data backfills or transformations
- Column renames, type changes, or constraint modifications
- Any change that touches production data
- Enum/status value migrations

## Important

- **Always run pre-deploy queries** before applying the migration.
- **Always have a rollback plan** — even for "simple" migrations.
- **Data changes are not code changes** — they can't be reverted with `git revert`.
- **Verify in staging first** when possible.
