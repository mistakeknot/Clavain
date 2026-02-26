package main

import "testing"

func TestPhaseCostEstimate(t *testing.T) {
	tests := []struct {
		phase string
		want  int64
	}{
		{"brainstorm", 30000},
		{"brainstorm-reviewed", 15000},
		{"strategized", 25000},
		{"planned", 35000},
		{"plan-reviewed", 50000},
		{"executing", 150000},
		{"shipping", 100000},
		{"reflect", 10000},
		{"done", 5000},
		{"unknown", 30000},   // default
		{"", 30000},          // default (empty)
		{"garbage", 30000},   // default (unknown phase)
		{"Brainstorm", 30000}, // case-sensitive — capitals fall through to default
	}
	for _, tt := range tests {
		got := phaseCostEstimate(tt.phase)
		if got != tt.want {
			t.Errorf("phaseCostEstimate(%q) = %d, want %d", tt.phase, got, tt.want)
		}
	}
}

func TestPhaseToStage_BudgetCases(t *testing.T) {
	tests := []struct {
		phase string
		want  string
	}{
		{"brainstorm", "discover"},
		{"brainstorm-reviewed", "design"},
		{"strategized", "design"},
		{"planned", "design"},
		{"plan-reviewed", "design"},
		{"executing", "build"},
		{"shipping", "ship"},
		{"reflect", "reflect"},
		{"done", "done"},
		{"garbage", "unknown"},  // default
		{"", "unknown"},         // default (empty)
		{"Executing", "unknown"}, // case-sensitive
	}
	for _, tt := range tests {
		got := phaseToStage(tt.phase)
		if got != tt.want {
			t.Errorf("phaseToStage(%q) = %q, want %q", tt.phase, got, tt.want)
		}
	}
}

func TestBudgetRemaining(t *testing.T) {
	tests := []struct {
		budget int64
		spent  int64
		want   int64
	}{
		{250000, 100000, 150000},   // normal
		{250000, 250000, 0},         // exactly spent
		{250000, 300000, 0},         // overspent — clamped to 0
		{0, 0, 0},                   // zero budget, zero spent
		{0, 100, 0},                 // zero budget, some spent — clamp
		{1000000, 0, 1000000},       // nothing spent
		{1, 1, 0},                   // edge: exactly 1
		{100, 99, 1},                // edge: 1 remaining
		{9223372036854775807, 0, 9223372036854775807}, // max int64
	}
	for _, tt := range tests {
		got := budgetRemaining(tt.budget, tt.spent)
		if got != tt.want {
			t.Errorf("budgetRemaining(%d, %d) = %d, want %d",
				tt.budget, tt.spent, got, tt.want)
		}
	}
}

func TestStageAllocation(t *testing.T) {
	tests := []struct {
		total     int64
		sharePct  int
		minTokens int64
		want      int64
	}{
		{250000, 20, 1000, 50000},   // 20% of 250k
		{250000, 50, 1000, 125000},  // 50% of 250k
		{10000, 20, 5000, 5000},     // min_tokens floor (2000 < 5000)
		{0, 20, 1000, 1000},         // zero budget — min_tokens floor
		{100000, 100, 1000, 100000}, // 100% share
		{100000, 0, 1000, 1000},     // 0% share — min_tokens floor
		{1, 50, 1000, 1000},         // tiny budget — min_tokens floor (0 < 1000)
		{250000, 10, 1000, 25000},   // 10% of 250k
		{250000, 5, 20000, 20000},   // 5% is 12500, below min 20000
		{1000000, 30, 1000, 300000}, // 30% of 1M
	}
	for _, tt := range tests {
		got := stageAllocation(tt.total, tt.sharePct, tt.minTokens)
		if got != tt.want {
			t.Errorf("stageAllocation(%d, %d, %d) = %d, want %d",
				tt.total, tt.sharePct, tt.minTokens, got, tt.want)
		}
	}
}

// TestStageAllocationInt64 verifies that budget math stays in int64
// and doesn't silently truncate with large values.
func TestStageAllocationInt64(t *testing.T) {
	// Large budget: 10 billion tokens, 20% share
	got := stageAllocation(10000000000, 20, 1000)
	want := int64(2000000000)
	if got != want {
		t.Errorf("stageAllocation(10B, 20, 1000) = %d, want %d", got, want)
	}
}

// TestBudgetRemainingClampNeverNegative ensures the clamp works for
// extreme values that might wrap around in int32.
func TestBudgetRemainingClampNeverNegative(t *testing.T) {
	// Spend much more than budget — should clamp, not underflow
	got := budgetRemaining(0, 9223372036854775807)
	if got != 0 {
		t.Errorf("budgetRemaining(0, MaxInt64) = %d, want 0", got)
	}
}

// TestAllStages verifies the canonical stage ordering.
func TestAllStages(t *testing.T) {
	want := []string{"discover", "design", "build", "ship", "reflect"}
	if len(allStages) != len(want) {
		t.Fatalf("allStages has %d entries, want %d", len(allStages), len(want))
	}
	for i, s := range allStages {
		if s != want[i] {
			t.Errorf("allStages[%d] = %q, want %q", i, s, want[i])
		}
	}
}

// TestPhaseToStageCoversAllPhases verifies every known phase from
// phaseCostEstimate maps to a non-"unknown" stage.
func TestPhaseToStageCoversAllPhases(t *testing.T) {
	knownPhases := []string{
		"brainstorm", "brainstorm-reviewed", "strategized", "planned",
		"plan-reviewed", "executing", "shipping", "reflect", "done",
	}
	for _, phase := range knownPhases {
		stage := phaseToStage(phase)
		if stage == "unknown" {
			t.Errorf("phaseToStage(%q) = %q — expected a known stage", phase, stage)
		}
	}
}

// TestPhaseCostEstimateAllPositive ensures every phase has a positive cost.
func TestPhaseCostEstimateAllPositive(t *testing.T) {
	phases := []string{
		"brainstorm", "brainstorm-reviewed", "strategized", "planned",
		"plan-reviewed", "executing", "shipping", "reflect", "done",
		"unknown", "",
	}
	for _, phase := range phases {
		cost := phaseCostEstimate(phase)
		if cost <= 0 {
			t.Errorf("phaseCostEstimate(%q) = %d, want > 0", phase, cost)
		}
	}
}

// TestPhaseCostEstimateSumsToReasonableTotal checks the total estimated
// sprint cost is in a reasonable range.
func TestPhaseCostEstimateSumsToReasonableTotal(t *testing.T) {
	phases := []string{
		"brainstorm", "brainstorm-reviewed", "strategized", "planned",
		"plan-reviewed", "executing", "shipping", "reflect", "done",
	}
	var total int64
	for _, phase := range phases {
		total += phaseCostEstimate(phase)
	}
	// Full sprint estimate: 30k+15k+25k+35k+50k+150k+100k+10k+5k = 420k
	if total != 420000 {
		t.Errorf("total phase cost estimate = %d, want 420000", total)
	}
}
