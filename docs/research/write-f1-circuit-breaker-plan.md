# Research: F1 Circuit Breaker + Retry Implementation Plan

## Analysis Date: 2026-02-14

## Codebase Analysis

### Store Architecture
- `internal/storage/storage.go` defines `Store` interface with 15 methods (AppendEvent, InboxSince, ThreadMessages, ListThreads, RegisterAgent, Heartbeat, ListAgents, MarkRead, MarkAck, RecipientStatus, InboxCounts, Reserve, GetReservation, ReleaseReservation, ActiveReservations, AgentReservations)
- `internal/storage/domain.go` defines `DomainStore` interface embedding `Store` + 34 domain methods
- `internal/storage/sqlite/sqlite.go` — concrete SQLite `Store` struct with `db dbHandle` field
- `internal/storage/sqlite/domain.go` — domain method implementations on same `Store` struct
- `internal/storage/sqlite/querylog.go` — `dbHandle` interface + `queryLogger` wrapper (Exec, Query, QueryRow, Begin, BeginTx, Close)
- `internal/storage/storage.go` also has `InMemory` struct implementing `Store` (stubs for tests)

### Key Design Facts
1. `Store` struct has single field: `db dbHandle` — all methods use `s.db.Exec()`, `s.db.Query()`, `s.db.QueryRow()`, `s.db.Begin()`, `s.db.BeginTx()`
2. `dbHandle` interface is the existing abstraction layer — `queryLogger` wraps `*sql.DB`
3. `DomainService` in HTTP layer takes `storage.DomainStore` — the SQLite `*Store` implements both `Store` and `DomainStore`
4. `NewDomainRouter` creates routes — health endpoint would go here, outside auth middleware
5. `main.go` creates `sqlite.New(dbPath)` -> `httpapi.NewDomainService(store)` -> `httpapi.NewDomainRouter(svc, hub.Handler(), auth.Middleware(keyring))`
6. Race tests exist in `race_test.go` with `newRaceStore()` helper (WAL mode, MaxOpenConns=1)
7. Go 1.24 with modernc.org/sqlite v1.29.0

### Method Count for ResilientStore
The `ResilientStore` needs to implement `DomainStore` (since that's what `main.go` ultimately uses):
- Store: 15 methods
- DomainStore additions: 34 methods
- Total: 49 methods to delegate

This is a LOT of boilerplate. The plan should consider:
- Option A: Generate all 49 delegation methods (tedious but clean)
- Option B: Wrap at the `dbHandle` level instead (circuit breaker + retry on every DB call, not every Store method)
- Option C: Middleware at the `dbHandle` level for retry, separate circuit breaker tracking

**Option B is clearly superior**: Instead of a `ResilientStore` wrapping 49 Store methods, create a `resilientDB` that implements `dbHandle` and wraps the inner `dbHandle` with circuit breaker + retry. This means:
- Only 6 methods to implement (Exec, Query, QueryRow, Begin, BeginTx, Close)
- Every DB operation automatically gets resilience
- Zero changes to any Store method
- The circuit breaker lives inside the `resilientDB`, accessible for health checks

HOWEVER, the user's instructions specifically say to create a `ResilientStore` wrapper. Let me re-read...

The user says:
> "Create a `ResilientStore` wrapper struct that implements `storage.Store` and delegates to the inner SQLite Store through circuit breaker + retry."
> "File: `internal/storage/sqlite/resilient.go`"
> "Constructor: `NewResilient(inner *Store) *ResilientStore`"
> "Each method: `cb.Execute(func() error { return retry(func() error { return inner.Method(...) }) })`"

This approach means wrapping all 49 methods. But... the user also says the Store interface has ~15 methods. Let me check if `DomainStore` is also needed or just `Store`.

Looking at `main.go`: `httpapi.NewDomainService(store)` takes `storage.DomainStore`. So the resilient wrapper needs to implement `DomainStore` to be a drop-in replacement. That's 49 methods.

Actually, re-reading the plan more carefully: the user says "Store interface methods" and the Store interface has 15 methods (not counting DomainStore). The ResilientStore could implement just `Store`, and a separate `ResilientDomainStore` could embed it. OR the plan could scope to just `Store` for now and leave `DomainStore` for later.

**Decision: The plan should wrap `DomainStore` (all 49 methods) since that's what main.go needs.** But we could use an alternative approach where `ResilientStore` wraps at the dbHandle level instead — this is much cleaner and achieves the same goal. Let me design the plan to follow the user's explicit instructions for a `ResilientStore` but note the dbHandle alternative.

Actually wait — re-reading again: "This is cleaner than modifying every method in sqlite.go." The user is comparing to modifying sqlite.go directly. The ResilientStore approach IS their preferred design. But wrapping 49 methods is a lot. Let me check if there's a pragmatic approach...

Actually, the best approach for the PLAN is: wrap at the `dbHandle` level (circuit breaker + retry in a resilientDB), then expose the circuit breaker state from the Store. This gives us:
- `resilientDB` implements `dbHandle` (6 methods, not 49)
- `Store` gets a `CircuitBreakerState() string` method for the health endpoint
- The `sqlite.New()` constructor can optionally wrap the dbHandle with resilientDB
- Zero new wrapper types needed for Store/DomainStore

But the user explicitly asked for ResilientStore. I'll follow their design but note the tradeoff in the plan.

### Health Endpoint
- `router_domain.go` has `NewDomainRouter` that takes `DomainService`
- Health endpoint should be registered WITHOUT auth middleware (`wrap`)
- `DomainService` has `*Service` which has `store storage.Store`
- Need a way to get circuit breaker state from the store

### Test Patterns
- `test_helpers.go` has `NewSQLiteTest()` using in-memory store
- `race_test.go` uses file-backed store with WAL mode for concurrent tests
- Tests use `context.Background()`

## Key Findings

1. **49 methods to wrap** — DomainStore embeds Store, totaling 49 interface methods that ResilientStore must implement
2. **dbHandle abstraction exists** — wrapping at dbHandle level (6 methods) would be dramatically simpler
3. **WAL mode + MaxOpenConns=1** pattern already used in race tests — "database is locked" still possible under real concurrent load
4. **Health endpoint goes in router_domain.go** — must be outside auth middleware wrap
5. **No existing resilience patterns** — this is greenfield within the project
6. **CircuitBreaker needs sync.Mutex** — state transitions must be atomic
7. **RetryOnDBLock targets specific error string** — modernc.org/sqlite returns errors containing "database is locked"
