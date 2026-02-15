# Research: F5 Unix Domain Socket Listener for intermute

## Analysis Date: 2026-02-14

## Codebase Assessment

### Target Repo: `/root/projects/intermute/` (Go 1.24)

**Server architecture is minimal and clean.** Two layers:

1. **`cmd/intermute/main.go`** — Cobra CLI with `serve` subcommand. Creates store, hub, service, router, server. Signal handling via `SIGINT`/`SIGTERM` with 5s graceful shutdown context. Current flags: `--port 7338`, `--host 127.0.0.1`, `--db intermute.db`.

2. **`internal/server/server.go`** — 37-line wrapper around `*http.Server`. Config holds `Addr` and `Handler`. `Start()` calls `ListenAndServe()`, `Shutdown(ctx)` delegates to `http.Server.Shutdown(ctx)`.

**No health endpoint exists.** Searched all Go files for `/health`, `healthz`, `health` — zero matches. Both routers (`router.go` and `router_domain.go`) have no health route. F5 acceptance criteria require health to be accessible via unix socket, so a minimal health handler is needed.

**Embedded server** (`pkg/embedded/server.go`) is a separate higher-level wrapper for in-process use. It creates its own `http.Server` directly, bypassing `internal/server`. This means unix socket support only needs to go in `internal/server/server.go` — the embedded server is not affected by F5.

**Client library** (`client/client.go`) uses `BaseURL` string and `*http.Client`. For unix socket client support, callers would need to configure a custom `http.Transport` with a `DialContext` that connects to the socket. This is outside F5 scope (F5 is server-side only), but worth noting for future client work.

### Key Design Decisions

1. **Two listeners, one handler.** The cleanest approach is to keep a single `http.Handler` (the router) and serve it on two listeners: TCP via `ListenAndServe()` and Unix via `http.Serve(unixListener, handler)`. This avoids duplicating handler setup.

2. **Socket lifecycle.** `net.Listen("unix", path)` creates the socket file. If a stale socket exists from a crash, `os.Remove` before `net.Listen` is standard practice. After creation, `os.Chmod(path, 0660)` sets permissions. On shutdown, `os.Remove` cleans up.

3. **Graceful shutdown order.** Both listeners need shutdown. The TCP `http.Server` has `Shutdown(ctx)`. For the Unix listener, we need a second `http.Server` (serving on the Unix listener) so we can call its `Shutdown(ctx)` too. Then `os.Remove` the socket file.

4. **Health endpoint placement.** Add `GET /health` to `router_domain.go` (the active router). It should be unauthenticated — health checks should not require API keys. Register it directly on the mux without the `wrap` middleware.

### Complexity Assessment

This is a small feature — approximately 4 focused tasks:

- **Task 1:** Health endpoint (~15 lines of Go + test)
- **Task 2:** Server struct changes (~50 lines of Go + test)
- **Task 3:** CLI flag wiring (~10 lines of Go)
- **Task 4:** Integration test via unix socket (~40 lines of Go)

Total estimated: ~115 lines of production Go, ~80 lines of test Go.

### Risk Areas

- **Socket file permissions on Linux.** `os.Chmod` after `net.Listen("unix", ...)` is the correct order. The file is created by `net.Listen` with the process's umask. Explicitly setting `0660` after creation ensures the right permissions regardless of umask.

- **Stale socket cleanup.** If the server crashes without cleanup, the socket file persists. `os.Remove` before `net.Listen` handles this. Must check `os.IsNotExist` to avoid failing on first run.

- **Race between socket creation and chmod.** There is a brief window where the socket has the default umask permissions before `os.Chmod` runs. This is standard practice and acceptable — the alternative (creating the socket in a restricted directory) is more complex.

- **Both listeners blocking.** `ListenAndServe()` and `http.Serve(unixListener, handler)` both block. One runs in a goroutine. Main goroutine waits for signal, then shuts down both.

### Files to Modify

| File | Change |
|------|--------|
| `internal/server/server.go` | Add `SocketPath` to Config, Unix listener lifecycle, shutdown cleanup |
| `internal/server/server_test.go` | Test Unix socket creation, permissions, cleanup |
| `internal/http/router_domain.go` | Add `/health` endpoint (unauthenticated) |
| `cmd/intermute/main.go` | Add `--socket` flag, pass to Config |

### Files NOT to Modify

| File | Reason |
|------|--------|
| `pkg/embedded/server.go` | Separate embedded server, not part of F5 |
| `client/client.go` | Client-side unix socket transport is out of scope |
| `internal/http/router.go` | Legacy router, superseded by `router_domain.go` |
