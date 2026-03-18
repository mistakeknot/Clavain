package main

import (
	"encoding/json"
	"os"
	"path/filepath"
	"testing"

	"gopkg.in/yaml.v3"
)

func TestScenarioYAMLRoundtrip(t *testing.T) {
	s := Scenario{
		SchemaVersion: 1,
		ID:            "test-checkout",
		Intent:        "User can complete checkout",
		Mode:          "behavioral",
		Setup:         []string{"App running", "User authenticated"},
		Steps: []ScenarioStep{
			{Action: "Navigate to cart", Expect: "Cart shows 2 items", Type: "llm-judge"},
			{Action: "Submit order", Expect: "exit_code: 0", Type: "shell"},
		},
		Rubric: []RubricItem{
			{Criterion: "Order persisted", Weight: 0.6},
			{Criterion: "Email queued", Weight: 0.4},
		},
		RiskTags: []string{"payment"},
		Holdout:  false,
	}

	data, err := yaml.Marshal(s)
	if err != nil {
		t.Fatalf("marshal: %v", err)
	}

	var decoded Scenario
	if err := yaml.Unmarshal(data, &decoded); err != nil {
		t.Fatalf("unmarshal: %v", err)
	}

	if decoded.ID != "test-checkout" {
		t.Errorf("ID: got %q, want %q", decoded.ID, "test-checkout")
	}
	if len(decoded.Steps) != 2 {
		t.Errorf("Steps: got %d, want 2", len(decoded.Steps))
	}
	if decoded.Steps[1].Type != "shell" {
		t.Errorf("Step[1].Type: got %q, want 'shell'", decoded.Steps[1].Type)
	}
}

func TestValidateScenario_Valid(t *testing.T) {
	s := Scenario{
		SchemaVersion: 1,
		ID:            "valid-scenario",
		Intent:        "Test something",
		Mode:          "static",
		Steps:         []ScenarioStep{{Action: "do thing", Expect: "result", Type: "exact"}},
		Rubric:        []RubricItem{{Criterion: "works", Weight: 1.0}},
	}

	errs := validateScenario(s)
	if len(errs) > 0 {
		t.Errorf("expected no errors, got: %v", errs)
	}
}

func TestValidateScenario_MissingFields(t *testing.T) {
	s := Scenario{
		SchemaVersion: 0,
		Mode:          "invalid",
	}

	errs := validateScenario(s)
	if len(errs) == 0 {
		t.Error("expected validation errors for empty scenario")
	}

	hasError := func(substr string) bool {
		for _, e := range errs {
			if contains(e, substr) {
				return true
			}
		}
		return false
	}

	if !hasError("schema_version") {
		t.Error("expected schema_version error")
	}
	if !hasError("id is required") {
		t.Error("expected id error")
	}
	if !hasError("intent is required") {
		t.Error("expected intent error")
	}
	if !hasError("mode must be") {
		t.Error("expected mode error")
	}
	if !hasError("at least one step") {
		t.Error("expected steps error")
	}
	if !hasError("at least one rubric") {
		t.Error("expected rubric error")
	}
}

func contains(s, substr string) bool {
	return len(s) >= len(substr) && (s == substr || len(s) > 0 && containsSubstr(s, substr))
}

func containsSubstr(s, substr string) bool {
	for i := 0; i <= len(s)-len(substr); i++ {
		if s[i:i+len(substr)] == substr {
			return true
		}
	}
	return false
}

func TestValidateScenario_BadWeights(t *testing.T) {
	s := Scenario{
		SchemaVersion: 1,
		ID:            "bad-weights",
		Intent:        "Test",
		Mode:          "static",
		Steps:         []ScenarioStep{{Action: "a", Expect: "b", Type: "exact"}},
		Rubric: []RubricItem{
			{Criterion: "c1", Weight: 0.3},
			{Criterion: "c2", Weight: 0.3},
		},
	}

	errs := validateScenario(s)
	hasWeightError := false
	for _, e := range errs {
		if containsSubstr(e, "weights must sum") {
			hasWeightError = true
		}
	}
	if !hasWeightError {
		t.Error("expected weight sum error")
	}
}

func TestValidateScenario_BadStepType(t *testing.T) {
	s := Scenario{
		SchemaVersion: 1,
		ID:            "bad-type",
		Intent:        "Test",
		Mode:          "behavioral",
		Steps:         []ScenarioStep{{Action: "a", Expect: "b", Type: "invalid-type"}},
		Rubric:        []RubricItem{{Criterion: "c", Weight: 1.0}},
	}

	errs := validateScenario(s)
	hasTypeError := false
	for _, e := range errs {
		if containsSubstr(e, "must be llm-judge") {
			hasTypeError = true
		}
	}
	if !hasTypeError {
		t.Error("expected step type error")
	}
}

func TestScenarioCreateAndList(t *testing.T) {
	tmpDir := t.TempDir()
	t.Setenv("SPRINT_LIB_PROJECT_DIR", tmpDir)

	// Create a dev scenario
	if err := cmdScenarioCreate([]string{"test-flow"}); err != nil {
		t.Fatalf("scenario-create: %v", err)
	}

	// Verify file exists
	path := filepath.Join(tmpDir, ".clavain", "scenarios", "dev", "test-flow.yaml")
	if _, err := os.Stat(path); os.IsNotExist(err) {
		t.Error("scenario file not created")
	}

	// Create a holdout scenario
	if err := cmdScenarioCreate([]string{"holdout-flow", "--holdout"}); err != nil {
		t.Fatalf("scenario-create holdout: %v", err)
	}

	holdoutPath := filepath.Join(tmpDir, ".clavain", "scenarios", "holdout", "holdout-flow.yaml")
	if _, err := os.Stat(holdoutPath); os.IsNotExist(err) {
		t.Error("holdout scenario file not created")
	}

	// Duplicate should fail
	err := cmdScenarioCreate([]string{"test-flow"})
	if err == nil {
		t.Error("expected error for duplicate scenario")
	}
}

func TestScenarioValidate(t *testing.T) {
	tmpDir := t.TempDir()
	t.Setenv("SPRINT_LIB_PROJECT_DIR", tmpDir)

	// Create a valid scenario file
	dir := filepath.Join(tmpDir, ".clavain", "scenarios", "dev")
	os.MkdirAll(dir, 0755)

	s := Scenario{
		SchemaVersion: 1,
		ID:            "valid",
		Intent:        "Test",
		Mode:          "static",
		Steps:         []ScenarioStep{{Action: "do", Expect: "done", Type: "exact"}},
		Rubric:        []RubricItem{{Criterion: "works", Weight: 1.0}},
	}
	data, _ := yaml.Marshal(s)
	os.WriteFile(filepath.Join(dir, "valid.yaml"), data, 0644)

	if err := cmdScenarioValidate(nil); err != nil {
		t.Errorf("expected validation to pass: %v", err)
	}
}

func TestScenarioValidate_Invalid(t *testing.T) {
	tmpDir := t.TempDir()
	t.Setenv("SPRINT_LIB_PROJECT_DIR", tmpDir)

	dir := filepath.Join(tmpDir, ".clavain", "scenarios", "dev")
	os.MkdirAll(dir, 0755)

	// Write an invalid scenario
	s := Scenario{
		SchemaVersion: 0,
		ID:            "",
	}
	data, _ := yaml.Marshal(s)
	os.WriteFile(filepath.Join(dir, "invalid.yaml"), data, 0644)

	err := cmdScenarioValidate(nil)
	if err == nil {
		t.Error("expected validation to fail")
	}
}

func TestSatisfactionThreshold_Default(t *testing.T) {
	tmpDir := t.TempDir()
	t.Setenv("SPRINT_LIB_PROJECT_DIR", tmpDir)

	threshold, source := loadSatisfactionThreshold()
	if threshold != 0.7 {
		t.Errorf("threshold: got %f, want 0.7", threshold)
	}
	if source != "default" {
		t.Errorf("source: got %q, want 'default'", source)
	}
}

func TestSatisfactionScoring(t *testing.T) {
	sr := ScenarioResult{
		ScenarioID: "test",
		Intent:     "test intent",
		Mode:       "static",
		Steps: []StepResult{
			{Action: "a", Passed: true},
			{Action: "b", Passed: false},
			{Action: "c", Passed: true},
		},
		PassCount:  2,
		TotalSteps: 3,
	}

	score := scoreScenarioResult(sr, "iv-test")
	if score.OverallScore < 0.66 || score.OverallScore > 0.67 {
		t.Errorf("score: got %f, want ~0.667", score.OverallScore)
	}
	if score.ScenarioID != "test" {
		t.Errorf("scenario_id: got %q, want 'test'", score.ScenarioID)
	}
}

func TestFindOptimalThreshold(t *testing.T) {
	scores := []historicalScore{
		{Score: 0.9, Success: true},
		{Score: 0.8, Success: true},
		{Score: 0.7, Success: true},
		{Score: 0.6, Success: false},
		{Score: 0.5, Success: false},
		{Score: 0.4, Success: false},
		{Score: 0.85, Success: true},
		{Score: 0.75, Success: true},
		{Score: 0.65, Success: false},
		{Score: 0.55, Success: false},
		{Score: 0.95, Success: true},
		{Score: 0.45, Success: false},
		{Score: 0.35, Success: false},
		{Score: 0.82, Success: true},
		{Score: 0.72, Success: true},
		{Score: 0.62, Success: false},
		{Score: 0.52, Success: false},
		{Score: 0.42, Success: false},
		{Score: 0.88, Success: true},
		{Score: 0.78, Success: true},
	}

	threshold, accuracy := findOptimalThreshold(scores)
	if threshold < 0.65 || threshold > 0.75 {
		t.Errorf("threshold: got %f, expected ~0.70", threshold)
	}
	if accuracy < 0.8 {
		t.Errorf("accuracy: got %f, expected >0.8", accuracy)
	}
}

func TestSatisfactionGateCheck_NoScenarios(t *testing.T) {
	tmpDir := t.TempDir()
	t.Setenv("SPRINT_LIB_PROJECT_DIR", tmpDir)

	// With no scenarios, gate should pass
	err := satisfactionGateCheck("iv-test")
	if err != nil {
		t.Errorf("expected gate to pass with no scenarios: %v", err)
	}
}

func TestSatisfactionGateCheck_Fail(t *testing.T) {
	tmpDir := t.TempDir()
	t.Setenv("SPRINT_LIB_PROJECT_DIR", tmpDir)

	// Create a satisfaction result with low score
	dir := filepath.Join(tmpDir, ".clavain", "scenarios", "satisfaction")
	os.MkdirAll(dir, 0755)

	result := SatisfactionResult{
		RunID: "run-1",
		Scores: []SatisfactionScore{
			{
				BeadID:       "iv-test",
				ScenarioID:   "s1",
				OverallScore: 0.3,
				Holdout:      true,
			},
		},
		AggregateScore: 0.3,
		Threshold:      0.7,
	}

	data, _ := json.MarshalIndent(result, "", "  ")
	os.WriteFile(filepath.Join(dir, "satisfaction-run-1.json"), data, 0644)

	err := satisfactionGateCheck("iv-test")
	if err == nil {
		t.Error("expected gate to fail with score 0.3 < threshold 0.7")
	}
}

// BenchmarkScoreScenarioResult benchmarks the pure scoring computation.
func BenchmarkScoreScenarioResult(b *testing.B) {
	sr := ScenarioResult{
		ScenarioID: "bench-checkout",
		Intent:     "User can complete checkout",
		Mode:       "behavioral",
		Steps: []StepResult{
			{Action: "Navigate to cart", Expected: "Cart shows items", Passed: true, Type: "llm-judge"},
			{Action: "Submit order", Expected: "exit_code: 0", Passed: true, Type: "shell"},
			{Action: "Verify email", Expected: "Email sent", Passed: false, Type: "llm-judge"},
			{Action: "Check inventory", Expected: "Stock decremented", Passed: true, Type: "shell"},
			{Action: "Validate receipt", Expected: "PDF generated", Passed: true, Type: "llm-judge"},
		},
		PassCount:  4,
		TotalSteps: 5,
	}
	b.ResetTimer()
	for i := 0; i < b.N; i++ {
		_ = scoreScenarioResult(sr, "bench-bead")
	}
}
