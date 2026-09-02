package main

import (
	"os"
	"path/filepath"
	"runtime"
	"strings"
	"testing"
)

// A set-artifact that records nothing must not exit 0. Callers record verdict
// evidence through it (test-pass-sha grounds quality-gates); a reported
// success over a silent double-failure is the quiet-pass disease. Found live
// 2026-09-02: from a checkout with no resolvable beads DB and no bound run,
// "Error: no beads database found" printed twice and the command exited 0.
func TestSetArtifact_BothStoresFail_IsAnError(t *testing.T) {
	if runtime.GOOS == "windows" {
		t.Skip("fake bd is a shell script")
	}
	dir := t.TempDir()
	fake := filepath.Join(dir, "bd")
	if err := os.WriteFile(fake, []byte("#!/bin/sh\necho 'Error: no beads database found' >&2\nexit 1\n"), 0o755); err != nil {
		t.Fatal(err)
	}
	t.Setenv("PATH", dir) // bd present but failing; ic absent entirely

	err := cmdSetArtifact([]string{"Sylveste-nonesuch", "test-pass-sha", "abc123"})
	if err == nil {
		t.Fatal("set-artifact reported success though neither bd nor Intercore recorded the artifact")
	}
	if !strings.Contains(err.Error(), "not recorded") {
		t.Fatalf("error should say the artifact was not recorded, got: %v", err)
	}
}

// The bd fallback alone is a real store: when bd succeeds and no Intercore
// run is bound, exit 0 is correct and must stay that way.
func TestSetArtifact_BDFallbackAlone_Succeeds(t *testing.T) {
	if runtime.GOOS == "windows" {
		t.Skip("fake bd is a shell script")
	}
	dir := t.TempDir()
	fake := filepath.Join(dir, "bd")
	// set-state succeeds; the resolveRunID "state" read finds no bound run.
	script := "#!/bin/sh\ncase \"$1\" in state) echo '(no state)' ;; esac\nexit 0\n"
	if err := os.WriteFile(fake, []byte(script), 0o755); err != nil {
		t.Fatal(err)
	}
	t.Setenv("PATH", dir)

	if err := cmdSetArtifact([]string{"Sylveste-nonesuch2", "test-pass-sha", "abc123"}); err != nil {
		t.Fatalf("bd fallback succeeded and no run is bound; expected success, got: %v", err)
	}
}
