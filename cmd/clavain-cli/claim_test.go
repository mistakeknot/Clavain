package main

import "testing"

func TestClaimStaleness_Fresh(t *testing.T) {
	// A claim from 30 minutes ago should block (not stale)
	if isClaimStale(30 * 60) {
		t.Error("30min claim should not be stale")
	}
}

func TestClaimStaleness_Old(t *testing.T) {
	// A claim from 3 hours ago should be stale (threshold: 2h = 7200s)
	if !isClaimStale(3 * 60 * 60) {
		t.Error("3h claim should be stale")
	}
}

func TestClaimStaleness_Boundary(t *testing.T) {
	// Exactly at threshold — should NOT be stale (> not >=, matching bash `$age_seconds -lt 7200`)
	if isClaimStale(7200) {
		t.Error("exactly 2h should not be stale (> check, not >=)")
	}
}

func TestClaimStaleness_JustOver(t *testing.T) {
	// One second over threshold — should be stale
	if !isClaimStale(7201) {
		t.Error("7201s should be stale")
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
