# Plan: F4 — Atomic Check-and-Reserve API Endpoint

**Date:** 2026-02-14
**Bead:** Clavain-gvw2
**Status:** Ready
**Target repo:** `/root/projects/intermute/`

## Overview

Feature F4 adds structured conflict responses to the reservation API and a read-only conflict-check endpoint. The `Store.Reserve()` method already performs atomic check-and-insert in a single SQLite transaction — the work is surfacing conflict details through the API layer with proper HTTP semantics.

**Critical path:** All Phase 2 features (F6-F11) depend on F4. Agents need to know *who* holds a conflicting reservation and *when* it expires to make retry/wait decisions.

---

## Task 1: Define ConflictError Type in Core Models

**File:** `/root/projects/intermute/internal/core/models.go`

Add structured error types after the existing `ErrNotFound` and `ErrConcurrentModification` definitions (around line 12):

```go
// ConflictDetail describes a single conflicting reservation.
type ConflictDetail struct {
    ReservationID string    `json:"reservation_id"`
    AgentID       string    `json:"agent_id"`
    AgentName     string    `json:"held_by"`     // Human-readable name from agents table
    Pattern       string    `json:"pattern"`
    Reason        string    `json:"reason,omitempty"`
    ExpiresAt     time.Time `json:"expires_at"`
}

// ConflictError is returned when a reservation conflicts with active reservations.
type ConflictError struct {
    Conflicts []ConflictDetail
}

func (e *ConflictError) Error() string {
    if len(e.Conflicts) == 1 {
        return fmt.Sprintf("reservation conflict with %s (%s)", e.Conflicts[0].AgentName, e.Conflicts[0].Pattern)
    }
    return fmt.Sprintf("reservation conflicts with %d active reservations", len(e.Conflicts))
}
```

Add `"fmt"` to the import block in `models.go` (currently only imports `"time"`).

**Verification:** `cd /root/projects/intermute && go build ./internal/core/...`

---

## Task 2: Update Store Layer — Return ConflictError and Add CheckConflicts

### 2a. Modify `Reserve()` to return `*ConflictError`

**File:** `/root/projects/intermute/internal/storage/sqlite/sqlite.go`

Replace the conflict detection loop (lines 928-965) to:
1. Expand the SELECT to include `agent_id` and `reason`
2. LEFT JOIN with `agents` table to get the human-readable `name`
3. Collect ALL conflicts (not just the first) into a `[]core.ConflictDetail` slice
4. Return `&core.ConflictError{Conflicts: details}` instead of `fmt.Errorf(...)`

The updated query (replaces lines 928-933):

```go
activeRows, err := tx.Query(
    `SELECT r.id, r.agent_id, COALESCE(a.name, r.agent_id), r.path_pattern, r.exclusive, r.reason, r.expires_at
     FROM file_reservations r
     LEFT JOIN agents a ON r.agent_id = a.id
     WHERE r.project = ? AND r.released_at IS NULL AND r.expires_at > ? AND r.agent_id != ?`,
    r.Project, now.Format(time.RFC3339Nano), r.AgentID,
)
```

The updated scan and conflict collection (replaces lines 939-958):

```go
var conflicts []core.ConflictDetail
for activeRows.Next() {
    var (
        existingID      string
        existingAgentID string
        existingName    string
        existingPattern string
        existingExcl    int
        existingReason  sql.NullString
        existingExpires string
    )
    if err := activeRows.Scan(&existingID, &existingAgentID, &existingName, &existingPattern, &existingExcl, &existingReason, &existingExpires); err != nil {
        return nil, fmt.Errorf("scan active reservation: %w", err)
    }
    if !r.Exclusive && existingExcl == 0 {
        continue
    }
    overlap, err := glob.PatternsOverlap(r.PathPattern, existingPattern)
    if err != nil {
        return nil, fmt.Errorf("check reservation overlap against %q: %w", existingPattern, err)
    }
    if overlap {
        expiresAt, _ := time.Parse(time.RFC3339Nano, existingExpires)
        conflicts = append(conflicts, core.ConflictDetail{
            ReservationID: existingID,
            AgentID:       existingAgentID,
            AgentName:     existingName,
            Pattern:       existingPattern,
            Reason:        existingReason.String,
            ExpiresAt:     expiresAt,
        })
    }
}
// ... existing activeRows.Err() and activeRows.Close() checks ...
if len(conflicts) > 0 {
    return nil, &core.ConflictError{Conflicts: conflicts}
}
```

### 2b. Add `CheckConflicts` method to Store

**File:** `/root/projects/intermute/internal/storage/sqlite/sqlite.go`

Add a new method after `Reserve()`. This is a read-only query (no transaction needed for reads, but use one for consistency with WAL mode):

```go
// CheckConflicts returns active reservations that would conflict with the given pattern.
func (s *Store) CheckConflicts(_ context.Context, project, pathPattern string, exclusive bool) ([]core.ConflictDetail, error) {
    if err := glob.ValidateComplexity(pathPattern); err != nil {
        return nil, fmt.Errorf("invalid pattern %q: %w", pathPattern, err)
    }

    now := time.Now().UTC()
    rows, err := s.db.Query(
        `SELECT r.id, r.agent_id, COALESCE(a.name, r.agent_id), r.path_pattern, r.exclusive, r.reason, r.expires_at
         FROM file_reservations r
         LEFT JOIN agents a ON r.agent_id = a.id
         WHERE r.project = ? AND r.released_at IS NULL AND r.expires_at > ?`,
        project, now.Format(time.RFC3339Nano),
    )
    if err != nil {
        return nil, fmt.Errorf("query active reservations: %w", err)
    }
    defer rows.Close()

    var conflicts []core.ConflictDetail
    for rows.Next() {
        var (
            id, agentID, name, pattern, reason string
            excl                               int
            expiresStr                         string
            reasonNull                         sql.NullString
        )
        if err := rows.Scan(&id, &agentID, &name, &pattern, &excl, &reasonNull, &expiresStr); err != nil {
            return nil, fmt.Errorf("scan: %w", err)
        }
        if !exclusive && excl == 0 {
            continue // shared-shared is always allowed
        }
        overlap, err := glob.PatternsOverlap(pathPattern, pattern)
        if err != nil {
            continue // skip invalid patterns
        }
        if overlap {
            expiresAt, _ := time.Parse(time.RFC3339Nano, expiresStr)
            conflicts = append(conflicts, core.ConflictDetail{
                ReservationID: id,
                AgentID:       agentID,
                AgentName:     name,
                Pattern:       pattern,
                Reason:        reasonNull.String,
                ExpiresAt:     expiresAt,
            })
        }
    }
    return conflicts, rows.Err()
}
```

### 2c. Update Storage Interface

**File:** `/root/projects/intermute/internal/storage/storage.go`

Add to the `Store` interface (after line 42, before the closing `}`):

```go
CheckConflicts(ctx context.Context, project, pathPattern string, exclusive bool) ([]core.ConflictDetail, error)
```

Add a stub to the `InMemory` store:

```go
func (m *InMemory) CheckConflicts(_ context.Context, project, pathPattern string, exclusive bool) ([]core.ConflictDetail, error) {
    return nil, nil // In-memory store doesn't track reservations
}
```

### 2d. Update ReservationStore interface

**File:** `/root/projects/intermute/internal/http/handlers_reservations.go`

Add `CheckConflicts` to the `ReservationStore` interface (after line 66):

```go
CheckConflicts(ctx context.Context, project, pathPattern string, exclusive bool) ([]core.ConflictDetail, error)
```

**Verification:** `cd /root/projects/intermute && go build ./...`

---

## Task 3: Update Handler Layer — 409 Responses and Check Endpoint

### 3a. Return 409 with structured conflict JSON on `createReservation`

**File:** `/root/projects/intermute/internal/http/handlers_reservations.go`

Replace lines 129-132 (the current error handling in `createReservation`):

```go
// Current:
if err != nil {
    w.WriteHeader(http.StatusInternalServerError)
    return
}

// New:
if err != nil {
    var conflictErr *core.ConflictError
    if errors.As(err, &conflictErr) {
        w.Header().Set("Content-Type", "application/json")
        w.WriteHeader(http.StatusConflict) // 409
        _ = json.NewEncoder(w).Encode(map[string]any{
            "error":     "reservation_conflict",
            "conflicts": conflictErr.Conflicts,
        })
        return
    }
    w.WriteHeader(http.StatusInternalServerError)
    return
}
```

Also change the success response to return 201 Created instead of implicit 200:

```go
w.Header().Set("Content-Type", "application/json")
w.WriteHeader(http.StatusCreated) // Add this line
_ = json.NewEncoder(w).Encode(toAPIReservation(*res))
```

Ensure `"errors"` is in the import block (it already is, used by `releaseReservation`).

### 3b. Add conflict-check endpoint

**File:** `/root/projects/intermute/internal/http/handlers_reservations.go`

Add a new handler method:

```go
func (s *Service) checkConflicts(w http.ResponseWriter, r *http.Request) {
    if r.Method != http.MethodGet {
        w.WriteHeader(http.StatusMethodNotAllowed)
        return
    }

    project := r.URL.Query().Get("project")
    pattern := r.URL.Query().Get("pattern")
    if project == "" || pattern == "" {
        w.WriteHeader(http.StatusBadRequest)
        return
    }

    exclusive := r.URL.Query().Get("exclusive") != "false" // default true

    conflicts, err := s.store.CheckConflicts(r.Context(), project, pattern, exclusive)
    if err != nil {
        w.WriteHeader(http.StatusInternalServerError)
        return
    }

    w.Header().Set("Content-Type", "application/json")
    _ = json.NewEncoder(w).Encode(map[string]any{
        "conflicts": conflicts,
    })
}
```

### 3c. Register the new route

**File:** `/root/projects/intermute/internal/http/router.go`

Add after line 22 (after the existing reservation routes):

```go
mux.Handle("/api/reservations/check", wrap(svc.checkConflicts))
```

**Important:** This MUST be registered before `/api/reservations/` (the trailing-slash catch-all) because Go's `http.ServeMux` matches longest prefix. Since `"/api/reservations/check"` is more specific than `"/api/reservations/"`, it will match correctly regardless of order in Go 1.22+. But for clarity, place it between the two existing reservation routes.

**Verification:** `cd /root/projects/intermute && go build ./... && go vet ./...`

---

## Task 4: Update Existing Tests and Add New Tests

### 4a. Fix existing tests for new status codes

**File:** `/root/projects/intermute/internal/http/handlers_reservations_test.go`

1. **`TestReleaseReservationOwnershipEnforced`** (line 36): Change `http.StatusOK` to `http.StatusCreated` for the create response assertion.

2. **`TestReservationCreateAndList`** (line 132): The test uses `requireStatus(t, resp, http.StatusOK)` — change to `http.StatusCreated`.

3. **`TestReservationOverlapConflict`** (line 181): Change `http.StatusInternalServerError` to `http.StatusConflict`. Also add assertions on the response body:

```go
requireStatus(t, resp2, http.StatusConflict)
conflictBody := decodeJSON[map[string]any](t, resp2)
if conflictBody["error"] != "reservation_conflict" {
    t.Fatalf("expected error=reservation_conflict, got %v", conflictBody["error"])
}
conflicts := conflictBody["conflicts"].([]any)
if len(conflicts) == 0 {
    t.Fatal("expected at least one conflict detail")
}
detail := conflicts[0].(map[string]any)
if detail["pattern"] == nil || detail["held_by"] == nil {
    t.Fatal("conflict detail missing pattern or held_by")
}
```

4. **`TestReservationSharedAllowed`** (lines 196, 205): Change `http.StatusOK` to `http.StatusCreated`.

5. **`TestReservationReleaseAndVerify`** (line 229): Change `http.StatusOK` to `http.StatusCreated`.

### 4b. Add concurrent reserve test

**File:** `/root/projects/intermute/internal/http/handlers_reservations_test.go`

```go
func TestConcurrentAtomicReserve(t *testing.T) {
    env := newReservationTestEnv(t)
    const project = "proj-concurrent"
    const n = 10

    var wg sync.WaitGroup
    results := make([]int, n)
    for i := 0; i < n; i++ {
        wg.Add(1)
        go func(idx int) {
            defer wg.Done()
            resp := env.post(t, "/api/reservations", map[string]any{
                "agent_id":     fmt.Sprintf("agent-%d", idx),
                "project":      project,
                "path_pattern": "internal/http/*.go",
                "exclusive":    true,
                "reason":       fmt.Sprintf("agent %d working", idx),
            })
            results[idx] = resp.StatusCode
            resp.Body.Close()
        }(i)
    }
    wg.Wait()

    created := 0
    conflicted := 0
    for _, code := range results {
        switch code {
        case http.StatusCreated:
            created++
        case http.StatusConflict:
            conflicted++
        default:
            t.Errorf("unexpected status code: %d", code)
        }
    }
    if created != 1 {
        t.Fatalf("expected exactly 1 created, got %d (conflicts: %d)", created, conflicted)
    }
    if conflicted != n-1 {
        t.Fatalf("expected %d conflicts, got %d", n-1, conflicted)
    }
}
```

Add `"fmt"` and `"sync"` to the test file imports.

### 4c. Add idempotent re-reserve test

**File:** `/root/projects/intermute/internal/http/handlers_reservations_test.go`

```go
func TestIdempotentReReserveBySameAgent(t *testing.T) {
    env := newReservationTestEnv(t)
    const project = "proj-idempotent"

    // First reservation
    resp1 := env.post(t, "/api/reservations", map[string]any{
        "agent_id":     "agent-a",
        "project":      project,
        "path_pattern": "src/*.go",
        "exclusive":    true,
    })
    requireStatus(t, resp1, http.StatusCreated)
    resp1.Body.Close()

    // Same agent, same pattern — should succeed (not conflict with self)
    resp2 := env.post(t, "/api/reservations", map[string]any{
        "agent_id":     "agent-a",
        "project":      project,
        "path_pattern": "src/*.go",
        "exclusive":    true,
    })
    requireStatus(t, resp2, http.StatusCreated)
    resp2.Body.Close()

    // Verify both reservations exist
    listResp := env.get(t, "/api/reservations?agent=agent-a")
    requireStatus(t, listResp, http.StatusOK)
    listData := decodeJSON[map[string]any](t, listResp)
    reservations := listData["reservations"].([]any)
    if len(reservations) < 2 {
        t.Fatalf("expected at least 2 reservations for same agent, got %d", len(reservations))
    }
}
```

### 4d. Add conflict-check endpoint test

**File:** `/root/projects/intermute/internal/http/handlers_reservations_test.go`

```go
func TestCheckConflictsEndpoint(t *testing.T) {
    env := newReservationTestEnv(t)
    const project = "proj-check"

    // Create an exclusive reservation
    resp := env.post(t, "/api/reservations", map[string]any{
        "agent_id":     "agent-a",
        "project":      project,
        "path_pattern": "internal/http/*.go",
        "exclusive":    true,
        "reason":       "refactoring handlers",
    })
    requireStatus(t, resp, http.StatusCreated)
    resp.Body.Close()

    // Check for conflicts — should find one
    checkResp := env.get(t, "/api/reservations/check?project="+project+"&pattern=internal/http/router.go")
    requireStatus(t, checkResp, http.StatusOK)
    checkData := decodeJSON[map[string]any](t, checkResp)
    conflicts := checkData["conflicts"].([]any)
    if len(conflicts) != 1 {
        t.Fatalf("expected 1 conflict, got %d", len(conflicts))
    }

    // Check non-overlapping pattern — no conflicts
    noConflict := env.get(t, "/api/reservations/check?project="+project+"&pattern=cmd/*.go")
    requireStatus(t, noConflict, http.StatusOK)
    noData := decodeJSON[map[string]any](t, noConflict)
    noConflicts := noData["conflicts"].([]any)
    if len(noConflicts) != 0 {
        t.Fatalf("expected 0 conflicts for non-overlapping pattern, got %d", len(noConflicts))
    }
}
```

### 4e. Add store-level concurrent reserve test

**File:** `/root/projects/intermute/internal/storage/sqlite/sqlite_test.go`

```go
func TestConcurrentReserveRace(t *testing.T) {
    ctx := context.Background()
    st := NewSQLiteTest(t)

    var wg sync.WaitGroup
    var mu sync.Mutex
    var successes, conflicts int

    for i := 0; i < 20; i++ {
        wg.Add(1)
        go func(idx int) {
            defer wg.Done()
            _, err := st.Reserve(ctx, core.Reservation{
                AgentID:     fmt.Sprintf("agent-%d", idx),
                Project:     "race-project",
                PathPattern: "pkg/events/*.go",
                Exclusive:   true,
            })
            mu.Lock()
            defer mu.Unlock()
            if err == nil {
                successes++
            } else {
                var conflictErr *core.ConflictError
                if errors.As(err, &conflictErr) {
                    conflicts++
                } else {
                    t.Errorf("unexpected error type: %v", err)
                }
            }
        }(i)
    }
    wg.Wait()

    if successes != 1 {
        t.Fatalf("expected exactly 1 success, got %d (conflicts: %d)", successes, conflicts)
    }
}
```

Add `"sync"` and `"errors"` to the sqlite_test.go imports.

**Verification:**

```bash
cd /root/projects/intermute
go test -race -count=5 ./internal/storage/sqlite/...
go test -race -count=5 ./internal/http/...
go test -race ./...
```

---

## Task 5: Validate Acceptance Criteria

Run the full matrix and mark off:

| Criterion | How to verify |
|---|---|
| `POST /api/reservations` creates reservation or returns 409 | `TestReservationCreateAndList` (201), `TestReservationOverlapConflict` (409) |
| Single SQLite transaction: check + insert | Code review of `Reserve()` — `BeginTx`/`Commit` wraps both query and insert |
| Response on 201: full reservation details | `TestReservationCreateAndList` checks id, is_active fields |
| Response on 409: conflict details with held_by, pattern, reason, expires_at | `TestReservationOverlapConflict` new body assertions |
| `GET /api/reservations/check` for read-only queries | `TestCheckConflictsEndpoint` |
| Concurrent atomic reserves (only one succeeds) | `TestConcurrentAtomicReserve` (handler) + `TestConcurrentReserveRace` (store) |
| Idempotent re-reserve by same agent | `TestIdempotentReReserveBySameAgent` |

The `if_not_conflict=true` query parameter from the PRD is intentionally omitted from the implementation. The rationale: 409 is returned unconditionally on conflict (not only when the param is present), which is the correct HTTP semantic. The param would only serve as documentation of client intent, adding complexity without behavior change. If needed later, it can be added as a no-op recognized parameter.

---

## File Change Summary

| File | Change |
|---|---|
| `internal/core/models.go` | Add `ConflictDetail`, `ConflictError` types |
| `internal/storage/sqlite/sqlite.go` | Update `Reserve()` conflict handling, add `CheckConflicts()` |
| `internal/storage/storage.go` | Add `CheckConflicts` to `Store` interface + `InMemory` stub |
| `internal/http/handlers_reservations.go` | 409 response, 201 status, `checkConflicts` handler, add to `ReservationStore` interface |
| `internal/http/router.go` | Register `/api/reservations/check` route |
| `internal/http/handlers_reservations_test.go` | Fix status codes, add 4 new test functions |
| `internal/storage/sqlite/sqlite_test.go` | Add `TestConcurrentReserveRace` |

**Estimated scope:** ~200 lines of production code, ~150 lines of test code.
