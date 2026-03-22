package main

import (
	"os"
	"testing"
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
