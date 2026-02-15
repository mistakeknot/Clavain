---
name: interspect-propose
description: Detect routing-eligible patterns and propose agent exclusions
argument-hint: "[optional: specific agent to check]"
---

# Interspect Propose

Tier 2 analysis: detect patterns eligible for routing overrides and present proposals.

<propose_target> #$ARGUMENTS </propose_target>

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

## Detect Routing-Eligible Patterns

Get classified patterns and filter for routing eligibility:

```bash
CLASSIFIED=$(_interspect_get_classified_patterns)
```

For each pattern classified as "ready":
1. Check `_interspect_is_routing_eligible "$agent"` — skip if not eligible (blacklisted, below threshold)
2. Check `_interspect_override_exists "$agent"` — skip if override already exists
3. Collect eligible patterns into a list

## Cross-Cutting Agent Check

Cross-cutting agents: `fd-architecture`, `fd-quality`, `fd-safety`, `fd-correctness`.

If a routing-eligible pattern involves a cross-cutting agent, it still appears in proposals but with an explicit warning:
> "Warning: {agent} provides structural/security coverage across all projects. Excluding it may hide systemic issues."

The proposal for cross-cutting agents requires the user to select "Yes, exclude despite warning" (not just "Accept").

## Present Proposals (Batch Mode)

Show the pattern analysis table first (same as `/interspect` output), then present all eligible proposals together for batch decision-making.

If no eligible patterns exist and no evidence exists at all:
> "No patterns detected yet. Record corrections via `/interspect:correction` when agents produce irrelevant findings. Interspect learns from your overrides."

If patterns exist but none are routing-eligible:
> "Patterns detected but not routing-eligible. Routing overrides require >=80% of corrections to be 'agent_wrong'. Keep recording corrections via `/interspect:correction`."

If eligible patterns exist, show a summary table first:

```
Interspect found N routing-eligible patterns:

| Agent | Events | Sessions | agent_wrong% | Warning |
|-------|--------|----------|-------------|---------|
| fd-game-design | 8 | 4 | 100% | |
| fd-performance | 6 | 3 | 83% | |
| fd-correctness | 5 | 3 | 100% | cross-cutting |
```

Then present a single multi-select AskUserQuestion:

```
Which agents do you want to exclude from this project? (Select all that apply)

Options:
- "fd-game-design — 100% irrelevant (8 events)"
- "fd-performance — 83% irrelevant (6 events)"
- "fd-correctness — cross-cutting, 100% irrelevant (5 events)"
- "Show evidence details" — View recent corrections before deciding
```

If "Show evidence details" is selected, query evidence for each eligible agent:

```bash
local escaped
escaped=$(_interspect_sql_escape "$agent")
sqlite3 -separator '|' "$DB" "SELECT ts, override_reason, substr(context, 1, 200) FROM evidence WHERE source = '${escaped}' AND event = 'override' ORDER BY ts DESC LIMIT 5;"
```

Format as human-readable summaries:
```
Recent corrections for fd-game-design:
- Feb 10, 2:23pm: Recommended async patterns for sync-only project
- Feb 9, 11:45am: Suggested multiplayer architecture for single-player game
```

Then re-present the multi-select choice.

For all selected agents, apply overrides in batch (call `_interspect_apply_routing_override` for each).

## Progress Display

For patterns that are "growing" (not yet ready), show progress:

```
### Approaching Threshold
- {agent}: {events}/{min_events} events, {sessions}/{min_sessions} sessions ({needs} more {criteria})
```

## On Accept

If user accepts, proceed to apply the override:
1. Call `_interspect_apply_routing_override "$agent" "$reason" "$evidence_ids" "interspect"` for each selected agent
2. Report result to user

## On Decline

Skip this pattern. It will re-propose next session if still eligible. Do not blacklist.
