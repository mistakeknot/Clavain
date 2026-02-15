# Research: F2 Session Identity with Collision Rejection — Codebase Analysis

## Summary

Analysis of the intermute codebase to inform the implementation plan for F2 (session identity with collision rejection). This documents the current state of every file that needs modification, identifies integration points, and highlights design constraints.

## Current State

### Schema (`internal/storage/sqlite/schema.sql`, line 68-78)

The `agents` table already has a `session_id TEXT` column, but:
- **No unique constraint** — multiple agents can have the same session_id
- **No index** on session_id — lookups by session_id would be full table scans
- Column is nullable (no NOT NULL constraint)

```sql
CREATE TABLE IF NOT EXISTS agents (
  id TEXT PRIMARY KEY,
  session_id TEXT,         -- <-- exists, but no UNIQUE constraint
  name TEXT NOT NULL,
  project TEXT,
  capabilities_json TEXT,
  metadata_json TEXT,
  status TEXT,
  created_at TEXT NOT NULL,
  last_seen TEXT NOT NULL
);
```

### RegisterAgent (`internal/storage/sqlite/sqlite.go`, lines 594-629)

Current behavior:
1. Always generates fresh `agent.ID = uuid.NewString()` if empty
2. Always generates fresh `agent.SessionID = uuid.NewString()` if empty
3. Uses `ON CONFLICT(id) DO UPDATE` — but since `id` is always fresh, this never triggers upsert
4. No session_id-based lookup, no staleness check, no conflict detection
5. No transaction wrapping — single INSERT statement

Key observation: The existing `ON CONFLICT(id)` upsert path is dead code in practice. The new session_id reuse logic will actually be the first real upsert path.

### Handler (`internal/http/handlers_agents.go`, lines 14-20, 94-137)

`registerAgentRequest` struct does NOT include session_id:
```go
type registerAgentRequest struct {
    Name         string            `json:"name"`
    Project      string            `json:"project"`
    Capabilities []string          `json:"capabilities"`
    Metadata     map[string]string `json:"metadata"`
    Status       string            `json:"status"`
}
```

The handler constructs `core.Agent{}` with empty SessionID, so `RegisterAgent` always generates a new one.

Response struct already includes SessionID:
```go
type registerAgentResponse struct {
    AgentID   string `json:"agent_id"`
    SessionID string `json:"session_id"`
    Name      string `json:"name"`
    Cursor    uint64 `json:"cursor"`
}
```

### Storage Interface (`internal/storage/storage.go`, line 28)

```go
RegisterAgent(ctx context.Context, agent core.Agent) (core.Agent, error)
```

The interface doesn't need to change — `core.Agent` already has `SessionID string`. The reuse logic can be entirely within the SQLite implementation.

### InMemory Store (`internal/storage/storage.go`, lines 196-205)

The in-memory store's `RegisterAgent` is a stub that uses `agent.Name` as ID. It will need updating to handle session_id reuse semantics for tests that use the in-memory store (specifically the HTTP handler tests).

### Error Types (`internal/core/domain.go`, lines 9-12)

Existing sentinel errors:
- `ErrConcurrentModification` — for optimistic locking
- `ErrNotFound` — for missing entities

**Need to add:** `ErrActiveSessionConflict` (or similar) for the 409 case.

### Existing Tests

**SQLite tests** (`internal/storage/sqlite/sqlite_test.go`):
- `TestSQLiteListAgents` — registers agents, lists by project
- `TestSQLiteListAgentsOrderByLastSeen` — heartbeat ordering
- Uses `NewSQLiteTest(t)` helper which creates an in-memory SQLite store

**HTTP handler tests** (`internal/http/handlers_agents_test.go`):
- `TestRegisterAgent` — basic POST, expects 200
- `TestListAgents` — registers 2, lists, expects 2
- `TestListAgentsProjectFilter` — project isolation
- Uses `storage.NewInMemory()` (not SQLite)

**Race tests** (`internal/storage/sqlite/race_test.go`):
- `newRaceStore(t)` creates file-backed store with WAL mode, `SetMaxOpenConns(1)`
- Tests concurrent appends, reservations, optimistic locks, inbox reads

### Migration Pattern

Existing migrations in `applySchema()` follow this pattern:
1. Check if migration is needed (table exists, column exists, etc.)
2. Use `ALTER TABLE ADD COLUMN` for additive changes, or rename-recreate for destructive ones
3. Idempotent — safe to run multiple times
4. Called sequentially from `applySchema()`

The session_id column already exists, so the migration only needs to add the unique partial index.

### UUID Validation

The codebase already imports `github.com/google/uuid` in `sqlite.go`. The `uuid.Parse()` function returns `(uuid.UUID, error)` and can be used for validation.

## Design Decisions

### 1. Reuse Logic in Store Layer, Not Handler

The reuse-or-reject decision is transactional — it must atomically check staleness, check reservations, and either update or reject. This belongs in `RegisterAgent`, not spread across handler + store.

### 2. Single Transaction for Reuse

The reuse path must:
1. BEGIN transaction
2. SELECT agent by session_id (with FOR UPDATE semantics via IMMEDIATE transaction)
3. Check last_seen staleness (>5min → reuse, <5min → conflict)
4. Check active reservations (all expired → reuse OK)
5. UPDATE agent heartbeat + metadata (or INSERT new agent)
6. COMMIT

This prevents race with F3 sweep that might delete the agent between steps 2 and 5.

### 3. Sentinel Error for 409

Add `ErrActiveSessionConflict` to `core/` so the handler can pattern-match and return 409. Using `errors.Is()` is cleaner than string matching.

### 4. Partial Unique Index

```sql
CREATE UNIQUE INDEX IF NOT EXISTS idx_agents_session_id
  ON agents(session_id)
  WHERE session_id IS NOT NULL AND session_id != '';
```

This is the cleanest approach — existing agents with empty/null session_id won't conflict, and the DB enforces uniqueness at the constraint level.

### 5. Staleness Threshold as Constant

Define `const SessionStaleThreshold = 5 * time.Minute` in `core/` or `sqlite/` for testability and consistency with PRD.

## Integration Points with Other Features

### F3 (Stale Reservation Cleanup)

F3's sweep goroutine will delete expired reservations. F2's reuse path checks `all reservations expired` — this means:
- If F3 has already cleaned up, the reservation check finds nothing → reuse OK
- If F3 hasn't run yet but reservations are expired (ExpiresAt < now), the reuse path must still detect them as expired
- The reuse path should check `expires_at < now AND released_at IS NULL` (active but expired), not rely on F3 having run

### Concurrency Safety

The concurrent reuse + F3 sweep test requires:
1. F2 reuse uses BEGIN IMMEDIATE transaction
2. F3 sweep also uses a transaction
3. SQLite serializes these — one completes before the other starts
4. If F3 deletes the agent first, F2's session_id lookup finds nothing → creates new agent
5. If F2 reuses first (updating last_seen), F3's sweep sees fresh heartbeat → skips agent

## Files to Modify (Exhaustive List)

1. **`internal/core/domain.go`** — Add `ErrActiveSessionConflict` sentinel error
2. **`internal/storage/sqlite/schema.sql`** — No change needed (column exists; index added via migration)
3. **`internal/storage/sqlite/sqlite.go`** — Migration function + `RegisterAgent` rewrite
4. **`internal/http/handlers_agents.go`** — Add `SessionID` to request struct, handle 409
5. **`internal/storage/storage.go`** — Update `InMemory.RegisterAgent` for session_id reuse
6. **`internal/storage/sqlite/sqlite_test.go`** — New tests for reuse/reject/create paths
7. **`internal/http/handlers_agents_test.go`** — New tests for 409 response
8. **`internal/storage/sqlite/race_test.go`** — Concurrent reuse test

## Risk Assessment

- **Low risk:** Schema migration (additive index only, no data change)
- **Low risk:** Handler changes (additive field, new error path)
- **Medium risk:** RegisterAgent rewrite (transactional logic, must handle all edge cases)
- **Medium risk:** Concurrent reuse + F3 interaction (requires careful transaction design)
- **Low risk:** Existing tests pass (changes are additive, not destructive)
