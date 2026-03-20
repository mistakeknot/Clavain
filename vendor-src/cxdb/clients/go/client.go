// Copyright 2025 StrongDM Inc
// SPDX-License-Identifier: Apache-2.0

// Package cxdb provides a Go client for the CXDB binary protocol.
//
// CXDB is a context database that stores conversation turns in a DAG structure,
// supporting efficient forking, branching, and content-addressed deduplication.
//
// # Endpoints
//
//   - Binary Protocol: localhost:9009 (plain TCP for local dev) or your-host:9009 (TLS for production)
//   - HTTP API: http://localhost:9010 (local dev) or https://your-domain.com (production with OAuth)
//
// # Basic Usage
//
//	// For local development:
//	client, err := cxdb.Dial("localhost:9009")
//	// For production with TLS:
//	// client, err := cxdb.DialTLS("your-host:9009")
//	if err != nil {
//	    log.Fatal(err)
//	}
//	defer client.Close()
//
//	// Create a context
//	ctx, err := client.CreateContext(context.Background(), 0)
//	if err != nil {
//	    log.Fatal(err)
//	}
//
//	// Append a turn
//	turn, err := client.AppendTurn(context.Background(), &cxdb.AppendRequest{
//	    ContextID:   ctx.ContextID,
//	    TypeID:      "com.example.Message",
//	    TypeVersion: 1,
//	    Payload:     payload,
//	})
//
// # Development Usage
//
// For local development, use plain TCP:
//
//	client, err := cxdb.Dial("localhost:9009")
package cxdb

import (
	"bytes"
	"context"
	"crypto/tls"
	"encoding/binary"
	"fmt"
	"io"
	"net"
	"sync"
	"sync/atomic"
	"time"
)

// Binary protocol message types
const (
	msgHello     uint16 = 1
	msgCtxCreate uint16 = 2
	msgCtxFork   uint16 = 3
	msgGetHead   uint16 = 4
	msgAppend    uint16 = 5
	msgGetLast   uint16 = 6
	msgGetBlob   uint16 = 9
	msgError     uint16 = 255
)

// Encoding and compression constants
const (
	EncodingMsgpack   uint32 = 1
	CompressionNone   uint32 = 0
	CompressionZstd   uint32 = 1
)

// Default timeouts
const (
	DefaultDialTimeout    = 5 * time.Second
	DefaultRequestTimeout = 30 * time.Second
)

// Client handles binary protocol communication with the CXDB server.
type Client struct {
	conn      net.Conn
	mu        sync.Mutex
	reqID     atomic.Uint64
	timeout   time.Duration
	closed    bool
	sessionID uint64    // Assigned by server on HELLO
	clientTag string    // Client's identifying tag
}

// Option configures client behavior.
type Option func(*clientOptions)

type clientOptions struct {
	dialTimeout    time.Duration
	requestTimeout time.Duration
	clientTag      string
}

// WithDialTimeout sets the connection timeout.
func WithDialTimeout(d time.Duration) Option {
	return func(o *clientOptions) {
		o.dialTimeout = d
	}
}

// WithRequestTimeout sets the per-request timeout.
func WithRequestTimeout(d time.Duration) Option {
	return func(o *clientOptions) {
		o.requestTimeout = d
	}
}

// WithClientTag sets the client identifier tag sent in the HELLO handshake.
// This allows the server to associate sessions with client types (e.g., "dotrunner", "claude-code").
func WithClientTag(tag string) Option {
	return func(o *clientOptions) {
		o.clientTag = tag
	}
}

// Dial connects to a CXDB server at the given address using plain TCP.
// For production use with TLS, use DialTLS instead.
func Dial(addr string, opts ...Option) (*Client, error) {
	options := clientOptions{
		dialTimeout:    DefaultDialTimeout,
		requestTimeout: DefaultRequestTimeout,
	}
	for _, opt := range opts {
		opt(&options)
	}

	conn, err := net.DialTimeout("tcp", addr, options.dialTimeout)
	if err != nil {
		return nil, fmt.Errorf("cxdb dial: %w", err)
	}

	client := &Client{
		conn:      conn,
		timeout:   options.requestTimeout,
		clientTag: options.clientTag,
	}

	// Send HELLO to establish session
	if err := client.sendHello(options.clientTag); err != nil {
		_ = conn.Close()
		return nil, fmt.Errorf("cxdb hello: %w", err)
	}

	return client, nil
}

// DialTLS connects to a CXDB server using TLS.
// This is the recommended method for production deployments.
func DialTLS(addr string, opts ...Option) (*Client, error) {
	options := clientOptions{
		dialTimeout:    DefaultDialTimeout,
		requestTimeout: DefaultRequestTimeout,
	}
	for _, opt := range opts {
		opt(&options)
	}

	dialer := &net.Dialer{Timeout: options.dialTimeout}
	conn, err := tls.DialWithDialer(dialer, "tcp", addr, &tls.Config{})
	if err != nil {
		return nil, fmt.Errorf("cxdb dial tls: %w", err)
	}

	client := &Client{
		conn:      conn,
		timeout:   options.requestTimeout,
		clientTag: options.clientTag,
	}

	// Send HELLO to establish session
	if err := client.sendHello(options.clientTag); err != nil {
		_ = conn.Close()
		return nil, fmt.Errorf("cxdb hello: %w", err)
	}

	return client, nil
}

// Close closes the connection to the server.
func (c *Client) Close() error {
	c.mu.Lock()
	defer c.mu.Unlock()
	if c.closed {
		return nil
	}
	c.closed = true
	return c.conn.Close()
}

// SessionID returns the session ID assigned by the server during the HELLO handshake.
func (c *Client) SessionID() uint64 {
	return c.sessionID
}

// ClientTag returns the client tag used for this connection.
func (c *Client) ClientTag() string {
	return c.clientTag
}

// sendHello sends the HELLO message to establish a session with the server.
// This is called automatically during Dial/DialTLS.
func (c *Client) sendHello(clientTag string) error {
	// Build HELLO payload:
	// protocol_version: u16 (1)
	// client_tag_len: u16
	// client_tag: [bytes]
	// client_meta_json_len: u32 (0)
	payload := &bytes.Buffer{}
	_ = binary.Write(payload, binary.LittleEndian, uint16(1)) // protocol version
	_ = binary.Write(payload, binary.LittleEndian, uint16(len(clientTag)))
	payload.WriteString(clientTag)
	_ = binary.Write(payload, binary.LittleEndian, uint32(0)) // no JSON metadata

	// Set deadline for handshake
	if err := c.conn.SetDeadline(time.Now().Add(c.timeout)); err != nil {
		return fmt.Errorf("set deadline: %w", err)
	}
	defer func() { _ = c.conn.SetDeadline(time.Time{}) }()

	reqID := c.reqID.Add(1)
	if err := c.writeFrame(msgHello, reqID, payload.Bytes()); err != nil {
		return err
	}

	resp, err := c.readFrame()
	if err != nil {
		return err
	}

	if resp.msgType == msgError {
		return parseServerError(resp.payload)
	}

	if resp.msgType != msgHello {
		return fmt.Errorf("unexpected response type: %d", resp.msgType)
	}

	// Parse response: session_id (u64) + protocol_version (u16)
	if len(resp.payload) >= 8 {
		c.sessionID = binary.LittleEndian.Uint64(resp.payload[0:8])
	}

	return nil
}

// frame represents a binary protocol frame.
type frame struct {
	msgType uint16
	reqID   uint64
	payload []byte
}

func (c *Client) sendRequest(ctx context.Context, msgType uint16, payload []byte) (*frame, error) {
	c.mu.Lock()
	defer c.mu.Unlock()

	if c.closed {
		return nil, ErrClientClosed
	}

	// Set deadline for this request
	deadline := time.Now().Add(c.timeout)
	if d, ok := ctx.Deadline(); ok && d.Before(deadline) {
		deadline = d
	}
	if err := c.conn.SetDeadline(deadline); err != nil {
		return nil, fmt.Errorf("set deadline: %w", err)
	}
	defer func() { _ = c.conn.SetDeadline(time.Time{}) }() // Clear deadline

	reqID := c.reqID.Add(1)

	if err := c.writeFrame(msgType, reqID, payload); err != nil {
		return nil, err
	}

	resp, err := c.readFrame()
	if err != nil {
		return nil, err
	}

	if resp.msgType == msgError {
		return nil, parseServerError(resp.payload)
	}

	return resp, nil
}

func (c *Client) writeFrame(msgType uint16, reqID uint64, payload []byte) error {
	header := &bytes.Buffer{}
	_ = binary.Write(header, binary.LittleEndian, uint32(len(payload)))
	_ = binary.Write(header, binary.LittleEndian, msgType)
	_ = binary.Write(header, binary.LittleEndian, uint16(0)) // flags
	_ = binary.Write(header, binary.LittleEndian, reqID)

	_, err := c.conn.Write(append(header.Bytes(), payload...))
	return err
}

func (c *Client) readFrame() (*frame, error) {
	header := make([]byte, 16)
	if _, err := io.ReadFull(c.conn, header); err != nil {
		return nil, fmt.Errorf("read header: %w", err)
	}

	length := binary.LittleEndian.Uint32(header[0:4])
	msgType := binary.LittleEndian.Uint16(header[4:6])
	reqID := binary.LittleEndian.Uint64(header[8:16])

	payload := make([]byte, length)
	if _, err := io.ReadFull(c.conn, payload); err != nil {
		return nil, fmt.Errorf("read payload: %w", err)
	}

	return &frame{msgType: msgType, reqID: reqID, payload: payload}, nil
}

func parseServerError(payload []byte) error {
	if len(payload) < 8 {
		return &ServerError{Code: 0, Detail: "unknown error"}
	}
	code := binary.LittleEndian.Uint32(payload[0:4])
	detailLen := binary.LittleEndian.Uint32(payload[4:8])
	detail := ""
	if int(detailLen) <= len(payload)-8 {
		detail = string(payload[8 : 8+detailLen])
	}
	return &ServerError{Code: code, Detail: detail}
}
