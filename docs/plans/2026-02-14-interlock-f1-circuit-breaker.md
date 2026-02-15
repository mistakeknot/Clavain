# F1: Circuit Breaker + Retry for SQLite Resilience — Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use clavain:executing-plans to implement this plan task-by-task.

**Goal:** Add a 3-state circuit breaker and exponential-backoff retry with jitter to intermute's SQLite Store layer, preventing cascade failures under sustained DB pressure and recovering gracefully from transient "database is locked" errors.

**Architecture:** The circuit breaker and retry logic wrap at the Store method level via a `ResilientStore` decorator that implements `storage.DomainStore` and delegates every method to the inner `*sqlite.Store` through `CircuitBreaker.Execute()` + `RetryOnDBLock()`. The circuit breaker state is exposed via a `HealthChecker` interface consumed by a new `/health` endpoint on the HTTP router. The `ResilientStore` implements all 49 methods of `DomainStore` (15 from `Store` + 34 domain methods). Each delegation method follows the pattern: `cb.Execute(func() error { return RetryOnDBLock(func() error { return inner.Method(...) }) })`. Methods returning values use a closure-captured variable for the result.

**Tech Stack:** Go 1.24, modernc.org/sqlite v1.29.0

**Bead:** Clavain-f8si

**PRD:** `docs/prds/2026-02-14-interlock-multi-agent-coordination.md` (F1)

---

### Task 1: Circuit Breaker Core

**Files:**
- Create: `internal/storage/sqlite/circuitbreaker.go`
- Create: `internal/storage/sqlite/circuitbreaker_test.go`

**Steps:**
1. Define `BreakerState` type as `int` with constants `StateClosed = 0`, `StateOpen = 1`, `StateHalfOpen = 2`. Add a `String()` method returning `"closed"`, `"open"`, `"half_open"`.
2. Define `CircuitBreaker` struct:
   ```go
   type CircuitBreaker struct {
       mu             sync.Mutex
       state          BreakerState
       failures       int
       threshold      int           // default 5
       resetTimeout   time.Duration // default 30s
       lastFailure    time.Time
   }
   ```
3. Constructor `NewCircuitBreaker(threshold int, resetTimeout time.Duration) *CircuitBreaker` — returns with state CLOSED.
4. Implement `Execute(fn func() error) error`:
   - Lock mutex at start, check state:
     - **CLOSED**: unlock, run fn. If fn returns error: lock, increment failures, if failures >= threshold set state=OPEN + record lastFailure, unlock. If fn succeeds: lock, reset failures to 0, unlock.
     - **OPEN**: check if `time.Since(lastFailure) >= resetTimeout`. If yes: set state=HALF_OPEN, unlock, run fn. If fn succeeds: lock, set state=CLOSED, reset failures, unlock. If fn fails: lock, set state=OPEN, record lastFailure, unlock. If timeout not reached: unlock, return `ErrCircuitOpen`.
     - **HALF_OPEN**: unlock, return `ErrCircuitOpen` (only one probe allowed per reset cycle — the OPEN->HALF_OPEN transition handles the single probe).
   - Important: unlock mutex BEFORE calling fn to avoid holding the lock during DB operations.
5. Implement `State() BreakerState` — lock, read state, unlock, return.
6. Define sentinel error: `var ErrCircuitOpen = errors.New("circuit breaker is open")`.
7. Write tests in `circuitbreaker_test.go`:
   - `TestBreakerStartsClosed` — new breaker has state CLOSED.
   - `TestBreakerOpensAfterThreshold` — inject 5 consecutive errors, verify state becomes OPEN.
   - `TestBreakerRejectsWhenOpen` — after opening, Execute returns `ErrCircuitOpen` without calling fn.
   - `TestBreakerResetsAfterTimeout` — open the breaker, advance time (use a `nowFunc` field for testing), verify transitions to HALF_OPEN and allows one request. On success: verify returns to CLOSED. On failure: verify returns to OPEN.
   - `TestBreakerSuccessResetsFailureCount` — 3 failures then 1 success then 3 failures should NOT open (threshold 5).
   - `TestBreakerConcurrentAccess` — 100 goroutines calling Execute simultaneously, verify no races (run with `-race`).
   - Use a `nowFunc func() time.Time` field on `CircuitBreaker` (defaults to `time.Now`) for deterministic time testing.

**Acceptance criteria:**
- [x] `CircuitBreaker` struct with `sync.Mutex`, states CLOSED/OPEN/HALF_OPEN, threshold 5, reset 30s
- [x] Breaker opens after threshold consecutive failures
- [x] Breaker resets after timeout
- [x] `go test -race` passes

---

### Task 2: Retry with Exponential Backoff and Jitter

**Files:**
- Create: `internal/storage/sqlite/retry.go`
- Create: `internal/storage/sqlite/retry_test.go`

**Steps:**
1. Define `RetryConfig` struct:
   ```go
   type RetryConfig struct {
       MaxRetries int           // default 7
       BaseDelay  time.Duration // default 50ms
       JitterPct  float64       // default 0.25 (25%)
   }
   ```
2. Define `DefaultRetryConfig()` returning the defaults.
3. Implement `RetryOnDBLock(fn func() error) error` using `DefaultRetryConfig()`.
4. Implement `RetryOnDBLockWithConfig(cfg RetryConfig, fn func() error) error`:
   - Call fn. If nil error, return nil.
   - Check if error message contains `"database is locked"` (case-insensitive via `strings.Contains(strings.ToLower(err.Error()), "database is locked")`).
   - If not a lock error, return immediately (no retry).
   - For retries 1..MaxRetries:
     - Calculate delay: `baseDelay * 2^(attempt-1)` — giving 50ms, 100ms, 200ms, 400ms, 800ms, 1600ms, 3200ms.
     - Apply jitter: `delay = delay + time.Duration(float64(delay) * rand.Float64() * cfg.JitterPct)`.
     - Sleep for delay.
     - Call fn again. If success, return nil. If non-lock error, return immediately.
   - After all retries exhausted, return the last error.
5. Use `math/rand/v2` (Go 1.22+) for jitter — no need for explicit seed.
6. For testability, add an internal variant that accepts a `sleepFunc func(time.Duration)` so tests can verify timing without actually sleeping.
7. Write tests in `retry_test.go`:
   - `TestRetrySucceedsOnTransientLock` — fn fails 3 times with "database is locked" then succeeds. Verify total calls = 4.
   - `TestRetryNoRetryOnOtherErrors` — fn returns "unique constraint violated". Verify fn called exactly once.
   - `TestRetryExhaustsAllAttempts` — fn always returns "database is locked". Verify fn called MaxRetries+1 times (1 initial + 7 retries = 8).
   - `TestRetrySucceedsImmediately` — fn returns nil. Verify fn called once.
   - `TestRetryJitterBounds` — capture sleep durations via sleepFunc, verify each is within `[delay, delay*1.25]`.
   - `TestRetryExponentialBackoff` — capture sleep durations, verify each is ~2x the previous (within jitter bounds).

**Acceptance criteria:**
- [x] `RetryOnDBLock` function: 7 retries, 0.05s base, 25% jitter, targets "database is locked"
- [x] Retry succeeds on transient lock
- [x] No retry on non-lock errors
- [x] `go test -race` passes

---

### Task 3: ResilientStore Wrapper

**Files:**
- Create: `internal/storage/sqlite/resilient.go`
- Create: `internal/storage/sqlite/resilient_test.go`

**Steps:**
1. Define `ResilientStore` struct:
   ```go
   type ResilientStore struct {
       inner *Store
       cb    *CircuitBreaker
   }
   ```
2. Constructor `NewResilient(inner *Store) *ResilientStore` — creates with `NewCircuitBreaker(5, 30*time.Second)`.
3. Add `NewResilientWithBreaker(inner *Store, cb *CircuitBreaker) *ResilientStore` for testing.
4. Implement all 15 `storage.Store` methods. Each follows this pattern (example for `AppendEvent`):
   ```go
   func (r *ResilientStore) AppendEvent(ctx context.Context, ev core.Event) (uint64, error) {
       var result uint64
       err := r.cb.Execute(func() error {
           return RetryOnDBLock(func() error {
               var innerErr error
               result, innerErr = r.inner.AppendEvent(ctx, ev)
               return innerErr
           })
       })
       return result, err
   }
   ```
5. Implement all 34 `storage.DomainStore` methods using the same pattern.
6. Add `CircuitBreakerState() string` method: `return r.cb.State().String()`.
7. Verify interface satisfaction with compile-time checks:
   ```go
   var _ storage.DomainStore = (*ResilientStore)(nil)
   ```
8. Write tests in `resilient_test.go`:
   - Use a test helper `errorStore` that wraps `*Store` (created via `NewInMemory()`) and injects errors via an `errFunc` field.
   - `TestResilientDelegatesToInner` — normal operations pass through (register agent, append event, read inbox).
   - `TestResilientCircuitBreakerTrips` — inject 5 consecutive errors, verify 6th call returns `ErrCircuitOpen`.
   - `TestResilientRetryOnLock` — inject "database is locked" error for first 2 calls then succeed, verify operation succeeds.
   - `TestResilientCircuitBreakerState` — verify `CircuitBreakerState()` returns "closed" initially, "open" after threshold failures.
   - All tests must pass with `go test -race`.

**Note on method count:** The `DomainStore` interface has 49 methods total. Each delegation method is mechanical boilerplate following the same pattern. For methods returning `(T, error)`, use a closure-captured variable. For methods returning just `error`, the closure returns the inner error directly. Methods with no error return don't exist in the current interface — all methods return error.

**Acceptance criteria:**
- [x] Store interface methods wrapped with both circuit breaker and retry
- [x] ResilientStore satisfies `storage.DomainStore` interface
- [x] Circuit breaker state accessible via `CircuitBreakerState()` method
- [x] `go test -race` passes

---

### Task 4: Health Endpoint

**Files:**
- Modify: `internal/http/router_domain.go` — add `/health` route
- Create: `internal/http/handlers_health.go` — health handler
- Modify: `internal/http/handlers_domain.go` — add `HealthChecker` field to `DomainService`
- Modify: `cmd/intermute/main.go` — pass `ResilientStore` and wire health checker
- Create: `internal/http/handlers_health_test.go` — health endpoint test

**Steps:**
1. Define `HealthChecker` interface in `handlers_health.go`:
   ```go
   type HealthChecker interface {
       CircuitBreakerState() string
   }
   ```
2. Add `health HealthChecker` field to `DomainService` struct in `handlers_domain.go`.
3. Add `WithHealthChecker(h HealthChecker) *DomainService` method.
4. Implement `handleHealth` handler in `handlers_health.go`:
   ```go
   func (s *DomainService) handleHealth(w http.ResponseWriter, r *http.Request) {
       if r.Method != http.MethodGet {
           http.Error(w, "method not allowed", http.StatusMethodNotAllowed)
           return
       }
       state := "unknown"
       if s.health != nil {
           state = s.health.CircuitBreakerState()
       }
       status := "ok"
       if state == "open" {
           status = "degraded"
       }
       w.Header().Set("Content-Type", "application/json")
       json.NewEncoder(w).Encode(map[string]string{
           "status":          status,
           "circuit_breaker": state,
       })
   }
   ```
5. Register `/health` in `NewDomainRouter` **without** the `wrap` middleware (no auth required):
   ```go
   mux.HandleFunc("/health", svc.handleHealth)
   ```
   Place this BEFORE the authenticated routes.
6. Update `cmd/intermute/main.go`:
   - Change `sqlite.New(dbPath)` to create the base store, then wrap with `sqlite.NewResilient(baseStore)`.
   - Pass `resilientStore` to `NewDomainService()`.
   - Call `.WithHealthChecker(resilientStore)` on the DomainService.
   ```go
   baseStore, err := sqlite.New(dbPath)
   if err != nil {
       return fmt.Errorf("store init: %w", err)
   }
   store := sqlite.NewResilient(baseStore)
   // ...
   svc := httpapi.NewDomainService(store).WithBroadcaster(hub).WithHealthChecker(store)
   ```
7. Write tests in `handlers_health_test.go`:
   - `TestHealthEndpointClosed` — mock `HealthChecker` returning "closed", verify JSON response `{"status":"ok","circuit_breaker":"closed"}`.
   - `TestHealthEndpointOpen` — mock returning "open", verify `{"status":"degraded","circuit_breaker":"open"}`.
   - `TestHealthEndpointNoAuth` — verify `/health` is accessible without auth token.
   - `TestHealthEndpointMethodNotAllowed` — POST to `/health` returns 405.

**Acceptance criteria:**
- [x] Circuit breaker state exposed via `/health` endpoint (`"circuit_breaker": "closed|open|half_open"`)
- [x] Health endpoint requires no authentication
- [x] Returns `"status": "ok"` when closed, `"status": "degraded"` when open

---

### Task 5: Integration Tests + Race Verification

**Files:**
- Create: `internal/storage/sqlite/resilient_integration_test.go`
- Modify: `internal/storage/sqlite/race_test.go` — add resilient race tests

**Steps:**
1. Create `resilient_integration_test.go` with end-to-end tests:
   - `TestResilientStoreFullWorkflow` — create a file-backed resilient store, register agent, append events, read inbox, verify all operations succeed through the resilient wrapper.
   - `TestResilientStoreCircuitBreakerRecovery` — use a custom `CircuitBreaker` with short reset timeout (100ms), inject errors to open it, wait for reset, verify recovery.
   - `TestResilientStoreLockRetryIntegration` — use a file-backed DB, create two stores pointing to the same file (one with MaxOpenConns > 1 to provoke lock contention), verify retry recovers.
2. Add resilient race tests to `race_test.go`:
   - `TestConcurrentResilientAppendEvent` — same as `TestConcurrentAppendEvent` but through `ResilientStore`. 10 goroutines, 10 messages each, verify all 100 delivered.
   - `TestConcurrentResilientCircuitBreaker` — 50 goroutines doing mixed reads/writes through `ResilientStore`, verify no data races.
3. Run full test suite with race detector:
   ```bash
   cd /root/projects/intermute && go test -race ./internal/storage/sqlite/...
   ```
4. Run health endpoint tests:
   ```bash
   cd /root/projects/intermute && go test -race ./internal/http/...
   ```
5. Run full project test suite:
   ```bash
   cd /root/projects/intermute && go test -race ./...
   ```

**Acceptance criteria:**
- [x] Unit tests: breaker opens after threshold, resets after timeout, retry succeeds on transient lock
- [x] Integration tests verify full workflow through resilient wrapper
- [x] `go test -race` passes on ALL packages
- [x] No regressions in existing tests

---

### Task 6: Documentation + Cleanup

**Files:**
- Modify: `internal/storage/sqlite/circuitbreaker.go` — add package-level doc comment
- Modify: `internal/storage/sqlite/retry.go` — add package-level doc comment
- Modify: `internal/storage/sqlite/resilient.go` — add package-level doc comment

**Steps:**
1. Add doc comments to all exported types and functions:
   - `CircuitBreaker` — describe 3-state model, threshold, reset behavior.
   - `RetryOnDBLock` — describe exponential backoff, jitter, targeted error matching.
   - `ResilientStore` — describe decorator pattern, how it composes circuit breaker + retry.
2. Verify all new files have consistent copyright/package headers.
3. Run `go vet ./...` to verify no issues.
4. Run `gofmt` / `goimports` on all new files.
5. Verify the full existing test suite still passes:
   ```bash
   cd /root/projects/intermute && go test ./...
   ```

**Acceptance criteria:**
- [x] All exported symbols have doc comments
- [x] `go vet` passes
- [x] `gofmt` clean
- [x] Full test suite green

---

## Pre-flight Checklist
- [ ] Verify Go 1.24 toolchain installed: `go version`
- [ ] Verify project builds clean: `cd /root/projects/intermute && go build ./...`
- [ ] Verify existing tests pass: `cd /root/projects/intermute && go test ./...`
- [ ] Verify race tests pass: `cd /root/projects/intermute && go test -race ./internal/storage/sqlite/...`
- [ ] Read `internal/storage/storage.go` to confirm Store interface method count (15)
- [ ] Read `internal/storage/domain.go` to confirm DomainStore method count (34 additional = 49 total)
- [ ] Confirm no existing circuit breaker or retry code: `grep -r "circuit" /root/projects/intermute/internal/`

## Post-execution Checklist
- [ ] All 6 tasks completed
- [ ] `go test -race ./...` passes from project root
- [ ] `/health` endpoint returns valid JSON with circuit_breaker state
- [ ] `go vet ./...` clean
- [ ] New files: `circuitbreaker.go`, `circuitbreaker_test.go`, `retry.go`, `retry_test.go`, `resilient.go`, `resilient_test.go`, `resilient_integration_test.go`, `handlers_health.go`, `handlers_health_test.go`
- [ ] Modified files: `router_domain.go`, `handlers_domain.go`, `main.go`, `race_test.go`
- [ ] No regressions in existing functionality
- [ ] Bead Clavain-f8si updated with completion status
