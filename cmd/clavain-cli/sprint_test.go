package main

import "testing"

func TestResolveRunID_Empty(t *testing.T) {
	_, err := resolveRunID("")
	if err == nil {
		t.Error("expected error for empty bead ID")
	}
}

func TestDefaultBudget(t *testing.T) {
	tests := []struct {
		complexity int
		want       int64
	}{
		{1, 50000},
		{2, 100000},
		{3, 250000},
		{4, 500000},
		{5, 1000000},
		{0, 1000000},  // default (out of range)
		{99, 1000000}, // default (out of range)
		{-1, 1000000}, // default (negative)
	}
	for _, tt := range tests {
		got := defaultBudget(tt.complexity)
		if got != tt.want {
			t.Errorf("defaultBudget(%d) = %d, want %d", tt.complexity, got, tt.want)
		}
	}
}

func TestRunIDCache(t *testing.T) {
	// Verify cache returns stored values
	runIDCache["test-bead"] = "test-run-123"
	defer delete(runIDCache, "test-bead")

	// resolveRunID should hit cache and not call bd
	got, err := resolveRunID("test-bead")
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if got != "test-run-123" {
		t.Errorf("resolveRunID(cached) = %q, want %q", got, "test-run-123")
	}
}

func TestBeadIDPattern(t *testing.T) {
	tests := []struct {
		input string
		want  string
	}{
		{"Created iv-abc123", "iv-abc123"},
		{"Bead Epic-xyz99 created", "Epic-xyz99"},
		{"no match here 123", ""},
		{"iv-sevis (F1)", "iv-sevis"},
	}
	for _, tt := range tests {
		got := beadIDPattern.FindString(tt.input)
		if got != tt.want {
			t.Errorf("beadIDPattern.FindString(%q) = %q, want %q", tt.input, got, tt.want)
		}
	}
}

func TestMustGetwd(t *testing.T) {
	wd := mustGetwd()
	if wd == "" {
		t.Error("mustGetwd returned empty string")
	}
}
