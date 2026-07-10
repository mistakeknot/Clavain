package main

import (
	"encoding/json"
	"errors"
	"math"
	"os"
	"path/filepath"
	"testing"
)

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
		{"unknown", 30000},    // default
		{"", 30000},           // default (empty)
		{"garbage", 30000},    // default (unknown phase)
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
		{"garbage", "unknown"},   // default
		{"", "unknown"},          // default (empty)
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
		{250000, 100000, 150000}, // normal
		{250000, 250000, 0},      // exactly spent
		{250000, 300000, 0},      // overspent — clamped to 0
		{0, 0, 0},                // zero budget, zero spent
		{0, 100, 0},              // zero budget, some spent — clamp
		{1000000, 0, 1000000},    // nothing spent
		{1, 1, 0},                // edge: exactly 1
		{100, 99, 1},             // edge: 1 remaining
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

func TestPhasesAfter(t *testing.T) {
	tests := []struct {
		phase string
		want  []string
	}{
		{"brainstorm", []string{"brainstorm-reviewed", "strategized", "planned", "plan-reviewed", "executing", "shipping", "reflect", "done"}},
		{"executing", []string{"shipping", "reflect", "done"}},
		{"reflect", []string{"done"}},
		{"done", nil},          // last phase → nothing remaining
		{"garbage", allPhases}, // unknown → all phases (conservative)
		{"", allPhases},        // empty → all phases (conservative)
	}
	for _, tt := range tests {
		got := phasesAfter(tt.phase)
		if len(got) != len(tt.want) {
			t.Errorf("phasesAfter(%q) returned %d phases, want %d: %v", tt.phase, len(got), len(tt.want), got)
			continue
		}
		for i := range got {
			if got[i] != tt.want[i] {
				t.Errorf("phasesAfter(%q)[%d] = %q, want %q", tt.phase, i, got[i], tt.want[i])
			}
		}
	}
}

func TestTokensToUSD(t *testing.T) {
	tests := []struct {
		model  string
		input  int64
		output int64
		want   float64
	}{
		// Opus: $15/M in + $75/M out
		{"claude-opus-4-6", 1_000_000, 1_000_000, 90.0},
		{"claude-opus-4-6", 100_000, 50_000, 5.25},
		// Sonnet: $3/M in + $15/M out
		{"claude-sonnet-4-6", 1_000_000, 1_000_000, 18.0},
		{"claude-sonnet-4-6", 500_000, 200_000, 4.5},
		// Haiku: $1/M in + $5/M out
		{"claude-haiku-4-5-20251001", 1_000_000, 1_000_000, 6.0},
		// Default (unknown model) → sonnet pricing
		{"unknown-model", 1_000_000, 1_000_000, 18.0},
		// Zero tokens
		{"claude-opus-4-6", 0, 0, 0},
	}
	for _, tt := range tests {
		got := tokensToUSD(tt.model, tt.input, tt.output)
		if math.Abs(got-tt.want) > 0.0001 {
			t.Errorf("tokensToUSD(%q, %d, %d) = %.4f, want %.4f",
				tt.model, tt.input, tt.output, got, tt.want)
		}
	}
}

func TestRemainingEstimateUSD(t *testing.T) {
	// All phases should produce a positive estimate
	allEst := remainingEstimateUSD(allPhases, "claude-sonnet-4-6")
	if allEst <= 0 {
		t.Errorf("remainingEstimateUSD(allPhases) = %.4f, want > 0", allEst)
	}

	// Nil/empty phases should produce 0
	nilEst := remainingEstimateUSD(nil, "claude-sonnet-4-6")
	if nilEst != 0 {
		t.Errorf("remainingEstimateUSD(nil) = %.4f, want 0", nilEst)
	}
	emptyEst := remainingEstimateUSD([]string{}, "claude-sonnet-4-6")
	if emptyEst != 0 {
		t.Errorf("remainingEstimateUSD(empty) = %.4f, want 0", emptyEst)
	}

	// Fewer phases → smaller estimate
	fewerEst := remainingEstimateUSD([]string{"reflect", "done"}, "claude-sonnet-4-6")
	if fewerEst >= allEst {
		t.Errorf("remainingEstimateUSD([reflect,done]) = %.4f, should be < allPhases %.4f", fewerEst, allEst)
	}

	// Opus pricing should produce higher estimates than sonnet
	opusEst := remainingEstimateUSD(allPhases, "claude-opus-4-6")
	if opusEst <= allEst {
		t.Errorf("remainingEstimateUSD(opus) = %.4f, should be > sonnet %.4f", opusEst, allEst)
	}
}

func TestDetectCostAnomaly(t *testing.T) {
	estimates := []CostEstimateEntry{
		{
			Phase:             "planned",
			Timestamp:         "2026-04-27T00:00:00Z",
			EstimatedTotalUSD: 1.25,
		},
	}
	snapshot := CostSnapshot{TotalCostUSD: 2.76}

	got, ok := detectCostAnomaly("sylveste-test", snapshot, estimates, "2026-04-27T01:00:00Z")
	if !ok {
		t.Fatal("detectCostAnomaly returned ok=false, want true")
	}
	if got.BeadID != "sylveste-test" {
		t.Errorf("BeadID = %q, want sylveste-test", got.BeadID)
	}
	if got.EstimateTimestamp != "2026-04-27T00:00:00Z" {
		t.Errorf("EstimateTimestamp = %q", got.EstimateTimestamp)
	}
	if got.Ratio != 2.21 {
		t.Errorf("Ratio = %.2f, want 2.21", got.Ratio)
	}
	if got.Reason != "actual_cost_exceeded_estimate_by_more_than_2x" {
		t.Errorf("Reason = %q", got.Reason)
	}
}

func TestDetectCostAnomalySkipsAtOrBelowThreshold(t *testing.T) {
	estimates := []CostEstimateEntry{{Timestamp: "t1", EstimatedTotalUSD: 1.00}}
	for _, actual := range []float64{0, 1.99, 2.00} {
		_, ok := detectCostAnomaly("sylveste-test", CostSnapshot{TotalCostUSD: actual}, estimates, "now")
		if ok {
			t.Fatalf("detectCostAnomaly(actual=%.2f) returned ok=true, want false", actual)
		}
	}
}

func TestDetectCostAnomalyUsesLatestNonzeroEstimate(t *testing.T) {
	estimates := []CostEstimateEntry{
		{Timestamp: "old", EstimatedTotalUSD: 1.00},
		{Timestamp: "zero", EstimatedTotalUSD: 0},
		{Timestamp: "latest", EstimatedTotalUSD: 3.00},
	}
	got, ok := detectCostAnomaly("sylveste-test", CostSnapshot{TotalCostUSD: 6.30}, estimates, "now")
	if !ok {
		t.Fatal("detectCostAnomaly returned ok=false, want true")
	}
	if got.EstimateTimestamp != "latest" {
		t.Errorf("EstimateTimestamp = %q, want latest", got.EstimateTimestamp)
	}
	if got.Ratio != 2.10 {
		t.Errorf("Ratio = %.2f, want 2.10", got.Ratio)
	}
}

func TestPhaseCostEstimateWithCalibration(t *testing.T) {
	// Create a temp directory with a calibration file
	tmpDir := t.TempDir()
	clavainDir := filepath.Join(tmpDir, ".clavain")
	if err := os.MkdirAll(clavainDir, 0755); err != nil {
		t.Fatal(err)
	}

	cal := PhaseCalibration{
		CalibratedAt: "2026-03-01T00:00:00Z",
		RunCount:     15,
		Phases: map[string]PhaseCalibData{
			"brainstorm": {Runs: 5, InputTokens: 20000, OutputTokens: 10000},
			"executing":  {Runs: 5, InputTokens: 80000, OutputTokens: 40000},
			"reflect":    {Runs: 2, InputTokens: 5000, OutputTokens: 3000}, // < 3 runs
		},
	}
	data, _ := json.Marshal(cal)
	calPath := filepath.Join(clavainDir, "phase-cost-calibration.json")
	if err := os.WriteFile(calPath, data, 0644); err != nil {
		t.Fatal(err)
	}

	// Point calibrationFilePath() at our temp dir
	t.Setenv("SPRINT_LIB_PROJECT_DIR", tmpDir)

	// Calibrated phase with >= 3 runs: should use calibrated value
	got := phaseCostEstimate("brainstorm")
	want := int64(30000) // 20000 + 10000
	if got != want {
		t.Errorf("phaseCostEstimate(brainstorm) with calibration = %d, want %d", got, want)
	}

	got = phaseCostEstimate("executing")
	want = int64(120000) // 80000 + 40000
	if got != want {
		t.Errorf("phaseCostEstimate(executing) with calibration = %d, want %d", got, want)
	}

	// Phase with < 3 runs: should fall back to default
	got = phaseCostEstimate("reflect")
	want = int64(10000) // hardcoded default
	if got != want {
		t.Errorf("phaseCostEstimate(reflect) with <3 runs = %d, want %d (default)", got, want)
	}

	// Phase not in calibration file: should fall back to default
	got = phaseCostEstimate("planned")
	want = int64(35000) // hardcoded default
	if got != want {
		t.Errorf("phaseCostEstimate(planned) not calibrated = %d, want %d (default)", got, want)
	}
}

func TestPhaseCostEstimateFallback(t *testing.T) {
	// Point at a directory with no calibration file
	t.Setenv("SPRINT_LIB_PROJECT_DIR", t.TempDir())

	// All should return hardcoded defaults
	got := phaseCostEstimate("brainstorm")
	if got != 30000 {
		t.Errorf("phaseCostEstimate(brainstorm) without calibration = %d, want 30000", got)
	}
	got = phaseCostEstimate("executing")
	if got != 150000 {
		t.Errorf("phaseCostEstimate(executing) without calibration = %d, want 150000", got)
	}
}

func TestReadCalibrationMalformed(t *testing.T) {
	tmpDir := t.TempDir()
	clavainDir := filepath.Join(tmpDir, ".clavain")
	os.MkdirAll(clavainDir, 0755)

	// Write malformed JSON
	os.WriteFile(filepath.Join(clavainDir, "phase-cost-calibration.json"), []byte("{invalid"), 0644)
	t.Setenv("SPRINT_LIB_PROJECT_DIR", tmpDir)

	got := readCalibration()
	if got != nil {
		t.Errorf("readCalibration() with malformed JSON = %+v, want nil", got)
	}

	// Write valid JSON but empty phases
	os.WriteFile(filepath.Join(clavainDir, "phase-cost-calibration.json"),
		[]byte(`{"calibrated_at":"2026-01-01","run_count":0,"phases":{}}`), 0644)

	got = readCalibration()
	if got != nil {
		t.Errorf("readCalibration() with empty phases = %+v, want nil", got)
	}
}

func TestRemainingEstimateUSDModelAware(t *testing.T) {
	// Create calibration with per-model breakdowns
	tmpDir := t.TempDir()
	clavainDir := filepath.Join(tmpDir, ".clavain")
	os.MkdirAll(clavainDir, 0755)

	cal := PhaseCalibration{
		CalibratedAt: "2026-03-01T00:00:00Z",
		RunCount:     10,
		Phases: map[string]PhaseCalibData{
			"executing": {
				Runs:         5,
				InputTokens:  100000,
				OutputTokens: 50000,
				Models: map[string]ModelCalibData{
					"claude-opus-4-6":   {Runs: 2, InputTokens: 60000, OutputTokens: 30000},
					"claude-sonnet-4-6": {Runs: 3, InputTokens: 40000, OutputTokens: 20000},
				},
			},
		},
	}
	data, _ := json.Marshal(cal)
	os.WriteFile(filepath.Join(clavainDir, "phase-cost-calibration.json"), data, 0644)
	t.Setenv("SPRINT_LIB_PROJECT_DIR", tmpDir)

	// Model-aware estimate for "executing" should use opus+sonnet pricing
	modelAware := remainingEstimateUSD([]string{"executing"}, "claude-sonnet-4-6")

	// Reset to no calibration for comparison
	t.Setenv("SPRINT_LIB_PROJECT_DIR", t.TempDir())
	defaultEst := remainingEstimateUSD([]string{"executing"}, "claude-sonnet-4-6")

	// Model-aware should differ from default (opus is more expensive)
	if modelAware == defaultEst {
		t.Errorf("model-aware estimate (%.4f) should differ from default (%.4f)", modelAware, defaultEst)
	}

	// Model-aware should be > 0
	if modelAware <= 0 {
		t.Errorf("model-aware estimate = %.4f, want > 0", modelAware)
	}

	// Specifically: opus portion (60k in, 30k out) = 60k*15/1M + 30k*75/1M = 0.9 + 2.25 = 3.15
	// Sonnet portion (40k in, 20k out) = 40k*3/1M + 20k*15/1M = 0.12 + 0.30 = 0.42
	// Total = 3.57
	expected := 3.57
	if math.Abs(modelAware-expected) > 0.01 {
		t.Errorf("model-aware estimate = %.4f, want ~%.2f", modelAware, expected)
	}
}

func setupPhaseCalibrationProducer(t *testing.T, body string) string {
	t.Helper()

	root := t.TempDir()
	sourceDir := filepath.Join(root, "Sylveste", "os", "Clavain")
	scriptPath := filepath.Join(root, "Sylveste", "interverse", "interstat", "scripts", "cost-query.sh")
	if err := os.MkdirAll(filepath.Dir(scriptPath), 0o755); err != nil {
		t.Fatalf("mkdir producer: %v", err)
	}
	if err := os.WriteFile(scriptPath, []byte("#!/usr/bin/env bash\nset -u\n"+body), 0o755); err != nil {
		t.Fatalf("write producer: %v", err)
	}

	projectDir := filepath.Join(root, "project")
	if err := os.MkdirAll(projectDir, 0o755); err != nil {
		t.Fatalf("mkdir project: %v", err)
	}
	t.Setenv("CLAUDE_PLUGIN_ROOT", "")
	t.Setenv("CLAVAIN_SOURCE_DIR", sourceDir)
	t.Setenv("SPRINT_LIB_PROJECT_DIR", projectDir)
	return filepath.Join(projectDir, ".clavain", "phase-cost-calibration.json")
}

func TestCalibratePhaseCostsStrictNoDataPreservesArtifact(t *testing.T) {
	calPath := setupPhaseCalibrationProducer(t, `
case "$1" in
  by-phase) printf '%s\n' '[]' ;;
  by-phase-model) printf '%s\n' '[]' ;;
esac
`)
	if err := os.MkdirAll(filepath.Dir(calPath), 0o755); err != nil {
		t.Fatal(err)
	}
	original := []byte(`{"calibrated_at":"keep","run_count":1,"phases":{"executing":{"runs":1}}}`)
	if err := os.WriteFile(calPath, original, 0o644); err != nil {
		t.Fatal(err)
	}

	err := cmdCalibratePhaseCosts([]string{"--auto", "--strict"})
	if !errors.Is(err, ErrNoUsablePhaseData) {
		t.Fatalf("strict empty calibration error = %v, want ErrNoUsablePhaseData", err)
	}
	after, readErr := os.ReadFile(calPath)
	if readErr != nil {
		t.Fatalf("read preserved artifact: %v", readErr)
	}
	if string(after) != string(original) {
		t.Fatalf("strict no-op changed artifact:\n got: %s\nwant: %s", after, original)
	}
}

func TestCalibratePhaseCostsStrictUpdatesArtifact(t *testing.T) {
	calPath := setupPhaseCalibrationProducer(t, `
case "$1" in
  by-phase) printf '%s\n' '[{"phase":"executing","runs":3,"input_tokens":300,"output_tokens":150}]' ;;
  by-phase-model) printf '%s\n' '[{"phase":"executing","model":"sonnet","runs":3,"input_tokens":180,"output_tokens":90}]' ;;
esac
`)

	if err := cmdCalibratePhaseCosts([]string{"--auto", "--strict"}); err != nil {
		t.Fatalf("strict calibration update returned %v", err)
	}
	data, err := os.ReadFile(calPath)
	if err != nil {
		t.Fatalf("read calibration: %v", err)
	}
	var got PhaseCalibration
	if err := json.Unmarshal(data, &got); err != nil {
		t.Fatalf("parse calibration: %v", err)
	}
	phase := got.Phases["executing"]
	if phase.InputTokens != 100 || phase.OutputTokens != 50 {
		t.Fatalf("aggregate averages = %d/%d, want 100/50", phase.InputTokens, phase.OutputTokens)
	}
	model := phase.Models["sonnet"]
	if model.InputTokens != 60 || model.OutputTokens != 30 {
		t.Fatalf("model averages = %d/%d, want 60/30", model.InputTokens, model.OutputTokens)
	}
}

func TestCalibratePhaseCostsStrictFailures(t *testing.T) {
	validAggregate := `[{"phase":"executing","runs":3,"input_tokens":300,"output_tokens":150}]`
	tests := []struct {
		name string
		body string
	}{
		{
			name: "aggregate query",
			body: `
case "$1" in
  by-phase) exit 9 ;;
  by-phase-model) printf '%s\n' '[]' ;;
esac
`,
		},
		{
			name: "aggregate parse",
			body: `
case "$1" in
  by-phase) printf '%s\n' '{not-json' ;;
  by-phase-model) printf '%s\n' '[]' ;;
esac
`,
		},
		{
			name: "model query",
			body: `
case "$1" in
  by-phase) printf '%s\n' '` + validAggregate + `' ;;
  by-phase-model) exit 9 ;;
esac
`,
		},
		{
			name: "model parse",
			body: `
case "$1" in
  by-phase) printf '%s\n' '` + validAggregate + `' ;;
  by-phase-model) printf '%s\n' '{not-json' ;;
esac
`,
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			calPath := setupPhaseCalibrationProducer(t, tt.body)
			err := cmdCalibratePhaseCosts([]string{"--auto", "--strict"})
			if err == nil || errors.Is(err, ErrNoUsablePhaseData) {
				t.Fatalf("strict %s error = %v, want hard failure", tt.name, err)
			}
			if _, statErr := os.Stat(calPath); !errors.Is(statErr, os.ErrNotExist) {
				t.Fatalf("strict %s wrote artifact, stat error = %v", tt.name, statErr)
			}
		})
	}
}

func TestCalibratePhaseCostsStrictMissingProducer(t *testing.T) {
	t.Setenv("CLAUDE_PLUGIN_ROOT", "")
	t.Setenv("CLAVAIN_SOURCE_DIR", "")
	t.Setenv("SPRINT_LIB_PROJECT_DIR", t.TempDir())

	err := cmdCalibratePhaseCosts([]string{"--auto", "--strict"})
	if err == nil || errors.Is(err, ErrNoUsablePhaseData) {
		t.Fatalf("strict missing producer error = %v, want hard failure", err)
	}
}

func TestCalibratePhaseCostsStrictWriteFailure(t *testing.T) {
	calPath := setupPhaseCalibrationProducer(t, `
case "$1" in
  by-phase) printf '%s\n' '[{"phase":"executing","runs":3,"input_tokens":300,"output_tokens":150}]' ;;
  by-phase-model) printf '%s\n' '[]' ;;
esac
`)
	if err := os.WriteFile(filepath.Dir(calPath), []byte("not-a-directory"), 0o644); err != nil {
		t.Fatal(err)
	}

	err := cmdCalibratePhaseCosts([]string{"--auto", "--strict"})
	if err == nil || errors.Is(err, ErrNoUsablePhaseData) {
		t.Fatalf("strict write error = %v, want hard failure", err)
	}
}

func TestCalibratePhaseCostsLegacyRemainsFailOpen(t *testing.T) {
	setupPhaseCalibrationProducer(t, `
case "$1" in
  by-phase) exit 9 ;;
esac
`)

	if err := cmdCalibratePhaseCosts(nil); err != nil {
		t.Fatalf("manual legacy mode returned %v, want fail-open nil", err)
	}
	if err := cmdCalibratePhaseCosts([]string{"--auto"}); err != nil {
		t.Fatalf("auto mode without --strict returned %v, want fail-open nil", err)
	}
}
