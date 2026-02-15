# Research: F9 Signal File Adapter — Pre-Plan Analysis

**Date:** 2026-02-14
**Scope:** Implementation plan for interlock companion's signal file adapter (F9)
**Bead:** Clavain-rmvl

---

## Context Gathered

### 1. PRD Acceptance Criteria (F9)

From `docs/prds/2026-02-14-interlock-multi-agent-coordination.md`, F9 specifies:

- Signal files written to `/var/run/intermute/signals/{project-slug}-{agent-id}.jsonl`
- Signal directory created with mode 0700 on setup
- Append-only writes using `O_APPEND` flag (atomic for <4KB payloads on Linux)
- Normalized schema: `{"version":1,"layer":"coordination","icon":"lock","text":"...","priority":3,"ts":"..."}`
- Schema includes `version: 1` field for forward compatibility
- Signals emitted on: reservation create, reservation release, message received
- Signal events are <200 bytes each (well within 4KB O_APPEND atomicity guarantee)
- Signal file rotation deferred to post-MVP

### 2. Consumer: interline Statusline

From `/root/projects/interline/scripts/statusline.sh`:

- interline reads signal files from various sources (dispatch state files, bead sideband files)
- Current pattern: JSON files at `/tmp/clavain-{type}-{session_id}.json`
- F13 (interline Signal Integration) will add reading from `/var/run/intermute/signals/`
- Priority ordering: dispatch > **coordination (new)** > bead > workflow > clodex
- interline parses the last line of JSONL files for latest state
- Gracefully ignores unknown schema versions

interline does NOT yet read the signal files. That's F13. F9 is the **writer** side only.

### 3. Companion Plugin Conventions

From the existing companion ecosystem (interphase, interflux, interpath, interwatch):

- **Discovery pattern:** env var (`INTERLOCK_ROOT`) > `find` in plugin cache for marker file
- **Marker files:** Specific to each plugin (e.g., `scripts/interpath.sh`, `scripts/interwatch.sh`)
- **Signal files:** Bash `>>` append uses O_APPEND flag, which is atomic for writes <4KB on Linux ext4/tmpfs
- **Project slug:** `basename $(git rev-parse --show-toplevel)` is the standard pattern in the ecosystem

### 4. Existing Plan Format

From `docs/plans/2026-02-14-interlock-f1-circuit-breaker.md` and `docs/plans/2026-02-14-auto-drift-check.md`:

- Plans use `> **For Claude:** REQUIRED SUB-SKILL: Use clavain:executing-plans` header
- Tasks are numbered with clear Steps, Files, and Acceptance criteria
- Pre-flight and post-execution checklists are included
- Test-first approach (write tests, verify they fail, implement, verify they pass)

### 5. Integration Points for Signal Emission

F9 signals should be emitted from:
1. **MCP server** (F6) — after successful `reserve_files` and `release_files` tool calls
2. **SessionStart hook** (F7) — after agent registration
3. **Stop hook** (F7) — after cleanup/deregistration
4. **Stale reservation cleanup** (F3) — when sweeping expired reservations

Since the interlock repo doesn't exist yet, the signal writer script is a standalone utility that other components call.

### 6. Key Design Decisions

- **3 tasks only** (per user request) — this is a small feature, shell scripts and JSON formatting
- **No rotation** — append-only, deferred to post-MVP
- **No consumer changes** — F13 handles interline integration separately
- **Bash `>>`** is sufficient for O_APPEND — no need for low-level `dd` or Python
- **`jq -nc`** for JSON construction — safe quoting, no injection risks
- **`date -u +%FT%TZ`** for ISO 8601 timestamps
- **`mkdir -p -m 0700`** for signal directory creation

### 7. Schema Validation

Each signal event must be:
```json
{"version":1,"layer":"coordination","icon":"lock","text":"reserved src/*.go","priority":3,"ts":"2026-02-14T12:00:00Z"}
```

Fields:
- `version` (int): Always 1 for now, forward compat
- `layer` (string): Always "coordination" for interlock signals
- `icon` (string): "lock" (reserve), "unlock" (release), "mail" (message)
- `text` (string): Human-readable description, <100 chars
- `priority` (int): 3 for reservations, 4 for messages (matches interline's priority system)
- `ts` (string): ISO 8601 UTC timestamp

At ~120-180 bytes per event, well within the 4KB O_APPEND atomicity guarantee.
