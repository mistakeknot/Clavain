package main

import (
	"io"
	"os"
	"path/filepath"
	"strings"
	"testing"
)

func TestFormatGoalPaste(t *testing.T) {
	out := formatGoalPaste("g1a2b3c4", "all tests exit 0, or stop after 20 turns")
	if !strings.Contains(out, "/goal all tests exit 0, or stop after 20 turns") {
		t.Errorf("missing paste line: %q", out)
	}
	if !strings.Contains(out, "g1a2b3c4") {
		t.Errorf("missing goal id: %q", out)
	}
}

func TestGoalMintRequiresProjectAndConditionFile(t *testing.T) {
	err := cmdGoalMint([]string{"Ship widget"})
	if err == nil || !strings.Contains(err.Error(), "--project and --condition-file are required") {
		t.Fatalf("cmdGoalMint error = %v", err)
	}
}

func TestGoalMintCreatesGoalAndPrintsPasteText(t *testing.T) {
	tmp := t.TempDir()
	conditionFile := filepath.Join(tmp, "condition.txt")
	if err := os.WriteFile(conditionFile, []byte("all tests exit 0\n"), 0o600); err != nil {
		t.Fatal(err)
	}
	fakeIC := filepath.Join(tmp, "ic")
	if err := os.WriteFile(fakeIC, []byte("#!/bin/sh\nprintf '{\"id\":\"g1a2b3c4\"}'\n"), 0o700); err != nil {
		t.Fatal(err)
	}

	oldICBin := icBin
	icBin = fakeIC
	t.Cleanup(func() { icBin = oldICBin })

	readEnd, writeEnd, err := os.Pipe()
	if err != nil {
		t.Fatal(err)
	}
	oldStdout := os.Stdout
	os.Stdout = writeEnd
	t.Cleanup(func() { os.Stdout = oldStdout })

	err = cmdGoalMint([]string{
		"Ship widget",
		"--project=" + tmp,
		"--condition-file=" + conditionFile,
	})
	if closeErr := writeEnd.Close(); closeErr != nil {
		t.Fatal(closeErr)
	}
	os.Stdout = oldStdout
	if err != nil {
		t.Fatalf("cmdGoalMint: %v", err)
	}
	out, err := io.ReadAll(readEnd)
	if err != nil {
		t.Fatalf("read stdout: %v", err)
	}
	if got := string(out); !strings.Contains(got, "Goal minted: g1a2b3c4") || !strings.Contains(got, "/goal all tests exit 0") {
		t.Fatalf("stdout = %q", got)
	}
}
