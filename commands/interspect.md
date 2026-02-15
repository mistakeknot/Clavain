---
name: interspect
description: Analyze Interspect evidence — detect patterns, classify by counting-rule thresholds, report readiness
---

# Interspect Analysis

Main analysis command. Queries the evidence store, detects patterns, classifies by counting-rule thresholds, and presents a structured report.

**Phase 1 notice:** No modifications are applied. This command shows what Interspect *would* propose in Phase 2.

## Locate Library

```bash
INTERSPECT_LIB=$(find ~/.claude/plugins/cache -path '*/clavain/*/hooks/lib-interspect.sh' 2>/dev/null | head -1)
[[ -z "$INTERSPECT_LIB" ]] && INTERSPECT_LIB=$(find ~/projects -path '*/hub/clavain/hooks/lib-interspect.sh' 2>/dev/null | head -1)
if [[ -z "$INTERSPECT_LIB" ]]; then
    echo "Error: Could not locate hooks/lib-interspect.sh" >&2
    exit 1
fi
source "$INTERSPECT_LIB"
_interspect_ensure_db
DB=$(_interspect_db_path)
```

## Pattern Detection

Query patterns grouped by (source, event, override_reason):

```bash
# Pattern summary: source, event, override_reason, event_count, session_count, project_count
PATTERNS=$(sqlite3 -separator '|' "$DB" "
    SELECT
        source,
        event,
        COALESCE(override_reason, ''),
        COUNT(*) as event_count,
        COUNT(DISTINCT session_id) as session_count,
        COUNT(DISTINCT project) as project_count
    FROM evidence
    GROUP BY source, event, override_reason
    HAVING COUNT(*) >= 2
    ORDER BY event_count DESC;
")
```

## Counting-Rule Classification

For each pattern, apply thresholds from design §3.3:

| Criterion | Threshold | Field |
|-----------|-----------|-------|
| Session diversity | >= 3 sessions | session_count |
| Cross-project diversity | >= 2 projects OR >= 2 languages | project_count |
| Event volume | >= 5 events | event_count |

Classify each pattern:
- **Ready** — ALL three thresholds met. "Eligible for proposal in Phase 2."
- **Growing** — SOME thresholds met. Show which criteria are not yet met.
- **Emerging** — BELOW all thresholds. "Watching."

## Report Format

Present the analysis as:

```
## Interspect Analysis Report

**Phase 1: Evidence + Reporting** — no modifications will be applied.

### Ready Patterns (eligible for Phase 2 proposals)

| Agent | Event | Reason | Events | Sessions | Projects | Status |
|-------|-------|--------|--------|----------|----------|--------|
{ready patterns}

> These patterns have sufficient evidence for a modification proposal.
> In Phase 2, each would generate an overlay or routing adjustment.

### Growing Patterns (approaching threshold)

| Agent | Event | Reason | Events | Sessions | Projects | Missing |
|-------|-------|--------|--------|----------|----------|---------|
{growing patterns with missing criteria}

### Emerging Patterns (watching)

| Agent | Event | Events | Sessions |
|-------|-------|--------|----------|
{emerging patterns}

### Evidence Health Summary
- Total evidence events: {total}
- Override events: {overrides} ({override_pct}%)
- Agent dispatch events: {dispatches}
- Active sessions (last 7d): {recent}
- Dark sessions: {dark}

### Recommendations
{based on data: suggest running /interspect:correction if few overrides,
suggest checking /interspect:health if evidence collection looks sparse}
```

## Edge Cases

- **Empty database:** Report "No evidence collected yet. Run `/interspect:correction <agent> <description>` to record your first correction, or wait for evidence hooks to collect data."
- **Only dispatch events:** Report "Evidence consists only of agent dispatch tracking. Run `/interspect:correction` to add correction signals for pattern analysis."
- **No patterns meeting any threshold:** Report all as emerging, with a note about how many more events/sessions are needed.
