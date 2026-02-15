# PRD: Interlock — Multi-Agent Same-Repo Coordination

## Problem

Multiple Claude Code sessions (human-driven tmux panes or `/clodex` orchestrated dispatch) editing the same repository have no coordination — agents overwrite each other's files, create merge conflicts, and lose work silently.

## Solution

Enrich intermute with resilience and concurrency primitives, then build an "interlock" companion plugin that provides Claude Code agents with explicit file reservation, messaging, and conflict detection — enforced via git pre-commit hooks as a mandatory backstop.

## Features

### F1: Circuit Breaker + Retry for SQLite Resilience
**What:** Add a 3-state circuit breaker and exponential-backoff retry with jitter to intermute's SQLite Store layer.
**Acceptance criteria:**
- [ ] `CircuitBreaker` struct with `sync.Mutex`, states CLOSED/OPEN/HALF_OPEN, threshold 5, reset 30s
- [ ] `RetryOnDBLock` function: 7 retries, 0.05s base, 25% jitter, targets "database is locked"
- [ ] Store interface methods wrapped with both circuit breaker and retry
- [ ] Circuit breaker state exposed via `/health` endpoint (`"circuit_breaker": "closed|open|half_open"`)
- [ ] Unit tests: breaker opens after threshold, resets after timeout, retry succeeds on transient lock
- [ ] `go test -race` passes on all new code

### F2: Session Identity with Collision Rejection
**What:** Allow agents to re-register with the same `session_id` after session restarts, while rejecting active collisions.
**Acceptance criteria:**
- [ ] `session_id` field added to `RegisterAgentRequest` (optional, must be valid UUID if provided)
- [ ] If `session_id` matches an existing agent with heartbeat >5min old AND all reservations expired, reuse identity (update heartbeat to now)
- [ ] If `session_id` matches an existing agent with heartbeat <5min old, return 409 Conflict
- [ ] On reuse: agent's heartbeat is updated to `now()`, preventing F3 sweep from deleting it mid-session
- [ ] Schema migration adds `session_id` column to `agents` table (nullable, unique when non-null)
- [ ] Agent names need not be unique — tracked internally by UUID, name is for human readability
- [ ] Tests: reuse after stale, reject active collision, null session_id creates new agent, concurrent reuse + F3 sweep is safe

### F3: Stale Reservation Cleanup
**What:** Background goroutine sweeps expired reservations atomically, with startup sweep for crash recovery.
**Acceptance criteria:**
- [ ] Sweep goroutine runs every 60s using single-statement atomic DELETE: `WHERE expires_at < ? AND agent_id NOT IN (SELECT id FROM agents WHERE last_heartbeat > ?)`
- [ ] Sweep NEVER deletes reservations held by agents with fresh heartbeats (even if expires_at passed — agent may be extending)
- [ ] On startup, release ALL reservations >5min old (crash recovery). Reservations <5min old preserved (agent may still be active post-crash)
- [ ] Graceful shutdown: cancel sweep context, checkpoint WAL, close DB cleanly
- [ ] Signal emission: on reservation deletion, emit an event via intermute's existing WebSocket/event system. Interlock polls or subscribes to these events and writes signal files (fire-and-forget — no retry if Interlock is offline)
- [ ] Tests: sweep deletes expired+inactive, preserves active, startup sweep clears stale, concurrent F2 reuse + F3 sweep is safe

### F4: Atomic Check-and-Reserve API
**What:** New API endpoint that atomically checks for conflicts and creates a reservation in one transaction.
**Acceptance criteria:**
- [ ] `POST /api/reservations?if_not_conflict=true` creates reservation or returns 409
- [ ] Single SQLite transaction: check conflict + insert reservation
- [ ] Response on 201: full reservation details
- [ ] Response on 409: conflict details (`held_by` = human-readable agent name, `pattern`, `reason`, `expires_at` ISO 8601)
- [ ] Existing `GET /api/reservations/check` preserved for read-only queries
- [ ] Tests: concurrent atomic reserves (only one succeeds), idempotent re-reserve by same agent

### F5: Unix Domain Socket Listener
**What:** Add Unix domain socket support to intermute alongside existing TCP listener.
**Acceptance criteria:**
- [ ] `--socket /var/run/intermute.sock` flag on intermute server
- [ ] Socket file created with mode 0660 (owner + group read/write)
- [ ] Socket file removed on graceful shutdown
- [ ] Health endpoint accessible via `curl --unix-socket`
- [ ] TCP listener remains available as fallback (both can run simultaneously)
- [ ] Tests: connect via socket, verify permission enforcement

### F6: Interlock MCP Server
**What:** Thin MCP stdio server in interlock companion that wraps intermute's HTTP/socket API, exposing 9 tools.
**Acceptance criteria:**
- [ ] `bin/interlock-mcp` binary (Go or shell+curl wrapper)
- [ ] 9 MCP tools: reserve_files, release_files, release_all, check_conflicts, my_reservations, send_message, fetch_inbox, list_agents, request_release
- [ ] Connects to intermute via Unix socket (fallback to TCP)
- [ ] `.mcp.json` in plugin root with correct `${CLAUDE_PLUGIN_ROOT}` paths
- [ ] Tools return structured JSON matching MCP protocol
- [ ] MCP tools handle intermute HTTP 5xx gracefully: return structured `{"error":"...","code":503,"retry_after":30}`, never crash
- [ ] MCP tools fail gracefully if intermute version lacks atomic reserve (fallback to non-atomic)
- [ ] Tests: each tool returns expected schema, error handling for intermute unavailable

### F7: Interlock Hooks
**What:** SessionStart, PreToolUse:Edit (advisory), and Stop hooks for agent lifecycle management.
**Acceptance criteria:**
- [ ] SessionStart hook: registers agent only if `~/.config/clavain/intermute-joined` exists (flag created by `/interlock:join`, removed by `/interlock:leave`)
- [ ] SessionStart hook: writes `/tmp/interlock-agent-${SESSION_ID}.json` with agent details
- [ ] SessionStart hook: exports `INTERMUTE_AGENT_ID` and `INTERMUTE_AGENT_NAME` to `CLAUDE_ENV_FILE`
- [ ] PreToolUse:Edit hook: advisory warning (not blocking) with structured recovery message:
  ```
  INTERLOCK: <file> reserved by <name> (<reason>, expires <time>)
  Recover: (1) work on other files, (2) intermute_request_release(to="<name>"), (3) wait for expiry
  Note: git commit will block until resolved.
  ```
- [ ] Stop hook: releases all reservations, cleans up temp files
- [ ] All hooks delegate to `interlock-*` scripts (not direct curl to intermute)
- [ ] All hooks skip silently if intermute unavailable (graceful degradation)
- [ ] If coordination was active and intermute becomes unreachable, emit one-time warning: "intermute coordination lost. Proceeding without reservation checks."

### F8: Interlock Commands
**What:** Four Claude Code commands for explicit coordination management.
**Acceptance criteria:**
- [ ] `/interlock:join [--name <label>]` — registers agent, sets onboarding flag, shows active agents
- [ ] `/interlock:leave` — releases all reservations, deregisters, removes onboarding flag
- [ ] `/interlock:status` — lists active agents with reservations, heartbeat, and human-readable names
- [ ] `/interlock:setup` — self-installing: checks/downloads intermute binary, creates systemd unit, starts service
- [ ] Agent name precedence: user-provided `--name` label > tmux pane title > `claude-{session:0:8}` fallback
- [ ] `/interlock:join` creates `~/.config/clavain/intermute-joined` flag; `/interlock:leave` removes it
- [ ] `/interlock:status` shows `(name, agent-id)` pairs to disambiguate name collisions

### F9: Signal File Adapter
**What:** Interlock generates normalized append-only JSONL signal files for interline consumption.
**Acceptance criteria:**
- [ ] Signal files written to `/var/run/intermute/signals/{project-slug}-{agent-id}.jsonl`
- [ ] Signal directory created with mode 0700 on setup
- [ ] Append-only writes using `O_APPEND` flag (atomic for <4KB payloads on Linux)
- [ ] Normalized schema: `{"version":1,"layer":"coordination","icon":"lock","text":"...","priority":3,"ts":"..."}`
- [ ] Schema includes `version: 1` field for forward compatibility
- [ ] Signals emitted on: reservation create, reservation release, message received
- [ ] Signal events are <200 bytes each (well within 4KB O_APPEND atomicity guarantee)
- [ ] Signal file rotation deferred to post-MVP (append-only, no rotation initially; revisit if files exceed 10MB in practice)

### F10: Git Pre-Commit Hook Generator
**What:** Script that installs a git pre-commit hook enforcing file reservations at commit time.
**Acceptance criteria:**
- [ ] `interlock-install-hooks` script generates `.git/hooks/pre-commit`
- [ ] Hook extracts changed files from `git diff --cached --name-only`
- [ ] Hook checks each file against intermute's conflict detection API
- [ ] Hook aborts commit with clear, actionable error message:
  ```
  ERROR: Cannot commit. Reserved files detected:
    - src/router.go (reserved by claude-tmux-2: "auth refactor", expires in 8m)
  Resolve: (1) /interlock:request-release claude-tmux-2, (2) wait 8m, (3) git commit --no-verify (risk: overwrite)
  ```
- [ ] Hook passes if no intermute agent is registered (graceful degradation)
- [ ] Hook skippable with `--no-verify` (escape hatch documented)

### F11: Coordination Skills
**What:** Two skills teaching agents the reservation workflow and conflict recovery protocol.
**Acceptance criteria:**
- [ ] `coordination-protocol` SKILL.md: reserve → work → release workflow, best practices
- [ ] `conflict-recovery` SKILL.md: handle blocked edits (check status, work elsewhere, request release, escalate)
- [ ] Skills reference MCP tool names for discoverability
- [ ] Skills are concise (<100 lines each)

### F12: Clavain Integration
**What:** Shim delegation, doctor check, and setup docs for interlock in Clavain.
**Acceptance criteria:**
- [ ] `_discover_interlock_plugin()` function in `hooks/lib.sh` (env var → find in plugin cache)
- [ ] SessionStart hook delegates to interlock if installed
- [ ] Doctor check 3f: interlock plugin installed, intermute service running, agent registered
- [ ] `commands/setup.md` updated to include interlock installation from marketplace
- [ ] `INTERLOCK_ROOT` env var support for development override

### F13: interline Signal Integration
**What:** interline reads interlock's normalized signal files and shows persistent coordination status.
**Acceptance criteria:**
- [ ] Reads `/var/run/intermute/signals/{project-slug}-{agent-id}.jsonl` (latest line)
- [ ] Coordination layer inserted into priority: dispatch > **coordination** > bead > workflow > clodex
- [ ] Persistent indicator when coordination active: `N agents | M files reserved` (shown only when `INTERMUTE_AGENT_ID` is set)
- [ ] Signal-based updates: reservation changes, new messages
- [ ] Gracefully ignores signal files with unknown schema version (logs warning, falls back to "no coordination status")
- [ ] Falls back gracefully when no signal file exists

## Success Criteria

### Technical
- [ ] Atomic check-and-reserve API prevents TOCTOU races (verified by `go test -race -count=100`)
- [ ] Stale reservation cleanup has zero false positives in 1-week stress test
- [ ] Signal file writes incur <10ms latency under 10 concurrent agents
- [ ] Circuit breaker correctly opens/closes under sustained SQLite lock contention

### User
- [ ] Zero silent file overwrites in multi-agent test runs with coordination active
- [ ] Conflict resolution guided by skills (agents use `intermute_request_release` without manual escalation)
- [ ] `/interlock:setup` completes in <30s on a fresh system (download + start + register)

### Post-Launch Measurement (after 2 weeks)
- [ ] Track: % of multi-agent sessions using `/interlock:join`
- [ ] Track: conflict detection events per session (expect <5/session average)
- [ ] Track: conflict resolution time (time from detection to release)
- [ ] Decision point: revisit auto-reserve if >3 users request in first month

## Non-goals

- **Auto-reserve on edit** — Removed. Creates lock contention, TOCTOU races, and false sense of safety.
- **Tool filtering profiles** — 9 MCP tools at ~1,800 tokens is 0.9% of context budget. No pressure.
- **Dual persistence (DB + Git)** — Audit trail without a reader. SQLite is sufficient.
- **Commit queue with batching** — No measured bottleneck for commit frequency.
- **Contact policies** — Over-engineering for trusted local agents.
- **Cross-project product bus** — Premature. Revisit when cross-repo coordination is needed.
- **MCP server inside intermute** — Avoids dual-protocol anti-pattern. Interlock owns the MCP layer.
- **Blocking PreToolUse:Edit** — Advisory only. Git pre-commit hooks provide mandatory enforcement.

## Dependencies

- **intermute** (`/root/projects/intermute/`) — Go 1.24, SQLite, existing agent registry + file reservations API
- **interline** (`/root/projects/interline/`) — Statusline renderer, 4-layer priority system
- **Clavain** (`/root/projects/Clavain/`) — Plugin ecosystem, hooks/lib.sh shim delegation pattern
- **interagency-marketplace** — For publishing interlock companion

## Open Questions

None — all 5 original questions resolved by flux-drive review:
1. Auto-reserve: NO (removed)
2. Reservation granularity: BOTH (glob patterns, default file-level)
3. Message protocol: Signals only, no broadcast messages
4. Service lifecycle: Hybrid (start on join, idle timeout 15min)
5. Graceful degradation: Silent skip (matches interphase)
