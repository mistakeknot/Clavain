---
name: interspect-status
description: Interspect overview — session counts, evidence stats, active canaries, and modifications
argument-hint: "[optional: agent or component name for detailed view]"
---

# Interspect Status

Show the current state of Interspect's evidence collection and (future) modification system.

<status_target> #$ARGUMENTS </status_target>

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

## Overview (no arguments)

Query and present:

```bash
# Session stats
TOTAL_SESSIONS=$(sqlite3 "$DB" "SELECT COUNT(*) FROM sessions;")
DARK_SESSIONS=$(sqlite3 "$DB" "SELECT COUNT(*) FROM sessions WHERE end_ts IS NULL AND start_ts < datetime('now', '-24 hours');")
RECENT_SESSIONS=$(sqlite3 "$DB" "SELECT COUNT(*) FROM sessions WHERE start_ts > datetime('now', '-7 days');")

# Evidence stats
TOTAL_EVIDENCE=$(sqlite3 "$DB" "SELECT COUNT(*) FROM evidence;")
OVERRIDE_COUNT=$(sqlite3 "$DB" "SELECT COUNT(*) FROM evidence WHERE event = 'override';")
DISPATCH_COUNT=$(sqlite3 "$DB" "SELECT COUNT(*) FROM evidence WHERE event = 'agent_dispatch';")

# Top agents by evidence count
TOP_AGENTS=$(sqlite3 -separator ' | ' "$DB" "SELECT source, COUNT(*) as cnt, COUNT(DISTINCT session_id) as sessions FROM evidence GROUP BY source ORDER BY cnt DESC LIMIT 10;")

# Active canaries (Phase 1: always 0)
ACTIVE_CANARIES=$(sqlite3 "$DB" "SELECT COUNT(*) FROM canary WHERE status = 'active';")

# Active modifications (Phase 1: always 0)
ACTIVE_MODS=$(sqlite3 "$DB" "SELECT COUNT(*) FROM modifications WHERE status = 'applied';")
```

Present as:

```
## Interspect Status

**Phase 1: Evidence + Reporting** (no modifications applied)

### Sessions
- Total: {total_sessions}
- Last 7 days: {recent_sessions}
- Dark (abandoned): {dark_sessions}

### Evidence
- Total events: {total_evidence}
- Overrides (corrections): {override_count}
- Agent dispatches: {dispatch_count}

### Top Agents by Evidence
| Agent | Events | Sessions |
|-------|--------|----------|
{top_agents rows}

### Canaries: {active_canaries} active
### Modifications: {active_mods} applied

Run `/interspect` for pattern analysis.
Run `/interspect:evidence <agent>` for detailed agent evidence.
Run `/interspect:health` for signal diagnostics.
```

## Detailed View (agent name provided)

If an agent/component name is given, show detailed view:

```bash
AGENT="$1"
E_AGENT="${AGENT//\'/\'\'}"

# Event breakdown
EVENTS=$(sqlite3 -separator ' | ' "$DB" "SELECT event, override_reason, COUNT(*) FROM evidence WHERE source = '${E_AGENT}' GROUP BY event, override_reason;")

# Timeline (last 4 weeks, weekly buckets)
TIMELINE=$(sqlite3 -separator ' | ' "$DB" "SELECT strftime('%Y-W%W', ts) as week, COUNT(*) FROM evidence WHERE source = '${E_AGENT}' AND ts > datetime('now', '-28 days') GROUP BY week ORDER BY week;")

# Recent events
RECENT=$(sqlite3 -separator ' | ' "$DB" "SELECT ts, event, override_reason, substr(context, 1, 100) FROM evidence WHERE source = '${E_AGENT}' ORDER BY ts DESC LIMIT 5;")
```

Present as:

```
## Interspect: {agent} Detail

### Event Breakdown
| Event | Reason | Count |
|-------|--------|-------|
{events rows}

### Weekly Timeline (last 4 weeks)
{week} | {count} {'█' * count}

### Recent Events
{recent events with timestamps}
```
