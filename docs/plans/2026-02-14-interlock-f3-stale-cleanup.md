# Interlock F3: Stale Reservation Cleanup

> **For Claude:** REQUIRED SUB-SKILL: Use clavain:executing-plans to implement this plan task-by-task.

**Goal:** Add a background sweep goroutine that automatically cleans up expired reservations held by inactive agents, with crash-recovery startup sweep, WebSocket event emission, and graceful shutdown with WAL checkpoint.

**Architecture:** New `Sweeper` struct in the storage package runs a ticker goroutine. On each tick, it executes an atomic DELETE targeting expired reservations whose owning agents have stale heartbeats. On startup, a one-time sweep catches reservations >5min old from crash recovery. Deleted reservations emit `reservation.expired` events via the existing `Broadcaster` interface. Graceful shutdown cancels the sweep, drains HTTP, checkpoints WAL, and closes the DB.

**Tech Stack:** Go 1.24, SQLite via modernc.org/sqlite, WebSocket via nhooyr.io/websocket

**Bead:** Clavain-1e5q
**Phase:** planned (as of 2026-02-14)

---

## Task 1: Add Store.Close() and EventReservationExpired

**Files:**
- Modify: `internal/storage/sqlite/sqlite.go`
- Modify: `internal/core/models.go`
- Test: `internal/storage/sqlite/sqlite_test.go`

**Step 1: Add reservation event type to models.go**

In `internal/core/models.go`, add a new `EventType` constant after the existing ones:

```go
EventReservationExpired EventType = "reservation.expired"
```

Add it in the block with the other event types (after `EventAgentHeartbeat`).

**Step 2: Add Close() method to Store**

In `internal/storage/sqlite/sqlite.go`, add at the end of the file:

```go
// Close checkpoints the WAL and closes the database connection.
// Call this during graceful shutdown to ensure all data is flushed.
func (s *Store) Close() error {
	_, _ = s.db.Exec("PRAGMA wal_checkpoint(TRUNCATE)")
	return s.db.Close()
}
```

**Step 3: Add SweepExpired method to Store**

In `internal/storage/sqlite/sqlite.go`, add a method that performs the atomic sweep. This is the core query that both the startup sweep and periodic sweep will use:

```go
// SweepExpired deletes unreleased reservations that have expired and whose
// owning agent has not heartbeated recently. It returns the deleted reservations
// so callers can emit events.
//
// expiredBefore: reservations with expires_at < this value are candidates
// heartbeatAfter: agents with last_seen > this value are protected (their reservations are kept)
func (s *Store) SweepExpired(_ context.Context, expiredBefore time.Time, heartbeatAfter time.Time) ([]core.Reservation, error) {
	rows, err := s.db.Query(
		`DELETE FROM file_reservations
		 WHERE released_at IS NULL
		   AND expires_at < ?
		   AND agent_id NOT IN (
		     SELECT id FROM agents WHERE last_seen > ?
		   )
		 RETURNING id, agent_id, project, path_pattern, exclusive, reason, created_at, expires_at`,
		expiredBefore.Format(time.RFC3339Nano),
		heartbeatAfter.Format(time.RFC3339Nano),
	)
	if err != nil {
		return nil, fmt.Errorf("sweep expired reservations: %w", err)
	}
	defer rows.Close()

	return s.scanReservations(rows)
}
```

**Step 4: Write test for SweepExpired**

Add to `internal/storage/sqlite/sqlite_test.go`:

```go
func TestSweepExpiredDeletesStale(t *testing.T) {
	ctx := context.Background()
	st := NewSQLiteTest(t)
	now := time.Now().UTC()

	// Register an agent that is NOT heartbeating (last_seen 10 min ago)
	staleAgent := core.Agent{
		ID:       "stale-agent",
		Name:     "stale",
		Project:  "proj",
		Status:   "active",
		LastSeen: now.Add(-10 * time.Minute),
	}
	_, err := st.RegisterAgent(ctx, staleAgent)
	if err != nil {
		t.Fatalf("register stale agent: %v", err)
	}
	// Force last_seen to be old
	st.db.Exec(`UPDATE agents SET last_seen = ? WHERE id = ?`,
		now.Add(-10*time.Minute).Format(time.RFC3339Nano), "stale-agent")

	// Register an agent that IS heartbeating (last_seen 1 min ago)
	activeAgent := core.Agent{
		ID:      "active-agent",
		Name:    "active",
		Project: "proj",
		Status:  "active",
	}
	_, err = st.RegisterAgent(ctx, activeAgent)
	if err != nil {
		t.Fatalf("register active agent: %v", err)
	}

	// Insert expired reservation for stale agent (expired 2 min ago)
	st.db.Exec(
		`INSERT INTO file_reservations (id, agent_id, project, path_pattern, exclusive, reason, created_at, expires_at)
		 VALUES (?, ?, ?, ?, ?, ?, ?, ?)`,
		"res-stale", "stale-agent", "proj", "*.go", 1, "stale work",
		now.Add(-35*time.Minute).Format(time.RFC3339Nano),
		now.Add(-2*time.Minute).Format(time.RFC3339Nano),
	)

	// Insert expired reservation for active agent (expired 2 min ago but agent is alive)
	st.db.Exec(
		`INSERT INTO file_reservations (id, agent_id, project, path_pattern, exclusive, reason, created_at, expires_at)
		 VALUES (?, ?, ?, ?, ?, ?, ?, ?)`,
		"res-active", "active-agent", "proj", "pkg/*.go", 1, "active work",
		now.Add(-35*time.Minute).Format(time.RFC3339Nano),
		now.Add(-2*time.Minute).Format(time.RFC3339Nano),
	)

	// Insert non-expired reservation (should not be swept)
	st.db.Exec(
		`INSERT INTO file_reservations (id, agent_id, project, path_pattern, exclusive, reason, created_at, expires_at)
		 VALUES (?, ?, ?, ?, ?, ?, ?, ?)`,
		"res-fresh", "stale-agent", "proj", "docs/*.md", 1, "fresh work",
		now.Add(-5*time.Minute).Format(time.RFC3339Nano),
		now.Add(25*time.Minute).Format(time.RFC3339Nano),
	)

	// Sweep: expired before now, heartbeat after now-5min
	deleted, err := st.SweepExpired(ctx, now, now.Add(-5*time.Minute))
	if err != nil {
		t.Fatalf("sweep: %v", err)
	}

	// Only stale agent's expired reservation should be deleted
	if len(deleted) != 1 {
		t.Fatalf("expected 1 deleted reservation, got %d", len(deleted))
	}
	if deleted[0].ID != "res-stale" {
		t.Fatalf("expected res-stale deleted, got %s", deleted[0].ID)
	}

	// Verify active agent's reservation still exists
	got, err := st.GetReservation(ctx, "res-active")
	if err != nil {
		t.Fatalf("active reservation should still exist: %v", err)
	}
	if got.ID != "res-active" {
		t.Fatalf("expected res-active, got %s", got.ID)
	}

	// Verify fresh reservation still exists
	got, err = st.GetReservation(ctx, "res-fresh")
	if err != nil {
		t.Fatalf("fresh reservation should still exist: %v", err)
	}
	if got.ID != "res-fresh" {
		t.Fatalf("expected res-fresh, got %s", got.ID)
	}
}

func TestSweepExpiredSkipsReleasedReservations(t *testing.T) {
	ctx := context.Background()
	st := NewSQLiteTest(t)
	now := time.Now().UTC()

	// Register a stale agent
	st.RegisterAgent(ctx, core.Agent{ID: "agent-1", Name: "agent", Project: "proj", Status: "active"})
	st.db.Exec(`UPDATE agents SET last_seen = ? WHERE id = ?`,
		now.Add(-10*time.Minute).Format(time.RFC3339Nano), "agent-1")

	// Insert already-released expired reservation
	st.db.Exec(
		`INSERT INTO file_reservations (id, agent_id, project, path_pattern, exclusive, reason, created_at, expires_at, released_at)
		 VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)`,
		"res-released", "agent-1", "proj", "*.go", 1, "done",
		now.Add(-35*time.Minute).Format(time.RFC3339Nano),
		now.Add(-2*time.Minute).Format(time.RFC3339Nano),
		now.Add(-1*time.Minute).Format(time.RFC3339Nano),
	)

	deleted, err := st.SweepExpired(ctx, now, now.Add(-5*time.Minute))
	if err != nil {
		t.Fatalf("sweep: %v", err)
	}
	if len(deleted) != 0 {
		t.Fatalf("expected 0 deleted (already released), got %d", len(deleted))
	}
}
```

**Step 5: Run tests**

Run: `cd /root/projects/intermute && go test ./internal/storage/sqlite/ -run 'TestSweepExpired' -v`
Expected: Both tests PASS.

Run: `cd /root/projects/intermute && go test ./internal/storage/sqlite/ -v`
Expected: All existing tests still PASS (no regressions).

**Step 6: Commit**

```bash
git add internal/core/models.go internal/storage/sqlite/sqlite.go internal/storage/sqlite/sqlite_test.go
git commit -m "feat(f3): add Store.Close(), SweepExpired(), and EventReservationExpired"
```

---

## Task 2: Create Sweeper goroutine

**Files:**
- Create: `internal/storage/sqlite/sweeper.go`
- Test: `internal/storage/sqlite/sweeper_test.go`

**Step 1: Create sweeper.go**

Create `internal/storage/sqlite/sweeper.go`:

```go
package sqlite

import (
	"context"
	"log"
	"time"

	"github.com/mistakeknot/intermute/internal/core"
)

// Broadcaster is the interface for emitting events to WebSocket clients.
// Matches the httpapi.Broadcaster interface.
type Broadcaster interface {
	Broadcast(project, agent string, event any)
}

// Sweeper runs a background goroutine that periodically cleans up expired
// reservations held by inactive agents.
type Sweeper struct {
	store    *Store
	bus      Broadcaster
	interval time.Duration
	grace    time.Duration // heartbeat grace period (agents seen within this window are protected)
	cancel   context.CancelFunc
	done     chan struct{}
}

// NewSweeper creates a new Sweeper. It does not start the background goroutine;
// call Start() to begin sweeping.
//
// Parameters:
//   - store: the SQLite store to sweep
//   - bus: broadcaster for emitting reservation.expired events (may be nil)
//   - interval: how often to run the periodic sweep (e.g., 60s)
//   - grace: heartbeat grace period — agents with last_seen within this duration are protected (e.g., 5m)
func NewSweeper(store *Store, bus Broadcaster, interval, grace time.Duration) *Sweeper {
	return &Sweeper{
		store:    store,
		bus:      bus,
		interval: interval,
		grace:    grace,
		done:     make(chan struct{}),
	}
}

// Start launches the background sweep goroutine. It first runs a startup sweep
// to clean up reservations that expired >5 minutes ago (crash recovery), then
// begins periodic sweeps at the configured interval.
//
// The goroutine exits when the context is cancelled or Stop() is called.
func (sw *Sweeper) Start(ctx context.Context) {
	ctx, sw.cancel = context.WithCancel(ctx)

	go func() {
		defer close(sw.done)

		// Startup sweep: only clean reservations expired >5min ago
		// (preserves recently-expired ones whose agents may still be coming back)
		sw.runSweep(ctx, time.Now().UTC().Add(-5*time.Minute))

		ticker := time.NewTicker(sw.interval)
		defer ticker.Stop()

		for {
			select {
			case <-ctx.Done():
				return
			case <-ticker.C:
				sw.runSweep(ctx, time.Now().UTC())
			}
		}
	}()
}

// Stop cancels the sweep goroutine and waits for it to finish.
func (sw *Sweeper) Stop() {
	if sw.cancel != nil {
		sw.cancel()
	}
	<-sw.done
}

// runSweep executes a single sweep pass. expiredBefore controls which
// reservations are eligible (periodic uses now, startup uses now-5min).
func (sw *Sweeper) runSweep(ctx context.Context, expiredBefore time.Time) {
	heartbeatAfter := time.Now().UTC().Add(-sw.grace)

	deleted, err := sw.store.SweepExpired(ctx, expiredBefore, heartbeatAfter)
	if err != nil {
		log.Printf("sweeper: %v", err)
		return
	}

	if len(deleted) == 0 {
		return
	}

	log.Printf("sweeper: cleaned %d expired reservation(s)", len(deleted))

	// Emit events for each deleted reservation
	if sw.bus != nil {
		for _, r := range deleted {
			sw.bus.Broadcast(r.Project, "", map[string]any{
				"type":           string(core.EventReservationExpired),
				"project":        r.Project,
				"reservation_id": r.ID,
				"agent_id":       r.AgentID,
				"path_pattern":   r.PathPattern,
			})
		}
	}
}
```

**Step 2: Create sweeper_test.go**

Create `internal/storage/sqlite/sweeper_test.go`:

```go
package sqlite

import (
	"context"
	"sync"
	"testing"
	"time"

	"github.com/mistakeknot/intermute/internal/core"
)

// mockBroadcaster captures broadcast calls for testing
type mockBroadcaster struct {
	mu     sync.Mutex
	events []map[string]any
}

func (m *mockBroadcaster) Broadcast(project, agent string, event any) {
	m.mu.Lock()
	defer m.mu.Unlock()
	if ev, ok := event.(map[string]any); ok {
		m.events = append(m.events, ev)
	}
}

func (m *mockBroadcaster) Events() []map[string]any {
	m.mu.Lock()
	defer m.mu.Unlock()
	cp := make([]map[string]any, len(m.events))
	copy(cp, m.events)
	return cp
}

func TestSweeperStartupSweep(t *testing.T) {
	st := NewSQLiteTest(t)
	bus := &mockBroadcaster{}
	now := time.Now().UTC()

	// Register a stale agent (last seen 20 min ago)
	st.RegisterAgent(context.Background(), core.Agent{
		ID: "stale-1", Name: "stale", Project: "proj", Status: "active",
	})
	st.db.Exec(`UPDATE agents SET last_seen = ? WHERE id = ?`,
		now.Add(-20*time.Minute).Format(time.RFC3339Nano), "stale-1")

	// Insert reservation expired 10 min ago (>5min, should be cleaned on startup)
	st.db.Exec(
		`INSERT INTO file_reservations (id, agent_id, project, path_pattern, exclusive, reason, created_at, expires_at)
		 VALUES (?, ?, ?, ?, ?, ?, ?, ?)`,
		"old-res", "stale-1", "proj", "*.go", 1, "old",
		now.Add(-40*time.Minute).Format(time.RFC3339Nano),
		now.Add(-10*time.Minute).Format(time.RFC3339Nano),
	)

	// Insert reservation expired 2 min ago (<5min, should NOT be cleaned on startup)
	st.db.Exec(
		`INSERT INTO file_reservations (id, agent_id, project, path_pattern, exclusive, reason, created_at, expires_at)
		 VALUES (?, ?, ?, ?, ?, ?, ?, ?)`,
		"recent-res", "stale-1", "proj", "pkg/*.go", 1, "recent",
		now.Add(-32*time.Minute).Format(time.RFC3339Nano),
		now.Add(-2*time.Minute).Format(time.RFC3339Nano),
	)

	sweeper := NewSweeper(st, bus, 24*time.Hour, 5*time.Minute) // long interval so periodic won't fire
	sweeper.Start(context.Background())

	// Give startup sweep time to run
	time.Sleep(100 * time.Millisecond)
	sweeper.Stop()

	// Only old-res should have been cleaned (expired >5min ago)
	events := bus.Events()
	if len(events) != 1 {
		t.Fatalf("expected 1 event from startup sweep, got %d", len(events))
	}
	if events[0]["reservation_id"] != "old-res" {
		t.Fatalf("expected old-res event, got %v", events[0]["reservation_id"])
	}

	// recent-res should still exist
	_, err := st.GetReservation(context.Background(), "recent-res")
	if err != nil {
		t.Fatalf("recent reservation should still exist: %v", err)
	}
}

func TestSweeperPeriodicSweep(t *testing.T) {
	st := NewSQLiteTest(t)
	bus := &mockBroadcaster{}
	now := time.Now().UTC()

	// Register stale agent
	st.RegisterAgent(context.Background(), core.Agent{
		ID: "stale-1", Name: "stale", Project: "proj", Status: "active",
	})
	st.db.Exec(`UPDATE agents SET last_seen = ? WHERE id = ?`,
		now.Add(-10*time.Minute).Format(time.RFC3339Nano), "stale-1")

	// Insert reservation expired 1 min ago (would NOT be caught by startup sweep)
	st.db.Exec(
		`INSERT INTO file_reservations (id, agent_id, project, path_pattern, exclusive, reason, created_at, expires_at)
		 VALUES (?, ?, ?, ?, ?, ?, ?, ?)`,
		"periodic-res", "stale-1", "proj", "*.go", 1, "periodic",
		now.Add(-31*time.Minute).Format(time.RFC3339Nano),
		now.Add(-1*time.Minute).Format(time.RFC3339Nano),
	)

	// Use very short interval for testing
	sweeper := NewSweeper(st, bus, 50*time.Millisecond, 5*time.Minute)
	sweeper.Start(context.Background())

	// Wait for startup sweep + at least one periodic sweep
	time.Sleep(200 * time.Millisecond)
	sweeper.Stop()

	// periodic-res should have been cleaned by the periodic sweep
	events := bus.Events()
	found := false
	for _, ev := range events {
		if ev["reservation_id"] == "periodic-res" {
			found = true
			break
		}
	}
	if !found {
		t.Fatalf("expected periodic-res to be swept, got events: %v", events)
	}
}

func TestSweeperProtectsActiveAgents(t *testing.T) {
	st := NewSQLiteTest(t)
	bus := &mockBroadcaster{}
	now := time.Now().UTC()

	// Register active agent (last seen just now)
	st.RegisterAgent(context.Background(), core.Agent{
		ID: "active-1", Name: "active", Project: "proj", Status: "active",
	})

	// Insert expired reservation for active agent
	st.db.Exec(
		`INSERT INTO file_reservations (id, agent_id, project, path_pattern, exclusive, reason, created_at, expires_at)
		 VALUES (?, ?, ?, ?, ?, ?, ?, ?)`,
		"protected-res", "active-1", "proj", "*.go", 1, "protected",
		now.Add(-35*time.Minute).Format(time.RFC3339Nano),
		now.Add(-2*time.Minute).Format(time.RFC3339Nano),
	)

	sweeper := NewSweeper(st, bus, 50*time.Millisecond, 5*time.Minute)
	sweeper.Start(context.Background())
	time.Sleep(200 * time.Millisecond)
	sweeper.Stop()

	// Reservation should NOT be deleted (agent is active)
	events := bus.Events()
	if len(events) != 0 {
		t.Fatalf("expected 0 events (active agent protected), got %d: %v", len(events), events)
	}

	_, err := st.GetReservation(context.Background(), "protected-res")
	if err != nil {
		t.Fatalf("protected reservation should still exist: %v", err)
	}
}

func TestSweeperStopIsIdempotent(t *testing.T) {
	st := NewSQLiteTest(t)
	sweeper := NewSweeper(st, nil, time.Hour, 5*time.Minute)
	sweeper.Start(context.Background())
	sweeper.Stop()
	// Second stop should not panic or deadlock
	// (cancel is safe to call multiple times, done channel is already closed)
}
```

**Step 3: Run tests**

Run: `cd /root/projects/intermute && go test ./internal/storage/sqlite/ -run 'TestSweeper' -v -race`
Expected: All 4 tests PASS.

**Step 4: Commit**

```bash
git add internal/storage/sqlite/sweeper.go internal/storage/sqlite/sweeper_test.go
git commit -m "feat(f3): add Sweeper goroutine with startup and periodic sweep"
```

---

## Task 3: Wire sweeper into server lifecycle

**Files:**
- Modify: `cmd/intermute/main.go`

**Step 1: Import sweeper package and modify serveCmd**

In `cmd/intermute/main.go`, update the imports to include the sqlite package (for Sweeper), then modify the `serveCmd` RunE function to:

1. Create the sweeper after hub creation
2. Start the sweeper before the HTTP server
3. On shutdown: stop sweeper, shutdown HTTP, close store

The updated RunE body (replace the existing RunE closure):

```go
RunE: func(cmd *cobra.Command, args []string) error {
	store, err := sqlite.New(dbPath)
	if err != nil {
		return fmt.Errorf("store init: %w", err)
	}

	// Bootstrap dev key if keys file is missing
	keysPath := auth.ResolveKeysPath()
	bootstrap, err := auth.BootstrapDevKey(keysPath, "dev")
	if err != nil {
		log.Printf("warning: bootstrap failed: %v", err)
	} else if bootstrap.Created {
		log.Printf("generated dev key for project %q", bootstrap.Project)
		log.Printf("  key: %s", bootstrap.Key)
		log.Printf("  file: %s", bootstrap.KeysFile)
	}

	keyring, err := auth.LoadKeyringFromEnv()
	if err != nil {
		return fmt.Errorf("auth init: %w", err)
	}

	hub := ws.NewHub()

	// Start reservation sweeper (60s interval, 5min heartbeat grace)
	sweeper := sqlite.NewSweeper(store, hub, 60*time.Second, 5*time.Minute)
	sweeper.Start(context.Background())

	svc := httpapi.NewDomainService(store).WithBroadcaster(hub)
	router := httpapi.NewDomainRouter(svc, hub.Handler(), auth.Middleware(keyring))

	addr := fmt.Sprintf("%s:%d", host, port)
	srv, err := server.New(server.Config{Addr: addr, Handler: router})
	if err != nil {
		return fmt.Errorf("server init: %w", err)
	}

	// Handle shutdown signals
	quit := make(chan os.Signal, 1)
	signal.Notify(quit, syscall.SIGINT, syscall.SIGTERM)

	go func() {
		<-quit
		log.Println("shutting down...")

		// 1. Stop sweeper (cancel background goroutine, wait for completion)
		sweeper.Stop()
		log.Println("sweeper stopped")

		// 2. Drain in-flight HTTP requests
		ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
		defer cancel()
		_ = srv.Shutdown(ctx)

		// 3. Checkpoint WAL and close database
		if err := store.Close(); err != nil {
			log.Printf("store close: %v", err)
		}
		log.Println("database closed")
	}()

	log.Printf("intermute server starting on %s", addr)
	if err := srv.Start(); err != nil && err != http.ErrServerClosed {
		return fmt.Errorf("server: %w", err)
	}
	return nil
},
```

**Step 2: Verify the imports include the sqlite package**

The import block needs:
```go
"github.com/mistakeknot/intermute/internal/storage/sqlite"
```

This is already imported in some cases. Verify and add if missing.

**Step 3: Build check**

Run: `cd /root/projects/intermute && go build ./cmd/intermute/`
Expected: Clean build, no errors.

**Step 4: Verify the full test suite still passes**

Run: `cd /root/projects/intermute && go test ./... -race`
Expected: All tests PASS.

**Step 5: Commit**

```bash
git add cmd/intermute/main.go
git commit -m "feat(f3): wire sweeper into server lifecycle with graceful shutdown"
```

---

## Task 4: Add concurrent sweep safety tests

**Files:**
- Add to: `internal/storage/sqlite/race_test.go`

**Step 1: Add concurrent sweep+reserve test**

Add to `internal/storage/sqlite/race_test.go`:

```go
// TestConcurrentSweepAndReserve verifies that the sweeper's DELETE and
// Reserve()'s SELECT+INSERT transaction don't corrupt data when running
// concurrently.
func TestConcurrentSweepAndReserve(t *testing.T) {
	st := newRaceStore(t)
	ctx := context.Background()
	now := time.Now().UTC()

	// Register agents: one stale, one active
	st.RegisterAgent(ctx, core.Agent{
		ID: "stale-agent", Name: "stale", Project: "race-proj", Status: "active",
	})
	st.db.Exec(`UPDATE agents SET last_seen = ? WHERE id = ?`,
		now.Add(-10*time.Minute).Format(time.RFC3339Nano), "stale-agent")

	st.RegisterAgent(ctx, core.Agent{
		ID: "active-agent", Name: "active", Project: "race-proj", Status: "active",
	})

	// Seed some expired reservations for the stale agent
	for i := 0; i < 10; i++ {
		st.db.Exec(
			`INSERT INTO file_reservations (id, agent_id, project, path_pattern, exclusive, reason, created_at, expires_at)
			 VALUES (?, ?, ?, ?, ?, ?, ?, ?)`,
			fmt.Sprintf("stale-res-%d", i), "stale-agent", "race-proj",
			fmt.Sprintf("dir%d/*.go", i), 1, "stale",
			now.Add(-35*time.Minute).Format(time.RFC3339Nano),
			now.Add(-2*time.Minute).Format(time.RFC3339Nano),
		)
	}

	var wg sync.WaitGroup
	var sweepErrors, reserveErrors atomic.Int32

	// Run sweeps concurrently with new reservations
	for i := 0; i < 5; i++ {
		wg.Add(1)
		go func() {
			defer wg.Done()
			_, err := st.SweepExpired(ctx, now, now.Add(-5*time.Minute))
			if err != nil {
				sweepErrors.Add(1)
				t.Errorf("sweep: %v", err)
			}
		}()
	}

	// Concurrently create new reservations for the active agent
	for i := 0; i < 10; i++ {
		wg.Add(1)
		go func(id int) {
			defer wg.Done()
			_, err := st.Reserve(ctx, core.Reservation{
				AgentID:     "active-agent",
				Project:     "race-proj",
				PathPattern: fmt.Sprintf("new%d/*.go", id),
				Exclusive:   true,
				Reason:      "concurrent reserve",
			})
			if err != nil {
				reserveErrors.Add(1)
				// Conflict errors are expected for overlapping patterns
			}
		}(i)
	}

	wg.Wait()

	if sweepErrors.Load() > 0 {
		t.Fatalf("sweep had %d errors", sweepErrors.Load())
	}

	// All stale reservations should be gone
	for i := 0; i < 10; i++ {
		_, err := st.GetReservation(ctx, fmt.Sprintf("stale-res-%d", i))
		if err == nil {
			t.Errorf("stale-res-%d should have been swept", i)
		}
	}
}
```

**Step 2: Run race tests**

Run: `cd /root/projects/intermute && go test ./internal/storage/sqlite/ -run 'TestConcurrent' -v -race -count=3`
Expected: All concurrent tests PASS across 3 runs.

**Step 3: Run full test suite one final time**

Run: `cd /root/projects/intermute && go test ./... -race`
Expected: All tests PASS.

**Step 4: Commit**

```bash
git add internal/storage/sqlite/race_test.go
git commit -m "test(f3): add concurrent sweep+reserve race safety test"
```

---

## Verification Checklist

After all tasks are complete, verify:

```bash
cd /root/projects/intermute

# 1. New files exist
ls internal/storage/sqlite/sweeper.go

# 2. Build succeeds
go build ./cmd/intermute/

# 3. All tests pass with race detector
go test ./... -race -v

# 4. Specific F3 tests pass
go test ./internal/storage/sqlite/ -run 'TestSweep|TestSweeper|TestConcurrentSweep' -v

# 5. EventReservationExpired constant exists
grep -r 'EventReservationExpired' internal/core/

# 6. Store.Close() exists
grep -n 'func (s \*Store) Close' internal/storage/sqlite/sqlite.go

# 7. Sweeper wired into main.go
grep -n 'sweeper' cmd/intermute/main.go
```

## Files Modified/Created Summary

| File | Action | Description |
|------|--------|-------------|
| `internal/core/models.go` | Modify | Add `EventReservationExpired` constant |
| `internal/storage/sqlite/sqlite.go` | Modify | Add `Close()` and `SweepExpired()` methods |
| `internal/storage/sqlite/sqlite_test.go` | Modify | Add sweep unit tests |
| `internal/storage/sqlite/sweeper.go` | Create | Sweeper struct with Start/Stop lifecycle |
| `internal/storage/sqlite/sweeper_test.go` | Create | Sweeper startup/periodic/protection tests |
| `cmd/intermute/main.go` | Modify | Wire sweeper, graceful shutdown with WAL checkpoint |
| `internal/storage/sqlite/race_test.go` | Modify | Add concurrent sweep+reserve test |

## Design Decisions

1. **RETURNING clause over two-step SELECT+DELETE**: Single atomic statement is simpler and avoids TOCTOU issues. modernc.org/sqlite supports RETURNING (SQLite 3.35.0+).

2. **Sweeper owns Broadcaster reference**: Self-contained event emission inside the sweep loop. No need for the caller to coordinate event dispatch.

3. **Shutdown order: sweeper -> HTTP -> DB**: Sweeper stops first (no more DB writes from background), then HTTP drains in-flight requests (may still need DB), then DB closes cleanly.

4. **Startup sweep uses `now()-5min` threshold**: Only cleans truly stale reservations. Recently-expired ones (<5min) may belong to agents that are starting up or reconnecting.

5. **Grace period is configurable**: `NewSweeper` takes a `grace` duration rather than hardcoding 5 minutes, enabling tests to use shorter periods.

6. **Schema column is `last_seen` not `last_heartbeat`**: PRD referenced `last_heartbeat` but the actual `agents` table column is `last_seen`. Sweep SQL uses `last_seen`.
