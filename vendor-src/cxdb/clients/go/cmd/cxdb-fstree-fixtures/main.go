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

	"github.com/strongdm/ai-cxdb/clients/go/fstree"
	"github.com/zeebo/blake3"
)

type Fixture struct {
	Name        string            `json:"name"`
	RootHashHex string            `json:"root_hash_hex"`
	Trees       map[string]string `json:"trees"`
	Files       map[string]string `json:"files"`
	Blake3      map[string]string `json:"blake3"`
	Notes       string            `json:"notes,omitempty"`
}

func main() {
	outDir := flag.String("out", "clients/rust/cxdb/tests/fixtures", "output directory for fixtures")
	flag.Parse()

	tmpDir, err := os.MkdirTemp("", "cxdb-fstree-fixtures")
	if err != nil {
		fmt.Fprintf(os.Stderr, "tmpdir: %v\n", err)
		os.Exit(1)
	}
	defer func() { _ = os.RemoveAll(tmpDir) }()

	if err := seedWorkspace(tmpDir); err != nil {
		fmt.Fprintf(os.Stderr, "seed workspace: %v\n", err)
		os.Exit(1)
	}

	snap, err := fstree.Capture(tmpDir)
	if err != nil {
		fmt.Fprintf(os.Stderr, "capture: %v\n", err)
		os.Exit(1)
	}

	trees := make(map[string]string)
	for hash, data := range snap.Trees {
		trees[hex.EncodeToString(hash[:])] = hex.EncodeToString(data)
	}

	files := make(map[string]string)
	for hash, ref := range snap.Files {
		rel, err := filepath.Rel(tmpDir, ref.Path)
		if err != nil {
			rel = ref.Path
		}
		files[filepath.ToSlash(rel)] = hex.EncodeToString(hash[:])
	}

	emptyHash := blake3.Sum256(nil)
	helloHash := blake3.Sum256([]byte("hello"))
	blake3Fixtures := map[string]string{
		"empty": hex.EncodeToString(emptyHash[:]),
		"hello": hex.EncodeToString(helloHash[:]),
	}

	fixture := Fixture{
		Name:        "fstree_basic",
		RootHashHex: hex.EncodeToString(snap.RootHash[:]),
		Trees:       trees,
		Files:       files,
		Blake3:      blake3Fixtures,
		Notes:       "Generated from a deterministic synthetic workspace.",
	}

	if err := os.MkdirAll(*outDir, 0o755); err != nil {
		fmt.Fprintf(os.Stderr, "mkdir: %v\n", err)
		os.Exit(1)
	}

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

func seedWorkspace(root string) error {
	if err := os.MkdirAll(filepath.Join(root, "src"), 0o755); err != nil {
		return err
	}
	if err := os.WriteFile(filepath.Join(root, "README.md"), []byte("# Test"), 0o644); err != nil {
		return err
	}
	if err := os.WriteFile(filepath.Join(root, "src", "main.go"), []byte("package main"), 0o644); err != nil {
		return err
	}
	if err := os.WriteFile(filepath.Join(root, "src", "lib.go"), []byte("package main\n\nfunc foo() {}"), 0o644); err != nil {
		return err
	}
	if err := os.WriteFile(filepath.Join(root, "script.sh"), []byte("#!/bin/bash\necho hi"), 0o755); err != nil {
		return err
	}
	return nil
}
