# F2: Session Identity with Collision Rejection — Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use clavain:executing-plans to implement this plan task-by-task.

**Goal:** Allow agents to re-register with the same `session_id` after session restarts (reusing their identity when stale), while rejecting registration when an active agent already holds that session_id — preventing identity collisions and enabling crash recovery.

**Architecture:** Session identity reuse is handled entirely within the SQLite `RegisterAgent` method using a BEGIN IMMEDIATE transaction that atomically checks staleness + reservations and either reuses the existing agent row or rejects with a sentinel error. The HTTP handler maps that error to 409 Conflict. A partial unique index on `session_id` enforces uniqueness at the DB level. The 5-minute staleness threshold is defined as a package-level constant for testability.

**Tech Stack:** Go 1.24, modernc.org/sqlite

**Bead:** Clavain-qdqe

**PRD:** `docs/prds/2026-02-14-interlock-multi-agent-coordination.md` (F2)

---

### Task 1: Add Sentinel Error and Staleness Constant

**Files:**
- Modify: `/root/projects/intermute/internal/core/domain.go`

**Steps:**
1. Add `ErrActiveSessionConflict` sentinel error:
   ```go
   // ErrActiveSessionConflict is returned when a session_id is already in use by an active agent
   var ErrActiveSessionConflict = errors.New("active session conflict: session_id is in use by an agent with a recent heartbeat")
   ```
2. Add staleness threshold constant:
   ```go
   // SessionStaleThreshold is the duration after which an agent's heartbeat is considered stale,
   // allowing session_id reuse. Agents with heartbeats newer than this threshold are considered active.
   const SessionStaleThreshold = 5 * time.Minute
   ```

**Acceptance criteria:**
- `ErrActiveSessionConflict` is a package-level `var` (sentinel error, usable with `errors.Is()`)
- `SessionStaleThreshold` is `5 * time.Minute`
- Existing code compiles without changes

---

### Task 2: Schema Migration — Partial Unique Index on session_id

**Files:**
- Modify: `/root/projects/intermute/internal/storage/sqlite/sqlite.go`

**Steps:**
1. Add `migrateAgentSessionID` function that creates a partial unique index:
   ```go
   func migrateAgentSessionID(db *sql.DB) error {
       if !tableExists(db, "agents") {
           return nil
       }
       // Create partial unique index — only enforced when session_id is non-null and non-empty.
       // Existing agents with empty/null session_id won't conflict.
       _, err := db.Exec(`CREATE UNIQUE INDEX IF NOT EXISTS idx_agents_session_id
           ON agents(session_id) WHERE session_id IS NOT NULL AND session_id != ''`)
       if err != nil {
           return fmt.Errorf("create session_id index: %w", err)
       }
       return nil
   }
   ```
2. Call `migrateAgentSessionID(db)` at the end of `applySchema()`, after existing migration calls (after `migrateDomainVersions`).

**Acceptance criteria:**
- `CREATE UNIQUE INDEX IF NOT EXISTS idx_agents_session_id ON agents(session_id) WHERE session_id IS NOT NULL AND session_id != ''` is executed on startup
- Migration is idempotent (uses `IF NOT EXISTS`)
- Existing databases with duplicate empty/null session_id values don't break
- `go test ./internal/storage/sqlite/...` passes (existing tests still work)

---

### Task 3: Rewrite RegisterAgent with Session Reuse Logic

**Files:**
- Modify: `/root/projects/intermute/internal/storage/sqlite/sqlite.go`

**Steps:**
1. Rewrite the `RegisterAgent` method with this logic:
   - **If `agent.SessionID` is non-empty:**
     a. Validate it's a valid UUID using `uuid.Parse(agent.SessionID)` — return error if invalid
     b. BEGIN IMMEDIATE transaction (serializes against concurrent reuse attempts and F3 sweep)
     c. `SELECT id, last_seen FROM agents WHERE session_id = ?` — look up existing agent
     d. **If found and `last_seen` is within `core.SessionStaleThreshold` of now:** ROLLBACK, return `core.ErrActiveSessionConflict`
     e. **If found and stale (last_seen > threshold ago):**
        - Check for active reservations: `SELECT COUNT(*) FROM file_reservations WHERE agent_id = ? AND released_at IS NULL AND expires_at > ?` (using current time)
        - If active reservations exist, ROLLBACK, return `core.ErrActiveSessionConflict` (agent is stale but still holds live reservations — unsafe to reuse)
        - Otherwise, UPDATE the existing agent row: set `name`, `capabilities_json`, `metadata_json`, `status`, `last_seen` to new values, keep existing `id` and `created_at`
        - COMMIT, return updated agent with the **existing** agent ID
     f. **If not found:** INSERT new agent normally (generate fresh UUID for `agent.ID` if empty), COMMIT
   - **If `agent.SessionID` is empty:** Current behavior — generate fresh UUIDs for both `agent.ID` and `agent.SessionID`, INSERT directly (no transaction needed for this path, but using one for consistency is fine)

2. Key implementation details:
   - Use `s.db.BeginTx(context.Background(), nil)` to get a `*sql.Tx` with IMMEDIATE mode (execute `tx.Exec("BEGIN IMMEDIATE")` or use `sql.LevelSerializable` isolation)
   - Actually, for modernc.org/sqlite: use `tx.Exec("PRAGMA busy_timeout=5000")` isn't available in transactions. Instead, start with `s.db.BeginTx(ctx, &sql.TxOptions{})` and rely on SQLite's single-writer serialization. The BEGIN IMMEDIATE is critical — achieve this by doing a write early in the transaction (or using `_txlock=immediate` connection parameter).
   - Simpler approach: use a regular `Begin()` transaction, and the first write statement will acquire the write lock. The SELECT + conditional UPDATE is safe because SQLite auto-upgrades to exclusive on the first write.

**Acceptance criteria:**
- Session reuse: providing a session_id matching a stale agent (last_seen > 5min ago, no active reservations) returns the existing agent with the same agent ID and updated heartbeat
- Collision rejection: providing a session_id matching an active agent (last_seen < 5min ago) returns `core.ErrActiveSessionConflict`
- No session_id: generates fresh UUIDs for both ID and SessionID (unchanged behavior)
- Invalid UUID session_id: returns a descriptive error
- Stale agent with active reservations: returns `core.ErrActiveSessionConflict` (reservation safety)
- Transaction prevents race between concurrent reuse attempts
- `go test ./internal/storage/sqlite/...` passes

---

### Task 4: Update HTTP Handler for Session ID and 409 Response

**Files:**
- Modify: `/root/projects/intermute/internal/http/handlers_agents.go`
- Modify: `/root/projects/intermute/internal/storage/storage.go` (InMemory store)

**Steps:**
1. Add `SessionID` field to `registerAgentRequest`:
   ```go
   type registerAgentRequest struct {
       Name         string            `json:"name"`
       SessionID    string            `json:"session_id,omitempty"`
       Project      string            `json:"project"`
       Capabilities []string          `json:"capabilities"`
       Metadata     map[string]string `json:"metadata"`
       Status       string            `json:"status"`
   }
   ```

2. Pass `SessionID` through to `core.Agent` in `handleRegisterAgent`:
   ```go
   agent, err := s.store.RegisterAgent(r.Context(), core.Agent{
       Name:         req.Name,
       SessionID:    strings.TrimSpace(req.SessionID),
       Project:      strings.TrimSpace(req.Project),
       Capabilities: req.Capabilities,
       Metadata:     req.Metadata,
       Status:       req.Status,
       CreatedAt:    now,
       LastSeen:     now,
   })
   ```

3. Handle `ErrActiveSessionConflict` in the error path:
   ```go
   if err != nil {
       if errors.Is(err, core.ErrActiveSessionConflict) {
           w.Header().Set("Content-Type", "application/json")
           w.WriteHeader(http.StatusConflict)
           _ = json.NewEncoder(w).Encode(map[string]string{
               "error": "session_id is in use by an active agent",
               "code":  "active_session_conflict",
           })
           return
       }
       w.WriteHeader(http.StatusInternalServerError)
       return
   }
   ```

4. Update `InMemory.RegisterAgent` in `storage.go` to handle session_id reuse for test compatibility:
   ```go
   func (m *InMemory) RegisterAgent(_ context.Context, agent core.Agent) (core.Agent, error) {
       // Check for session_id reuse
       if agent.SessionID != "" {
           for _, existing := range m.agents {
               if existing.SessionID == agent.SessionID {
                   if time.Since(existing.LastSeen) < core.SessionStaleThreshold {
                       return core.Agent{}, core.ErrActiveSessionConflict
                   }
                   // Reuse: update existing agent
                   existing.Name = agent.Name
                   existing.Capabilities = agent.Capabilities
                   existing.Metadata = agent.Metadata
                   existing.Status = agent.Status
                   existing.LastSeen = time.Now().UTC()
                   m.agents[existing.ID] = existing
                   return existing, nil
               }
           }
       }
       if agent.ID == "" {
           agent.ID = agent.Name
       }
       if agent.SessionID == "" {
           agent.SessionID = agent.ID + "-session"
       }
       m.agents[agent.ID] = agent
       return agent, nil
   }
   ```

5. Add `"errors"` and `"github.com/mistakeknot/intermute/internal/core"` to imports in `handlers_agents.go` (if not already present).

**Acceptance criteria:**
- `POST /api/agents` with `{"session_id": "<valid-uuid>"}` passes session_id through to store
- Active session collision returns HTTP 409 with JSON body `{"error": "...", "code": "active_session_conflict"}`
- Missing or empty session_id creates a new agent (backward compatible)
- InMemory store handles session_id reuse for HTTP handler tests
- `go test ./internal/http/...` passes

---

### Task 5: Tests — Reuse, Rejection, Creation, and Concurrency

**Files:**
- Modify: `/root/projects/intermute/internal/storage/sqlite/sqlite_test.go`
- Modify: `/root/projects/intermute/internal/http/handlers_agents_test.go`
- Modify: `/root/projects/intermute/internal/storage/sqlite/race_test.go`

**Steps:**

1. **SQLite store tests** (add to `sqlite_test.go`):

   a. `TestRegisterAgentSessionReuse` — Register agent with session_id, wait/simulate staleness (by directly updating last_seen in DB to >5min ago), re-register with same session_id. Verify: same agent ID returned, last_seen updated, name updated.

   b. `TestRegisterAgentSessionConflict` — Register agent with session_id (fresh heartbeat). Re-register with same session_id immediately. Verify: `errors.Is(err, core.ErrActiveSessionConflict)`.

   c. `TestRegisterAgentNoSessionID` — Register agent without session_id. Verify: fresh UUID generated for both ID and SessionID (unchanged behavior).

   d. `TestRegisterAgentInvalidSessionID` — Register agent with `session_id: "not-a-uuid"`. Verify: error returned (not a panic).

   e. `TestRegisterAgentSessionReuseWithActiveReservations` — Register agent with session_id, create a reservation with future expiry, simulate staleness (update last_seen to >5min ago). Re-register with same session_id. Verify: `ErrActiveSessionConflict` returned (agent is stale but reservations are still active).

   f. `TestRegisterAgentSessionReuseWithExpiredReservations` — Same as above but reservation has `expires_at` in the past. Re-register succeeds — stale agent with expired reservations is safe to reuse.

   To simulate staleness without `time.Sleep`, directly execute:
   ```go
   st.db.Exec(`UPDATE agents SET last_seen = ? WHERE session_id = ?`,
       time.Now().Add(-10*time.Minute).UTC().Format(time.RFC3339Nano), sessionID)
   ```
   This requires exposing `db` or adding a test helper. Since `sqlite_test.go` is in the `sqlite` package (not `sqlite_test`), it has access to `st.db` directly.

2. **HTTP handler tests** (add to `handlers_agents_test.go`):

   a. `TestRegisterAgentWithSessionID` — POST with session_id, verify 200 and session_id in response.

   b. `TestRegisterAgentSessionConflict409` — Register agent with session_id, immediately register again with same session_id. Verify: HTTP 409 with JSON error body.

   c. `TestRegisterAgentWithoutSessionID` — POST without session_id field. Verify: 200, fresh session_id in response (backward compat).

3. **Race tests** (add to `race_test.go`):

   a. `TestConcurrentSessionReuse` — Use `newRaceStore(t)`. Register agent with session_id, simulate staleness. Launch 5 goroutines all trying to re-register with the same session_id simultaneously. Verify: exactly 1 succeeds, 4 fail (either with conflict or unique constraint violation).

**Acceptance criteria:**
- All 6 SQLite store tests pass
- All 3 HTTP handler tests pass
- Concurrent reuse test passes with `-race` flag
- `go test -race ./internal/...` passes
- No regressions in existing tests

---

## Pre-flight Checklist

- [ ] Read current `internal/core/domain.go` to confirm exact error/import structure
- [ ] Read current `internal/storage/sqlite/sqlite.go` to confirm `applySchema` call chain
- [ ] Read current `internal/http/handlers_agents.go` to confirm import list
- [ ] Run `go test ./internal/...` to establish baseline (all green)
- [ ] Verify `github.com/google/uuid` is already in `go.mod`

## Post-execution Checklist

- [ ] `go test ./internal/...` passes (all tests, including new ones)
- [ ] `go test -race ./internal/storage/sqlite/...` passes
- [ ] `go vet ./...` clean
- [ ] Verify migration is idempotent: run tests twice without cleaning DB
- [ ] Verify backward compatibility: register agent without session_id still works
- [ ] Verify 409 response body is valid JSON with `error` and `code` fields
- [ ] Manual smoke test: `curl -X POST localhost:PORT/api/agents -d '{"name":"test","session_id":"<uuid>","project":"p"}'` twice — first 200, second 409
