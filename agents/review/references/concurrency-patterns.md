# Concurrency Patterns Reference

This file contains extracted concurrency code patterns used by `agents/review/fd-correctness.md`.

## Go

### State Machine Lifecycle

**Guard transitions with explicit state and a mutex:**

```go
type connState int
const (
    stateIdle connState = iota
    stateConnecting
    stateConnected
    stateClosing
)

// Guard transitions with a mutex
func (c *Client) connect() error {
    c.mu.Lock()
    if c.state != stateIdle {
        c.mu.Unlock()
        return fmt.Errorf("connect called in state %v", c.state)
    }
    c.state = stateConnecting
    c.mu.Unlock()
    // ... proceed
}
```

### Cancellation & Cleanup

**Every goroutine must have a cancellation path:**

```go
func (s *Server) processRequests(ctx context.Context) error {
    for {
        select {
        case <-ctx.Done():
            return ctx.Err()
        case req := <-s.incoming:
            if err := s.handle(ctx, req); err != nil {
                return err
            }
        }
    }
}

// Every goroutine must have a cancellation path
func (s *Server) Start(ctx context.Context) {
    ctx, cancel := context.WithCancel(ctx)
    defer cancel()

    g, ctx := errgroup.WithContext(ctx)
    g.Go(func() error { return s.processRequests(ctx) })
    g.Go(func() error { return s.healthCheck(ctx) })
    // errgroup cancels ctx on first error — all goroutines hear it
    return g.Wait()
}
```

### Race Conditions

**Shared mutable state without synchronization (BAD/GOOD):**

```go
// BAD: map access from multiple goroutines
func (c *Cache) Set(k string, v any) { c.data[k] = v }
func (c *Cache) Get(k string) any    { return c.data[k] }

// GOOD: sync.RWMutex for read-heavy maps
func (c *Cache) Set(k string, v any) {
    c.mu.Lock()
    defer c.mu.Unlock()
    c.data[k] = v
}
func (c *Cache) Get(k string) any {
    c.mu.RLock()
    defer c.mu.RUnlock()
    return c.data[k]
}
```

**Check-then-act on channel (BAD/GOOD):**

```go
// BAD: check-then-act on channel
if len(ch) > 0 {
    v := <-ch  // another goroutine may have drained it
}

// GOOD: non-blocking select
select {
case v := <-ch:
    handle(v)
default:
    // nothing available
}
```

### Error Propagation in Concurrent Code

**errgroup fail-fast with cancellation:**

```go
g, ctx := errgroup.WithContext(ctx)
for _, url := range urls {
    url := url // capture loop variable
    g.Go(func() error {
        return fetch(ctx, url)
    })
}
if err := g.Wait(); err != nil {
    // First error cancels ctx, all goroutines wind down
    return fmt.Errorf("fetch failed: %w", err)
}
```

### Resource Leaks

**Goroutine send may block forever (BAD/GOOD):**

```go
// BAD: goroutine blocks forever if nobody reads ch
ch := make(chan result)
go func() {
    ch <- expensiveComputation() // blocks if receiver is gone
}()

// GOOD: use buffered channel or select with context
ch := make(chan result, 1) // won't block on send
go func() {
    select {
    case ch <- expensiveComputation():
    case <-ctx.Done():
    }
}()
```

**Unclosed resources on error path (BAD/GOOD):**

```go
// BAD: leak on error path
resp, err := http.Get(url)
if err != nil { return err }
// if processing fails, resp.Body is never closed

// GOOD: defer immediately
resp, err := http.Get(url)
if err != nil { return err }
defer resp.Body.Close()
```

**Timer leak in loop (BAD/GOOD):**

```go
// BAD: time.After in a loop creates a new timer each iteration
for {
    select {
    case <-time.After(5 * time.Second): // leaked timer if other case fires
        timeout()
    case msg := <-ch:
        handle(msg)
    }
}

// GOOD: reusable timer
timer := time.NewTimer(5 * time.Second)
defer timer.Stop()
for {
    timer.Reset(5 * time.Second)
    select {
    case <-timer.C:
        timeout()
    case msg := <-ch:
        handle(msg)
    }
}
```

### Synchronization Patterns

**Nested lock ordering deadlock risk (BAD/GOOD):**

```go
// BAD: nested locks in inconsistent order
func (s *Service) updateBoth() {
    s.muA.Lock()
    s.muB.Lock() // if another goroutine locks B then A: deadlock
    // ...
}

// GOOD: single lock, or always lock in alphabetical/documented order
// Or better: restructure so you don't need two locks
```

**Channel pattern reference:**

```go
// Unbuffered: synchronization point (sender blocks until receiver ready)
ch := make(chan T)

// Buffered: decoupling (sender blocks only when buffer full)
ch := make(chan T, 100)

// Select with default: non-blocking check
select {
case v := <-ch:
    handle(v)
default:
    // don't block
}

// Fan-out, fan-in: use done channel or context for lifecycle
```

**sync.Once one-time initialization:**

```go
var (
    instance *Client
    once     sync.Once
)
func GetClient() *Client {
    once.Do(func() {
        instance = &Client{} // guaranteed exactly once, even under contention
    })
    return instance
}
```

**sync.WaitGroup Add-before-Go:**

```go
var wg sync.WaitGroup
for _, item := range items {
    wg.Add(1) // MUST be before the goroutine starts
    go func(item Item) {
        defer wg.Done()
        process(item)
    }(item)
}
wg.Wait()
```

### Timeout & Retry

**Timeout around blocking wait:**

```go
ctx, cancel := context.WithTimeout(ctx, 5*time.Second)
defer cancel()

select {
case result := <-ch:
    return result, nil
case <-ctx.Done():
    return nil, fmt.Errorf("timed out waiting for result: %w", ctx.Err())
}
```

**Retry with backoff + jitter (BAD/GOOD):**

```go
// BAD: immediate retry hammers the server
for i := 0; i < maxRetries; i++ {
    if err := doRequest(); err == nil {
        return nil
    }
}

// GOOD: exponential backoff with jitter
for i := 0; i < maxRetries; i++ {
    if err := doRequest(); err == nil {
        return nil
    }
    backoff := time.Duration(1<<i) * 100 * time.Millisecond
    jitter := time.Duration(rand.Int63n(int64(backoff / 2)))
    select {
    case <-time.After(backoff + jitter):
    case <-ctx.Done():
        return ctx.Err()
    }
}
```

**Graceful shutdown with timeout:**

```go
func (s *Server) Shutdown(ctx context.Context) error {
    // Signal all workers to stop
    close(s.quit)

    // Wait for workers OR timeout
    done := make(chan struct{})
    go func() {
        s.wg.Wait()
        close(done)
    }()

    select {
    case <-done:
        return nil // clean shutdown
    case <-ctx.Done():
        return fmt.Errorf("shutdown timed out, %d workers still running", s.activeWorkers())
    }
}
```

### Testing Concurrent Code

**Deterministic testing (BAD/GOOD):**

```go
// BAD: flaky, slow, non-deterministic
go producer(ch)
time.Sleep(100 * time.Millisecond)
assert.Equal(t, expected, <-ch)

// GOOD: synchronize on the event itself
go producer(ch)
select {
case result := <-ch:
    assert.Equal(t, expected, result)
case <-time.After(5 * time.Second):
    t.Fatal("timed out waiting for producer")
}
```

## Python

### State Machine Lifecycle

**Guard transitions with explicit enum state:**

```python
from enum import Enum, auto

class PipelineState(Enum):
    IDLE = auto()
    RUNNING = auto()
    DRAINING = auto()
    STOPPED = auto()

# Guard transitions
async def start(self) -> None:
    if self._state != PipelineState.IDLE:
        raise RuntimeError(f"Cannot start in state {self._state}")
    self._state = PipelineState.RUNNING
```

### Cancellation & Cleanup

**`CancelledError` cleanup and re-raise:**

```python
async def worker(self) -> None:
    try:
        while True:
            item = await self._queue.get()
            await self._process(item)
    except asyncio.CancelledError:
        # Clean up partial work
        await self._flush_pending()
        raise  # ALWAYS re-raise CancelledError

# Use async context managers for lifecycle
async with asyncio.TaskGroup() as tg:
    tg.create_task(worker())
    tg.create_task(monitor())
# All tasks cancelled and awaited on exit
```

### Race Conditions

**TOCTOU file write (BAD/GOOD):**

```python
# BAD: race between check and write
if not path.exists():
    path.write_text(data)

# GOOD: atomic operation
import tempfile, os
fd, tmp = tempfile.mkstemp(dir=path.parent)
try:
    os.write(fd, data.encode())
    os.replace(tmp, path)  # atomic on POSIX
finally:
    os.close(fd)
```

### Error Propagation in Concurrent Code

**TaskGroup fail-fast and gather partial-failure mode:**

```python
# GOOD: TaskGroup propagates first exception, cancels siblings
async with asyncio.TaskGroup() as tg:
    tg.create_task(fetch(url1))
    tg.create_task(fetch(url2))

# ACCEPTABLE: gather with return_exceptions for partial-failure tolerance
results = await asyncio.gather(*tasks, return_exceptions=True)
errors = [r for r in results if isinstance(r, Exception)]
successes = [r for r in results if not isinstance(r, Exception)]
```

### Timeout & Retry

**Timeout handling with cleanup:**

```python
try:
    result = await asyncio.wait_for(coroutine(), timeout=5.0)
except asyncio.TimeoutError:
    # Handle gracefully — don't just log and continue
    await cleanup_partial_state()
    raise
```

### Testing Concurrent Code

**Deterministic async testing (BAD/GOOD):**

```python
# BAD: time.sleep in async tests
await asyncio.sleep(0.1)
assert result == expected

# GOOD: use events or conditions
event = asyncio.Event()
# ... production code calls event.set() when done
await asyncio.wait_for(event.wait(), timeout=5.0)
assert result == expected
```

## TypeScript

### State Machine Lifecycle

**Guard transitions with explicit symbols:**

```typescript
const STATE_IDLE = Symbol("idle");
const STATE_LOADING = Symbol("loading");
const STATE_ERRORED = Symbol("errored");
const STATE_LOADED = Symbol("loaded");

// Refuse operations that conflict with current state
if (this.state !== STATE_IDLE) return;
this.state = STATE_LOADING;
```

### Cancellation & Cleanup

**AbortController cancellation and React cleanup:**

```typescript
const controller = new AbortController();

async function fetchWithCleanup(url: string): Promise<Response> {
    try {
        return await fetch(url, { signal: controller.signal });
    } catch (err) {
        if (err instanceof DOMException && err.name === "AbortError") {
            // Expected cancellation, clean up
            return;
        }
        throw err;
    }
}

// In React useEffect:
useEffect(() => {
    const controller = new AbortController();
    loadData(controller.signal);
    return () => controller.abort(); // cleanup on unmount
}, [dep]);
```

### Error Propagation in Concurrent Code

**`Promise.all` vs `Promise.allSettled` (BAD/GOOD):**

```typescript
// BAD: One rejection tanks everything, others silently ignored
const results = await Promise.all(promises);

// GOOD: Inspect each outcome
const results = await Promise.allSettled(promises);
const failures = results.filter(r => r.status === "rejected");
if (failures.length > 0) {
    log.warn(`${failures.length} of ${results.length} tasks failed`);
}
```

## JavaScript

### Cancellation & Cleanup

**Centralized DOM listener manager:**

```javascript
class EventListenerManager {
    constructor() { this.releaseFns = []; }

    add(target, event, handlerFn, options) {
        target.addEventListener(event, handlerFn, options);
        this.releaseFns.unshift(() =>
            target.removeEventListener(event, handlerFn, options)
        );
    }

    removeAll() {
        for (const r of this.releaseFns) r();
        this.releaseFns.length = 0;
    }
}
```

### Resource Leaks

**`requestAnimationFrame` loop cancellation:**

```javascript
let cancelToken = { canceled: false };
const animFn = () => {
    // ... do work ...
    if (!cancelToken.canceled) {
        requestAnimationFrame(animFn);
    }
};
requestAnimationFrame(animFn);
// In disconnect/cleanup:
cancelToken.canceled = true;
```

## Shell / Bash

### Cancellation & Cleanup

**Process cleanup with trap and wait:**

```bash
cleanup() {
    kill "$worker_pid" 2>/dev/null
    wait "$worker_pid" 2>/dev/null
    rm -f "$lockfile"
}
trap cleanup EXIT INT TERM

long_running_process &
worker_pid=$!
wait "$worker_pid"
```

### Error Propagation in Concurrent Code

**`set -e` is not enough for background jobs (BAD/GOOD):**

```bash
set -euo pipefail

# BAD: background job errors are invisible
task_a &
task_b &
wait  # exit code is last job only

# GOOD: check each
task_a & pid_a=$!
task_b & pid_b=$!
wait "$pid_a" || { echo "task_a failed"; exit 1; }
wait "$pid_b" || { echo "task_b failed"; exit 1; }
```

### Testing Concurrent Code

**Go race detector command:**

```bash
go test -race ./...
```
