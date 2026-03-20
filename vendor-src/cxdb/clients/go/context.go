// Copyright 2025 StrongDM Inc
// SPDX-License-Identifier: Apache-2.0

package cxdb

import (
	"context"
	"encoding/binary"
	"fmt"
)

// ContextHead represents the head of a context (branch).
type ContextHead struct {
	ContextID  uint64
	HeadTurnID uint64
	HeadDepth  uint32
}

// CreateContext creates a new context in CXDB.
// If baseTurnID is 0, creates an empty context.
// If baseTurnID is non-zero, creates a context starting from that turn.
func (c *Client) CreateContext(ctx context.Context, baseTurnID uint64) (*ContextHead, error) {
	payload := make([]byte, 8)
	binary.LittleEndian.PutUint64(payload, baseTurnID)

	resp, err := c.sendRequest(ctx, msgCtxCreate, payload)
	if err != nil {
		return nil, fmt.Errorf("create context: %w", err)
	}

	return parseContextHead(resp.payload)
}

// ForkContext creates a new context branching from a specific turn.
// This is an O(1) operation - it creates a new head pointer without copying data.
func (c *Client) ForkContext(ctx context.Context, baseTurnID uint64) (*ContextHead, error) {
	payload := make([]byte, 8)
	binary.LittleEndian.PutUint64(payload, baseTurnID)

	resp, err := c.sendRequest(ctx, msgCtxFork, payload)
	if err != nil {
		return nil, fmt.Errorf("fork context: %w", err)
	}

	return parseContextHead(resp.payload)
}

// GetHead retrieves the current head of a context.
func (c *Client) GetHead(ctx context.Context, contextID uint64) (*ContextHead, error) {
	payload := make([]byte, 8)
	binary.LittleEndian.PutUint64(payload, contextID)

	resp, err := c.sendRequest(ctx, msgGetHead, payload)
	if err != nil {
		return nil, fmt.Errorf("get head: %w", err)
	}

	return parseContextHead(resp.payload)
}

func parseContextHead(payload []byte) (*ContextHead, error) {
	if len(payload) < 20 {
		return nil, fmt.Errorf("%w: context head too short (%d bytes)", ErrInvalidResponse, len(payload))
	}
	return &ContextHead{
		ContextID:  binary.LittleEndian.Uint64(payload[0:8]),
		HeadTurnID: binary.LittleEndian.Uint64(payload[8:16]),
		HeadDepth:  binary.LittleEndian.Uint32(payload[16:20]),
	}, nil
}
