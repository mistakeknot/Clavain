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

// Regression: goal-mint prepended /goal unconditionally, so a condition written
// in docs/guide-goal-shape.md's canonical form produced "/goal /goal Clavain — ".
func TestFormatGoalPasteDoesNotDoubleThePrefix(t *testing.T) {
	canonical := "Clavain — close the bypass\n\nOUTCOME: something is true.\n"
	out := formatGoalPaste("g1a2b3c4", "/goal "+canonical)
	if strings.Contains(out, "/goal /goal") {
		t.Errorf("doubled prefix: %q", out)
	}
	if !strings.Contains(out, "/goal "+canonical) {
		t.Errorf("lost the condition: %q", out)
	}
	// A bare condition still gets the prefix.
	bare := formatGoalPaste("g1a2b3c4", "all tests exit 0")
	if !strings.Contains(bare, "/goal all tests exit 0") {
		t.Errorf("missing prefix on a bare condition: %q", bare)
	}
	// A word merely starting with the letters is not the prefix.
	notPrefix := formatGoalPaste("g1a2b3c4", "/goalpost alignment holds")
	if !strings.Contains(notPrefix, "/goal /goalpost alignment holds") {
		t.Errorf("treated /goalpost as the prefix: %q", notPrefix)
	}
}

// Regression: the bind called `bd state <bead> <key> <value>`, but bd state
// READS and accepts two arguments, so every bind failed as "accepts 2 arg(s),
// received 3" and goals minted unbound.
func TestGoalMintBindsBeadWithSetState(t *testing.T) {
	tmp := t.TempDir()
	conditionFile := filepath.Join(tmp, "condition.txt")
	if err := os.WriteFile(conditionFile, []byte("all tests exit 0\n"), 0o600); err != nil {
		t.Fatal(err)
	}
	fakeIC := filepath.Join(tmp, "ic")
	if err := os.WriteFile(fakeIC, []byte("#!/bin/sh\nprintf '{\"id\":\"g1a2b3c4\"}'\n"), 0o700); err != nil {
		t.Fatal(err)
	}
	argvLog := filepath.Join(tmp, "bd-argv.txt")
	fakeBD := filepath.Join(tmp, "bd")
	if err := os.WriteFile(fakeBD,
		[]byte("#!/bin/sh\nprintf '%s\\n' \"$*\" >> "+argvLog+"\nexit 0\n"), 0o700); err != nil {
		t.Fatal(err)
	}
	t.Setenv("PATH", tmp+string(os.PathListSeparator)+os.Getenv("PATH"))

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

	mintErr := cmdGoalMint([]string{
		"Ship widget",
		"--project=" + tmp,
		"--condition-file=" + conditionFile,
		"--bead=Sylveste-ymp2",
	})
	if closeErr := writeEnd.Close(); closeErr != nil {
		t.Fatal(closeErr)
	}
	os.Stdout = oldStdout
	if _, err := io.ReadAll(readEnd); err != nil {
		t.Fatalf("read stdout: %v", err)
	}
	if mintErr != nil {
		t.Fatalf("cmdGoalMint: %v", mintErr)
	}

	logged, err := os.ReadFile(argvLog)
	if err != nil {
		t.Fatalf("bd was never invoked for the bind: %v", err)
	}
	got := strings.TrimSpace(string(logged))
	want := "set-state Sylveste-ymp2 ic_goal_id=g1a2b3c4 --reason goal g1a2b3c4 minted for this bead"
	if got != want {
		t.Errorf("bind argv\n  got:  %q\n  want: %q", got, want)
	}
}
