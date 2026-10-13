package main

import (
	"os"
	"os/exec"
	"path/filepath"
	"testing"
	"time"
)

func TestClaimStaleness_Fresh(t *testing.T) {
	// A claim from 5 minutes ago should block (not stale)
	if isClaimStale(5 * 60) {
		t.Error("5min claim should not be stale")
	}
}

func TestClaimStaleness_Old(t *testing.T) {
	// A claim from 1 hour ago should be stale (threshold: 10min = 600s)
	if !isClaimStale(1 * 60 * 60) {
		t.Error("1h claim should be stale")
	}
}

func TestClaimStaleness_Boundary(t *testing.T) {
	// Exactly at threshold — should NOT be stale (> not >=)
	if isClaimStale(600) {
		t.Error("exactly 10min should not be stale (> check, not >=)")
	}
}

func TestClaimStaleness_JustOver(t *testing.T) {
	// One second over threshold — should be stale
	if !isClaimStale(601) {
		t.Error("601s should be stale")
	}
}

func TestClaimStaleness_Zero(t *testing.T) {
	// Zero age — definitely not stale
	if isClaimStale(0) {
		t.Error("0s claim should not be stale")
	}
}

func TestClaimStaleness_Negative(t *testing.T) {
	// Negative age (clock skew) — not stale
	if isClaimStale(-100) {
		t.Error("negative age should not be stale")
	}
}

func TestBeadClaimLockSerializes(t *testing.T) {
	// Clean up any stale lock from prior interrupted test run
	fallbackUnlock("bead-claim", "test-serialize")

	// First acquisition should succeed
	err := fallbackLock("bead-claim", "test-serialize")
	if err != nil {
		t.Fatalf("first lock acquisition failed: %v", err)
	}
	defer fallbackUnlock("bead-claim", "test-serialize")

	// Second acquisition of the same lock should fail
	err2 := fallbackLock("bead-claim", "test-serialize")
	if err2 == nil {
		t.Error("second lock acquisition should have failed but succeeded")
		fallbackUnlock("bead-claim", "test-serialize")
	}
}

func TestBeadClaimLockDifferentNamespace(t *testing.T) {
	fallbackUnlock("bead-claim", "test-ns")
	fallbackUnlock("sprint-claim", "test-ns")

	// "bead-claim" and "sprint-claim" are independent namespaces — no conflict
	err1 := fallbackLock("bead-claim", "test-ns")
	if err1 != nil {
		t.Fatalf("bead-claim lock failed: %v", err1)
	}
	defer fallbackUnlock("bead-claim", "test-ns")

	err2 := fallbackLock("sprint-claim", "test-ns")
	if err2 != nil {
		t.Errorf("sprint-claim lock should succeed independently: %v", err2)
	} else {
		fallbackUnlock("sprint-claim", "test-ns")
	}
}

func TestFallbackLockCleanup(t *testing.T) {
	fallbackUnlock("bead-claim", "test-cleanup")

	// Lock directory should be cleaned up after unlock
	err := fallbackLock("bead-claim", "test-cleanup")
	if err != nil {
		t.Fatalf("lock failed: %v", err)
	}

	lockDir := "/tmp/intercore/locks/bead-claim/test-cleanup"
	if _, err := os.Stat(lockDir); os.IsNotExist(err) {
		t.Error("lock directory should exist while held")
	}

	fallbackUnlock("bead-claim", "test-cleanup")

	if _, err := os.Stat(lockDir); !os.IsNotExist(err) {
		t.Error("lock directory should be removed after unlock")
		os.Remove(lockDir + "/owner.json")
		os.Remove(lockDir)
	}
}

// fakeBD installs a fake `bd` (labels kept as files under a temp dir) as the
// only binary on PATH, so ic is absent and the mkdir fallback lock is used.
// A marker file named fail_<key> makes `bd state <id> <key>` exit non-zero.
func fakeBD(t *testing.T) string {
	t.Helper()
	dir := t.TempDir()
	state := filepath.Join(dir, "state")
	if err := os.MkdirAll(state, 0o755); err != nil {
		t.Fatal(err)
	}
	script := `#!/bin/sh
S="` + state + `"
case "$1" in
state)
  if [ -e "$S/fail_$3" ]; then echo boom >&2; exit 1; fi
  if [ -f "$S/$3" ]; then cat "$S/$3"; else echo "(no $3 state set)"; fi ;;
update)
  shift 2
  while [ $# -gt 0 ]; do
    case "$1" in
      --remove-label) k="${2%%:*}"; rm -f "$S/$k" ;;
      --add-label) k="${2%%:*}"; v="${2#*:}"; printf '%s' "$v" > "$S/$k" ;;
    esac
    shift 2
  done ;;
esac
`
	bin := filepath.Join(dir, "bin")
	if err := os.MkdirAll(bin, 0o755); err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(filepath.Join(bin, "bd"), []byte(script), 0o755); err != nil {
		t.Fatal(err)
	}
	for _, tool := range []string{"cat", "rm"} {
		real, err := exec.LookPath(tool)
		if err != nil {
			t.Skipf("%s not found", tool)
		}
		if err := os.Symlink(real, filepath.Join(bin, tool)); err != nil {
			t.Fatal(err)
		}
	}
	t.Setenv("PATH", bin)
	icBin = ""
	return state
}

func fakeLabel(t *testing.T, state, key string) string {
	t.Helper()
	b, _ := os.ReadFile(filepath.Join(state, key))
	return string(b)
}

func TestHeartbeatSerializesWithReacquire(t *testing.T) {
	state := fakeBD(t)
	const bead = "test-hb-race"
	fallbackUnlock("bead-claim", bead)
	t.Setenv("CLAUDE_SESSION_ID", "s1")
	if err := cmdBeadClaim([]string{bead, "s1"}); err != nil {
		t.Fatal(err)
	}
	if g := fakeLabel(t, state, "claim_gen"); g != "1" {
		t.Fatalf("setup gen = %q, want 1", g)
	}

	// After heartbeat validated generation 1, a same-holder reacquire runs.
	done := make(chan error, 1)
	fired := false
	leaseReadHook = func() {
		if fired {
			return
		}
		fired = true
		go func() { done <- cmdBeadClaim([]string{bead, "s1"}) }()
		select { // unserialized, the reacquire finishes here
		case err := <-done:
			done <- err
		case <-time.After(300 * time.Millisecond):
		}
	}
	defer func() { leaseReadHook = nil }()

	if err := cmdBeadHeartbeat([]string{bead, "--fence=1"}); err != nil {
		t.Fatalf("heartbeat: %v", err)
	}
	select {
	case err := <-done:
		if err != nil {
			t.Fatalf("reacquire: %v", err)
		}
	case <-time.After(5 * time.Second):
		t.Fatal("reacquire never finished")
	}
	if g := fakeLabel(t, state, "claim_gen"); g != "2" {
		t.Fatalf("final claim_gen = %q, want 2 (heartbeat wrote a stale generation back)", g)
	}
}

func TestMalformedFenceRejectedBeforeMutation(t *testing.T) {
	state := fakeBD(t)
	t.Setenv("CLAUDE_SESSION_ID", "s1")
	for _, bad := range []string{"--fence=garbage", "--fence=", "--fence"} {
		if err := cmdBeadHeartbeat([]string{"b1", bad}); err == nil {
			t.Errorf("heartbeat %q: want error", bad)
		}
		if err := cmdBeadRelease([]string{"b1", bad, "--failure-class=retriable"}); err == nil {
			t.Errorf("release %q: want error", bad)
		}
		if err := cmdBeadClaim([]string{"b1", "s1", bad}); err == nil {
			t.Errorf("claim %q: want error", bad)
		}
	}
	entries, _ := os.ReadDir(state)
	if len(entries) != 0 {
		t.Fatalf("malformed fence mutated state: %v", entries)
	}
}

func TestClaimGenReadErrorFailsClosed(t *testing.T) {
	state := fakeBD(t)
	const bead = "test-gen-fail"
	fallbackUnlock("bead-claim", bead)
	t.Setenv("CLAUDE_SESSION_ID", "s1")
	if err := cmdBeadClaim([]string{bead, "s1"}); err != nil {
		t.Fatal(err)
	}
	if err := cmdBeadRelease([]string{bead}); err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(filepath.Join(state, "fail_claim_gen"), nil, 0o644); err != nil {
		t.Fatal(err)
	}
	before := fakeLabel(t, state, "claimed_by")
	if err := cmdBeadClaim([]string{bead, "s2"}); err == nil {
		t.Fatal("claim must fail when claim_gen cannot be read")
	}
	if g := fakeLabel(t, state, "claim_gen"); g != "1" {
		t.Fatalf("claim_gen = %q, want unchanged 1", g)
	}
	if after := fakeLabel(t, state, "claimed_by"); after != before {
		t.Fatalf("claimed_by changed %q -> %q", before, after)
	}
}
