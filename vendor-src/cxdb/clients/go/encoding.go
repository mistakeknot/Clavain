// Copyright 2025 StrongDM Inc
// SPDX-License-Identifier: Apache-2.0

package cxdb

import (
	"bytes"

	"github.com/vmihailenco/msgpack/v5"
)

// EncodeMsgpack encodes a value as msgpack with sorted map keys.
// This ensures deterministic encoding for content-addressed storage.
func EncodeMsgpack(v any) ([]byte, error) {
	buf := &bytes.Buffer{}
	enc := msgpack.NewEncoder(buf)
	enc.SetSortMapKeys(true)
	if err := enc.Encode(v); err != nil {
		return nil, err
	}
	return buf.Bytes(), nil
}

// DecodeMsgpack decodes msgpack data into a map with uint64 keys.
// CXDB payloads use numeric field tags as keys.
func DecodeMsgpack(data []byte) (map[uint64]any, error) {
	var result map[uint64]any
	if err := msgpack.Unmarshal(data, &result); err != nil {
		return nil, err
	}
	return result, nil
}

// DecodeMsgpackInto decodes msgpack data into the provided value.
func DecodeMsgpackInto(data []byte, v any) error {
	return msgpack.Unmarshal(data, v)
}
