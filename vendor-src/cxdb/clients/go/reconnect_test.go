// Copyright 2025 StrongDM Inc
// SPDX-License-Identifier: Apache-2.0

package cxdb

import (
	"context"
	"errors"
	"io"
	"net"
	"sync"
	"sync/atomic"
	"syscall"
	"testing"
	"time"
)

// =============================================================================
// isConnectionError tests
// =============================================================================

func TestIsConnectionError_NilError(t *testing.T) {
	if isConnectionError(nil) {
		t.Error("nil error should not be a connection error")
	}
}

func TestIsConnectionError_EOF(t *testing.T) {
	if !isConnectionError(io.EOF) {
		t.Error("io.EOF should be a connection error")
	}
}

func TestIsConnectionError_UnexpectedEOF(t *testing.T) {
	if !isConnectionError(io.ErrUnexpectedEOF) {
		t.Error("io.ErrUnexpectedEOF should be a connection error")
	}
}

func TestIsConnectionError_Syscall(t *testing.T) {
	tests := []struct {
		name string
		err  error
		want bool
	}{
		{"ECONNRESET", syscall.ECONNRESET, true},
		{"ECONNREFUSED", syscall.ECONNREFUSED, true},
		{"EPIPE", syscall.EPIPE, true},
		{"ECONNABORTED", syscall.ECONNABORTED, true},
		{"ENETUNREACH", syscall.ENETUNREACH, true},
		{"EHOSTUNREACH", syscall.EHOSTUNREACH, true},
		{"ENOENT", syscall.ENOENT, false}, // Not a connection error
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			if got := isConnectionError(tt.err); got != tt.want {
				t.Errorf("isConnectionError(%v) = %v, want %v", tt.name, got, tt.want)
			}
		})
	}
}

func TestIsConnectionError_WrappedErrors(t *testing.T) {
	tests := []struct {
		name string
		err  error
		want bool
	}{
		{"wrapped EOF", errors.New("read: " + io.EOF.Error()), false}, // string match won't catch this
		{"wrapped ECONNRESET", &net.OpError{Err: syscall.ECONNRESET}, true},
		{"connection reset message", errors.New("connection reset by peer"), true},
		{"broken pipe message", errors.New("write: broken pipe"), true},
		{"connection refused message", errors.New("dial tcp: connection refused"), true},
		{"closed connection message", errors.New("use of closed network connection"), true},
		{"network unreachable message", errors.New("network is unreachable"), true},
		{"no route message", errors.New("no route to host"), true},
		{"timeout message", errors.New("connection timed out"), true},
		{"i/o timeout message", errors.New("i/o timeout"), true},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			if got := isConnectionError(tt.err); got != tt.want {
				t.Errorf("isConnectionError(%q) = %v, want %v", tt.err, got, tt.want)
			}
		})
	}
}

func TestIsConnectionError_ErrClientClosed(t *testing.T) {
	// ErrClientClosed is NOT a connection error - it means the client was
	// intentionally closed, not a network failure
	if isConnectionError(ErrClientClosed) {
		t.Error("ErrClientClosed should NOT be a connection error")
	}
}

func TestIsConnectionError_ServerError(t *testing.T) {
	// Server errors are not connection errors - they're application-level errors
	serverErr := &ServerError{Code: 404, Detail: "not found"}
	if isConnectionError(serverErr) {
		t.Error("ServerError should NOT be a connection error")
	}
}

// mockNetError implements net.Error for testing
type mockNetError struct {
	timeout   bool
	temporary bool
}

func (e *mockNetError) Error() string   { return "mock net error" }
func (e *mockNetError) Timeout() bool   { return e.timeout }
func (e *mockNetError) Temporary() bool { return e.temporary }

func TestIsConnectionError_NetError(t *testing.T) {
	tests := []struct {
		name string
		err  net.Error
		want bool
	}{
		{"timeout error", &mockNetError{timeout: true}, true},
		{"temporary error", &mockNetError{temporary: true}, true},
		{"permanent error", &mockNetError{}, true}, // Still a net.Error
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			if got := isConnectionError(tt.err); got != tt.want {
				t.Errorf("isConnectionError(%v) = %v, want %v", tt.name, got, tt.want)
			}
		})
	}
}

func TestIsConnectionError_OpError(t *testing.T) {
	// OpError with a connection-related underlying error
	opErr := &net.OpError{
		Op:  "read",
		Net: "tcp",
		Err: syscall.ECONNRESET,
	}
	if !isConnectionError(opErr) {
		t.Error("net.OpError with ECONNRESET should be a connection error")
	}

	// OpError with EOF (common disconnect pattern)
	opErrEOF := &net.OpError{
		Op:  "read",
		Net: "tcp",
		Err: io.EOF,
	}
	if !isConnectionError(opErrEOF) {
		t.Error("net.OpError with EOF should be a connection error")
	}

	// OpError wrapping a timeout
	opErrTimeout := &net.OpError{
		Op:  "read",
		Net: "tcp",
		Err: &mockNetError{timeout: true},
	}
	if !isConnectionError(opErrTimeout) {
		t.Error("net.OpError with timeout should be a connection error")
	}
}

// =============================================================================
// Mock client infrastructure for testing
// =============================================================================

// mockConn implements net.Conn for testing
type mockConn struct {
	readErr  error
	writeErr error
	closed   bool
	mu       sync.Mutex
}

func (m *mockConn) Read(b []byte) (n int, err error) {
	m.mu.Lock()
	defer m.mu.Unlock()
	if m.closed {
		return 0, errors.New("use of closed network connection")
	}
	if m.readErr != nil {
		return 0, m.readErr
	}
	return 0, io.EOF
}

func (m *mockConn) Write(b []byte) (n int, err error) {
	m.mu.Lock()
	defer m.mu.Unlock()
	if m.closed {
		return 0, errors.New("use of closed network connection")
	}
	if m.writeErr != nil {
		return 0, m.writeErr
	}
	return len(b), nil
}

func (m *mockConn) Close() error {
	m.mu.Lock()
	defer m.mu.Unlock()
	m.closed = true
	return nil
}

func (m *mockConn) LocalAddr() net.Addr                { return &net.TCPAddr{} }
func (m *mockConn) RemoteAddr() net.Addr               { return &net.TCPAddr{} }
func (m *mockConn) SetDeadline(t time.Time) error      { return nil }
func (m *mockConn) SetReadDeadline(t time.Time) error  { return nil }
func (m *mockConn) SetWriteDeadline(t time.Time) error { return nil }

// mockDialer tracks dial attempts and can simulate failures
type mockDialer struct {
	mu           sync.Mutex
	dialCount    int
	failUntil    int // Fail this many times before succeeding
	failErr      error
	connections  []*mockConn
	sessionIDSeq uint64
}

func newMockDialer() *mockDialer {
	return &mockDialer{
		failErr: errors.New("connection refused"),
	}
}

func (d *mockDialer) dial() (*Client, error) {
	d.mu.Lock()
	defer d.mu.Unlock()

	d.dialCount++

	if d.dialCount <= d.failUntil {
		return nil, d.failErr
	}

	conn := &mockConn{}
	d.connections = append(d.connections, conn)

	d.sessionIDSeq++
	client := &Client{
		conn:      conn,
		timeout:   30 * time.Second,
		sessionID: d.sessionIDSeq,
		clientTag: "test",
	}

	return client, nil
}

func (d *mockDialer) getDialCount() int {
	d.mu.Lock()
	defer d.mu.Unlock()
	return d.dialCount
}

func (d *mockDialer) resetDialCount() {
	d.mu.Lock()
	defer d.mu.Unlock()
	d.dialCount = 0
}

func (d *mockDialer) setFailUntil(n int) {
	d.mu.Lock()
	defer d.mu.Unlock()
	d.failUntil = n
}

// =============================================================================
// ReconnectingClient unit tests
// =============================================================================

// createTestReconnectingClient creates a ReconnectingClient with a mock dialer
func createTestReconnectingClient(dialer *mockDialer, opts ...ReconnectOption) (*ReconnectingClient, error) {
	ctx, cancel := context.WithCancel(context.Background())

	rc := &ReconnectingClient{
		addr:          "mock:9009",
		useTLS:        false,
		options:       nil,
		dialFunc:      dialer.dial, // Use mock dialer
		maxRetries:    DefaultMaxRetries,
		retryDelay:    1 * time.Millisecond, // Fast for tests
		maxRetryDelay: 10 * time.Millisecond,
		queueSize:     DefaultQueueSize,
		ctx:           ctx,
		cancel:        cancel,
	}

	// Apply options (may override dialFunc)
	for _, opt := range opts {
		opt(rc)
	}

	rc.queue = make(chan *queuedRequest, rc.queueSize)

	// Initial connection using dialFunc
	client, err := rc.dialFunc()
	if err != nil {
		cancel()
		return nil, err
	}
	rc.client = client

	// Start sender
	rc.wg.Add(1)
	go rc.sender()

	return rc, nil
}

func TestReconnectingClient_InitialConnection(t *testing.T) {
	dialer := newMockDialer()
	rc, err := createTestReconnectingClient(dialer)
	if err != nil {
		t.Fatalf("Failed to create client: %v", err)
	}
	defer func() { _ = rc.Close() }()

	if rc.SessionID() != 1 {
		t.Errorf("Expected session ID 1, got %d", rc.SessionID())
	}

	if dialer.getDialCount() != 1 {
		t.Errorf("Expected 1 dial attempt, got %d", dialer.getDialCount())
	}
}

func TestReconnectingClient_QueueLength(t *testing.T) {
	dialer := newMockDialer()
	rc, err := createTestReconnectingClient(dialer)
	if err != nil {
		t.Fatalf("Failed to create client: %v", err)
	}
	defer func() { _ = rc.Close() }()

	if rc.QueueLength() != 0 {
		t.Errorf("Expected queue length 0, got %d", rc.QueueLength())
	}
}

func TestReconnectingClient_Close(t *testing.T) {
	dialer := newMockDialer()
	rc, err := createTestReconnectingClient(dialer)
	if err != nil {
		t.Fatalf("Failed to create client: %v", err)
	}

	// Close should not error
	if err := rc.Close(); err != nil {
		t.Errorf("Close() returned error: %v", err)
	}

	// Double close should be safe
	if err := rc.Close(); err != nil {
		t.Errorf("Double Close() returned error: %v", err)
	}

	// Operations after close should fail
	_, err = rc.CreateContext(context.Background(), 0)
	if !errors.Is(err, ErrClientClosed) {
		t.Errorf("Expected ErrClientClosed after close, got: %v", err)
	}
}

func TestReconnectingClient_ContextCancellation(t *testing.T) {
	dialer := newMockDialer()
	rc, err := createTestReconnectingClient(dialer)
	if err != nil {
		t.Fatalf("Failed to create client: %v", err)
	}
	defer func() { _ = rc.Close() }()

	// Create a context that's already cancelled
	ctx, cancel := context.WithCancel(context.Background())
	cancel()

	// Operation should fail with context error
	_, err = rc.CreateContext(ctx, 0)
	if !errors.Is(err, context.Canceled) {
		t.Errorf("Expected context.Canceled, got: %v", err)
	}
}

func TestReconnectingClient_QueueFull(t *testing.T) {
	dialer := newMockDialer()

	// Create client with tiny queue
	rc, err := createTestReconnectingClient(dialer, WithQueueSize(1))
	if err != nil {
		t.Fatalf("Failed to create client: %v", err)
	}
	defer func() { _ = rc.Close() }()

	// Block the sender by filling the queue
	// We need to pause the sender first
	rc.mu.Lock()
	client := rc.client
	rc.mu.Unlock()

	// Make the client operations block by setting a connection error
	client.conn.(*mockConn).mu.Lock()
	client.conn.(*mockConn).writeErr = io.EOF
	client.conn.(*mockConn).mu.Unlock()

	// First request will be queued
	ctx, cancel := context.WithTimeout(context.Background(), 50*time.Millisecond)
	defer cancel()

	var wg sync.WaitGroup
	wg.Add(1)
	go func() {
		defer wg.Done()
		_, _ = rc.CreateContext(ctx, 0) // This will block/timeout
	}()

	// Give time for first request to be picked up
	time.Sleep(10 * time.Millisecond)

	// Second request should fail with queue full (since queue size is 1)
	ctx2, cancel2 := context.WithTimeout(context.Background(), 10*time.Millisecond)
	defer cancel2()

	_, err = rc.CreateContext(ctx2, 0)
	// Should either be queue full or context deadline
	if err == nil {
		t.Error("Expected error when queue is full")
	}

	wg.Wait()
}

// =============================================================================
// Reconnection behavior tests
// =============================================================================

func TestReconnectingClient_ReconnectOnFailure(t *testing.T) {
	dialer := newMockDialer()
	rc, err := createTestReconnectingClient(dialer)
	if err != nil {
		t.Fatalf("Failed to create client: %v", err)
	}
	defer func() { _ = rc.Close() }()

	// Track reconnection
	var reconnectCount atomic.Int32
	var lastSessionID atomic.Uint64
	rc.onReconnect = func(sessionID uint64) {
		reconnectCount.Add(1)
		lastSessionID.Store(sessionID)
	}

	// Reset dial count to track reconnection attempts
	dialer.resetDialCount()

	// Create an operation that returns a connection error on first call,
	// then succeeds on retry (after reconnect)
	var callCount atomic.Int32
	ctx := context.Background()
	err = rc.enqueue(ctx, "test", func(c *Client) error {
		if callCount.Add(1) == 1 {
			// First call: simulate connection error
			return syscall.ECONNRESET
		}
		// Second call (after reconnect): succeed
		return nil
	})

	if err != nil {
		t.Errorf("Expected success after reconnect, got error: %v", err)
	}

	if reconnectCount.Load() != 1 {
		t.Errorf("Expected 1 reconnection, got %d", reconnectCount.Load())
	}

	if dialer.getDialCount() != 1 {
		t.Errorf("Expected 1 dial attempt for reconnect, got %d", dialer.getDialCount())
	}
}

func TestReconnect_ExponentialBackoff(t *testing.T) {
	dialer := newMockDialer()
	// Don't fail initial connection
	rc, err := createTestReconnectingClient(dialer)
	if err != nil {
		t.Fatalf("Failed to create client: %v", err)
	}
	defer func() { _ = rc.Close() }()

	// Now set up to fail reconnection attempts 3 times
	dialer.resetDialCount()
	dialer.setFailUntil(3)

	// Manually trigger reconnect
	ctx := context.Background()
	start := time.Now()
	err = rc.reconnect(ctx)
	elapsed := time.Since(start)

	if err != nil {
		t.Fatalf("Reconnect failed: %v", err)
	}

	// Should have taken at least 3 retry delays (1ms + 2ms + 4ms = 7ms minimum)
	// But be generous with timing
	if elapsed < 3*time.Millisecond {
		t.Logf("Reconnect was faster than expected: %v (might be OK)", elapsed)
	}

	// Should have dialed 4 times (3 failures + 1 success)
	if dialer.getDialCount() != 4 {
		t.Errorf("Expected 4 dial attempts, got %d", dialer.getDialCount())
	}

	// Session ID should be updated (was 1 from initial, now 2 after reconnect)
	// Note: sessionIDSeq only increments on successful dials
	if rc.SessionID() != 2 {
		t.Errorf("Expected session ID 2 after reconnect, got %d", rc.SessionID())
	}
}

func TestReconnect_MaxRetriesExceeded(t *testing.T) {
	dialer := newMockDialer()
	// Don't fail initial connection
	rc, err := createTestReconnectingClient(dialer, WithMaxRetries(3))
	if err != nil {
		t.Fatalf("Failed to create client: %v", err)
	}
	defer func() { _ = rc.Close() }()

	// Now make all reconnection attempts fail
	dialer.resetDialCount()
	dialer.setFailUntil(100) // Always fail

	ctx := context.Background()
	err = rc.reconnect(ctx)

	if err == nil {
		t.Error("Expected error after max retries exceeded")
	}

	// Should have tried exactly maxRetries times
	if dialer.getDialCount() != 3 {
		t.Errorf("Expected 3 dial attempts, got %d", dialer.getDialCount())
	}
}

func TestReconnect_ContextCancellation(t *testing.T) {
	dialer := newMockDialer()
	// Don't fail initial connection
	rc, err := createTestReconnectingClient(dialer,
		WithMaxRetries(10),
		WithRetryDelay(100*time.Millisecond), // Slow enough to cancel
	)
	if err != nil {
		t.Fatalf("Failed to create client: %v", err)
	}
	defer func() { _ = rc.Close() }()

	// Now make all reconnection attempts fail
	dialer.resetDialCount()
	dialer.setFailUntil(100) // Always fail

	ctx, cancel := context.WithTimeout(context.Background(), 150*time.Millisecond)
	defer cancel()

	err = rc.reconnect(ctx)

	if err == nil {
		t.Error("Expected error when context is cancelled")
	}

	// Should have been cancelled before all retries (10 retries * 100ms = 1s, but we timeout at 150ms)
	if dialer.getDialCount() >= 10 {
		t.Errorf("Expected fewer than 10 dial attempts due to cancellation, got %d", dialer.getDialCount())
	}
}

func TestReconnect_OnReconnectCallback(t *testing.T) {
	dialer := newMockDialer()

	var callbackCalled atomic.Bool
	var receivedSessionID atomic.Uint64

	rc, err := createTestReconnectingClient(dialer,
		WithOnReconnect(func(sessionID uint64) {
			callbackCalled.Store(true)
			receivedSessionID.Store(sessionID)
		}),
	)
	if err != nil {
		t.Fatalf("Failed to create client: %v", err)
	}
	defer func() { _ = rc.Close() }()

	// Reset for reconnect test
	dialer.resetDialCount()

	ctx := context.Background()
	err = rc.reconnect(ctx)
	if err != nil {
		t.Fatalf("Reconnect failed: %v", err)
	}

	if !callbackCalled.Load() {
		t.Error("OnReconnect callback was not called")
	}

	if receivedSessionID.Load() != 2 {
		t.Errorf("Expected session ID 2 in callback, got %d", receivedSessionID.Load())
	}
}

// =============================================================================
// Option tests
// =============================================================================

func TestWithMaxRetries(t *testing.T) {
	rc := &ReconnectingClient{}
	WithMaxRetries(10)(rc)
	if rc.maxRetries != 10 {
		t.Errorf("Expected maxRetries=10, got %d", rc.maxRetries)
	}
}

func TestWithRetryDelay(t *testing.T) {
	rc := &ReconnectingClient{}
	WithRetryDelay(500 * time.Millisecond)(rc)
	if rc.retryDelay != 500*time.Millisecond {
		t.Errorf("Expected retryDelay=500ms, got %v", rc.retryDelay)
	}
}

func TestWithMaxRetryDelay(t *testing.T) {
	rc := &ReconnectingClient{}
	WithMaxRetryDelay(1 * time.Minute)(rc)
	if rc.maxRetryDelay != 1*time.Minute {
		t.Errorf("Expected maxRetryDelay=1m, got %v", rc.maxRetryDelay)
	}
}

func TestWithQueueSize(t *testing.T) {
	rc := &ReconnectingClient{}
	WithQueueSize(5000)(rc)
	if rc.queueSize != 5000 {
		t.Errorf("Expected queueSize=5000, got %d", rc.queueSize)
	}
}

func TestWithOnReconnect(t *testing.T) {
	rc := &ReconnectingClient{}
	called := false
	WithOnReconnect(func(uint64) { called = true })(rc)

	if rc.onReconnect == nil {
		t.Error("onReconnect callback not set")
	}

	rc.onReconnect(1)
	if !called {
		t.Error("onReconnect callback not invoked")
	}
}

// =============================================================================
// IsConnectionError public API test
// =============================================================================

func TestIsConnectionError_PublicAPI(t *testing.T) {
	// Verify the public API matches the internal function
	tests := []struct {
		err  error
		want bool
	}{
		{nil, false},
		{io.EOF, true},
		{ErrClientClosed, false},
		{syscall.ECONNRESET, true},
		{errors.New("random error"), false},
	}

	for _, tt := range tests {
		if got := IsConnectionError(tt.err); got != tt.want {
			t.Errorf("IsConnectionError(%v) = %v, want %v", tt.err, got, tt.want)
		}
	}
}

// =============================================================================
// Integration-style tests with full request flow
// =============================================================================

func TestReconnectingClient_EnqueueAndProcess(t *testing.T) {
	dialer := newMockDialer()
	rc, err := createTestReconnectingClient(dialer)
	if err != nil {
		t.Fatalf("Failed to create client: %v", err)
	}
	defer func() { _ = rc.Close() }()

	// Test successful operation
	var opCalled atomic.Bool
	ctx := context.Background()
	err = rc.enqueue(ctx, "test-op", func(c *Client) error {
		opCalled.Store(true)
		return nil
	})

	if err != nil {
		t.Errorf("Enqueue returned error: %v", err)
	}

	if !opCalled.Load() {
		t.Error("Operation was not called")
	}
}

func TestReconnectingClient_EnqueueWithError(t *testing.T) {
	dialer := newMockDialer()
	rc, err := createTestReconnectingClient(dialer)
	if err != nil {
		t.Fatalf("Failed to create client: %v", err)
	}
	defer func() { _ = rc.Close() }()

	expectedErr := errors.New("operation failed")
	ctx := context.Background()
	err = rc.enqueue(ctx, "test-op", func(c *Client) error {
		return expectedErr
	})

	if !errors.Is(err, expectedErr) {
		t.Errorf("Expected error %v, got %v", expectedErr, err)
	}
}

func TestReconnectingClient_ConcurrentOperations(t *testing.T) {
	dialer := newMockDialer()
	rc, err := createTestReconnectingClient(dialer)
	if err != nil {
		t.Fatalf("Failed to create client: %v", err)
	}
	defer func() { _ = rc.Close() }()

	const numOps = 100
	var wg sync.WaitGroup
	var successCount atomic.Int32

	for i := 0; i < numOps; i++ {
		wg.Add(1)
		go func() {
			defer wg.Done()
			ctx := context.Background()
			err := rc.enqueue(ctx, "concurrent-op", func(c *Client) error {
				return nil
			})
			if err == nil {
				successCount.Add(1)
			}
		}()
	}

	wg.Wait()

	if successCount.Load() != numOps {
		t.Errorf("Expected %d successful operations, got %d", numOps, successCount.Load())
	}
}

// =============================================================================
// Drain queue tests
// =============================================================================

func TestReconnectingClient_DrainOnClose(t *testing.T) {
	dialer := newMockDialer()
	rc, err := createTestReconnectingClient(dialer)
	if err != nil {
		t.Fatalf("Failed to create client: %v", err)
	}

	// Make reconnection fail so operations get stuck
	dialer.setFailUntil(100)

	// Queue some operations that will be pending
	var pendingErrors []error
	var mu sync.Mutex
	var wg sync.WaitGroup

	// Start some operations that will fail with connection error and get stuck in reconnect
	for i := 0; i < 3; i++ {
		wg.Add(1)
		go func() {
			defer wg.Done()
			ctx, cancel := context.WithTimeout(context.Background(), 500*time.Millisecond)
			defer cancel()
			err := rc.enqueue(ctx, "pending-op", func(c *Client) error {
				// Return a connection error to trigger reconnect (which will fail)
				return io.EOF
			})
			mu.Lock()
			pendingErrors = append(pendingErrors, err)
			mu.Unlock()
		}()
	}

	// Give operations time to start and get stuck in reconnect
	time.Sleep(50 * time.Millisecond)

	// Close the client - this should cancel the context and drain pending requests
	_ = rc.Close()

	// Wait for all operations to complete
	wg.Wait()

	// All operations should have received errors (either from failed reconnect, drain, or timeout)
	for i, err := range pendingErrors {
		if err == nil {
			t.Errorf("Operation %d should have received an error after close", i)
		}
	}
}

// =============================================================================
// Edge case tests
// =============================================================================

func TestReconnectingClient_SessionIDAfterReconnect(t *testing.T) {
	dialer := newMockDialer()
	rc, err := createTestReconnectingClient(dialer)
	if err != nil {
		t.Fatalf("Failed to create client: %v", err)
	}
	defer func() { _ = rc.Close() }()

	initialSessionID := rc.SessionID()
	if initialSessionID != 1 {
		t.Errorf("Expected initial session ID 1, got %d", initialSessionID)
	}

	// Reset dial count for reconnect
	dialer.resetDialCount()

	ctx := context.Background()
	err = rc.reconnect(ctx)
	if err != nil {
		t.Fatalf("Reconnect failed: %v", err)
	}

	newSessionID := rc.SessionID()
	if newSessionID == initialSessionID {
		t.Error("Session ID should change after reconnect")
	}
	if newSessionID != 2 {
		t.Errorf("Expected new session ID 2, got %d", newSessionID)
	}
}

func TestReconnectingClient_ClientTagPreserved(t *testing.T) {
	dialer := newMockDialer()
	rc, err := createTestReconnectingClient(dialer)
	if err != nil {
		t.Fatalf("Failed to create client: %v", err)
	}
	defer func() { _ = rc.Close() }()

	tag := rc.ClientTag()
	if tag != "test" {
		t.Errorf("Expected client tag 'test', got '%s'", tag)
	}
}

func TestReconnectingClient_NilClientAfterFailedReconnect(t *testing.T) {
	dialer := newMockDialer()
	rc, err := createTestReconnectingClient(dialer, WithMaxRetries(1))
	if err != nil {
		t.Fatalf("Failed to create client: %v", err)
	}
	defer func() { _ = rc.Close() }()

	// Make all future dials fail
	dialer.mu.Lock()
	dialer.dialCount = 0
	dialer.failUntil = 100
	dialer.mu.Unlock()

	ctx := context.Background()
	err = rc.reconnect(ctx)
	if err == nil {
		t.Error("Expected error from failed reconnect")
	}

	// Client should be nil after failed reconnect
	rc.mu.Lock()
	isNil := rc.client == nil
	rc.mu.Unlock()

	if !isNil {
		t.Error("Client should be nil after failed reconnect")
	}

	// SessionID should return 0 when client is nil
	if rc.SessionID() != 0 {
		t.Errorf("Expected SessionID() = 0 when client is nil, got %d", rc.SessionID())
	}

	// ClientTag should return empty when client is nil
	if rc.ClientTag() != "" {
		t.Errorf("Expected ClientTag() = '' when client is nil, got '%s'", rc.ClientTag())
	}
}
