# F5: Unix Domain Socket Listener for intermute

> **For Claude:** REQUIRED SUB-SKILL: Use clavain:executing-plans to implement this plan task-by-task.

**Goal:** Add Unix domain socket listener to intermute server so local agents can connect without TCP overhead, with a health endpoint verifiable via `curl --unix-socket`.

**Tech Stack:** Go 1.24, net/http, net (Unix listener), cobra (CLI)

**Bead:** Clavain-8z9c
**Target Repo:** `/root/projects/intermute/`

---

## Task 1: Add `/health` endpoint

**Files:**
- Modify: `/root/projects/intermute/internal/http/router_domain.go`
- Create: `/root/projects/intermute/internal/http/handlers_health.go`
- Create: `/root/projects/intermute/internal/http/handlers_health_test.go`

**Step 1: Create the health handler**

Create `/root/projects/intermute/internal/http/handlers_health.go`:

```go
package httpapi

import (
	"encoding/json"
	"net/http"
)

func handleHealth(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodGet {
		http.Error(w, "method not allowed", http.StatusMethodNotAllowed)
		return
	}
	w.Header().Set("Content-Type", "application/json")
	json.NewEncoder(w).Encode(map[string]string{"status": "ok"})
}
```

**Step 2: Register in the domain router**

In `/root/projects/intermute/internal/http/router_domain.go`, add this line after the mux creation (before the existing messaging endpoints). Register it directly on `mux` without `wrap` so it is unauthenticated:

```go
// Health check (unauthenticated)
mux.HandleFunc("/health", handleHealth)
```

**Step 3: Write the test**

Create `/root/projects/intermute/internal/http/handlers_health_test.go`:

```go
package httpapi

import (
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"testing"
)

func TestHealthEndpoint(t *testing.T) {
	w := httptest.NewRecorder()
	r := httptest.NewRequest(http.MethodGet, "/health", nil)
	handleHealth(w, r)

	if w.Code != http.StatusOK {
		t.Fatalf("expected 200, got %d", w.Code)
	}

	var body map[string]string
	if err := json.NewDecoder(w.Body).Decode(&body); err != nil {
		t.Fatalf("decode: %v", err)
	}
	if body["status"] != "ok" {
		t.Fatalf("expected status ok, got %q", body["status"])
	}
}

func TestHealthEndpointRejectsPost(t *testing.T) {
	w := httptest.NewRecorder()
	r := httptest.NewRequest(http.MethodPost, "/health", nil)
	handleHealth(w, r)

	if w.Code != http.StatusMethodNotAllowed {
		t.Fatalf("expected 405, got %d", w.Code)
	}
}
```

**Step 4: Run tests**

```bash
cd /root/projects/intermute && go test ./internal/http/ -run TestHealth -v
```

Expected: Both tests PASS.

**Step 5: Commit**

```bash
git add internal/http/handlers_health.go internal/http/handlers_health_test.go internal/http/router_domain.go
git commit -m "feat: add /health endpoint (unauthenticated)"
```

---

## Task 2: Add Unix socket support to Server

**Files:**
- Modify: `/root/projects/intermute/internal/server/server.go`
- Modify: `/root/projects/intermute/internal/server/server_test.go`

**Step 1: Extend Config and Server**

Rewrite `/root/projects/intermute/internal/server/server.go` to support an optional Unix socket listener alongside TCP:

```go
package server

import (
	"context"
	"fmt"
	"net"
	"net/http"
	"os"
)

type Config struct {
	Addr       string
	SocketPath string
	Handler    http.Handler
}

type Server struct {
	cfg        Config
	http       *http.Server
	unix       *http.Server
	unixLn     net.Listener
}

func New(cfg Config) (*Server, error) {
	if cfg.Addr == "" {
		return nil, fmt.Errorf("addr required")
	}
	h := cfg.Handler
	if h == nil {
		h = http.NewServeMux()
	}
	srv := &http.Server{Addr: cfg.Addr, Handler: h}
	s := &Server{cfg: cfg, http: srv}

	if cfg.SocketPath != "" {
		// Remove stale socket file from previous run
		if err := os.Remove(cfg.SocketPath); err != nil && !os.IsNotExist(err) {
			return nil, fmt.Errorf("remove stale socket: %w", err)
		}
		ln, err := net.Listen("unix", cfg.SocketPath)
		if err != nil {
			return nil, fmt.Errorf("unix listen: %w", err)
		}
		if err := os.Chmod(cfg.SocketPath, 0660); err != nil {
			ln.Close()
			return nil, fmt.Errorf("chmod socket: %w", err)
		}
		s.unixLn = ln
		s.unix = &http.Server{Handler: h}
	}

	return s, nil
}

func (s *Server) Start() error {
	if s.unixLn != nil {
		go s.unix.Serve(s.unixLn)
	}
	return s.http.ListenAndServe()
}

func (s *Server) Shutdown(ctx context.Context) error {
	var firstErr error

	if s.unix != nil {
		if err := s.unix.Shutdown(ctx); err != nil && firstErr == nil {
			firstErr = err
		}
	}
	if s.cfg.SocketPath != "" {
		os.Remove(s.cfg.SocketPath)
	}

	if err := s.http.Shutdown(ctx); err != nil && firstErr == nil {
		firstErr = err
	}

	return firstErr
}

// SocketPath returns the configured socket path, or empty if not configured.
func (s *Server) SocketPath() string {
	return s.cfg.SocketPath
}
```

**Step 2: Write tests**

Replace `/root/projects/intermute/internal/server/server_test.go`:

```go
package server

import (
	"context"
	"encoding/json"
	"fmt"
	"net"
	"net/http"
	"os"
	"path/filepath"
	"testing"
	"time"
)

func TestServerStarts(t *testing.T) {
	if _, err := New(Config{}); err == nil {
		t.Fatalf("expected error without addr")
	}
}

func TestUnixSocket_CreatedAndRemoved(t *testing.T) {
	sockPath := filepath.Join(t.TempDir(), "test.sock")

	mux := http.NewServeMux()
	mux.HandleFunc("/health", func(w http.ResponseWriter, r *http.Request) {
		json.NewEncoder(w).Encode(map[string]string{"status": "ok"})
	})

	srv, err := New(Config{
		Addr:       "127.0.0.1:0",
		SocketPath: sockPath,
		Handler:    mux,
	})
	if err != nil {
		t.Fatalf("new: %v", err)
	}

	// Socket file should exist after New()
	if _, err := os.Stat(sockPath); err != nil {
		t.Fatalf("socket file not created: %v", err)
	}

	// Verify permissions are 0660
	info, err := os.Stat(sockPath)
	if err != nil {
		t.Fatalf("stat: %v", err)
	}
	perm := info.Mode().Perm()
	if perm != 0660 {
		t.Fatalf("expected socket perm 0660, got %o", perm)
	}

	// Start server in background
	go srv.Start()
	time.Sleep(50 * time.Millisecond)

	// Connect via unix socket and hit /health
	client := &http.Client{
		Transport: &http.Transport{
			DialContext: func(ctx context.Context, _, _ string) (net.Conn, error) {
				return net.DialTimeout("unix", sockPath, 2*time.Second)
			},
		},
	}
	resp, err := client.Get("http://unix/health")
	if err != nil {
		t.Fatalf("get via socket: %v", err)
	}
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusOK {
		t.Fatalf("expected 200, got %d", resp.StatusCode)
	}

	var body map[string]string
	if err := json.NewDecoder(resp.Body).Decode(&body); err != nil {
		t.Fatalf("decode: %v", err)
	}
	if body["status"] != "ok" {
		t.Fatalf("expected status ok, got %q", body["status"])
	}

	// Shutdown and verify socket removed
	ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
	defer cancel()
	if err := srv.Shutdown(ctx); err != nil {
		t.Fatalf("shutdown: %v", err)
	}
	if _, err := os.Stat(sockPath); !os.IsNotExist(err) {
		t.Fatalf("socket file should be removed after shutdown")
	}
}

func TestUnixSocket_StaleSocketRemoved(t *testing.T) {
	sockPath := filepath.Join(t.TempDir(), "stale.sock")

	// Create a stale socket file
	if err := os.WriteFile(sockPath, []byte("stale"), 0600); err != nil {
		t.Fatalf("write stale: %v", err)
	}

	srv, err := New(Config{
		Addr:       "127.0.0.1:0",
		SocketPath: sockPath,
		Handler:    http.NewServeMux(),
	})
	if err != nil {
		t.Fatalf("new with stale socket: %v", err)
	}

	// Socket should be a real unix socket now, not the stale file
	info, err := os.Stat(sockPath)
	if err != nil {
		t.Fatalf("stat: %v", err)
	}
	if info.Mode()&os.ModeSocket == 0 {
		t.Fatalf("expected socket file type, got %v", info.Mode())
	}

	ctx, cancel := context.WithTimeout(context.Background(), 2*time.Second)
	defer cancel()
	srv.Shutdown(ctx)
}

func TestNoSocket_TCPOnly(t *testing.T) {
	srv, err := New(Config{
		Addr:    fmt.Sprintf("127.0.0.1:%d", freePort(t)),
		Handler: http.NewServeMux(),
	})
	if err != nil {
		t.Fatalf("new: %v", err)
	}
	if srv.SocketPath() != "" {
		t.Fatalf("expected empty socket path")
	}

	go srv.Start()
	time.Sleep(50 * time.Millisecond)

	ctx, cancel := context.WithTimeout(context.Background(), 2*time.Second)
	defer cancel()
	srv.Shutdown(ctx)
}

func freePort(t *testing.T) int {
	t.Helper()
	ln, err := net.Listen("tcp", "127.0.0.1:0")
	if err != nil {
		t.Fatalf("free port: %v", err)
	}
	port := ln.Addr().(*net.TCPAddr).Port
	ln.Close()
	return port
}
```

**Step 3: Run tests**

```bash
cd /root/projects/intermute && go test ./internal/server/ -v -count=1
```

Expected: All 4 tests PASS.

**Step 4: Commit**

```bash
git add internal/server/server.go internal/server/server_test.go
git commit -m "feat: add Unix domain socket listener support to Server"
```

---

## Task 3: Wire `--socket` CLI flag

**Files:**
- Modify: `/root/projects/intermute/cmd/intermute/main.go`

**Step 1: Add the flag and pass to Config**

In `serveCmd()`, add a `socketPath` variable alongside the existing `port`, `host`, `dbPath`:

```go
var (
    port       int
    host       string
    dbPath     string
    socketPath string
)
```

Add the flag registration after the existing flags:

```go
cmd.Flags().StringVar(&socketPath, "socket", "", "Unix domain socket path (e.g. /var/run/intermute.sock)")
```

In the `RunE` function, pass `socketPath` to the server config:

```go
srv, err := server.New(server.Config{Addr: addr, SocketPath: socketPath, Handler: router})
```

After the existing `log.Printf("intermute server starting on %s", addr)` line, add a conditional log:

```go
if socketPath != "" {
    log.Printf("intermute unix socket: %s", socketPath)
}
```

**Step 2: Verify it compiles**

```bash
cd /root/projects/intermute && go build ./cmd/intermute/
```

Expected: Compiles with no errors.

**Step 3: Verify the flag shows in help**

```bash
cd /root/projects/intermute && go run ./cmd/intermute/ serve --help
```

Expected: `--socket` flag appears in output.

**Step 4: Commit**

```bash
git add cmd/intermute/main.go
git commit -m "feat: add --socket flag for Unix domain socket listener"
```

---

## Task 4: Integration test — health via Unix socket

**Files:**
- Create: `/root/projects/intermute/internal/server/integration_test.go`

This test exercises the full stack: real router with health endpoint, server with Unix socket, HTTP client connecting via socket.

**Step 1: Write the integration test**

Create `/root/projects/intermute/internal/server/integration_test.go`:

```go
package server_test

import (
	"context"
	"encoding/json"
	"net"
	"net/http"
	"os"
	"path/filepath"
	"testing"
	"time"

	httpapi "github.com/mistakeknot/intermute/internal/http"
	"github.com/mistakeknot/intermute/internal/server"
	"github.com/mistakeknot/intermute/internal/storage/sqlite"
	"github.com/mistakeknot/intermute/internal/ws"
)

func TestHealthViaUnixSocket(t *testing.T) {
	tmp := t.TempDir()
	sockPath := filepath.Join(tmp, "intermute.sock")
	dbPath := filepath.Join(tmp, "test.db")

	store, err := sqlite.New(dbPath)
	if err != nil {
		t.Fatalf("store: %v", err)
	}
	_ = store

	hub := ws.NewHub()
	svc := httpapi.NewDomainService(store).WithBroadcaster(hub)
	router := httpapi.NewDomainRouter(svc, hub.Handler(), nil)

	srv, err := server.New(server.Config{
		Addr:       "127.0.0.1:0",
		SocketPath: sockPath,
		Handler:    router,
	})
	if err != nil {
		t.Fatalf("server new: %v", err)
	}

	go srv.Start()
	time.Sleep(100 * time.Millisecond)

	// Verify socket permissions
	info, err := os.Stat(sockPath)
	if err != nil {
		t.Fatalf("stat socket: %v", err)
	}
	if perm := info.Mode().Perm(); perm != 0660 {
		t.Fatalf("expected 0660, got %o", perm)
	}

	// Connect via unix socket
	client := &http.Client{
		Transport: &http.Transport{
			DialContext: func(ctx context.Context, _, _ string) (net.Conn, error) {
				return net.DialTimeout("unix", sockPath, 2*time.Second)
			},
		},
	}

	resp, err := client.Get("http://unix/health")
	if err != nil {
		t.Fatalf("health via socket: %v", err)
	}
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusOK {
		t.Fatalf("expected 200, got %d", resp.StatusCode)
	}

	var body map[string]string
	if err := json.NewDecoder(resp.Body).Decode(&body); err != nil {
		t.Fatalf("decode: %v", err)
	}
	if body["status"] != "ok" {
		t.Fatalf("expected ok, got %q", body["status"])
	}

	// Shutdown
	ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
	defer cancel()
	if err := srv.Shutdown(ctx); err != nil {
		t.Fatalf("shutdown: %v", err)
	}

	// Socket should be cleaned up
	if _, err := os.Stat(sockPath); !os.IsNotExist(err) {
		t.Fatalf("socket should be removed after shutdown")
	}
}
```

**Step 2: Run all tests**

```bash
cd /root/projects/intermute && go test ./... -count=1 -timeout 60s
```

Expected: All tests PASS, including the new integration test.

**Step 3: Commit**

```bash
git add internal/server/integration_test.go
git commit -m "test: integration test for health endpoint via Unix socket"
```

---

## Verification Checklist

After all tasks:

```bash
cd /root/projects/intermute

# 1. All tests pass
go test ./... -count=1 -timeout 60s

# 2. Binary builds
go build ./cmd/intermute/

# 3. --socket flag exists
./intermute serve --help | grep socket

# 4. Quick manual smoke test (optional)
./intermute serve --socket /tmp/test-intermute.sock --db /tmp/test.db &
curl --unix-socket /tmp/test-intermute.sock http://localhost/health
kill %1
rm -f /tmp/test-intermute.sock /tmp/test.db
```

## Acceptance Criteria Mapping

| PRD Criterion | Task | Verified By |
|---------------|------|-------------|
| `--socket /var/run/intermute.sock` flag | Task 3 | `serve --help` output |
| Socket file mode 0660 | Task 2 | `TestUnixSocket_CreatedAndRemoved` perm check |
| Socket removed on shutdown | Task 2 | `TestUnixSocket_CreatedAndRemoved` post-shutdown stat |
| Health via `curl --unix-socket` | Task 1 + Task 4 | `TestHealthViaUnixSocket` |
| TCP remains as fallback | Task 2 | `TestNoSocket_TCPOnly`, both listeners in `Start()` |
| Tests: connect via socket, verify perms | Task 2 + Task 4 | All unix socket tests |
