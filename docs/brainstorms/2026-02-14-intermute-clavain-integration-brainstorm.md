# Brainstorm: Clavain + intermute Integration for Multi-Agent Same-Repo Coordination

**Date:** 2026-02-14
**Status:** Reviewed (post flux-drive review)
**Context:** How to make Clavain autonomously work with intermute for multiple agents editing the same repo without worktrees

## Problem Statement

Multiple Claude Code sessions (human-driven or orchestrated via `/clodex`) need to work on the same repository simultaneously without worktrees. Currently there is no coordination — agents can edit the same files, create merge conflicts, and overwrite each other's work.

**Two use cases:**
1. **Concurrent sessions** — Multiple `cc` terminal sessions (e.g., tmux panes) working on different parts of the same repo
2. **Orchestrated dispatch** — Clavain dispatches multiple agents (via `/clodex`, subagents) to work in parallel on a plan

## Existing Systems

### intermute (`/root/projects/intermute/`)

Go service with HTTP+WebSocket API, SQLite storage. Already has:
- **Agent registry** — Register/heartbeat/list agents per project
- **Messaging** — Project-scoped messages with threading, cursor-based inboxes, WebSocket delivery
- **File reservations** — Glob-pattern exclusive/shared locks with expiry (`file_reservations` table)
- **Domain entities** — Specs/epics/stories/tasks/insights/sessions
- **Auth** — Bearer token auth with project scoping, localhost bypass
- **Go client** — `client/client.go` SDK for agent communication
- **Autarch integration** — Embedded server, TUI coordination

**111 tests, 75.5% coverage, port 7338**

### mcp_agent_mail (reference: github.com/Dicklesworthstone/mcp_agent_mail)

Python MCP server (~40 tools) with patterns worth adapting:
- **Circuit breaker** for DB operations (3-state: CLOSED/OPEN/HALF_OPEN)
- **Retry with jitter** for SQLite lock contention
- **Signal files** for push notifications (filesystem-based, no WebSocket needed)
- **Session/window identity** (survive session restarts without re-registration)
- **Git-level enforcement** (pre-commit/pre-push hooks check reservations)
- **Stale lock detection** (PID-based cleanup of orphaned reservations)

### Clavain (`/root/projects/Clavain/`)

Plugin ecosystem with existing coordination patterns:
- File-based sideband: `/tmp/clavain-dispatch-*.json`, `/tmp/clavain-bead-*.json`
- SessionStart hook captures `CLAUDE_SESSION_ID` via `CLAUDE_ENV_FILE`
- Shim delegation pattern: env var → `find` in plugin cache
- 7 hooks, 27 skills, 36 commands, 5 agents

## Design: Two-Layer Architecture (Revised)

### Design Principles (from flux-drive review)

1. **intermute stays protocol-agnostic** — HTTP API only, no MCP server. Interlock owns Claude Code integration.
2. **Explicit coordination** — No auto-reserve. Agents explicitly reserve files before editing.
3. **Atomic operations** — No check-then-act patterns. Use conditional create APIs to close TOCTOU races.
4. **Defense-in-depth** — Git pre-commit hooks as enforcement backstop, not just advisory hooks.
5. **Graceful degradation** — Silent skip when intermute is unavailable (matches interphase pattern).
6. **Visible coordination** — Persistent statusline, explicit join, human-readable agent names.

### Layer 1: intermute Enrichments (Go-side)

4 core enrichments only. No MCP server, no signal files, no git hook generation in intermute.

#### 1a. Resilience: Circuit Breaker + Retry

```go
// internal/resilience/circuit_breaker.go
type CircuitBreaker struct {
    mu           sync.Mutex  // Required: concurrent goroutine access
    state        State       // CLOSED, OPEN, HALF_OPEN
    failures     int
    threshold    int         // default: 5
    resetTimeout time.Duration  // default: 30s
    lastFailure  time.Time
}

// Wraps Store interface — any method failure counts toward breaker
func (cb *CircuitBreaker) Execute(fn func() error) error
```

```go
// internal/resilience/retry.go
// Exponential backoff + 25% jitter on "database is locked"
// 7 retries, 0.05s base delay
func RetryOnDBLock(fn func() error) error
```

**Integration:** Wrap `Store` interface methods in `sqlite.go` with both circuit breaker and retry.

#### 1b. Session Identity (Survive Restarts)

```go
// Addition to POST /api/agents request
type RegisterAgentRequest struct {
    Name         string `json:"name"`
    Project      string `json:"project"`
    SessionID    string `json:"session_id,omitempty"`    // Must be valid UUID
    Capabilities []string `json:"capabilities,omitempty"`
}
```

**Behavior:**
- Validate `session_id` is a valid UUID (reject malformed values)
- If `session_id` matches an existing agent AND that agent's last heartbeat is >5 minutes old, reuse the identity
- If `session_id` matches an existing agent AND that agent is still active (heartbeat <5min), reject with 409 Conflict
- This lets agents survive Claude Code session restarts while preventing identity collisions

#### 1c. Stale Reservation Cleanup

```go
// Background goroutine in cmd/intermute/main.go
// Sweeps every 60s using single-statement atomic DELETE:
//
// DELETE FROM reservations
// WHERE expires_at < ? AND agent_id NOT IN (
//     SELECT id FROM agents WHERE last_heartbeat > ?
// )
//
// This closes the race where an agent extends TTL between SELECT and DELETE.
func (s *Server) sweepStaleReservations(ctx context.Context)
```

**Startup sweep:** On launch, release ALL reservations >5 minutes old (handles crash recovery).

**Graceful shutdown:** On SIGTERM/SIGINT, flush signal files, checkpoint WAL, close DB cleanly.

#### 1d. Atomic Check-and-Reserve API

```
POST /api/reservations?if_not_conflict=true
```

**Behavior:**
- Atomically checks for conflicts AND creates reservation in a single transaction
- Returns 201 Created with reservation details if successful
- Returns 409 Conflict with conflict details if the file is already reserved
- Eliminates the TOCTOU race between separate check and reserve calls

```
GET /api/reservations/check?project=...&path=src/router.go
```

Returns conflict status (existing API, kept for read-only queries).

### Layer 2: Interlock Companion Plugin

New `interlock` companion plugin following the inter* pattern. Owns ALL Claude Code integration.

#### 2a. MCP Server (in interlock, wraps HTTP calls)

Thin MCP shim that wraps intermute's HTTP API. Lives in interlock, NOT in intermute.

```json
// interlock/.mcp.json
{
  "mcpServers": {
    "intermute": {
      "type": "stdio",
      "command": "${CLAUDE_PLUGIN_ROOT}/bin/interlock-mcp",
      "env": {
        "INTERMUTE_SOCKET": "/var/run/intermute.sock",
        "INTERMUTE_PROJECT": "${CWD}"
      }
    }
  }
}
```

**MCP Tools (9 tools):**

| Tool | Description |
|------|-------------|
| `intermute_reserve_files` | Atomically reserve file patterns (exclusive/shared) with reason and TTL |
| `intermute_release_files` | Release specific reservations by ID or pattern |
| `intermute_release_all` | Release all my reservations |
| `intermute_check_conflicts` | Check if paths conflict with active reservations |
| `intermute_my_reservations` | List my current reservations |
| `intermute_send_message` | Send message to another agent (by name or broadcast) |
| `intermute_fetch_inbox` | Get messages since last cursor (client-side cursor, at-least-once delivery) |
| `intermute_list_agents` | See who else is working in this repo |
| `intermute_request_release` | Send structured release request to reservation holder |

#### 2b. Interlock Hooks

**SessionStart hook** (`hooks/session-start.sh`):

```bash
# Register with intermute via interlock (delegates protocol details)
# Only if user has explicitly joined coordination
if [ -f ~/.config/clavain/intermute-joined ] && command -v interlock-register >/dev/null 2>&1; then
    interlock-register "$SESSION_ID" "$(pwd)" > /tmp/interlock-agent-${SESSION_ID}.json
    AGENT_ID=$(jq -r '.id' /tmp/interlock-agent-${SESSION_ID}.json)
    AGENT_NAME=$(jq -r '.name' /tmp/interlock-agent-${SESSION_ID}.json)
    echo "INTERMUTE_AGENT_ID=${AGENT_ID}" >> "$CLAUDE_ENV_FILE"
    echo "INTERMUTE_AGENT_NAME=${AGENT_NAME}" >> "$CLAUDE_ENV_FILE"
fi
```

**PreToolUse:Edit hook** — Advisory conflict check (non-blocking):

The PreToolUse hook checks reservations but does NOT block edits. Instead, it warns the agent and injects recovery instructions. Git pre-commit hooks provide the actual enforcement backstop.

```bash
if [ -n "$INTERMUTE_AGENT_ID" ]; then
    FILE_PATH=$(echo "$TOOL_INPUT" | jq -r '.file_path')
    CONFLICT=$(interlock-check "$FILE_PATH" 2>/dev/null)
    if echo "$CONFLICT" | jq -e '.conflict == true' >/dev/null 2>&1; then
        HELD_BY=$(echo "$CONFLICT" | jq -r '.held_by')
        REASON=$(echo "$CONFLICT" | jq -r '.reason')
        EXPIRES=$(echo "$CONFLICT" | jq -r '.expires_in')
        echo "{\"decision\":\"warn\",\"message\":\"File reserved by ${HELD_BY}: ${REASON} (expires in ${EXPIRES}). Consider: intermute_request_release, work on other files, or wait for expiry. Git pre-commit will enforce.\"}"
        exit 0
    fi
fi
```

**Stop hook** (`hooks/stop.sh`):

```bash
# Release all reservations and deregister
if [ -n "$INTERMUTE_AGENT_ID" ]; then
    interlock-release-all "$INTERMUTE_AGENT_ID" 2>/dev/null || true
    rm -f /tmp/interlock-agent-${SESSION_ID}.json
fi
```

#### 2c. Interlock Commands and Skills

**Commands:**
- `/interlock:join [--name <label>]` — Explicit opt-in to coordination. Registers agent, explains behavior, shows active agents.
- `/interlock:leave` — Opt-out. Releases all reservations, deregisters.
- `/interlock:status` — Show active agents, their reservations, and heartbeat status.
- `/interlock:setup` — Self-installing setup. Downloads intermute binary, creates systemd unit, starts service, registers session.

**Skills:**
- `coordination-protocol` — Teaches agents the reservation workflow: list files, reserve, work, release.
- `conflict-recovery` — Teaches agents how to handle blocked edits: check status, work elsewhere, request release, escalate.

#### 2d. Signal Files (owned by interlock, not intermute)

Interlock generates normalized signal files for interline consumption:

```bash
# interlock writes normalized signals to /var/run/intermute/signals/
# Format: append-only JSONL with O_APPEND (atomic <4KB writes on Linux)
# One file per agent: /var/run/intermute/signals/{project-slug}-{agent-id}.jsonl
```

**Normalized schema for interline:**
```json
{"layer": "coordination", "icon": "lock", "text": "BlueTiger reserved src/*.go", "priority": 3, "ts": "2026-02-14T12:00:00Z"}
```

interline reads interlock's normalized format, NOT intermute's raw data. This insulates interline from intermute schema changes.

#### 2e. Git Hook Generator

Interlock generates git pre-commit hooks (defense-in-depth enforcement):

```bash
# interlock-install-hooks generates .git/hooks/pre-commit
# The hook:
# 1. Extracts changed files from git diff --cached
# 2. Checks each against intermute's conflict detection API
# 3. Aborts commit if conflicting reservation exists (not held by current agent)
# 4. Outputs clear error message with recovery instructions
```

This is the actual enforcement layer. PreToolUse hooks are advisory; git hooks are mandatory.

### Layer 3: Clavain Integration (minimal)

#### 3a. Shim Delegation in SessionStart

```bash
# Clavain's hooks/session-start.sh — add to existing hook
# Delegates to interlock if installed (matches interphase pattern)
if command -v interlock-register >/dev/null 2>&1; then
    interlock-register "$SESSION_ID" "$(pwd)" > /tmp/interlock-agent-${SESSION_ID}.json 2>/dev/null || true
fi
```

#### 3b. Environment Setup

Read interlock's output file to set `INTERMUTE_AGENT_ID` in `CLAUDE_ENV_FILE`.

#### 3c. Doctor Check

Add check 3f to `commands/doctor.md`:
```
3f. Interlock companion
    ✓ Interlock plugin installed (v0.1.0)
    ✓ intermute service running
    ✓ Agent registered
```

### Layer 4: interline Integration (minimal)

Read interlock's normalized signal files (not intermute's raw data):

```bash
# Coordination layer added to interline's 4-layer priority system
# Priority: dispatch state > coordination > bead context > workflow phase > clodex mode
INTERLOCK_SIGNAL="/var/run/intermute/signals/$(basename $(pwd))-${AGENT_ID}.jsonl"
if [ -f "$INTERLOCK_SIGNAL" ]; then
    LATEST=$(tail -1 "$INTERLOCK_SIGNAL")
    LAYER=$(echo "$LATEST" | jq -r '.layer')
    if [ "$LAYER" = "coordination" ]; then
        echo "$(echo "$LATEST" | jq -r '.text')"
    fi
fi
```

**Persistent indicator** when coordination is active:
```
3 agents | 2 files reserved
```

## Companion Plugin Decision

**Decision: Option B — "interlock" companion** (confirmed by flux-drive review)

Reasons:
1. Follows established inter* extraction pattern (interphase, interflux, interline, interpath, interwatch)
2. Keeps Clavain's hook count manageable (already at 7)
3. Allows non-Clavain users of intermute to also use coordination
4. Clear ownership: interlock owns coordination UX + protocol, intermute owns state + API
5. MCP server in interlock (not intermute) avoids dual-protocol anti-pattern

## Adaptation Checklist from mcp_agent_mail

| Pattern | Adapt? | Location | Priority | Notes |
|---------|--------|----------|----------|-------|
| Circuit breaker (3-state) | Yes | intermute | Must-have | Wrap Store interface, requires sync.Mutex |
| Retry with jitter | Yes | intermute | Must-have | SQLite WAL contention |
| Session identity (survive restarts) | Yes | intermute | Must-have | UUID validation + active collision rejection |
| Stale lock detection + cleanup | Yes | intermute | Must-have | Atomic single-statement DELETE + startup sweep |
| Signal files (push notification) | Yes | Interlock | Must-have | Append-only JSONL with O_APPEND, normalized schema |
| Git-level enforcement hooks | Yes | Interlock | Must-have | Pre-commit hook generator script |
| Tool filtering profiles | No | — | Cut | 9 MCP tools = ~1,800 tokens = 0.9% of context budget |
| Window identity (tmux UUID) | No | — | Cut | Redundant with CLAUDE_SESSION_ID |
| Dual persistence (DB + Git) | No | — | Cut | Audit trail without a reader |
| Commit queue with batching | No | — | Cut | No measured bottleneck |
| Auto-registration of recipients | No | — | Cut | Contact policies are over-engineering |
| Contact policies | No | — | Cut | Trusted local agents, no adversarial model |

## Open Questions — Resolved

1. **Auto-reserve on by default?** **NO.** Removed entirely. Require explicit `intermute_reserve_files` calls. Auto-reserve creates lock contention, race conditions, and false sense of safety. (All 4 reviewers agreed.)

2. **Reservation granularity?** **BOTH.** intermute's glob pattern support handles file-level and directory-level. Default to file-level (safest). Log warning if glob matches >10 files.

3. **Message protocol for reservations?** **Signals only, no messages.** Reservation events emit signal files, not inbox messages. Opt-in broadcast via `intermute_reserve_files(..., notify=true)`.

4. **Systemd vs. on-demand?** **Hybrid with idle timeout.** Start on first `/interlock:join`. Idle timeout (15 min with no registered agents) shuts down. Systemd unit available for always-on users.

5. **Graceful degradation?** **Silent skip** (matches interphase pattern). If intermute is unavailable, hooks skip silently. If coordination was active and is lost, emit one-time "coordination lost" warning.

## Security Mitigations (from safety review)

1. **Unix domain socket** — intermute listens on `/var/run/intermute.sock` (mode 0660) instead of TCP port 7338. Eliminates port-squat risk, provides kernel-enforced access control.

2. **Restricted signal directory** — `/var/run/intermute/signals/` (mode 0700, owned by intermute process). Prevents signal file injection from world-writable `/tmp`.

3. **Git pre-commit enforcement** — Mandatory backstop. PreToolUse hooks are advisory; git hooks are enforcement. Agents cannot bypass git hooks without `--no-verify`.

4. **Startup sweep** — On intermute launch, release all reservations >5 minutes old. Prevents deadlock from crashed sessions.

5. **Rollback procedure** — DB snapshots before upgrades. `POST /api/admin/release-all` emergency API. Fresh-state recovery via DB deletion.

## Concurrency Fixes (from correctness review)

1. **Atomic check-and-reserve** — `POST /api/reservations?if_not_conflict=true` closes the TOCTOU race window.

2. **Append-only JSONL signals** — `O_APPEND` flag for atomic writes <4KB. Eliminates signal file corruption.

3. **Single-statement stale DELETE** — Atomic delete with heartbeat check prevents sweeping active reservations.

4. **sync.Mutex on CircuitBreaker** — All state access synchronized. Standard Go pattern.

5. **Client-side cursor with idempotency** — Inbox messages are at-least-once delivery. Agents must handle reprocessing.

6. **Reservation TTL auto-extension** — Heartbeat extends all held reservations by +60s, preventing expiry during long edits.

## Migration Path

### Phase 1: intermute Core (1 day)
1. Add circuit breaker + retry to `internal/store/sqlite.go`
2. Add `session_id` field to agent registration (UUID validation + active collision rejection)
3. Add stale lock cleanup goroutine (atomic DELETE + startup sweep)
4. Add atomic check-and-reserve API (`POST /api/reservations?if_not_conflict=true`)
5. Add graceful shutdown (WAL checkpoint, signal flush)
6. Add Unix domain socket listener option
7. Tests: 111 → 125+

### Phase 2: Interlock Companion (1-2 days)
1. Create `/root/projects/interlock/` repo
2. Add MCP server (stdio, wraps HTTP/Unix socket calls to intermute)
3. Add 9 MCP tools
4. Add SessionStart/Stop hooks
5. Add signal file adapter (append-only JSONL, normalized schema)
6. Add git pre-commit hook generator
7. Add `/interlock:join`, `/interlock:leave`, `/interlock:status`, `/interlock:setup` commands
8. Add `coordination-protocol` and `conflict-recovery` skills
9. Tests: 20+ structural tests

### Phase 3: Clavain + interline Integration (0.5 day)
1. Add shim delegation to Clavain's SessionStart hook
2. Add discovery function `_discover_interlock_plugin()` to `hooks/lib.sh`
3. Update interline to read interlock's normalized signals
4. Add doctor check 3f (interlock companion)
5. Update setup.md to install interlock from marketplace

**Total: ~3 days implementation.**

## Flux-Drive Review Summary

Reviewed by 4 agents (fd-architecture, fd-safety, fd-correctness, fd-user-product). Key convergent findings:

| Finding | Agents | Resolution |
|---------|--------|------------|
| Remove auto-reserve | All 4 | Removed entirely |
| MCP server in interlock, not intermute | Architecture, Safety | Moved to interlock |
| TOCTOU race in PreToolUse:Edit | Correctness, Safety | Atomic check-and-reserve API |
| Explicit join, not silent registration | User-Product, Architecture | `/interlock:join` command required |
| Unix domain socket, not TCP | Safety | `/var/run/intermute.sock` |
| Git pre-commit enforcement | Safety, Correctness | Defense-in-depth, mandatory backstop |
| Signal file atomicity | Correctness | Append-only JSONL with O_APPEND |
| Agent recovery protocol | User-Product | `conflict-recovery` skill + structured block messages |

**Full review documents:** `docs/research/{architecture,safety,correctness,user-product}-review-of-brainstorm.md`

---

*Brainstorm complete. Validated by flux-drive multi-agent review. Ready for `/clavain:strategy` → `/clavain:write-plan`.*
