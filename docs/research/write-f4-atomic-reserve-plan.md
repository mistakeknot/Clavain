# Research: F4 Atomic Check-and-Reserve for intermute

**Date:** 2026-02-14
**Bead:** Clavain-gvw2

## Codebase Analysis

### Current Store Layer (`internal/storage/sqlite/sqlite.go`, lines 894-981)

The `Reserve()` method already implements atomic check-and-insert within a single SQLite transaction:

1. Opens a transaction (`BeginTx`)
2. Queries active reservations that:
   - Match the same project
   - Are not released (`released_at IS NULL`)
   - Haven't expired (`expires_at > now`)
   - Belong to a DIFFERENT agent (`agent_id != r.AgentID`)
3. For each active reservation, checks if the new pattern overlaps via `glob.PatternsOverlap()`
4. Shared-shared overlaps are allowed (both `!r.Exclusive && existingExcl == 0`)
5. On conflict, returns a generic error: `fmt.Errorf("reservation conflict with active reservation %s (%s)", existingID, existingPattern)`
6. If no conflict, inserts and commits

**Critical finding:** The conflict error at line 957 is a plain `fmt.Errorf` with no structured type. The handler at `createReservation` (handlers_reservations.go:129-131) catches ALL errors as 500, making conflicts indistinguishable from database errors.

**Critical finding:** The conflict query only selects `id, path_pattern, exclusive` from `file_reservations`. It does NOT join with the `agents` table, so the agent's human-readable `name` field is not available in the conflict response. The `agents` table schema (schema.sql:68-78) has `name TEXT NOT NULL`.

**Critical finding:** The `file_reservations` table has no foreign key to `agents`. The `agent_id` in `file_reservations` is a TEXT field that may or may not correspond to an `agents.id` record (agents register via `/api/agents` POST, but reservations don't enforce agent existence).

### Current Handler Layer (`internal/http/handlers_reservations.go`)

- `createReservation` (line 95): Decodes request, validates required fields, resolves project from auth context, calls `store.Reserve()`, returns JSON on success
- On ANY error from `Reserve()`: returns bare `500` with no body (line 130-131)
- No `if_not_conflict` query parameter handling
- No conflict-check endpoint
- Response on success: `toAPIReservation(*res)` which includes id, agent_id, project, path_pattern, exclusive, reason, created_at, expires_at, released_at, is_active
- Note: existing test at line 181 expects `StatusInternalServerError` for conflicts - this test will need updating

### Router Layer (`internal/http/router.go`)

- `POST /api/reservations` -> `handleReservations` -> `createReservation`
- `GET /api/reservations` -> `handleReservations` -> `listReservations`
- `DELETE /api/reservations/{id}` -> `handleReservationByID` -> `releaseReservation`
- No `/api/reservations/check` endpoint exists yet

**Important:** `router_domain.go` (NewDomainRouter) does NOT include reservation routes. Only `router.go` (NewRouter) does. The reservation test env uses `NewRouter`.

### Storage Interface (`internal/storage/storage.go`)

The `Store` interface (lines 23-43) needs a new method: `CheckConflicts(ctx, project, pattern) ([]ConflictDetail, error)`.

The `InMemory` store (lines 46-274) has stub implementations for all reservation methods. It will also need a stub for `CheckConflicts`.

### Core Models (`internal/core/models.go`)

- `Reservation` struct (lines 75-86): Has all expected fields
- `IsActive()` method (lines 89-91): Checks released_at == nil AND not expired
- Error types: Only `ErrNotFound` (domain.go:12) and `ErrConcurrentModification` (domain.go:9) exist. No `ConflictError` type.

### Schema (`internal/storage/sqlite/schema.sql`)

- `file_reservations` table (lines 52-62): id, agent_id, project, path_pattern, exclusive, reason, created_at, expires_at, released_at
- `agents` table (lines 68-78): id, session_id, name, project, capabilities_json, metadata_json, status, created_at, last_seen
- Agent name JOIN path: `file_reservations.agent_id = agents.id` then `agents.name`
- Note: agent may not exist in agents table (no FK constraint), so JOIN must be LEFT JOIN with fallback to agent_id as name

### Existing Tests

**Handler tests** (`handlers_reservations_test.go`):
- `TestReleaseReservationOwnershipEnforced`: Uses auth middleware, creates/releases reservations
- `TestReservationCreateAndList`: Creates reservation, lists by project and agent
- `TestReservationOverlapConflict`: Creates overlapping exclusive reservations, expects 500 (line 181) - **MUST UPDATE to 409**
- `TestReservationSharedAllowed`: Two shared overlapping reservations succeed
- `TestReservationReleaseAndVerify`: Create then release, verify gone from active list
- `TestReservationListRequiresProjectOrAgent`: No params -> 400

**Store tests** (`sqlite_test.go`):
- `TestFileReservation`: Basic CRUD
- `TestFileReservationOverlapSubsetAndSuperset`: Pattern overlap detection
- `TestFileReservationOverlapPartial`: Partial glob intersection
- `TestFileReservationSharedOverlapSemantics`: Shared/exclusive interaction
- `TestReservationExpiry`: Negative TTL creates expired reservation

### Idempotent Re-Reserve Analysis

The current Reserve() query at line 931 filters with `agent_id != r.AgentID`. This means conflicts from the SAME agent are ignored. So if agent-A already holds `pkg/events/*.go` exclusively, agent-A can create another reservation for the same or overlapping pattern. This is the desired behavior for idempotent re-reserve, BUT it creates a second reservation row rather than returning the existing one. For true idempotency, the code should detect "same agent, same pattern" and return the existing reservation. However, the PRD says "idempotent re-reserve by same agent" which could mean either interpretation. The current behavior (allowing it, creating new row) may be acceptable.

### Glob Overlap Engine (`internal/glob/overlap.go`)

- `PatternsOverlap(a, b string) (bool, error)`: NFA-based overlap detection
- `ValidateComplexity(pattern string) error`: Limits tokens and wildcards to prevent DoS
- Both are called during Reserve() before the conflict check

## Design Decisions

### 1. ConflictError Type Location

Place in `internal/core/models.go` alongside `ErrNotFound` and `ErrConcurrentModification`. This keeps all error types in the core package where they're accessible to both store and handler layers.

### 2. Agent Name Resolution

LEFT JOIN with agents table in the conflict query. If agent not registered, fall back to `agent_id` as the name. This handles the case where reservations are created before agent registration.

### 3. 409 Always vs. Only with Query Param

The PRD says `if_not_conflict=true` triggers 409. But returning 500 for conflicts without the param is misleading. Since this is pre-release, return 409 ALWAYS on conflict. The `if_not_conflict` param serves as documentation of intent (client explicitly expects atomic semantics) but doesn't change behavior.

### 4. Status Code for Success

Current code returns 200 on create (line 36 in test). Should be 201 Created per HTTP semantics. This is a breaking change but correct. Tests need updating.

### 5. CheckConflicts Method

New read-only method that runs the same conflict-detection logic as Reserve() but without the INSERT. Returns `[]ConflictDetail` (empty if no conflicts). Exposed via `GET /api/reservations/check?project=X&pattern=Y`.

### 6. Concurrent Safety

SQLite with WAL mode (which intermute uses via modernc.org/sqlite) serializes writers. Two concurrent `Reserve()` calls in the same process will serialize at the `BeginTx` level. The existing transaction-based approach is already correct for single-process concurrency. For multi-process (unlikely given the single-binary architecture), SQLite's file-level locking handles it.

### 7. Conflict Response Shape

```json
{
  "error": "reservation_conflict",
  "conflicts": [
    {
      "reservation_id": "uuid",
      "held_by": "Agent Name",
      "agent_id": "agent-id",
      "pattern": "pkg/events/*.go",
      "reason": "Refactoring events package",
      "expires_at": "2026-02-14T12:30:00Z"
    }
  ]
}
```

Including both `held_by` (human name) and `agent_id` (machine identifier) gives clients what they need for both display and programmatic use.

## Risk Assessment

1. **Breaking change: 500 -> 409 on conflict** - Low risk, pre-release. One test to update.
2. **Breaking change: 200 -> 201 on create** - Low risk, pre-release. Several tests to update.
3. **LEFT JOIN performance** - Negligible. The conflict query typically returns 0-3 rows.
4. **Storage interface expansion** - `CheckConflicts` added to `Store` interface. All implementations (SQLite, InMemory) must be updated. InMemory gets a stub.
5. **Agent not in agents table** - LEFT JOIN with COALESCE handles gracefully.
