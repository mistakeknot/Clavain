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

## Pattern Detection & Classification

Use the lib-interspect.sh confidence gate to query and classify all patterns:

```bash
# Get classified patterns: source|event|reason|event_count|session_count|project_count|classification
CLASSIFIED=$(_interspect_get_classified_patterns)
```

Thresholds are loaded from `.clavain/interspect/confidence.json` (defaults: 3 sessions, 2 projects, 5 events).

Classification levels:
- **Ready** (all 3 thresholds met) — "Eligible for proposal in Phase 2."
- **Growing** (1-2 thresholds met) — Show which criteria are not yet met.
- **Emerging** (no thresholds met) — "Watching."

Parse each row and bucket by classification:

```bash
READY_PATTERNS=""
GROWING_PATTERNS=""
EMERGING_PATTERNS=""

while IFS='|' read -r src evt reason ec sc pc cls; do
    [[ -z "$src" ]] && continue
    case "$cls" in
        ready)    READY_PATTERNS+="${src}|${evt}|${reason}|${ec}|${sc}|${pc}\n" ;;
        growing)  GROWING_PATTERNS+="${src}|${evt}|${reason}|${ec}|${sc}|${pc}\n" ;;
        emerging) EMERGING_PATTERNS+="${src}|${evt}|${reason}|${ec}|${sc}|${pc}\n" ;;
    esac
done <<< "$CLASSIFIED"
```

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
