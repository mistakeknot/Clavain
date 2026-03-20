// Copyright 2025 StrongDM Inc
// SPDX-License-Identifier: Apache-2.0

package main

import (
	"encoding/hex"
	"encoding/json"
	"flag"
	"fmt"
	"os"
	"path/filepath"

	cxdb "github.com/strongdm/ai-cxdb/clients/go"
	"github.com/strongdm/ai-cxdb/clients/go/types"
)

type Fixture struct {
	Name       string `json:"name"`
	PayloadHex string `json:"payload_hex"`
	Notes      string `json:"notes,omitempty"`
}

func main() {
	outDir := flag.String("out", "clients/rust/cxdb/tests/fixtures", "output directory for fixtures")
	flag.Parse()

	fixtures := []Fixture{
		conversationFixture(),
		numericMapFixture(),
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

func conversationFixture() Fixture {
	item := types.NewUserInput("Hello from fixtures", "file.txt")
	item.ID = "item-1"
	item.Timestamp = 1700000000000
	item.WithContextMetadata(&types.ContextMetadata{
		ClientTag: "fixture-tag",
		Title:     "Fixture Title",
		Labels:    []string{"alpha", "beta"},
		Custom:    map[string]string{"env": "test"},
	})

	payload, err := cxdb.EncodeMsgpack(item)
	if err != nil {
		panic(err)
	}
	return Fixture{
		Name:       "msgpack_conversation_item",
		PayloadHex: hex.EncodeToString(payload),
		Notes:      "ConversationItem with user input + context metadata.",
	}
}

func numericMapFixture() Fixture {
	payload, err := cxdb.EncodeMsgpack(map[uint64]any{
		2: "two",
		1: "one",
		3: "three",
	})
	if err != nil {
		panic(err)
	}
	return Fixture{
		Name:       "msgpack_numeric_map",
		PayloadHex: hex.EncodeToString(payload),
		Notes:      "Map with numeric keys for ordering test.",
	}
}
