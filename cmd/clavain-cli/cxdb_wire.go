package main

// Minimal CXDB binary protocol client.
// Implements only the 5 operations clavain-cli needs: Dial, Close, CreateContext, AppendTurn, GetLast.
// Wire protocol: little-endian binary frames over TCP.
// Frame layout: [payload_len:u32][msg_type:u16][flags:u16][req_id:u64][payload...]

import (
	"bytes"
	"context"
	"encoding/binary"
	"errors"
	"fmt"
	"io"
	"net"
	"sync"
	"sync/atomic"
	"time"

	"github.com/zeebo/blake3"
)

// Message types
const (
	wireHello     uint16 = 1
	wireCtxCreate uint16 = 2
	wireAppend    uint16 = 5
	wireGetLast   uint16 = 6
	wireError     uint16 = 255
)

// Encoding constants
const (
	encodingMsgpack uint32 = 1
	compressionNone uint32 = 0
)

// CXDBClient handles binary protocol communication with the CXDB server.
type CXDBClient struct {
	conn    net.Conn
	mu      sync.Mutex
	reqID   atomic.Uint64
	timeout time.Duration
	closed  bool
}

// CXDBContextHead represents the head of a context (branch).
type CXDBContextHead struct {
	ContextID  uint64
	HeadTurnID uint64
	HeadDepth  uint32
}

// CXDBAppendRequest contains parameters for appending a turn.
type CXDBAppendRequest struct {
	ContextID      uint64
	ParentTurnID   uint64
	TypeID         string
	TypeVersion    uint32
	Payload        []byte
	IdempotencyKey string
}

// CXDBAppendResult contains the result of an append operation.
type CXDBAppendResult struct {
	ContextID   uint64
	TurnID      uint64
	Depth       uint32
	PayloadHash [32]byte
}

// CXDBTurnRecord represents a turn returned from the server.
type CXDBTurnRecord struct {
	TurnID      uint64
	ParentID    uint64
	Depth       uint32
	TypeID      string
	TypeVersion uint32
	Encoding    uint32
	Compression uint32
	PayloadHash [32]byte
	Payload     []byte
}

// CXDBGetLastOptions configures GetLast behavior.
type CXDBGetLastOptions struct {
	Limit          uint32
	IncludePayload bool
}

var (
	errCXDBClosed  = errors.New("cxdb: client closed")
	errCXDBInvalid = errors.New("cxdb: invalid response")
)

// CXDBServerError represents an error returned by the CXDB server.
type CXDBServerError struct {
	Code   uint32
	Detail string
}

func (e *CXDBServerError) Error() string {
	return fmt.Sprintf("cxdb server error %d: %s", e.Code, e.Detail)
}

// CXDBDial connects to a CXDB server at the given address.
func CXDBDial(addr string) (*CXDBClient, error) {
	conn, err := net.DialTimeout("tcp", addr, 5*time.Second)
	if err != nil {
		return nil, fmt.Errorf("cxdb dial: %w", err)
	}

	c := &CXDBClient{conn: conn, timeout: 30 * time.Second}

	// HELLO handshake
	payload := &bytes.Buffer{}
	_ = binary.Write(payload, binary.LittleEndian, uint16(1)) // protocol version
	_ = binary.Write(payload, binary.LittleEndian, uint16(0)) // no client tag
	_ = binary.Write(payload, binary.LittleEndian, uint32(0)) // no metadata

	if err := c.conn.SetDeadline(time.Now().Add(c.timeout)); err != nil {
		_ = conn.Close()
		return nil, err
	}
	reqID := c.reqID.Add(1)
	if err := c.writeFrame(wireHello, reqID, payload.Bytes()); err != nil {
		_ = conn.Close()
		return nil, fmt.Errorf("cxdb hello: %w", err)
	}
	resp, err := c.readFrame()
	if err != nil {
		_ = conn.Close()
		return nil, fmt.Errorf("cxdb hello: %w", err)
	}
	if resp.msgType == wireError {
		_ = conn.Close()
		return nil, parseCXDBError(resp.payload)
	}
	_ = c.conn.SetDeadline(time.Time{})

	return c, nil
}

// Close closes the connection.
func (c *CXDBClient) Close() error {
	c.mu.Lock()
	defer c.mu.Unlock()
	if c.closed {
		return nil
	}
	c.closed = true
	return c.conn.Close()
}

// CreateContext creates a new context in CXDB.
func (c *CXDBClient) CreateContext(ctx context.Context, baseTurnID uint64) (*CXDBContextHead, error) {
	payload := make([]byte, 8)
	binary.LittleEndian.PutUint64(payload, baseTurnID)

	resp, err := c.sendRequest(ctx, wireCtxCreate, payload)
	if err != nil {
		return nil, fmt.Errorf("create context: %w", err)
	}
	if len(resp.payload) < 20 {
		return nil, fmt.Errorf("%w: context head too short (%d bytes)", errCXDBInvalid, len(resp.payload))
	}
	return &CXDBContextHead{
		ContextID:  binary.LittleEndian.Uint64(resp.payload[0:8]),
		HeadTurnID: binary.LittleEndian.Uint64(resp.payload[8:16]),
		HeadDepth:  binary.LittleEndian.Uint32(resp.payload[16:20]),
	}, nil
}

// AppendTurn appends a new turn to a context.
func (c *CXDBClient) AppendTurn(ctx context.Context, req *CXDBAppendRequest) (*CXDBAppendResult, error) {
	hash := blake3.Sum256(req.Payload)

	buf := &bytes.Buffer{}
	_ = binary.Write(buf, binary.LittleEndian, req.ContextID)
	_ = binary.Write(buf, binary.LittleEndian, req.ParentTurnID)
	_ = binary.Write(buf, binary.LittleEndian, uint32(len(req.TypeID)))
	buf.WriteString(req.TypeID)
	_ = binary.Write(buf, binary.LittleEndian, req.TypeVersion)
	_ = binary.Write(buf, binary.LittleEndian, encodingMsgpack)
	_ = binary.Write(buf, binary.LittleEndian, compressionNone)
	_ = binary.Write(buf, binary.LittleEndian, uint32(len(req.Payload))) // uncompressed len
	buf.Write(hash[:])
	_ = binary.Write(buf, binary.LittleEndian, uint32(len(req.Payload)))
	buf.Write(req.Payload)
	_ = binary.Write(buf, binary.LittleEndian, uint32(len(req.IdempotencyKey)))
	if len(req.IdempotencyKey) > 0 {
		buf.WriteString(req.IdempotencyKey)
	}

	resp, err := c.sendRequest(ctx, wireAppend, buf.Bytes())
	if err != nil {
		return nil, fmt.Errorf("append turn: %w", err)
	}
	if len(resp.payload) < 52 {
		return nil, fmt.Errorf("%w: append response too short (%d bytes)", errCXDBInvalid, len(resp.payload))
	}

	result := &CXDBAppendResult{
		ContextID: binary.LittleEndian.Uint64(resp.payload[0:8]),
		TurnID:    binary.LittleEndian.Uint64(resp.payload[8:16]),
		Depth:     binary.LittleEndian.Uint32(resp.payload[16:20]),
	}
	copy(result.PayloadHash[:], resp.payload[20:52])
	return result, nil
}

// GetLast retrieves the last N turns from a context.
func (c *CXDBClient) GetLast(ctx context.Context, contextID uint64, opts CXDBGetLastOptions) ([]CXDBTurnRecord, error) {
	limit := opts.Limit
	if limit == 0 {
		limit = 10
	}

	buf := &bytes.Buffer{}
	_ = binary.Write(buf, binary.LittleEndian, contextID)
	_ = binary.Write(buf, binary.LittleEndian, limit)
	var includePayload uint32
	if opts.IncludePayload {
		includePayload = 1
	}
	_ = binary.Write(buf, binary.LittleEndian, includePayload)

	resp, err := c.sendRequest(ctx, wireGetLast, buf.Bytes())
	if err != nil {
		return nil, fmt.Errorf("get last: %w", err)
	}

	if len(resp.payload) < 4 {
		return nil, fmt.Errorf("%w: turn records too short", errCXDBInvalid)
	}

	cursor := bytes.NewReader(resp.payload)
	var count uint32
	if err := binary.Read(cursor, binary.LittleEndian, &count); err != nil {
		return nil, err
	}

	records := make([]CXDBTurnRecord, 0, count)
	for i := uint32(0); i < count; i++ {
		var rec CXDBTurnRecord
		if err := binary.Read(cursor, binary.LittleEndian, &rec.TurnID); err != nil {
			return nil, err
		}
		if err := binary.Read(cursor, binary.LittleEndian, &rec.ParentID); err != nil {
			return nil, err
		}
		if err := binary.Read(cursor, binary.LittleEndian, &rec.Depth); err != nil {
			return nil, err
		}
		var typeLen uint32
		if err := binary.Read(cursor, binary.LittleEndian, &typeLen); err != nil {
			return nil, err
		}
		typeBytes := make([]byte, typeLen)
		if _, err := cursor.Read(typeBytes); err != nil {
			return nil, err
		}
		rec.TypeID = string(typeBytes)
		if err := binary.Read(cursor, binary.LittleEndian, &rec.TypeVersion); err != nil {
			return nil, err
		}
		if err := binary.Read(cursor, binary.LittleEndian, &rec.Encoding); err != nil {
			return nil, err
		}
		if err := binary.Read(cursor, binary.LittleEndian, &rec.Compression); err != nil {
			return nil, err
		}
		var uncompressedLen uint32
		if err := binary.Read(cursor, binary.LittleEndian, &uncompressedLen); err != nil {
			return nil, err
		}
		if _, err := cursor.Read(rec.PayloadHash[:]); err != nil {
			return nil, err
		}
		var payloadLen uint32
		if err := binary.Read(cursor, binary.LittleEndian, &payloadLen); err != nil {
			return nil, err
		}
		rec.Payload = make([]byte, payloadLen)
		if _, err := cursor.Read(rec.Payload); err != nil {
			return nil, err
		}
		records = append(records, rec)
	}
	return records, nil
}

// --- internal wire protocol ---

type cxdbFrame struct {
	msgType uint16
	reqID   uint64
	payload []byte
}

func (c *CXDBClient) sendRequest(ctx context.Context, msgType uint16, payload []byte) (*cxdbFrame, error) {
	c.mu.Lock()
	defer c.mu.Unlock()

	if c.closed {
		return nil, errCXDBClosed
	}

	deadline := time.Now().Add(c.timeout)
	if d, ok := ctx.Deadline(); ok && d.Before(deadline) {
		deadline = d
	}
	_ = c.conn.SetDeadline(deadline)
	defer func() { _ = c.conn.SetDeadline(time.Time{}) }()

	reqID := c.reqID.Add(1)
	if err := c.writeFrame(msgType, reqID, payload); err != nil {
		return nil, err
	}

	resp, err := c.readFrame()
	if err != nil {
		return nil, err
	}
	if resp.msgType == wireError {
		return nil, parseCXDBError(resp.payload)
	}
	return resp, nil
}

func (c *CXDBClient) writeFrame(msgType uint16, reqID uint64, payload []byte) error {
	header := &bytes.Buffer{}
	_ = binary.Write(header, binary.LittleEndian, uint32(len(payload)))
	_ = binary.Write(header, binary.LittleEndian, msgType)
	_ = binary.Write(header, binary.LittleEndian, uint16(0)) // flags
	_ = binary.Write(header, binary.LittleEndian, reqID)
	_, err := c.conn.Write(append(header.Bytes(), payload...))
	return err
}

func (c *CXDBClient) readFrame() (*cxdbFrame, error) {
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
	return &cxdbFrame{msgType: msgType, reqID: reqID, payload: payload}, nil
}

func parseCXDBError(payload []byte) error {
	if len(payload) < 8 {
		return &CXDBServerError{Code: 0, Detail: "unknown error"}
	}
	code := binary.LittleEndian.Uint32(payload[0:4])
	detailLen := binary.LittleEndian.Uint32(payload[4:8])
	detail := ""
	if int(detailLen) <= len(payload)-8 {
		detail = string(payload[8 : 8+detailLen])
	}
	return &CXDBServerError{Code: code, Detail: detail}
}
