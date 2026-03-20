// Copyright 2025 StrongDM Inc
// SPDX-License-Identifier: Apache-2.0

package main

import (
	"encoding/binary"
	"encoding/hex"
	"encoding/json"
	"flag"
	"fmt"
	"os"
	"path/filepath"

	"github.com/zeebo/blake3"
)

type Fixture struct {
	Name       string `json:"name"`
	MsgType    uint16 `json:"msg_type"`
	Flags      uint16 `json:"flags"`
	PayloadHex string `json:"payload_hex"`
	Notes      string `json:"notes,omitempty"`
}

func main() {
	outDir := flag.String("out", "clients/rust/cxdb/tests/fixtures", "output directory for fixtures")
	flag.Parse()

	fixtures := []Fixture{
		helloFixture("hello_empty", ""),
		helloFixture("hello_tag", "test-client"),
		ctxCreateFixture("ctx_create_base0", 0),
		ctxForkFixture("ctx_fork_base123", 123),
		getHeadFixture("get_head_ctx42", 42),
		appendFixture("append_parent0", 1, 0, "cxdb.ConversationItem", 3, []byte{0x91, 0x01}, ""),
		appendFixture("append_parent7", 1, 7, "cxdb.ConversationItem", 3, []byte{0x91, 0x02}, ""),
		appendFixture("append_idempotent", 1, 0, "cxdb.ConversationItem", 3, []byte{0x91, 0x03}, "idem-1"),
		getLastFixture("get_last_default", 1, 10, false),
		getLastFixture("get_last_payload", 1, 5, true),
		attachFsFixture("attach_fs", 99, testHash(0xAA)),
		putBlobFixture("put_blob", []byte("hello blob")),
		getBlobFixture("get_blob", testHash(0xCC)),
		appendWithFsFixture("append_with_fs", 1, 0, "cxdb.ConversationItem", 3, []byte{0x91, 0x04}, "", testHash(0xBB)),
	}

	if err := os.MkdirAll(*outDir, 0o755); err != nil {
		fmt.Fprintf(os.Stderr, "mkdir: %v\n", err)
		os.Exit(1)
	}

	for _, fixture := range fixtures {
		path := filepath.Join(*outDir, fixture.Name+".json")
		data, err := json.MarshalIndent(fixture, "", "  ")
		if err != nil {
			fmt.Fprintf(os.Stderr, "marshal %s: %v\n", fixture.Name, err)
			os.Exit(1)
		}
		if err := os.WriteFile(path, data, 0o644); err != nil {
			fmt.Fprintf(os.Stderr, "write %s: %v\n", path, err)
			os.Exit(1)
		}
	}
}

func helloFixture(name, tag string) Fixture {
	payload := make([]byte, 0, 2+2+len(tag)+4)
	payload = appendU16(payload, 1)
	payload = appendU16(payload, uint16(len(tag)))
	payload = append(payload, []byte(tag)...)
	payload = appendU32(payload, 0)
	return Fixture{Name: name, MsgType: 1, Flags: 0, PayloadHex: hex.EncodeToString(payload)}
}

func ctxCreateFixture(name string, baseTurn uint64) Fixture {
	payload := make([]byte, 8)
	binary.LittleEndian.PutUint64(payload, baseTurn)
	return Fixture{Name: name, MsgType: 2, Flags: 0, PayloadHex: hex.EncodeToString(payload)}
}

func ctxForkFixture(name string, baseTurn uint64) Fixture {
	payload := make([]byte, 8)
	binary.LittleEndian.PutUint64(payload, baseTurn)
	return Fixture{Name: name, MsgType: 3, Flags: 0, PayloadHex: hex.EncodeToString(payload)}
}

func getHeadFixture(name string, contextID uint64) Fixture {
	payload := make([]byte, 8)
	binary.LittleEndian.PutUint64(payload, contextID)
	return Fixture{Name: name, MsgType: 4, Flags: 0, PayloadHex: hex.EncodeToString(payload)}
}

func appendFixture(name string, ctxID, parentID uint64, typeID string, typeVersion uint32, payloadBytes []byte, idem string) Fixture {
	payload := make([]byte, 0, 128+len(payloadBytes))
	payload = appendU64(payload, ctxID)
	payload = appendU64(payload, parentID)
	payload = appendU32(payload, uint32(len(typeID)))
	payload = append(payload, []byte(typeID)...)
	payload = appendU32(payload, typeVersion)
	payload = appendU32(payload, 1) // EncodingMsgpack
	payload = appendU32(payload, 0) // CompressionNone
	payload = appendU32(payload, uint32(len(payloadBytes)))
	hash := blake3.Sum256(payloadBytes)
	payload = append(payload, hash[:]...)
	payload = appendU32(payload, uint32(len(payloadBytes)))
	payload = append(payload, payloadBytes...)
	payload = appendU32(payload, uint32(len(idem)))
	if len(idem) > 0 {
		payload = append(payload, []byte(idem)...)
	}
	return Fixture{Name: name, MsgType: 5, Flags: 0, PayloadHex: hex.EncodeToString(payload)}
}

func appendWithFsFixture(name string, ctxID, parentID uint64, typeID string, typeVersion uint32, payloadBytes []byte, idem string, fsHash [32]byte) Fixture {
	fixture := appendFixture(name, ctxID, parentID, typeID, typeVersion, payloadBytes, idem)
	payload, _ := hex.DecodeString(fixture.PayloadHex)
	payload = append(payload, fsHash[:]...)
	fixture.Flags = 1
	fixture.PayloadHex = hex.EncodeToString(payload)
	return fixture
}

func getLastFixture(name string, contextID uint64, limit uint32, includePayload bool) Fixture {
	payload := make([]byte, 0, 16)
	payload = appendU64(payload, contextID)
	payload = appendU32(payload, limit)
	if includePayload {
		payload = appendU32(payload, 1)
	} else {
		payload = appendU32(payload, 0)
	}
	return Fixture{Name: name, MsgType: 6, Flags: 0, PayloadHex: hex.EncodeToString(payload)}
}

func getBlobFixture(name string, hash [32]byte) Fixture {
	payload := make([]byte, 0, 32)
	payload = append(payload, hash[:]...)
	return Fixture{Name: name, MsgType: 9, Flags: 0, PayloadHex: hex.EncodeToString(payload)}
}

func attachFsFixture(name string, turnID uint64, fsHash [32]byte) Fixture {
	payload := make([]byte, 0, 40)
	payload = appendU64(payload, turnID)
	payload = append(payload, fsHash[:]...)
	return Fixture{Name: name, MsgType: 10, Flags: 0, PayloadHex: hex.EncodeToString(payload)}
}

func putBlobFixture(name string, data []byte) Fixture {
	hash := blake3.Sum256(data)
	payload := make([]byte, 0, 36+len(data))
	payload = append(payload, hash[:]...)
	payload = appendU32(payload, uint32(len(data)))
	payload = append(payload, data...)
	return Fixture{Name: name, MsgType: 11, Flags: 0, PayloadHex: hex.EncodeToString(payload)}
}

func appendU16(buf []byte, val uint16) []byte {
	b := make([]byte, 2)
	binary.LittleEndian.PutUint16(b, val)
	return append(buf, b...)
}

func appendU32(buf []byte, val uint32) []byte {
	b := make([]byte, 4)
	binary.LittleEndian.PutUint32(b, val)
	return append(buf, b...)
}

func appendU64(buf []byte, val uint64) []byte {
	b := make([]byte, 8)
	binary.LittleEndian.PutUint64(b, val)
	return append(buf, b...)
}

func testHash(seed byte) [32]byte {
	var hash [32]byte
	for i := 0; i < len(hash); i++ {
		hash[i] = seed
	}
	return hash
}
