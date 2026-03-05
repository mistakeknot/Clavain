package main

import (
	"encoding/json"
	"fmt"
	"os"
	"path/filepath"
	"strings"
	"time"

	"gopkg.in/yaml.v3"
)

// Scenario represents a v1 scenario YAML file.
type Scenario struct {
	SchemaVersion int            `yaml:"schema_version" json:"schema_version"`
	ID            string         `yaml:"id" json:"id"`
	Intent        string         `yaml:"intent" json:"intent"`
	Mode          string         `yaml:"mode" json:"mode"` // "static" or "behavioral"
	Setup         []string       `yaml:"setup,omitempty" json:"setup,omitempty"`
	Steps         []ScenarioStep `yaml:"steps" json:"steps"`
	Rubric        []RubricItem   `yaml:"rubric" json:"rubric"`
	RiskTags      []string       `yaml:"risk_tags,omitempty" json:"risk_tags,omitempty"`
	Holdout       bool           `yaml:"holdout" json:"holdout"`
}

// ScenarioStep is a single step in a scenario.
type ScenarioStep struct {
	Action string `yaml:"action" json:"action"`
	Expect string `yaml:"expect" json:"expect"`
	Type   string `yaml:"type" json:"type"` // "llm-judge" | "exact" | "regex" | "shell"
}

// RubricItem is a criterion with weight for satisfaction scoring.
type RubricItem struct {
	Criterion string  `yaml:"criterion" json:"criterion"`
	Weight    float64 `yaml:"weight" json:"weight"`
}

// scenarioDir returns the base scenarios directory, creating it if needed.
func scenarioDir() string {
	base := os.Getenv("SPRINT_LIB_PROJECT_DIR")
	if base == "" {
		base = "."
	}
	dir := filepath.Join(base, ".clavain", "scenarios")
	os.MkdirAll(dir, 0755)
	return dir
}

// scenarioSubDir returns a subdirectory under .clavain/scenarios/, creating it.
func scenarioSubDir(sub string) string {
	dir := filepath.Join(scenarioDir(), sub)
	os.MkdirAll(dir, 0755)
	return dir
}

// cmdScenarioCreate scaffolds a new scenario YAML file.
// Usage: scenario-create <name> [--holdout]
func cmdScenarioCreate(args []string) error {
	if len(args) < 1 {
		return fmt.Errorf("usage: scenario-create <name> [--holdout]")
	}

	name := args[0]
	holdout := false
	for _, a := range args[1:] {
		if a == "--holdout" {
			holdout = true
		}
	}

	subDir := "dev"
	if holdout {
		subDir = "holdout"
	}

	dir := scenarioSubDir(subDir)
	filename := filepath.Join(dir, name+".yaml")

	if _, err := os.Stat(filename); err == nil {
		return fmt.Errorf("scenario already exists: %s", filename)
	}

	scenario := Scenario{
		SchemaVersion: 1,
		ID:            name,
		Intent:        "TODO: describe what this scenario tests",
		Mode:          "behavioral",
		Setup:         []string{"TODO: describe preconditions"},
		Steps: []ScenarioStep{
			{
				Action: "TODO: describe agent action",
				Expect: "TODO: describe expected outcome",
				Type:   "llm-judge",
			},
		},
		Rubric: []RubricItem{
			{
				Criterion: "TODO: evaluation criterion",
				Weight:    1.0,
			},
		},
		Holdout: holdout,
	}

	data, err := yaml.Marshal(scenario)
	if err != nil {
		return fmt.Errorf("scenario-create: marshal: %w", err)
	}

	if err := os.WriteFile(filename, data, 0644); err != nil {
		return fmt.Errorf("scenario-create: write: %w", err)
	}

	fmt.Println(filename)
	return nil
}

// cmdScenarioList lists scenarios with metadata.
// Usage: scenario-list [--holdout] [--dev]
func cmdScenarioList(args []string) error {
	showDev := true
	showHoldout := true

	for _, a := range args {
		switch a {
		case "--dev":
			showHoldout = false
		case "--holdout":
			showDev = false
		}
	}

	base := scenarioDir()
	var scenarios []Scenario

	if showDev {
		devScenarios, _ := loadScenariosFromDir(filepath.Join(base, "dev"))
		scenarios = append(scenarios, devScenarios...)
	}
	if showHoldout {
		holdoutScenarios, _ := loadScenariosFromDir(filepath.Join(base, "holdout"))
		scenarios = append(scenarios, holdoutScenarios...)
	}

	if len(scenarios) == 0 {
		fmt.Fprintln(os.Stderr, "No scenarios found.")
		return nil
	}

	for _, s := range scenarios {
		source := "dev"
		if s.Holdout {
			source = "holdout"
		}
		tags := ""
		if len(s.RiskTags) > 0 {
			tags = " [" + strings.Join(s.RiskTags, ", ") + "]"
		}
		fmt.Printf("%-30s %-12s %-10s %d steps%s  %s\n",
			s.ID, source, s.Mode, len(s.Steps), tags, s.Intent)
	}
	return nil
}

// cmdScenarioValidate validates all scenarios against the v1 schema.
// Usage: scenario-validate
func cmdScenarioValidate(args []string) error {
	base := scenarioDir()
	dirs := []string{
		filepath.Join(base, "dev"),
		filepath.Join(base, "holdout"),
	}

	var errors []string
	count := 0

	for _, dir := range dirs {
		scenarios, loadErrors := loadScenariosFromDirWithErrors(dir)
		errors = append(errors, loadErrors...)
		for _, s := range scenarios {
			count++
			errs := validateScenario(s)
			for _, e := range errs {
				errors = append(errors, fmt.Sprintf("%s: %s", s.ID, e))
			}
		}
	}

	if len(errors) > 0 {
		for _, e := range errors {
			fmt.Fprintf(os.Stderr, "ERROR: %s\n", e)
		}
		return fmt.Errorf("scenario-validate: %d errors in %d scenarios", len(errors), count)
	}

	fmt.Fprintf(os.Stderr, "scenario-validate: %d scenarios OK\n", count)
	return nil
}

// validateScenario checks a scenario against v1 schema rules.
func validateScenario(s Scenario) []string {
	var errs []string

	if s.SchemaVersion != 1 {
		errs = append(errs, fmt.Sprintf("schema_version must be 1, got %d", s.SchemaVersion))
	}
	if s.ID == "" {
		errs = append(errs, "id is required")
	}
	if s.Intent == "" {
		errs = append(errs, "intent is required")
	}
	if s.Mode != "static" && s.Mode != "behavioral" {
		errs = append(errs, fmt.Sprintf("mode must be 'static' or 'behavioral', got %q", s.Mode))
	}
	if len(s.Steps) == 0 {
		errs = append(errs, "at least one step is required")
	}
	for i, step := range s.Steps {
		if step.Action == "" {
			errs = append(errs, fmt.Sprintf("step[%d].action is required", i))
		}
		if step.Expect == "" {
			errs = append(errs, fmt.Sprintf("step[%d].expect is required", i))
		}
		validTypes := map[string]bool{"llm-judge": true, "exact": true, "regex": true, "shell": true}
		if !validTypes[step.Type] {
			errs = append(errs, fmt.Sprintf("step[%d].type must be llm-judge|exact|regex|shell, got %q", i, step.Type))
		}
	}
	if len(s.Rubric) == 0 {
		errs = append(errs, "at least one rubric criterion is required")
	}
	var totalWeight float64
	for i, r := range s.Rubric {
		if r.Criterion == "" {
			errs = append(errs, fmt.Sprintf("rubric[%d].criterion is required", i))
		}
		if r.Weight <= 0 || r.Weight > 1.0 {
			errs = append(errs, fmt.Sprintf("rubric[%d].weight must be >0 and <=1.0, got %f", i, r.Weight))
		}
		totalWeight += r.Weight
	}
	if len(s.Rubric) > 0 && (totalWeight < 0.99 || totalWeight > 1.01) {
		errs = append(errs, fmt.Sprintf("rubric weights must sum to 1.0, got %f", totalWeight))
	}

	return errs
}

// loadScenariosFromDir loads all .yaml files from a directory.
func loadScenariosFromDir(dir string) ([]Scenario, error) {
	scenarios, _ := loadScenariosFromDirWithErrors(dir)
	return scenarios, nil
}

func loadScenariosFromDirWithErrors(dir string) ([]Scenario, []string) {
	var scenarios []Scenario
	var errors []string

	entries, err := os.ReadDir(dir)
	if err != nil {
		return nil, nil // Directory doesn't exist — not an error
	}

	for _, entry := range entries {
		if entry.IsDir() || (!strings.HasSuffix(entry.Name(), ".yaml") && !strings.HasSuffix(entry.Name(), ".yml")) {
			continue
		}
		path := filepath.Join(dir, entry.Name())
		data, err := os.ReadFile(path)
		if err != nil {
			errors = append(errors, fmt.Sprintf("%s: read error: %v", entry.Name(), err))
			continue
		}
		var s Scenario
		if err := yaml.Unmarshal(data, &s); err != nil {
			errors = append(errors, fmt.Sprintf("%s: parse error: %v", entry.Name(), err))
			continue
		}
		scenarios = append(scenarios, s)
	}
	return scenarios, errors
}

// cmdScenarioRun executes scenarios against the codebase.
// Usage: scenario-run <pattern> [--sprint=<id>]
func cmdScenarioRun(args []string) error {
	if len(args) < 1 {
		return fmt.Errorf("usage: scenario-run <pattern> [--sprint=<id>]")
	}
	pattern := args[0]
	sprintID := ""
	for _, a := range args[1:] {
		if strings.HasPrefix(a, "--sprint=") {
			sprintID = strings.TrimPrefix(a, "--sprint=")
		}
	}

	// Find matching scenarios
	base := scenarioDir()
	var matched []Scenario
	for _, sub := range []string{"dev", "holdout"} {
		scenarios, _ := loadScenariosFromDir(filepath.Join(base, sub))
		for _, s := range scenarios {
			match, _ := filepath.Match(pattern, s.ID)
			if match || strings.Contains(s.ID, pattern) {
				matched = append(matched, s)
			}
		}
	}

	if len(matched) == 0 {
		return fmt.Errorf("scenario-run: no scenarios matching %q", pattern)
	}

	fmt.Fprintf(os.Stderr, "scenario-run: %d scenarios matched\n", len(matched))

	// Record in CXDB if available
	var ctxID uint64
	if cxdbAvailable() && sprintID != "" {
		c, err := cxdbConnect()
		if err == nil {
			ctxID, _ = cxdbSprintContext(c, sprintID)
		}
	}
	_ = ctxID

	// Execute each scenario
	results := ScenarioRunResults{
		SprintID:  sprintID,
		Scenarios: make([]ScenarioResult, 0, len(matched)),
	}

	for _, s := range matched {
		result := executeScenario(s)
		results.Scenarios = append(results.Scenarios, result)
		fmt.Fprintf(os.Stderr, "  %s: %d/%d steps passed\n", s.ID, result.PassCount, len(s.Steps))
	}

	// Write results
	resultsDir := scenarioSubDir("satisfaction")
	runID := fmt.Sprintf("run-%d", results.Timestamp())
	resultsPath := filepath.Join(resultsDir, runID+".json")
	if err := writeScenarioJSON(resultsPath, results); err != nil {
		return fmt.Errorf("scenario-run: write results: %w", err)
	}

	fmt.Println(resultsPath)
	return nil
}

// writeScenarioJSON writes a value as indented JSON to a file.
func writeScenarioJSON(path string, v any) error {
	data, err := json.MarshalIndent(v, "", "  ")
	if err != nil {
		return err
	}
	return os.WriteFile(path, data, 0644)
}

// ScenarioRunResults holds results from a scenario run.
type ScenarioRunResults struct {
	SprintID  string           `json:"sprint_id,omitempty"`
	Scenarios []ScenarioResult `json:"scenarios"`
}

func (r ScenarioRunResults) Timestamp() int64 {
	return time.Now().Unix()
}

// ScenarioResult holds the result of executing a single scenario.
type ScenarioResult struct {
	ScenarioID string       `json:"scenario_id"`
	Intent     string       `json:"intent"`
	Mode       string       `json:"mode"`
	Steps      []StepResult `json:"steps"`
	PassCount  int          `json:"pass_count"`
	TotalSteps int          `json:"total_steps"`
}

// StepResult holds the result of a single scenario step.
type StepResult struct {
	Action   string `json:"action"`
	Expected string `json:"expected"`
	Actual   string `json:"actual,omitempty"`
	Type     string `json:"type"`
	Passed   bool   `json:"passed"`
	Error    string `json:"error,omitempty"`
}

// executeScenario runs a single scenario's steps.
// Currently implements exact, regex, and shell types.
// LLM-judge type requires agent dispatch (stubbed for now).
func executeScenario(s Scenario) ScenarioResult {
	result := ScenarioResult{
		ScenarioID: s.ID,
		Intent:     s.Intent,
		Mode:       s.Mode,
		TotalSteps: len(s.Steps),
	}

	for _, step := range s.Steps {
		sr := StepResult{
			Action:   step.Action,
			Expected: step.Expect,
			Type:     step.Type,
		}

		switch step.Type {
		case "shell":
			out, err := runCommandExec("sh", "-c", step.Action)
			sr.Actual = strings.TrimSpace(string(out))
			if err != nil {
				sr.Error = err.Error()
				sr.Passed = false
			} else {
				sr.Passed = strings.Contains(sr.Actual, step.Expect) || sr.Actual == step.Expect
			}
		case "exact":
			// Exact match requires agent to produce output matching expect
			sr.Passed = false
			sr.Error = "exact type requires agent dispatch (not yet implemented)"
		case "regex":
			sr.Passed = false
			sr.Error = "regex type requires agent dispatch (not yet implemented)"
		case "llm-judge":
			sr.Passed = false
			sr.Error = "llm-judge type requires agent dispatch (not yet implemented)"
		default:
			sr.Error = fmt.Sprintf("unknown step type: %s", step.Type)
		}

		if sr.Passed {
			result.PassCount++
		}
		result.Steps = append(result.Steps, sr)
	}

	return result
}
