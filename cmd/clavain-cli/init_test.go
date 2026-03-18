package main

import (
	"strings"
	"testing"
)

func TestFormatBanner_Basic(t *testing.T) {
	d := sprintInitData{
		beadID:     "Demarch-czxk",
		title:      "clavain-cli sprint-init: consolidated sprint bootstrap",
		complexity: 3,
		compLabel:  "moderate",
		phase:      "planned",
		nextPhase:  "plan-reviewed",
		budget:     250000,
		spent:      42000,
		hasRun:     true,
	}

	// Test plain text (no color)
	out := formatBanner(d, false)

	if !strings.Contains(out, "Demarch-czxk") {
		t.Errorf("missing bead ID in output:\n%s", out)
	}
	if !strings.Contains(out, "3/5 (moderate)") {
		t.Errorf("missing complexity in output:\n%s", out)
	}
	if !strings.Contains(out, "planned → plan-reviewed") {
		t.Errorf("missing phase transition in output:\n%s", out)
	}
	if !strings.Contains(out, "42k / 250k (16%)") {
		t.Errorf("missing budget in output:\n%s", out)
	}

	// Ensure no ANSI escapes in plain mode
	if strings.Contains(out, "\033[") {
		t.Errorf("unexpected ANSI escape in plain mode:\n%s", out)
	}
}

func TestFormatBanner_Color(t *testing.T) {
	d := sprintInitData{
		beadID:     "Demarch-abc1",
		title:      "test",
		complexity: 2,
		compLabel:  "simple",
		phase:      "brainstorm",
		budget:     100000,
		spent:      10000,
		hasRun:     true,
	}

	out := formatBanner(d, true)

	// Should contain ANSI escapes
	if !strings.Contains(out, "\033[") {
		t.Errorf("expected ANSI escapes in color mode:\n%s", out)
	}
	if !strings.Contains(out, "Demarch-abc1") {
		t.Errorf("missing bead ID in color output")
	}
}

func TestFormatBanner_NoRun(t *testing.T) {
	d := sprintInitData{
		beadID:     "Demarch-xyz9",
		title:      "some task",
		complexity: 3,
		compLabel:  "moderate",
		phase:      "",
		hasRun:     false,
	}

	out := formatBanner(d, false)

	// Should NOT contain Budget or Phase lines
	if strings.Contains(out, "Budget:") {
		t.Errorf("should not show budget when no run:\n%s", out)
	}
	if strings.Contains(out, "Phase:") {
		t.Errorf("should not show phase when empty:\n%s", out)
	}
}

func TestFormatBanner_BudgetWarning(t *testing.T) {
	tests := []struct {
		name      string
		spent     int64
		budget    int64
		wantColor string
	}{
		{"healthy", 30000, 100000, colorSuccess},
		{"warning", 75000, 100000, colorWarning},
		{"danger", 95000, 100000, colorError},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			d := sprintInitData{
				beadID:     "Demarch-test",
				title:      "test",
				complexity: 3,
				compLabel:  "moderate",
				budget:     tt.budget,
				spent:      tt.spent,
				hasRun:     true,
			}

			out := formatBanner(d, true)
			if !strings.Contains(out, tt.wantColor) {
				t.Errorf("%s: expected color %q in output", tt.name, tt.wantColor)
			}
		})
	}
}

func TestFormatBanner_LongTitle(t *testing.T) {
	d := sprintInitData{
		beadID:     "Demarch-long",
		title:      "This is a very long title that should be truncated because it exceeds the maximum display width",
		complexity: 3,
		compLabel:  "moderate",
	}

	out := formatBanner(d, false)
	if !strings.Contains(out, "...") {
		t.Errorf("expected truncated title with ellipsis:\n%s", out)
	}
}

func TestParseBDTitle(t *testing.T) {
	tests := []struct {
		input string
		want  string
	}{
		{
			"✓ Demarch-czxk · clavain-cli sprint-init [in_progress]",
			"clavain-cli sprint-init",
		},
		{
			"Demarch-abc1 — some task title [open]",
			"some task title",
		},
		{
			"plain title without markers",
			"plain title without markers",
		},
		{
			"",
			"",
		},
	}

	for _, tt := range tests {
		got := parseBDTitle(tt.input)
		if got != tt.want {
			t.Errorf("parseBDTitle(%q) = %q, want %q", tt.input, got, tt.want)
		}
	}
}

func TestCmdSprintNextStepPure(t *testing.T) {
	tests := []struct {
		phase string
		want  string
	}{
		{"brainstorm", "brainstorm-reviewed"},
		{"planned", "plan-reviewed"},
		{"executing", "shipping"},
		{"done", ""},
		{"unknown", ""},
	}

	for _, tt := range tests {
		got := cmdSprintNextStepPure(tt.phase)
		if got != tt.want {
			t.Errorf("cmdSprintNextStepPure(%q) = %q, want %q", tt.phase, got, tt.want)
		}
	}
}

func TestFormatBanner_NoBudgetSet(t *testing.T) {
	d := sprintInitData{
		beadID:     "Demarch-nob",
		title:      "test",
		complexity: 3,
		compLabel:  "moderate",
		hasRun:     true,
		budget:     0,
	}

	out := formatBanner(d, false)
	if !strings.Contains(out, "(no budget set)") {
		t.Errorf("expected 'no budget set' message:\n%s", out)
	}
}
