// Copyright 2025 StrongDM Inc
// SPDX-License-Identifier: Apache-2.0

package cxdb

import (
	"bytes"
	"context"
	"encoding/binary"
	"fmt"

	"github.com/zeebo/blake3"
)

// AppendRequest contains parameters for appending a turn.
type AppendRequest struct {
	// ContextID is the context to append to.
	ContextID uint64

	// ParentTurnID is the parent turn. If 0, uses the current context head.
	ParentTurnID uint64

	// TypeID is the declared type identifier (e.g., "com.example.Message").
	TypeID string

	// TypeVersion is the schema version for the type.
	TypeVersion uint32

	// Payload is the msgpack-encoded turn data.
	Payload []byte

	// IdempotencyKey is an optional key for safe retries.
	// If provided, duplicate appends with the same key are ignored.
	IdempotencyKey string

	// Encoding specifies the payload encoding. Defaults to EncodingMsgpack.
	Encoding uint32

	// Compression specifies payload compression. Defaults to CompressionNone.
	Compression uint32
}

// TurnRecord represents a turn returned from the server.
type TurnRecord struct {
	TurnID      uint64
	ParentID    uint64
	Depth       uint32
	TypeID      string
	TypeVersion uint32
	Encoding    uint32
	Compression uint32
	PayloadHash [32]byte
	Payload     []byte // Only populated if requested
}

// AppendResult contains the result of an append operation.
type AppendResult struct {
	ContextID   uint64
	TurnID      uint64
	Depth       uint32
	PayloadHash [32]byte
}

// AppendTurn appends a new turn to a context.
func (c *Client) AppendTurn(ctx context.Context, req *AppendRequest) (*AppendResult, error) {
	encoding := req.Encoding
	if encoding == 0 {
		encoding = EncodingMsgpack
	}
	compression := req.Compression

	// Compute BLAKE3 hash of payload
	hash := blake3.Sum256(req.Payload)

	payload := &bytes.Buffer{}
	_ = binary.Write(payload, binary.LittleEndian, req.ContextID)
	_ = binary.Write(payload, binary.LittleEndian, req.ParentTurnID)

	_ = binary.Write(payload, binary.LittleEndian, uint32(len(req.TypeID)))
	payload.WriteString(req.TypeID)
	_ = binary.Write(payload, binary.LittleEndian, req.TypeVersion)

	_ = binary.Write(payload, binary.LittleEndian, encoding)
	_ = binary.Write(payload, binary.LittleEndian, compression)
	_ = binary.Write(payload, binary.LittleEndian, uint32(len(req.Payload))) // uncompressed len
	payload.Write(hash[:])

	_ = binary.Write(payload, binary.LittleEndian, uint32(len(req.Payload)))
	payload.Write(req.Payload)

	_ = binary.Write(payload, binary.LittleEndian, uint32(len(req.IdempotencyKey)))
	if len(req.IdempotencyKey) > 0 {
		payload.WriteString(req.IdempotencyKey)
	}

	resp, err := c.sendRequest(ctx, msgAppend, payload.Bytes())
	if err != nil {
		return nil, fmt.Errorf("append turn: %w", err)
	}

	if len(resp.payload) < 52 {
		return nil, fmt.Errorf("%w: append response too short (%d bytes)", ErrInvalidResponse, len(resp.payload))
	}

	result := &AppendResult{
		ContextID: binary.LittleEndian.Uint64(resp.payload[0:8]),
		TurnID:    binary.LittleEndian.Uint64(resp.payload[8:16]),
		Depth:     binary.LittleEndian.Uint32(resp.payload[16:20]),
	}
	copy(result.PayloadHash[:], resp.payload[20:52])

	return result, nil
}

// GetLastOptions configures GetLast behavior.
type GetLastOptions struct {
	// Limit is the maximum number of turns to return.
	Limit uint32

	// IncludePayload controls whether to include turn payloads.
	IncludePayload bool
}

// GetLast retrieves the last N turns from a context, walking back from the head.
func (c *Client) GetLast(ctx context.Context, contextID uint64, opts GetLastOptions) ([]TurnRecord, error) {
	limit := opts.Limit
	if limit == 0 {
		limit = 10
	}

	payload := &bytes.Buffer{}
	_ = binary.Write(payload, binary.LittleEndian, contextID)
	_ = binary.Write(payload, binary.LittleEndian, limit)
	var includePayload uint32
	if opts.IncludePayload {
		includePayload = 1
	}
	_ = binary.Write(payload, binary.LittleEndian, includePayload)

	resp, err := c.sendRequest(ctx, msgGetLast, payload.Bytes())
	if err != nil {
		return nil, fmt.Errorf("get last: %w", err)
	}

	return parseTurnRecords(resp.payload)
}

func parseTurnRecords(data []byte) ([]TurnRecord, error) {
	if len(data) < 4 {
		return nil, fmt.Errorf("%w: turn records too short", ErrInvalidResponse)
	}

	cursor := bytes.NewReader(data)
	var count uint32
	if err := binary.Read(cursor, binary.LittleEndian, &count); err != nil {
		return nil, err
	}

	records := make([]TurnRecord, 0, count)
	for i := uint32(0); i < count; i++ {
		var rec TurnRecord

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
