package main

import "testing"

func TestClaimStaleness_Fresh(t *testing.T) {
	// A claim from 10 minutes ago should block (not stale)
	if isClaimStale(10 * 60) {
		t.Error("10min claim should not be stale")
	}
}

func TestClaimStaleness_Old(t *testing.T) {
	// A claim from 1 hour ago should be stale (threshold: 45min = 2700s)
	if !isClaimStale(1 * 60 * 60) {
		t.Error("1h claim should be stale")
	}
}

func TestClaimStaleness_Boundary(t *testing.T) {
	// Exactly at threshold — should NOT be stale (> not >=, matching bash `$age_sec -lt 2700`)
	if isClaimStale(2700) {
		t.Error("exactly 45min should not be stale (> check, not >=)")
	}
}

func TestClaimStaleness_JustOver(t *testing.T) {
	// One second over threshold — should be stale
	if !isClaimStale(2701) {
		t.Error("2701s should be stale")
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
