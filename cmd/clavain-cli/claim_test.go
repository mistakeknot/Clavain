package main

import "testing"

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
