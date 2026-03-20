// Copyright 2025 StrongDM Inc
// SPDX-License-Identifier: Apache-2.0

package cxdb

import (
	"context"
	"errors"
	"fmt"
	"io"
	"log/slog"
	"net"
	"strings"
	"sync"
	"syscall"
	"time"
)

// Default reconnection settings
const (
	DefaultMaxRetries    = 5
	DefaultRetryDelay    = 100 * time.Millisecond
	DefaultMaxRetryDelay = 30 * time.Second
	DefaultQueueSize     = 10_000
)

// DialFunc is a function that creates a new Client connection.
// Used for dependency injection in testing.
type DialFunc func() (*Client, error)

// ReconnectingClient wraps Client with automatic reconnection and request queuing.
// When the connection fails, operations are queued and retried once the connection
// is re-established. This provides resilience against transient network failures.
type ReconnectingClient struct {
	client *Client
	mu     sync.Mutex

	// Connection parameters for reconnection
	addr    string
	useTLS  bool
	options []Option

	// Dial function (injectable for testing)
	dialFunc DialFunc

	// Reconnection configuration
	maxRetries    int
	retryDelay    time.Duration
	maxRetryDelay time.Duration
	onReconnect   func(sessionID uint64)

	// Request queue
	queue     chan *queuedRequest
	queueSize int

	// Lifecycle
	ctx       context.Context
	cancel    context.CancelFunc
	wg        sync.WaitGroup
	closeOnce sync.Once
	closed    bool
}

// queuedRequest represents a queued operation waiting to be sent.
type queuedRequest struct {
	ctx      context.Context
	op       func(*Client) error
	resultCh chan error
	desc     string // For logging
}

// ReconnectOption configures reconnection behavior.
type ReconnectOption func(*ReconnectingClient)

// WithMaxRetries sets maximum reconnection attempts (default: 5).
func WithMaxRetries(n int) ReconnectOption {
	return func(rc *ReconnectingClient) {
		rc.maxRetries = n
	}
}

// WithRetryDelay sets initial retry delay with exponential backoff (default: 100ms).
func WithRetryDelay(d time.Duration) ReconnectOption {
	return func(rc *ReconnectingClient) {
		rc.retryDelay = d
	}
}

// WithMaxRetryDelay sets maximum retry delay cap (default: 30s).
func WithMaxRetryDelay(d time.Duration) ReconnectOption {
	return func(rc *ReconnectingClient) {
		rc.maxRetryDelay = d
	}
}

// WithQueueSize sets the maximum number of queued requests (default: 10,000).
func WithQueueSize(n int) ReconnectOption {
	return func(rc *ReconnectingClient) {
		rc.queueSize = n
	}
}

// WithOnReconnect sets callback invoked after successful reconnection.
// The callback receives the new session ID.
func WithOnReconnect(fn func(sessionID uint64)) ReconnectOption {
	return func(rc *ReconnectingClient) {
		rc.onReconnect = fn
	}
}

// DialReconnecting creates a client with automatic reconnection and request queuing.
// Operations that fail due to connection errors are automatically retried after reconnection.
func DialReconnecting(addr string, ropts []ReconnectOption, opts ...Option) (*ReconnectingClient, error) {
	return dialReconnecting(addr, false, ropts, opts...)
}

// DialTLSReconnecting creates a TLS client with automatic reconnection and request queuing.
// This is the recommended method for production use.
func DialTLSReconnecting(addr string, ropts []ReconnectOption, opts ...Option) (*ReconnectingClient, error) {
	return dialReconnecting(addr, true, ropts, opts...)
}

func dialReconnecting(addr string, useTLS bool, ropts []ReconnectOption, opts ...Option) (*ReconnectingClient, error) {
	ctx, cancel := context.WithCancel(context.Background())

	rc := &ReconnectingClient{
		addr:          addr,
		useTLS:        useTLS,
		options:       opts,
		maxRetries:    DefaultMaxRetries,
		retryDelay:    DefaultRetryDelay,
		maxRetryDelay: DefaultMaxRetryDelay,
		queueSize:     DefaultQueueSize,
		ctx:           ctx,
		cancel:        cancel,
	}

	// Set up default dial function
	rc.dialFunc = func() (*Client, error) {
		if useTLS {
			return DialTLS(addr, opts...)
		}
		return Dial(addr, opts...)
	}

	// Apply options
	for _, opt := range ropts {
		opt(rc)
	}

	// Initialize queue
	rc.queue = make(chan *queuedRequest, rc.queueSize)

	// Establish initial connection
	client, err := rc.dialFunc()
	if err != nil {
		cancel()
		return nil, fmt.Errorf("initial connection failed: %w", err)
	}
	rc.client = client

	// Start background sender
	rc.wg.Add(1)
	go rc.sender()

	slog.Info("[cxdb] reconnecting client initialized",
		"addr", addr,
		"tls", useTLS,
		"queue_size", rc.queueSize,
		"session_id", client.SessionID(),
	)

	return rc, nil
}

// sender is the background goroutine that processes queued requests.
func (rc *ReconnectingClient) sender() {
	defer rc.wg.Done()

	for {
		select {
		case <-rc.ctx.Done():
			// Drain remaining requests with error
			rc.drainQueue(errors.New("client closed"))
			return

		case req := <-rc.queue:
			rc.processRequest(req)
		}
	}
}

// processRequest executes a queued request, handling reconnection if needed.
func (rc *ReconnectingClient) processRequest(req *queuedRequest) {
	// Check if request context is already cancelled
	if req.ctx.Err() != nil {
		req.resultCh <- req.ctx.Err()
		return
	}

	rc.mu.Lock()
	client := rc.client
	rc.mu.Unlock()

	// Try the operation
	err := req.op(client)

	// If connection error, attempt reconnect and retry
	if err != nil && isConnectionError(err) {
		slog.Error("[cxdb] connection error, attempting reconnect",
			"error", err,
			"operation", req.desc,
		)

		if reconnErr := rc.reconnect(req.ctx); reconnErr != nil {
			slog.Error("[cxdb] reconnection failed",
				"error", reconnErr,
				"original_error", err,
				"operation", req.desc,
			)
			req.resultCh <- fmt.Errorf("%w (reconnect failed: %v)", err, reconnErr)
			return
		}

		// Retry with new connection
		rc.mu.Lock()
		client = rc.client
		rc.mu.Unlock()

		err = req.op(client)
		if err != nil {
			slog.Error("[cxdb] operation failed after reconnect",
				"error", err,
				"operation", req.desc,
			)
		}
	}

	req.resultCh <- err
}

// reconnect attempts to re-establish the connection with exponential backoff.
func (rc *ReconnectingClient) reconnect(ctx context.Context) error {
	rc.mu.Lock()
	defer rc.mu.Unlock()

	delay := rc.retryDelay
	var lastErr error

	for attempt := 1; attempt <= rc.maxRetries; attempt++ {
		if attempt > 1 {
			slog.Info("[cxdb] reconnect attempt",
				"attempt", attempt,
				"max_attempts", rc.maxRetries,
				"delay", delay,
			)

			select {
			case <-ctx.Done():
				return fmt.Errorf("reconnect cancelled: %w", ctx.Err())
			case <-rc.ctx.Done():
				return errors.New("client closed during reconnect")
			case <-time.After(delay):
			}

			// Exponential backoff
			delay = min(delay*2, rc.maxRetryDelay)
		}

		// Close old connection
		if rc.client != nil {
			_ = rc.client.Close()
			rc.client = nil
		}

		// Attempt new connection using the dial function
		newClient, err := rc.dialFunc()
		if err != nil {
			lastErr = err
			slog.Error("[cxdb] reconnect dial failed",
				"attempt", attempt,
				"error", err,
			)
			continue
		}

		rc.client = newClient
		slog.Info("[cxdb] reconnected successfully",
			"attempt", attempt,
			"new_session_id", newClient.SessionID(),
		)

		if rc.onReconnect != nil {
			rc.onReconnect(newClient.SessionID())
		}

		return nil
	}

	return fmt.Errorf("reconnect failed after %d attempts: %w", rc.maxRetries, lastErr)
}

// drainQueue empties the queue, sending the given error to all waiting requests.
func (rc *ReconnectingClient) drainQueue(err error) {
	for {
		select {
		case req := <-rc.queue:
			req.resultCh <- err
		default:
			return
		}
	}
}

// enqueue adds an operation to the queue and waits for the result.
func (rc *ReconnectingClient) enqueue(ctx context.Context, desc string, op func(*Client) error) error {
	rc.mu.Lock()
	if rc.closed {
		rc.mu.Unlock()
		return ErrClientClosed
	}
	rc.mu.Unlock()

	req := &queuedRequest{
		ctx:      ctx,
		op:       op,
		resultCh: make(chan error, 1),
		desc:     desc,
	}

	select {
	case rc.queue <- req:
		// Queued successfully
	case <-ctx.Done():
		return ctx.Err()
	default:
		// Queue full
		slog.Error("[cxdb] request queue full, dropping request",
			"operation", desc,
			"queue_size", rc.queueSize,
		)
		return errors.New("cxdb: request queue full")
	}

	// Wait for result
	select {
	case err := <-req.resultCh:
		return err
	case <-ctx.Done():
		return ctx.Err()
	}
}

// Close closes the client and drains any pending requests.
func (rc *ReconnectingClient) Close() error {
	var err error
	rc.closeOnce.Do(func() {
		rc.mu.Lock()
		rc.closed = true
		rc.mu.Unlock()

		rc.cancel()
		rc.wg.Wait()

		rc.mu.Lock()
		if rc.client != nil {
			err = rc.client.Close()
		}
		rc.mu.Unlock()

		slog.Info("[cxdb] reconnecting client closed")
	})
	return err
}

// SessionID returns the current session ID.
// Note: This may change after reconnection.
func (rc *ReconnectingClient) SessionID() uint64 {
	rc.mu.Lock()
	defer rc.mu.Unlock()
	if rc.client == nil {
		return 0
	}
	return rc.client.SessionID()
}

// ClientTag returns the client tag used for this connection.
func (rc *ReconnectingClient) ClientTag() string {
	rc.mu.Lock()
	defer rc.mu.Unlock()
	if rc.client == nil {
		return ""
	}
	return rc.client.ClientTag()
}

// QueueLength returns the current number of queued requests.
func (rc *ReconnectingClient) QueueLength() int {
	return len(rc.queue)
}

// --- Wrapped operations ---

// CreateContext creates a new context, optionally based on an existing turn.
func (rc *ReconnectingClient) CreateContext(ctx context.Context, baseTurnID uint64) (*ContextHead, error) {
	var result *ContextHead
	err := rc.enqueue(ctx, "CreateContext", func(c *Client) error {
		var opErr error
		result, opErr = c.CreateContext(ctx, baseTurnID)
		return opErr
	})
	return result, err
}

// ForkContext creates a new context forked from an existing turn.
func (rc *ReconnectingClient) ForkContext(ctx context.Context, baseTurnID uint64) (*ContextHead, error) {
	var result *ContextHead
	err := rc.enqueue(ctx, "ForkContext", func(c *Client) error {
		var opErr error
		result, opErr = c.ForkContext(ctx, baseTurnID)
		return opErr
	})
	return result, err
}

// GetHead retrieves the current head turn for a context.
func (rc *ReconnectingClient) GetHead(ctx context.Context, contextID uint64) (*ContextHead, error) {
	var result *ContextHead
	err := rc.enqueue(ctx, "GetHead", func(c *Client) error {
		var opErr error
		result, opErr = c.GetHead(ctx, contextID)
		return opErr
	})
	return result, err
}

// AppendTurn appends a new turn to a context.
func (rc *ReconnectingClient) AppendTurn(ctx context.Context, req *AppendRequest) (*AppendResult, error) {
	var result *AppendResult
	err := rc.enqueue(ctx, "AppendTurn", func(c *Client) error {
		var opErr error
		result, opErr = c.AppendTurn(ctx, req)
		return opErr
	})
	return result, err
}

// GetLast retrieves the last N turns from a context.
func (rc *ReconnectingClient) GetLast(ctx context.Context, contextID uint64, opts GetLastOptions) ([]TurnRecord, error) {
	var result []TurnRecord
	err := rc.enqueue(ctx, "GetLast", func(c *Client) error {
		var opErr error
		result, opErr = c.GetLast(ctx, contextID, opts)
		return opErr
	})
	return result, err
}

// AttachFs attaches a filesystem tree to a context.
func (rc *ReconnectingClient) AttachFs(ctx context.Context, req *AttachFsRequest) (*AttachFsResult, error) {
	var result *AttachFsResult
	err := rc.enqueue(ctx, "AttachFs", func(c *Client) error {
		var opErr error
		result, opErr = c.AttachFs(ctx, req)
		return opErr
	})
	return result, err
}

// GetBlob retrieves a blob by its BLAKE3-256 hash.
func (rc *ReconnectingClient) GetBlob(ctx context.Context, hash [32]byte) ([]byte, error) {
	var result []byte
	err := rc.enqueue(ctx, "GetBlob", func(c *Client) error {
		var opErr error
		result, opErr = c.GetBlob(ctx, hash)
		return opErr
	})
	return result, err
}

// PutBlob stores a blob and returns its hash.
func (rc *ReconnectingClient) PutBlob(ctx context.Context, req *PutBlobRequest) (*PutBlobResult, error) {
	var result *PutBlobResult
	err := rc.enqueue(ctx, "PutBlob", func(c *Client) error {
		var opErr error
		result, opErr = c.PutBlob(ctx, req)
		return opErr
	})
	return result, err
}

// PutBlobIfAbsent stores a blob only if it doesn't already exist.
func (rc *ReconnectingClient) PutBlobIfAbsent(ctx context.Context, data []byte) ([32]byte, bool, error) {
	var hash [32]byte
	var existed bool
	err := rc.enqueue(ctx, "PutBlobIfAbsent", func(c *Client) error {
		var opErr error
		hash, existed, opErr = c.PutBlobIfAbsent(ctx, data)
		return opErr
	})
	return hash, existed, err
}

// AppendTurnWithFs appends a turn with an attached filesystem snapshot.
func (rc *ReconnectingClient) AppendTurnWithFs(ctx context.Context, req *AppendRequest, fsRootHash *[32]byte) (*AppendResult, error) {
	var result *AppendResult
	err := rc.enqueue(ctx, "AppendTurnWithFs", func(c *Client) error {
		var opErr error
		result, opErr = c.AppendTurnWithFs(ctx, req, fsRootHash)
		return opErr
	})
	return result, err
}

// --- Connection error detection ---

// connectionSyscallErrors are syscall errors that indicate connection problems.
var connectionSyscallErrors = map[syscall.Errno]bool{
	syscall.ECONNRESET:   true,
	syscall.ECONNREFUSED: true,
	syscall.EPIPE:        true,
	syscall.ECONNABORTED: true,
	syscall.ENETUNREACH:  true,
	syscall.EHOSTUNREACH: true,
	syscall.ENETDOWN:     true,
	syscall.ETIMEDOUT:    true,
}

// isConnectionError returns true if the error indicates a broken connection
// that may be recoverable via reconnection.
func isConnectionError(err error) bool {
	if err == nil {
		return false
	}

	// Client already closed - not recoverable via reconnect
	if errors.Is(err, ErrClientClosed) {
		return false
	}

	// Check for EOF errors
	if errors.Is(err, io.EOF) || errors.Is(err, io.ErrUnexpectedEOF) {
		return true
	}

	// Check for specific syscall connection errors
	var errno syscall.Errno
	if errors.As(err, &errno) {
		return connectionSyscallErrors[errno]
	}

	// Check for net.OpError (wraps underlying connection errors)
	var opErr *net.OpError
	if errors.As(err, &opErr) {
		// Recursively check the underlying error
		if opErr.Err != nil {
			return isConnectionError(opErr.Err)
		}
		return true
	}

	// Check for generic net.Error (timeouts, etc.)
	var netErr net.Error
	if errors.As(err, &netErr) {
		return true
	}

	// Check error message patterns for wrapped errors
	errStr := strings.ToLower(err.Error())
	connectionPatterns := []string{
		"connection reset",
		"connection refused",
		"broken pipe",
		"use of closed network connection",
		"network is unreachable",
		"no route to host",
		"connection timed out",
		"i/o timeout",
	}
	for _, pattern := range connectionPatterns {
		if strings.Contains(errStr, pattern) {
			return true
		}
	}

	return false
}

// IsConnectionError is the public API for checking connection errors.
// Applications can use this to implement their own retry logic if not using
// ReconnectingClient.
func IsConnectionError(err error) bool {
	return isConnectionError(err)
}
