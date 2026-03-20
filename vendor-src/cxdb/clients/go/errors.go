// Copyright 2025 StrongDM Inc
// SPDX-License-Identifier: Apache-2.0

package cxdb

import (
	"errors"
	"fmt"
)

// Common errors
var (
	// ErrClientClosed is returned when operations are attempted on a closed client.
	ErrClientClosed = errors.New("cxdb: client closed")

	// ErrContextNotFound is returned when a context ID doesn't exist.
	ErrContextNotFound = errors.New("cxdb: context not found")

	// ErrTurnNotFound is returned when a turn ID doesn't exist.
	ErrTurnNotFound = errors.New("cxdb: turn not found")

	// ErrInvalidResponse is returned when the server response is malformed.
	ErrInvalidResponse = errors.New("cxdb: invalid response")

	// ErrBlobNotFound is returned when a blob hash doesn't exist in the store.
	ErrBlobNotFound = errors.New("cxdb: blob not found")
)

// ServerError represents an error returned by the CXDB server.
type ServerError struct {
	Code   uint32
	Detail string
}

func (e *ServerError) Error() string {
	return fmt.Sprintf("cxdb server error %d: %s", e.Code, e.Detail)
}

// IsServerError checks if an error is a ServerError with the given code.
func IsServerError(err error, code uint32) bool {
	var se *ServerError
	if errors.As(err, &se) {
		return se.Code == code
	}
	return false
}
