# Research: F3 Stale Reservation Cleanup — Codebase Analysis

**Date:** 2026-02-14
**Bead:** Clavain-1e5q
**Target Repo:** `/root/projects/intermute/`

## Codebase Structure Analysis

### Storage Layer

**`internal/storage/sqlite/sqlite.go`** (1150 lines)
- `Store` struct wraps `dbHandle` (interface for `*sql.DB` via `queryLogger`)
- `New(path)` opens file-backed DB, `NewInMemory()` for tests
- `Reserve()` uses a transaction: checks active reservations for overlap, then inserts
- `ReleaseReservation()` does atomic `UPDATE ... SET released_at = ? WHERE id = ? AND agent_id = ? AND released_at IS NULL`
- `ActiveReservations()` filters with `WHERE released_at IS NULL AND expires_at > ?`
- `Heartbeat()` updates `last_seen` on agents table
- No `Close()` method exists on Store — only the inner `dbHandle` has `Close()`
- The `dbHandle` interface includes `Close() error` so Store can call `s.db.Close()`

**`internal/storage/sqlite/querylog.go`** (74 lines)
- `dbHandle` interface: `Exec`, `Query`, `QueryRow`, `Begin`, `BeginTx`, `Close`
- `queryLogger` wraps `*sql.DB` with slow query logging (100ms threshold)
- The logger's `Close()` delegates to `inner.Close()`

**`internal/storage/sqlite/schema.sql`** (234 lines)
- `file_reservations` table: id, agent_id, project, path_pattern, exclusive, reason, created_at, expires_at, released_at
- `agents` table: id, session_id, name, project, capabilities_json, metadata_json, status, created_at, last_seen
- Indexes: `idx_reservations_active` is a partial index on `(project, expires_at) WHERE released_at IS NULL`

**Key observation:** The schema uses `last_seen` (not `last_heartbeat`). The PRD acceptance criteria references `last_heartbeat` but the actual column is `last_seen`. The sweep SQL must use `last_seen`.

### Core Models

**`internal/core/models.go`**
- `Reservation` struct: ID, AgentID, Project, PathPattern, Exclusive, Reason, TTL, CreatedAt, ExpiresAt, ReleasedAt
- `Agent` struct: ID, SessionID, Name, Project, Capabilities, Metadata, Status, LastSeen, CreatedAt
- `EventType` constants: message.created, message.ack, message.read, agent.heartbeat
- No reservation event types exist yet

**`internal/core/domain.go`**
- Additional event types for domain entities (spec.created, task.completed, etc.)
- `ErrNotFound` and `ErrConcurrentModification` sentinel errors

### Event System

**`internal/ws/gateway.go`** (155 lines)
- `Hub` struct with mutex-protected connection map: project -> agent -> set of websocket connections
- `Broadcast(project, agent string, event any)` sends to matching connections
- Events are arbitrary `any` values, encoded as JSON via `wsjson.Write`

**`internal/http/service.go`**
- `Service` struct has `store` and `bus Broadcaster`
- `Broadcaster` interface: single `Broadcast(project, agent string, event any)` method
- `DomainService` extends `Service` with `domainStore`

**Broadcast patterns in handlers:**
- Message events: `s.bus.Broadcast(project, agent, map[string]any{"type": "message.created", ...})`
- Domain events: `s.bus.Broadcast(project, "", map[string]any{"type": "spec.created", ...})`
- Reservation events: NOT emitted currently — `handlers_reservations.go` never calls `s.bus.Broadcast`

### Server Lifecycle

**`cmd/intermute/main.go`** (152 lines)
- `serveCmd()` creates: `store` -> `hub` -> `svc` -> `router` -> `server`
- Shutdown: SIGINT/SIGTERM -> 5s context -> `srv.Shutdown(ctx)`
- No store cleanup on shutdown — no `Close()` call
- No background goroutines

### Test Infrastructure

**`internal/storage/sqlite/test_helpers.go`**
- `NewSQLiteTest(t)` creates in-memory Store for unit tests

**`internal/storage/sqlite/race_test.go`**
- `newRaceStore(t)` creates file-backed Store with WAL mode and `SetMaxOpenConns(1)`
- Tests concurrent event appends, reservation conflicts, optimistic locking, inbox reads
- Pattern to follow for concurrent sweep+reserve tests

### Storage Interface

**`internal/storage/storage.go`**
- `Store` interface with all messaging + reservation methods
- `DomainStore` extends `Store` with CRUD for specs/epics/stories/tasks/insights/sessions/cujs
- Neither interface has a `Close()` method — this is a gap we need to consider

## Design Analysis

### Sweep SQL Correctness

PRD says: `DELETE FROM file_reservations WHERE expires_at < ? AND agent_id NOT IN (SELECT id FROM agents WHERE last_heartbeat > ?)`

Corrected for actual schema:
```sql
DELETE FROM file_reservations
WHERE released_at IS NULL
  AND expires_at < ?
  AND agent_id NOT IN (
    SELECT id FROM agents WHERE last_seen > ?
  )
RETURNING id, agent_id, project, path_pattern
```

The `released_at IS NULL` filter is critical — without it, we'd re-delete already-released reservations (harmless but wasteful). The `RETURNING` clause gives us the deleted rows for event emission without a second query.

**Heartbeat protection:** An agent that's actively heartbeating but hasn't renewed its reservation will be in the `last_seen > ?` subquery, so its expired reservation won't be swept. This gives the agent a grace period to call Reserve() again.

The `?` for `last_seen >` should be `now - 5 minutes`, matching the PRD requirement.

### Startup Sweep vs Periodic Sweep

- **Startup sweep:** `expires_at < now() - 5min` — only truly stale reservations from crash recovery
- **Periodic sweep:** `expires_at < now()` — all expired reservations where agent is also inactive
- Both share the heartbeat-protection subquery

### Event Emission Considerations

The Sweeper needs access to the Broadcaster. Two options:
1. Sweeper struct holds a Broadcaster reference (passed at construction)
2. Sweeper returns deleted reservations, caller emits events

Option 1 is cleaner — the Sweeper is self-contained. It needs project and agent info from deleted reservations for the broadcast call.

Event format should match existing patterns:
```go
map[string]any{
    "type":           "reservation.expired",
    "project":        project,
    "reservation_id": id,
    "agent_id":       agentID,
    "path_pattern":   pattern,
}
```

Broadcast with `agent=""` (broadcast to all project subscribers) since any agent may need to know about freed reservations.

### Graceful Shutdown Ordering

Current: SIGINT -> 5s context -> srv.Shutdown()

Required: SIGINT -> cancel sweeper -> wait for sweeper.Stop() -> WAL checkpoint -> close DB -> srv.Shutdown()

The HTTP server shutdown should happen after sweeper stop but the order between DB close and HTTP shutdown matters: in-flight HTTP requests need the DB, so HTTP should drain first, then DB closes.

Revised order:
1. Cancel sweeper context -> sweeper.Stop() (quick, just waits for current tick)
2. srv.Shutdown(ctx) with 5s timeout (drains in-flight HTTP requests)
3. WAL checkpoint + store.Close()

### Store.Close() Method

The Store struct uses `dbHandle` interface, which already has `Close()`. Adding a `Close()` method to Store is straightforward:

```go
func (s *Store) Close() error {
    _, _ = s.db.Exec("PRAGMA wal_checkpoint(TRUNCATE)")
    return s.db.Close()
}
```

The WAL checkpoint with TRUNCATE mode flushes all WAL frames to the main DB file and truncates the WAL file to zero bytes — clean for next startup.

### Concurrency Safety

SQLite with WAL mode allows concurrent reads and a single writer. The sweeper's DELETE runs in a single statement (atomic), so it won't conflict with Reserve()'s transaction. However, they share the single-writer lock, so the sweep may block briefly during a Reserve() call and vice versa.

The `newRaceStore()` pattern in race_test.go uses `SetMaxOpenConns(1)` — this is fine for the sweep since it's a single atomic DELETE.

### modernc.org/sqlite RETURNING Support

modernc.org/sqlite (the pure-Go SQLite driver) supports `RETURNING` as of SQLite 3.35.0. The modernc.org/sqlite library bundles SQLite 3.44.2+, so `RETURNING` is available. However, using `RETURNING` with `Exec` vs `Query` matters — we need `Query` to read the returned rows.

Alternative: Use a two-step approach in a transaction: SELECT the candidates, then DELETE them. This is more portable and easier to test.

Better yet: the single-statement DELETE approach is cleaner. Use `s.db.Query(deleteSql, args...)` to get returned rows.

### Test Approach

1. **Unit test (in-memory):** Insert reservations with various ages and agent heartbeat states, run sweep, verify correct ones deleted
2. **Concurrent test (file-backed):** Run sweep while Reserve() calls are happening, verify no data corruption
3. **Startup sweep test:** Insert very old reservations, create Sweeper, verify immediate cleanup on Start()

The test_helpers.go pattern (`NewSQLiteTest`) uses in-memory stores. For sweep tests, we need controlled time. Options:
- Insert reservations with explicit timestamps in the past using raw SQL
- Use the existing `NewInMemory()` and manipulate data directly

Since sweep uses raw SQL with time parameters, we can test by:
1. Inserting reservations with past timestamps via `s.db.Exec()`
2. Inserting/not inserting agents with various `last_seen` timestamps
3. Calling the sweep method with "now" parameters
4. Verifying which reservations remain

## Key Findings

1. **Column name mismatch**: PRD says `last_heartbeat` but schema has `last_seen` — use `last_seen`
2. **No Close() on Store**: Need to add it for WAL checkpoint on shutdown
3. **No reservation events**: Need new `EventReservationExpired` constant
4. **Broadcast pattern**: Use `project, ""` (all subscribers in project) for expired reservation events
5. **RETURNING clause available**: modernc.org/sqlite supports it, but two-step SELECT+DELETE in a transaction is safer for testability
6. **Shutdown order matters**: Sweeper stop -> HTTP drain -> DB close
7. **`dbHandle` interface needs no changes**: `Close()` already exposed
8. **race_test.go pattern**: Follow `newRaceStore()` for concurrent sweep tests
