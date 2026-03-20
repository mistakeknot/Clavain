// Copyright 2025 StrongDM Inc
// SPDX-License-Identifier: Apache-2.0

package cxdb

import (
	"bytes"
	"context"
	"encoding/binary"
	"fmt"
	"time"

	"github.com/zeebo/blake3"
)

// Protocol message types for filesystem operations
const (
	msgAttachFs uint16 = 10
	msgPutBlob  uint16 = 11
)

// AttachFsRequest contains parameters for attaching a filesystem snapshot to a turn.
type AttachFsRequest struct {
	// TurnID is the turn to attach the snapshot to.
	TurnID uint64

	// FsRootHash is the BLAKE3-256 hash of the root tree object.
	FsRootHash [32]byte
}

// AttachFsResult contains the result of an attach operation.
type AttachFsResult struct {
	TurnID     uint64
	FsRootHash [32]byte
}

// AttachFs attaches a filesystem snapshot to an existing turn.
// The tree objects and file blobs must already exist in the blob store.
func (c *Client) AttachFs(ctx context.Context, req *AttachFsRequest) (*AttachFsResult, error) {
	payload := &bytes.Buffer{}
	_ = binary.Write(payload, binary.LittleEndian, req.TurnID)
	payload.Write(req.FsRootHash[:])

	resp, err := c.sendRequest(ctx, msgAttachFs, payload.Bytes())
	if err != nil {
		return nil, fmt.Errorf("attach fs: %w", err)
	}

	if len(resp.payload) < 40 {
		return nil, fmt.Errorf("%w: attach fs response too short (%d bytes)", ErrInvalidResponse, len(resp.payload))
	}

	result := &AttachFsResult{
		TurnID: binary.LittleEndian.Uint64(resp.payload[0:8]),
	}
	copy(result.FsRootHash[:], resp.payload[8:40])

	return result, nil
}

// GetBlob retrieves a blob by its BLAKE3-256 hash from the content-addressed store.
// Returns ErrBlobNotFound (wrapped in a ServerError) if the hash doesn't exist.
func (c *Client) GetBlob(ctx context.Context, hash [32]byte) ([]byte, error) {
	resp, err := c.sendRequest(ctx, msgGetBlob, hash[:])
	if err != nil {
		if IsServerError(err, 404) {
			return nil, fmt.Errorf("%w: %s", ErrBlobNotFound, err)
		}
		return nil, fmt.Errorf("get blob: %w", err)
	}

	if len(resp.payload) < 4 {
		return nil, fmt.Errorf("%w: get blob response too short (%d bytes)", ErrInvalidResponse, len(resp.payload))
	}

	rawLen := binary.LittleEndian.Uint32(resp.payload[0:4])
	if uint32(len(resp.payload)-4) < rawLen {
		return nil, fmt.Errorf("%w: get blob payload truncated (expected %d, got %d)", ErrInvalidResponse, rawLen, len(resp.payload)-4)
	}

	return resp.payload[4 : 4+rawLen], nil
}

// PutBlobRequest contains parameters for storing a blob.
type PutBlobRequest struct {
	// Data is the raw blob content.
	Data []byte
}

// PutBlobResult contains the result of a put blob operation.
type PutBlobResult struct {
	// Hash is the BLAKE3-256 hash of the blob.
	Hash [32]byte

	// WasNew indicates whether this was a new blob (true) or already existed (false).
	WasNew bool
}

// PutBlob stores a blob in the content-addressed store.
// The hash is computed from the data and verified by the server.
func (c *Client) PutBlob(ctx context.Context, req *PutBlobRequest) (*PutBlobResult, error) {
	// Compute hash
	hash := blake3.Sum256(req.Data)

	payload := &bytes.Buffer{}
	payload.Write(hash[:])
	_ = binary.Write(payload, binary.LittleEndian, uint32(len(req.Data)))
	payload.Write(req.Data)

	resp, err := c.sendRequest(ctx, msgPutBlob, payload.Bytes())
	if err != nil {
		return nil, fmt.Errorf("put blob: %w", err)
	}

	if len(resp.payload) < 33 {
		return nil, fmt.Errorf("%w: put blob response too short (%d bytes)", ErrInvalidResponse, len(resp.payload))
	}

	result := &PutBlobResult{
		WasNew: resp.payload[32] == 1,
	}
	copy(result.Hash[:], resp.payload[0:32])

	return result, nil
}

// PutBlobIfAbsent stores a blob only if it doesn't already exist.
// Returns the hash and whether the blob was stored.
func (c *Client) PutBlobIfAbsent(ctx context.Context, data []byte) ([32]byte, bool, error) {
	result, err := c.PutBlob(ctx, &PutBlobRequest{Data: data})
	if err != nil {
		return [32]byte{}, false, err
	}
	return result.Hash, result.WasNew, nil
}

// AppendTurnWithFs appends a new turn with an optional filesystem snapshot.
// If fsRootHash is non-nil, the filesystem snapshot will be attached to the turn.
func (c *Client) AppendTurnWithFs(ctx context.Context, req *AppendRequest, fsRootHash *[32]byte) (*AppendResult, error) {
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

	// If fsRootHash is provided, append it and set flags
	var flags uint16
	if fsRootHash != nil {
		flags = 1 // bit 0 = has_fs_root
		payload.Write(fsRootHash[:])
	}

	resp, err := c.sendRequestWithFlags(ctx, msgAppend, flags, payload.Bytes())
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

// sendRequestWithFlags is like sendRequest but allows setting custom flags.
func (c *Client) sendRequestWithFlags(ctx context.Context, msgType uint16, flags uint16, payload []byte) (*frame, error) {
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

	if err := c.writeFrameWithFlags(msgType, flags, reqID, payload); err != nil {
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

func (c *Client) writeFrameWithFlags(msgType uint16, flags uint16, reqID uint64, payload []byte) error {
	header := &bytes.Buffer{}
	_ = binary.Write(header, binary.LittleEndian, uint32(len(payload)))
	_ = binary.Write(header, binary.LittleEndian, msgType)
	_ = binary.Write(header, binary.LittleEndian, flags)
	_ = binary.Write(header, binary.LittleEndian, reqID)

	_, err := c.conn.Write(append(header.Bytes(), payload...))
	return err
}
