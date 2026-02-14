# Correctness Review: Intermute-Clavain Integration Brainstorm

**Reviewer:** Julik (fd-correctness agent)
**Date:** 2026-02-14
**Document:** `docs/brainstorms/2026-02-14-intermute-clavain-integration-brainstorm.md`
**Status:** Critical race conditions and concurrency bugs found

---

## Executive Summary

The integration design has **7 high-severity correctness bugs** that will cause data corruption, stale reads, and undefined behavior under concurrent load. All involve TOCTOU races, signal file atomicity, or missing synchronization. The SQLite WAL mode and circuit breaker are necessary but insufficient—the application-layer coordination logic has fundamental race windows.

**Critical path to fix:** Address findings 1-5 before any implementation. Findings 6-7 are medium severity but should be resolved before production use.

---

## Race Condition Analysis

### 1. PreToolUse:Edit TOCTOU Race (CRITICAL)

**Location:** Section 2b, PreToolUse:Edit hook (lines 214-228)

**The Race:**
```
Time  Agent A (editing router.go)          Agent B (editing router.go)
---   ---------------------------------     ---------------------------------
T0    PreToolUse hook fires
T1    GET /api/reservations/check
      → {conflict: false}
T2                                          PreToolUse hook fires
T3                                          GET /api/reservations/check
                                            → {conflict: false}
T4    Edit proceeds, writes to file
T5                                          Edit proceeds, writes to file
T6    PostToolUse completes                 PostToolUse completes

Result: Both agents edited router.go without reservations. Last write wins, silent data loss.
```

**Root cause:** Classic check-then-act pattern. The reservation state can change between the `check` API call and the actual Edit tool execution. Claude Code does not provide atomic "check-and-edit" semantics, and the hook has no way to block other agents during the window.

**Severity:** CRITICAL — Silent data corruption, guaranteed to happen under concurrent edits.

**Fix options:**

**Option 1 (Robust):** Optimistic concurrency with file content hashing.
- PreToolUse hook: Capture file hash (SHA256 of current content)
- PostToolUse hook: Compare file hash after edit
- If hash changed between Pre and Post (by another agent), roll back the edit and notify the agent
- Requires either: (a) Git-level rollback (`git checkout HEAD -- <file>`), or (b) Claude Code hook support for aborting/reverifying tool results
- **Problem:** Claude Code's Edit tool uses atomic write (temp file + rename), so rolling back requires Git or filesystem snapshots. Not all edits are committed immediately.

**Option 2 (Pragmatic):** Reservation-on-intent via PreToolUse with conditional check.
- PreToolUse hook: Atomically reserve the file if not already reserved by someone else
- Use a conditional create API: `POST /api/reservations?conflict_action=fail`
- If reservation succeeds → allow edit
- If reservation fails → block edit, return conflict message
- PostToolUse hook: Optionally release or extend TTL
- **Trade-off:** Creates implicit short-lived reservations. If edit is aborted (user cancels, hook fails), reservation lingers until TTL expires.

**Option 3 (Conservative):** Require explicit reservations before editing.
- PreToolUse hook: Check reservation. If file NOT reserved by this agent, block.
- Agent must call `intermute_reserve_files` MCP tool BEFORE editing.
- **Trade-off:** UX burden. Agent must remember to reserve. Reduces autonomy.

**Recommendation:** Option 2 with 60-second TTL. It's the smallest change that closes the race window without requiring agent intervention. The stale reservation sweep (1d) handles orphaned locks.

---

### 2. Signal File Atomicity (HIGH)

**Location:** Section 1b, SignalWriter (lines 83-101)

**The Race:**
```
Time  Goroutine A (Reserve event)          Goroutine B (Message event)
---   ---------------------------------     ---------------------------------
T0    Emit("reservation.created")
T1    open("/tmp/intermute-signal-...")
      → fd
T2    marshal JSON for reservation event
T3                                          Emit("message.received")
T4                                          open("/tmp/intermute-signal-...")
                                            → same fd (or overwrites)
T5    write(fd, reservation JSON)
T6                                          marshal JSON for message event
T7                                          write(fd, message JSON)
      close(fd)                             close(fd)

Result: Signal file contains partial JSON or only the last event. Interline reads corrupted JSON or misses events.
```

**Root cause:** No synchronization on signal file writes. Multiple goroutines in the Intermute service call `SignalWriter.Emit()` concurrently (Reserve, SendMessage, ReleaseReservation all trigger signals). Standard `os.OpenFile` + `Write` is not atomic for multiple writers.

**Severity:** HIGH — Corrupted signal files break statusline, cause interline to crash or display stale data.

**Fix:**

**Option 1 (File-per-event):** Write to `/tmp/intermute-signal-{project}-{agent}-{eventID}.json`, rotate/prune old files.
- Each event gets its own file with monotonic ID (timestamp + UUID suffix)
- Interline reads all files, sorts by timestamp, displays latest
- Prune files older than 5 minutes
- **Trade-off:** More filesystem churn, requires cleanup logic in both writer and reader.

**Option 2 (Append-only log with reader cursor):** Signal file is append-only JSONL (one event per line).
- Use `O_APPEND` flag for atomic writes (kernel guarantees writes <4KB are atomic on Linux)
- Interline maintains a cursor (line offset or event ID) and reads new lines since last poll
- Rotate file when >1MB
- **Trade-off:** Reader must parse JSONL and track cursor state.

**Option 3 (Per-agent mutex in SignalWriter):** Lock per agent signal file.
```go
type SignalWriter struct {
    dir   string
    locks map[string]*sync.Mutex  // key: "{project}-{agent}"
}

func (sw *SignalWriter) Emit(project, agentID string, event SignalEvent) error {
    key := fmt.Sprintf("%s-%s", project, agentID)
    sw.mu.Lock()
    if sw.locks[key] == nil {
        sw.locks[key] = &sync.Mutex{}
    }
    lock := sw.locks[key]
    sw.mu.Unlock()

    lock.Lock()
    defer lock.Unlock()
    // open, write, close
}
```
- Serializes writes to each signal file
- **Trade-off:** Mutex contention if many events for the same agent. Also doesn't help if Intermute is running multiple instances (not currently the case, but possible future).

**Recommendation:** Option 2 (append-only JSONL with O_APPEND). It's the most robust for both single-process and multi-process scenarios, and aligns with the "signal file as event stream" mental model.

**Implementation detail:** Go's `os.OpenFile` with `O_APPEND|O_WRONLY|O_CREATE` + single `Write()` call for <4KB payloads is atomic on Linux. For larger payloads, wrap with flock or per-file mutex.

---

### 3. Session Identity Collision (MEDIUM)

**Location:** Section 1c, Session Identity (lines 105-118)

**The Race:**
```
Time  Claude Session A                     Claude Session B
---   ---------------------------------     ---------------------------------
T0    SessionStart hook fires
      SESSION_ID="abc123def456..."
T1    POST /api/agents
      {session_id: "abc123def456..."}
T2    Intermute: check if session_id exists
      → no match, create new agent
      → returns agent_id=1
T3                                          SessionStart hook fires
                                            SESSION_ID="abc123def456..."
                                            (collision: same session_id!)
T4                                          POST /api/agents
                                            {session_id: "abc123def456..."}
T5                                          Intermute: check if session_id exists
                                            → MATCH (agent_id=1)
                                            → returns agent_id=1 (same!)

Result: Both sessions share the same agent_id. Reservations and messages are conflated. If Session A releases all reservations, Session B's reservations are also released.
```

**Likelihood:** Low with UUID-based session IDs (collision probability ~0 for practical purposes), but CLAUDE_SESSION_ID format is not specified. If it's a short hash or timestamp-based, collisions are plausible.

**Severity:** MEDIUM — If collision occurs, correctness guarantees break entirely. Two sessions masquerade as one agent.

**Fix:**

**Option 1 (Defense in depth):** Require session_id to be a UUID (validate on server).
```go
func (s *Server) RegisterAgent(req RegisterAgentRequest) (*Agent, error) {
    if req.SessionID != "" {
        if _, err := uuid.Parse(req.SessionID); err != nil {
            return nil, ErrInvalidSessionID
        }
    }
    // ... existing logic
}
```

**Option 2 (Composite key):** Use `(session_id, process_pid, hostname)` as the identity tuple.
- SessionStart hook includes PID and hostname in registration
- Intermute checks all three fields for match
- **Trade-off:** More complex identity logic, but eliminates collision risk entirely.

**Option 3 (Reject collision):** If session_id exists AND the agent is still active (heartbeat <5min ago), reject the registration.
```go
if existingAgent != nil {
    if time.Since(existingAgent.LastHeartbeat) < 5*time.Minute {
        return nil, ErrSessionIDInUse
    }
    // else: existing agent is stale, reuse the ID
}
```
- Forces the new session to pick a new session_id or wait for the old one to expire.

**Recommendation:** Combination of Option 1 (validate UUID format) and Option 3 (reject if active). This defends against both accidental short-hash collisions and intentional reuse.

**Additional concern:** CLAUDE_SESSION_ID might not be stable across `/clear` or session compaction. The design assumes session_id persists, but if Claude Code generates a new one on compaction, the agent will lose its identity. Document this assumption and test with real Claude Code session lifecycle.

---

### 4. Stale Reservation Sweep Race (HIGH)

**Location:** Section 1d, Stale Reservation Cleanup (lines 120-129)

**The Race:**
```
Time  Sweep Goroutine                      Agent A (normal operation)
---   ---------------------------------     ---------------------------------
T0    sweepStaleReservations() fires
T1    Query: SELECT * FROM reservations
      WHERE expires_at < now()
      → finds reservation R1 (expires_at = T0 - 1s)
T2                                          Agent A heartbeats (updates last_heartbeat)
T3                                          Agent A extends R1's TTL
                                            UPDATE reservations SET expires_at = T3 + 60s
                                            WHERE id = R1
T4    DELETE FROM reservations
      WHERE id = R1
      (sweep still holding old query result)
T5                                          Agent A attempts to edit file under R1
                                            → reservation gone, PreToolUse check fails

Result: Reservation deleted while agent was actively using it. Agent's edit is blocked despite holding a valid (extended) reservation.
```

**Root cause:** Multi-step read-then-delete with no transaction isolation. The sweep goroutine queries expired reservations, then deletes them in a separate statement. Between the query and delete, the reservation's `expires_at` could be updated by the owning agent. SQLite WAL mode provides snapshot isolation for reads, but the DELETE is a separate write transaction.

**Severity:** HIGH — Active agents lose reservations they just extended. Breaks the reservation guarantee.

**Fix:**

**Option 1 (Single-statement atomic delete):**
```sql
DELETE FROM reservations
WHERE expires_at < ? AND (
    -- Only delete if agent is ALSO inactive (belt-and-suspenders)
    agent_id NOT IN (
        SELECT id FROM agents WHERE last_heartbeat > ?
    )
)
```
- Single statement = single transaction. No window for concurrent UPDATE.
- Parameters: `now()` for first `?`, `now() - 5*time.Minute` for second `?`.
- **Trade-off:** More complex query. Relies on heartbeat freshness.

**Option 2 (Row-level lock with FOR UPDATE):**
```sql
-- Not directly supported in SQLite, but can simulate:
BEGIN IMMEDIATE;
SELECT id FROM reservations WHERE expires_at < ? FOR UPDATE;
DELETE FROM reservations WHERE id IN (...);
COMMIT;
```
- SQLite doesn't support `FOR UPDATE`, but `BEGIN IMMEDIATE` locks the entire database for writes.
- **Trade-off:** Blocks all other writes (Reserve, Release, Message) during sweep. Could cause contention.

**Option 3 (Optimistic concurrency with version field):**
- Add `version` column to reservations (integer, increment on each UPDATE)
- Sweep query captures `(id, version)` pairs
- Delete with: `DELETE FROM reservations WHERE id = ? AND version = ?`
- If version changed (agent extended TTL), DELETE affects 0 rows (silent no-op)
- **Trade-off:** Schema change, more complex application logic.

**Recommendation:** Option 1 (single-statement atomic delete with agent heartbeat check). It's the simplest fix that closes the race window without schema changes. The sweep only deletes reservations where BOTH conditions are true: (a) expired, and (b) agent is inactive. This prevents deleting actively-used reservations.

**Additional safeguard:** Emit signal files BEFORE deleting (not after). If delete fails mid-sweep, at least agents are notified of the attempt.

---

### 5. Auto-Reserve on PostToolUse Race (CRITICAL)

**Location:** Section 2d, Auto-Reserve on First Edit (lines 256-267)

**The Race:**
```
Time  Agent A (editing router.go)          Agent B (editing router.go)
---   ---------------------------------     ---------------------------------
T0    PreToolUse hook fires
      GET /api/reservations/check
      → {conflict: false}
T1    Edit tool executes, writes to file
T2                                          PreToolUse hook fires
                                            GET /api/reservations/check
                                            → {conflict: false}
                                            (no reservation yet, A's hasn't been created)
T3    PostToolUse hook fires                Edit tool executes, writes to file
T4    POST /api/reservations
      {path_pattern: "router.go", exclusive: true}
      → creates reservation R1 for Agent A
T5                                          PostToolUse hook fires
T6                                          POST /api/reservations
                                            {path_pattern: "router.go", exclusive: true}
                                            → CONFLICT or duplicate reservation?

Result: If Intermute allows duplicate exclusive reservations, both agents hold locks. If Intermute rejects the second, Agent B's edit already happened but PostToolUse fails. Data corruption either way.
```

**Root cause:** Multi-stage race with no atomicity. The PreToolUse check, Edit execution, and PostToolUse reserve are three separate operations with no transaction boundary. The auto-reserve happens AFTER the edit, so the file is already modified before the reservation is created.

**Severity:** CRITICAL — Worse than finding #1 because it LOOKS like it solves the race (via auto-reserve) but actually introduces a new race window.

**Fix:**

**Do not implement auto-reserve as PostToolUse.** The only correct auto-reserve pattern is PreToolUse with atomic check-and-reserve (see finding #1, Option 2). If you implement PostToolUse auto-reserve, you're adding a footgun.

**Alternative design (if auto-reserve is desired):**
- Auto-reserve in **PreToolUse** with a conditional create API:
  ```bash
  RESERVE_RESP=$(curl -sf -X POST "http://localhost:7338/api/reservations?conflict_action=fail" \
      -H "Content-Type: application/json" \
      -d "{\"agent_id\":\"${INTERMUTE_AGENT_ID}\",\"project\":\"$(pwd)\",\"path_pattern\":\"${FILE_PATH}\",\"exclusive\":true,\"reason\":\"auto-reserved on edit\",\"ttl\":60}")

  if [ $? -ne 0 ]; then
      # Reservation failed (conflict), block the edit
      echo '{"decision":"block","message":"Auto-reserve failed, file in use by another agent"}'
      exit 0
  fi

  # Reservation succeeded, allow edit
  ```
- In PostToolUse: Extend the TTL or convert to long-lived reservation (if needed)

**Recommendation:** Remove section 2d from the design entirely. If auto-reserve is a must-have, implement it as PreToolUse atomic check-and-reserve (finding #1 fix). Do not implement it as PostToolUse.

---

### 6. Circuit Breaker Concurrent State Access (MEDIUM)

**Location:** Section 1a, Circuit Breaker (lines 59-71)

**The Race:**
```go
type CircuitBreaker struct {
    state        State  // CLOSED, OPEN, HALF_OPEN
    failures     int
    threshold    int
    resetTimeout time.Duration
    lastFailure  time.Time
}

func (cb *CircuitBreaker) Execute(fn func() error) error {
    // RACE: Multiple goroutines read/write cb.state, cb.failures, cb.lastFailure
    if cb.state == OPEN {
        if time.Since(cb.lastFailure) > cb.resetTimeout {
            cb.state = HALF_OPEN  // WRITE without mutex
        } else {
            return ErrCircuitOpen
        }
    }

    err := fn()
    if err != nil {
        cb.failures++  // WRITE without mutex
        if cb.failures >= cb.threshold {
            cb.state = OPEN  // WRITE without mutex
            cb.lastFailure = time.Now()  // WRITE without mutex
        }
    } else {
        cb.failures = 0  // WRITE without mutex
        cb.state = CLOSED  // WRITE without mutex
    }
    return err
}
```

**Root cause:** Shared mutable state (`state`, `failures`, `lastFailure`) accessed by multiple goroutines (HTTP handlers, WebSocket handlers, sweep goroutine) with no synchronization.

**Failure modes:**
- Lost increments (two goroutines increment `failures` concurrently, one increment is lost)
- State transition corruption (goroutine A sets OPEN, goroutine B sets HALF_OPEN concurrently)
- Incorrect failure threshold (race between read and write of `failures`)

**Severity:** MEDIUM — Circuit breaker is a safety mechanism. If it fails open incorrectly (too sensitive), requests are rejected unnecessarily. If it fails closed incorrectly (too permissive), the DB is hammered during outages.

**Fix:**

Add a `sync.Mutex` to protect all state access:
```go
type CircuitBreaker struct {
    mu           sync.Mutex
    state        State
    failures     int
    threshold    int
    resetTimeout time.Duration
    lastFailure  time.Time
}

func (cb *CircuitBreaker) Execute(fn func() error) error {
    cb.mu.Lock()
    if cb.state == OPEN {
        if time.Since(cb.lastFailure) > cb.resetTimeout {
            cb.state = HALF_OPEN
        } else {
            cb.mu.Unlock()
            return ErrCircuitOpen
        }
    }
    cb.mu.Unlock()

    err := fn()

    cb.mu.Lock()
    defer cb.mu.Unlock()
    if err != nil {
        cb.failures++
        if cb.failures >= cb.threshold {
            cb.state = OPEN
            cb.lastFailure = time.Now()
        }
    } else {
        cb.failures = 0
        cb.state = CLOSED
    }
    return err
}
```

**Alternative (lock-free with atomic):** Use `sync/atomic` for `state` and `failures` (cast to int32), but `lastFailure` still needs a mutex (time.Time is not atomic-safe). The mutex approach is simpler and sufficient.

**Recommendation:** Add `sync.Mutex` to CircuitBreaker. This is a standard pattern from Go's circuit breaker libraries (e.g., gobreaker, circuitbreaker).

---

### 7. Cursor-Based Inbox Message Loss (MEDIUM)

**Location:** Section 2a, MCP Tools (line 193) — `intermute_fetch_inbox`

**The Race:**
```
Time  Agent A                              Intermute
---   ---------------------------------     ---------------------------------
T0    intermute_fetch_inbox(cursor=10)
T1                                          Query: SELECT * FROM messages
                                            WHERE id > 10
                                            → returns messages 11, 12, 13
T2    Process message 11
T3    **CRASH** (Claude Code session terminated, PreToolUse hook error, user Ctrl+C)
      Cursor never updated to 13
T4    (session restarts)
T5    intermute_fetch_inbox(cursor=10)
      → returns messages 11, 12, 13 AGAIN
      (reprocessing, idempotency issue)

Alternate failure mode:
T0    intermute_fetch_inbox(cursor=10)
      → returns messages 11, 12, 13
T1    Agent updates cursor to 13
T2                                          New message 14 arrives
T3                                          New message 15 arrives
T4    Agent crashes before processing 14, 15
T5    (session restarts)
T6    intermute_fetch_inbox(cursor=13)
      → returns 14, 15
      (no loss, but cursor was updated BEFORE processing)
```

**Root cause:** Cursor update timing is not specified. If cursor is updated BEFORE message processing completes, crashes cause reprocessing. If cursor is updated AFTER processing, crashes cause message loss (messages never marked as read).

**Severity:** MEDIUM — Depends on message idempotency requirements. If messages are informational (statusline updates), reprocessing is harmless. If messages are commands (release reservation, transfer task), reprocessing could cause incorrect state.

**Fix:**

**Option 1 (At-least-once delivery with idempotency):**
- Update cursor AFTER fetching but BEFORE processing
- Agent must handle duplicate messages (idempotent processing)
- Messages include a unique ID (already in schema as `id`)
- Agent tracks processed message IDs (in-memory set or persistent store)
- **Trade-off:** Requires idempotency discipline. More complex agent logic.

**Option 2 (At-most-once delivery with ACK):**
- Add an ACK mechanism: `POST /api/messages/{id}/ack`
- Cursor is server-side: "last ACKed message ID"
- Agent fetches messages, processes, then ACKs
- If agent crashes mid-processing, messages are re-delivered on next fetch
- **Trade-off:** Requires server-side ACK API and cursor storage per agent.

**Option 3 (Cursor as client-side state, no guarantees):**
- Document that cursor must be updated by the agent after SUCCESSFUL processing
- Agents store cursor in `CLAUDE_ENV_FILE` or a persistent file (`.intermute-cursor`)
- On crash, cursor reverts to last persisted value, messages are reprocessed
- **Trade-off:** Simple, but requires idempotent message handlers.

**Recommendation:** Option 3 (client-side cursor with idempotency requirement) for MVP. It's the simplest and aligns with the "signal file" design (agents poll and process, no server-side delivery guarantees). Document the idempotency requirement prominently in the MCP tool description.

**Long-term:** If Intermute evolves to support command messages (e.g., "transfer task X to Agent B"), implement Option 2 (server-side ACK) for exactly-once semantics.

---

## Additional Correctness Concerns

### A. Signal File Pollution on Multi-Agent Projects

**Scenario:** 10 agents working in the same project. Every reservation event writes signals to 10 files (one per agent). Every message writes to 10 files. 100 events/minute = 1000 signal file writes/minute.

**Risk:** Filesystem I/O saturation, signal file lag (interline reads stale data).

**Mitigation:** Throttle signal file writes (coalesce events within 1-second windows), or switch to a shared signal file with append-only JSONL (finding #2, Option 2).

### B. Reservation Expiry During Long-Running Edits

**Scenario:** Agent reserves `src/router.go` with 60s TTL, starts a large refactor (multi-step edit sequence). Edit takes 90 seconds. Reservation expires at T+60s. At T+70s, another agent's PreToolUse check sees no conflict, edits the same file.

**Risk:** Reservation TTL too short for complex workflows.

**Mitigation:** Auto-extend reservation TTL on heartbeat (agent sends heartbeat every 30s, Intermute extends all reservations held by that agent by +60s). Or allow agents to specify custom TTLs.

### C. Glob Pattern Reservation Ambiguity

**Scenario:** Agent A reserves `src/*.go` (shared). Agent B reserves `src/router.go` (exclusive). Which takes precedence?

**Risk:** Ambiguous conflict resolution. PreToolUse check might allow edits that violate exclusive reservations.

**Mitigation:** Define precedence rules in Intermute's conflict detection logic. Suggestion: Most specific pattern wins (exact path > glob with `**` > glob with `*`). Document clearly.

### D. Stop Hook Failure Modes

**Scenario:** Agent's Stop hook runs `curl -sf -X POST /api/agents/${AGENT_ID}/release-all`. Network timeout, Intermute server down, or agent ID invalid. `curl` fails silently (`-f` flag). Reservations are orphaned.

**Risk:** Stale reservations linger until sweep goroutine cleans them up (up to 60s delay).

**Mitigation:** Rely on stale reservation sweep (finding #4 fix). Also, log Stop hook failures (remove `-s` from curl, redirect to a debug log) so orphaned reservations are visible.

---

## Testing Requirements

To validate the fixes for findings 1-7, the following concurrency tests are required:

### T1. TOCTOU Race in PreToolUse (Finding #1)
**Test:** Two agents concurrently call PreToolUse for the same file path, with no reservations held.
**Expected:** Exactly one agent proceeds with edit. The other is blocked.
**Implementation:** Use Go test with goroutines, mock Claude Code tool calls, assert reservation creation order.

### T2. Signal File Concurrent Writes (Finding #2)
**Test:** 10 goroutines concurrently emit 100 signal events to the same agent's signal file.
**Expected:** All 100 events appear in the signal file (JSONL format), no corruption, no lost events.
**Implementation:** Parse signal file, count lines, verify JSON validity for each line.

### T3. Session Identity Collision (Finding #3)
**Test:** Two agents register with identical session_id strings, one second apart.
**Expected:** Second registration is rejected with `ErrSessionIDInUse`, or both agents get distinct agent_ids (composite key logic).
**Implementation:** Parallel POST /api/agents requests with same session_id.

### T4. Stale Reservation Sweep vs. Active Agent (Finding #4)
**Test:** Agent holds reservation R1, TTL expires, agent extends TTL 1ms before sweep goroutine runs DELETE.
**Expected:** DELETE does NOT remove R1 (agent's heartbeat is fresh, or extension succeeded).
**Implementation:** Mock time.Now() to control sweep timing, verify reservation persists.

### T5. Auto-Reserve Race (Finding #5)
**Test:** Two agents concurrently edit the same file with auto-reserve enabled (PostToolUse).
**Expected:** Both edits are blocked (if auto-reserve is removed), OR exactly one auto-reserve succeeds (if PreToolUse atomic reserve is implemented).
**Implementation:** Parallel Edit tool calls, assert reservation table state.

### T6. Circuit Breaker Concurrent State (Finding #6)
**Test:** 100 goroutines concurrently call CircuitBreaker.Execute(), half with errors (to trigger threshold).
**Expected:** Circuit opens exactly once when threshold is reached, no lost increments, no state corruption.
**Implementation:** Use `go test -race`, assert final state is deterministic.

### T7. Cursor-Based Inbox Reprocessing (Finding #7)
**Test:** Agent fetches messages, crashes mid-processing (simulated), restarts with same cursor.
**Expected:** Messages are reprocessed (at-least-once delivery).
**Implementation:** Mock message processing failure, verify duplicate delivery, test idempotency.

### T8. Reservation Expiry During Long Edit (Concern B)
**Test:** Agent reserves file, edit takes 90s, reservation TTL is 60s.
**Expected:** Reservation is auto-extended on heartbeat, remains valid throughout edit.
**Implementation:** Mock long-running edit, send heartbeats every 30s, verify reservation persists.

**Coverage target:** All 8 tests passing under `go test -race -count=100` (stress testing).

---

## Shutdown and Cleanup Behavior

### Missing: Graceful Shutdown for Intermute Service

The design does not specify what happens when the Intermute service is stopped (systemd restart, SIGTERM, server crash).

**Critical questions:**
1. Do in-flight HTTP requests complete, or are they aborted mid-write?
2. Are WebSocket connections closed gracefully with notification to agents?
3. Is the sweep goroutine canceled cleanly, or does it leave partial DELETEs?
4. Are signal files flushed before shutdown?

**Fix:** Intermute must implement graceful shutdown:
```go
func (s *Server) Shutdown(ctx context.Context) error {
    // 1. Stop accepting new HTTP requests
    s.httpServer.Shutdown(ctx)

    // 2. Close all WebSocket connections with close frame
    s.hub.BroadcastClose()

    // 3. Cancel sweep goroutine
    s.sweepCancel()

    // 4. Flush signal files (if buffered)
    s.signalWriter.Flush()

    // 5. Close SQLite DB (WAL checkpoint)
    s.store.Close()

    return nil
}
```

**Test:** Send SIGTERM to Intermute, verify all agent signal files are intact, no partial writes, DB is not corrupted.

---

## Observability Gaps

The design lacks instrumentation for detecting and debugging concurrency failures in production.

**Required metrics/logs:**
1. **Reservation conflict rate** — How often does PreToolUse block edits due to conflicts? (HIGH = too much locking, LOW = races are occurring)
2. **Signal file write latency** — How long does `SignalWriter.Emit()` take? (HIGH = contention or I/O bottleneck)
3. **Circuit breaker state transitions** — Log every CLOSED→OPEN transition with failure count and error type
4. **Stale reservation sweep stats** — How many reservations are deleted per sweep cycle? Which agents are they from?
5. **Cursor reprocessing count** — How often do agents re-fetch the same messages? (indicates crash-and-restart frequency)

**Implementation:** Add structured logging (zerolog or zap) to Intermute. Expose Prometheus metrics at `/metrics`.

**Alerting:** If reservation conflict rate >10/min, or circuit breaker opens, send alert (systemd OnFailure hook or external monitoring).

---

## Prioritized Fix Roadmap

### Phase 1: Critical Races (Must-Fix Before Any Implementation)
1. **Finding #1 (TOCTOU in PreToolUse)** — Implement atomic check-and-reserve in PreToolUse hook
2. **Finding #5 (Auto-Reserve Race)** — Remove PostToolUse auto-reserve from design, or move to PreToolUse
3. **Finding #2 (Signal File Atomicity)** — Switch to append-only JSONL with O_APPEND

**Estimated effort:** 2-3 days (Go service changes + hook script updates)

### Phase 2: High-Severity Concurrency Bugs (Must-Fix Before Multi-Agent Use)
4. **Finding #4 (Stale Reservation Sweep Race)** — Single-statement atomic delete with heartbeat check
5. **Finding #6 (Circuit Breaker Mutex)** — Add sync.Mutex to CircuitBreaker

**Estimated effort:** 1 day

### Phase 3: Medium-Severity Issues (Fix Before Production)
6. **Finding #3 (Session ID Collision)** — Validate UUID format + reject active collisions
7. **Finding #7 (Cursor-Based Inbox)** — Document idempotency requirement, add client-side cursor persistence
8. **Graceful Shutdown** — Implement Server.Shutdown() with context timeout
9. **Observability** — Add metrics and structured logging

**Estimated effort:** 2 days

### Phase 4: Defense in Depth (Harden for Production)
10. **Concern A (Signal File Pollution)** — Add event coalescing (1s window)
11. **Concern B (Reservation Expiry)** — Auto-extend TTL on heartbeat
12. **Concern C (Glob Ambiguity)** — Document precedence rules, add conflict detection tests
13. **Concern D (Stop Hook Failures)** — Log failures, monitor orphaned reservations

**Estimated effort:** 2 days

**Total estimated effort:** 7-8 days (one developer, full-time). Add 3-4 days for comprehensive test suite (T1-T8 above).

---

## Conclusion

The Intermute-Clavain integration design is architecturally sound (two-layer approach, companion plugin pattern, MCP server exposure), but the concurrency model has **7 critical/high-severity race conditions** that will cause data loss, stale reads, and undefined behavior under concurrent load.

**Primary root causes:**
1. Multi-step check-then-act patterns with no atomicity (TOCTOU races)
2. Shared mutable state with no synchronization (signal files, circuit breaker)
3. Missing specifications for crash recovery (cursor semantics, shutdown behavior)

**All findings are fixable** with the recommended changes. The fixes do not require architectural redesign—just rigorous application of concurrency primitives (mutexes, atomic operations, transactional writes) and defensive API design (conditional creates, conflict detection).

**Do not proceed with implementation until findings 1, 2, 4, 5, 6 are resolved.** These are not "nice to have" hardening—they are foundational correctness bugs that will manifest immediately under concurrent agent load.

**Post-fix validation:** Run the full test suite (T1-T8) under `go test -race -count=100` before declaring the integration production-ready. If any test fails under race detector or stress testing, treat it as a P0 blocker.

**Final note:** The brainstorm explicitly asks for flux-drive review. This correctness review should be paired with reviews from fd-architecture (Layer 1/2 separation), fd-quality (test coverage), and fd-safety (auth boundaries, signal file permissions). A single-domain review is insufficient for production readiness.

---

**Next steps:**
1. Present this review to the design author
2. Prioritize fixes (Phase 1 → Phase 2 → Phase 3 → Phase 4)
3. Implement fixes with paired unit tests (one test per finding)
4. Re-review after fixes before moving to implementation
5. Schedule follow-up reviews from other fd-* agents (architecture, safety, quality)
