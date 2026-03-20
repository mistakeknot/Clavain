// Copyright 2025 StrongDM Inc
// SPDX-License-Identifier: Apache-2.0

package main

import (
	"context"
	"flag"
	"fmt"
	"os"

	cxdb "github.com/strongdm/ai-cxdb/clients/go"
)

func main() {
	addr := flag.String("addr", "127.0.0.1:9009", "server address")
	contextID := flag.Uint64("context", 0, "context id")
	flag.Parse()

	if *contextID == 0 {
		fmt.Println("context is required")
		os.Exit(1)
	}

	client, err := cxdb.Dial(*addr)
	if err != nil {
		fmt.Fprintf(os.Stderr, "dial error: %v\n", err)
		os.Exit(1)
	}
	defer func() { _ = client.Close() }()

	turns, err := client.GetLast(context.Background(), *contextID, cxdb.GetLastOptions{Limit: 1, IncludePayload: true})
	if err != nil {
		fmt.Fprintf(os.Stderr, "get last error: %v\n", err)
		os.Exit(1)
	}
	if len(turns) == 0 {
		fmt.Println("no turns")
		return
	}

	decoded, err := cxdb.DecodeMsgpack(turns[0].Payload)
	if err != nil {
		fmt.Fprintf(os.Stderr, "decode error: %v\n", err)
		os.Exit(1)
	}

	role, _ := decoded[uint64(1)].(string)
	text, _ := decoded[uint64(2)].(string)
	fmt.Printf("role=%s text=%s\n", role, text)
}
