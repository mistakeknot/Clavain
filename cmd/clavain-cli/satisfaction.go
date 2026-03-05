package main

import (
	"encoding/json"
	"fmt"
	"math"
	"os"
	"path/filepath"
	"sort"
	"strings"
	"time"

	"github.com/vmihailenco/msgpack/v5"
)

// SatisfactionScore holds the result of scoring a scenario run.
type SatisfactionScore struct {
	BeadID              string             `json:"bead_id" msgpack:"1"`
	ScenarioID          string             `json:"scenario_id" msgpack:"2"`
	OverallScore        float64            `json:"overall_score" msgpack:"3"`
	PerCriterionScores  map[string]float64 `json:"per_criterion_scores" msgpack:"4"`
	JudgeModelVersion   string             `json:"judge_model_version" msgpack:"5"`
	JudgeAgent          string             `json:"judge_agent" msgpack:"6"`
	TrajectoryContextID uint64             `json:"trajectory_context_id" msgpack:"7"`
	SprintOutcome       string             `json:"sprint_outcome,omitempty" msgpack:"8"`
	Holdout             bool               `json:"holdout" msgpack:"9"`
	Timestamp           uint64             `json:"timestamp" msgpack:"10"`
}

// SatisfactionResult aggregates scores across scenarios in a run.
type SatisfactionResult struct {
	RunID              string              `json:"run_id"`
	Scores             []SatisfactionScore `json:"scores"`
	AggregateScore     float64             `json:"aggregate_score"`
	PassCount          int                 `json:"pass_count"`
	FailCount          int                 `json:"fail_count"`
	Threshold          float64             `json:"threshold"`
	ThresholdSource    string              `json:"threshold_source"` // "calibrated", "budget.yml", "default"
}

// SatisfactionCalibration stores the calibrated threshold.
type SatisfactionCalibration struct {
	Threshold    float64 `json:"threshold"`
	SprintCount  int     `json:"sprint_count"`
	Accuracy     float64 `json:"accuracy"`
	CalibratedAt string  `json:"calibrated_at"`
}

const defaultSatisfactionThreshold = 0.7

// cmdScenarioScore scores a scenario run using satisfaction rubrics.
// Usage: scenario-score <run-id> [--summary]
func cmdScenarioScore(args []string) error {
	if len(args) < 1 {
		return fmt.Errorf("usage: scenario-score <run-id> [--summary]")
	}
	runID := args[0]
	summary := false
	for _, a := range args[1:] {
		if a == "--summary" {
			summary = true
		}
	}

	// Load run results
	resultsDir := filepath.Join(scenarioDir(), "satisfaction")
	runPath := filepath.Join(resultsDir, runID+".json")
	data, err := os.ReadFile(runPath)
	if err != nil {
		return fmt.Errorf("scenario-score: cannot read run %s: %w", runID, err)
	}

	var run ScenarioRunResults
	if err := json.Unmarshal(data, &run); err != nil {
		return fmt.Errorf("scenario-score: parse run: %w", err)
	}

	// Load threshold
	threshold, source := loadSatisfactionThreshold()

	// Score each scenario
	result := SatisfactionResult{
		RunID:           runID,
		Threshold:       threshold,
		ThresholdSource: source,
	}

	for _, sr := range run.Scenarios {
		score := scoreScenarioResult(sr, run.SprintID)
		if score.OverallScore >= threshold {
			result.PassCount++
		} else {
			result.FailCount++
		}
		result.Scores = append(result.Scores, score)
	}

	// Compute aggregate
	if len(result.Scores) > 0 {
		var total float64
		for _, s := range result.Scores {
			total += s.OverallScore
		}
		result.AggregateScore = total / float64(len(result.Scores))
	}

	// Record in CXDB
	if cxdbAvailable() && run.SprintID != "" {
		recordSatisfactionToCXDB(run.SprintID, result.Scores)
	}

	// Write results
	outPath := filepath.Join(resultsDir, "satisfaction-"+runID+".json")
	if err := writeScenarioJSON(outPath, result); err != nil {
		return fmt.Errorf("scenario-score: write: %w", err)
	}

	if summary {
		fmt.Printf("Satisfaction: %.2f (threshold: %.2f, source: %s)\n",
			result.AggregateScore, threshold, source)
		fmt.Printf("Pass: %d, Fail: %d, Total: %d\n",
			result.PassCount, result.FailCount, len(result.Scores))
		if result.AggregateScore >= threshold {
			fmt.Println("PASS")
		} else {
			fmt.Println("FAIL")
		}
	} else {
		fmt.Println(outPath)
	}

	return nil
}

// scoreScenarioResult computes a satisfaction score for a scenario result.
// Without LLM judges available, uses pass rate as score.
func scoreScenarioResult(sr ScenarioResult, beadID string) SatisfactionScore {
	score := SatisfactionScore{
		BeadID:             beadID,
		ScenarioID:         sr.ScenarioID,
		PerCriterionScores: make(map[string]float64),
		JudgeModelVersion:  "passrate-v1",
		JudgeAgent:         "builtin",
		Timestamp:          uint64(time.Now().Unix()),
	}

	if sr.TotalSteps > 0 {
		score.OverallScore = float64(sr.PassCount) / float64(sr.TotalSteps)
	}

	// Per-step scores as pseudo-criteria
	for _, step := range sr.Steps {
		val := 0.0
		if step.Passed {
			val = 1.0
		}
		score.PerCriterionScores[step.Action] = val
	}

	return score
}

// loadSatisfactionThreshold returns the threshold and its source.
func loadSatisfactionThreshold() (float64, string) {
	// Stage 4: Try calibrated threshold
	calPath := filepath.Join(scenarioDir(), "..", "satisfaction-calibration.json")
	if data, err := os.ReadFile(calPath); err == nil {
		var cal SatisfactionCalibration
		if json.Unmarshal(data, &cal) == nil && cal.Threshold > 0 {
			return cal.Threshold, "calibrated"
		}
	}

	// Stage 1: Try budget.yml override
	base := os.Getenv("SPRINT_LIB_PROJECT_DIR")
	if base == "" {
		base = "."
	}
	budgetPath := filepath.Join(base, ".clavain", "budget.yml")
	if data, err := os.ReadFile(budgetPath); err == nil {
		// Simple line scan for satisfaction_threshold
		for _, line := range strings.Split(string(data), "\n") {
			line = strings.TrimSpace(line)
			if strings.HasPrefix(line, "satisfaction_threshold:") {
				var t float64
				if _, err := fmt.Sscanf(line, "satisfaction_threshold: %f", &t); err == nil && t > 0 {
					return t, "budget.yml"
				}
			}
		}
	}

	return defaultSatisfactionThreshold, "default"
}

// cmdScenarioCalibrate computes an optimal satisfaction threshold from historical data.
// Usage: scenario-calibrate
func cmdScenarioCalibrate(args []string) error {
	// Collect all satisfaction scores with outcomes
	scores, err := collectHistoricalScores()
	if err != nil {
		return fmt.Errorf("scenario-calibrate: %w", err)
	}

	if len(scores) < 20 {
		fmt.Fprintf(os.Stderr, "scenario-calibrate: only %d sprints (need 20+), using default %.1f\n",
			len(scores), defaultSatisfactionThreshold)
		return nil
	}

	// Find optimal threshold via ROC-like sweep
	threshold, accuracy := findOptimalThreshold(scores)

	cal := SatisfactionCalibration{
		Threshold:    threshold,
		SprintCount:  len(scores),
		Accuracy:     accuracy,
		CalibratedAt: time.Now().Format(time.RFC3339),
	}

	calPath := filepath.Join(scenarioDir(), "..", "satisfaction-calibration.json")
	if err := writeScenarioJSON(calPath, cal); err != nil {
		return fmt.Errorf("scenario-calibrate: write: %w", err)
	}

	fmt.Fprintf(os.Stderr, "scenario-calibrate: threshold=%.3f accuracy=%.3f from %d sprints\n",
		threshold, accuracy, len(scores))
	return nil
}

type historicalScore struct {
	Score   float64
	Success bool // merged = true, reverted/abandoned = false
}

func collectHistoricalScores() ([]historicalScore, error) {
	resultsDir := filepath.Join(scenarioDir(), "satisfaction")
	entries, err := os.ReadDir(resultsDir)
	if err != nil {
		return nil, fmt.Errorf("read satisfaction dir: %w", err)
	}

	var scores []historicalScore
	for _, entry := range entries {
		if !strings.HasPrefix(entry.Name(), "satisfaction-") || !strings.HasSuffix(entry.Name(), ".json") {
			continue
		}
		data, err := os.ReadFile(filepath.Join(resultsDir, entry.Name()))
		if err != nil {
			continue
		}
		var result SatisfactionResult
		if json.Unmarshal(data, &result) != nil {
			continue
		}
		for _, s := range result.Scores {
			if s.SprintOutcome == "" {
				continue
			}
			scores = append(scores, historicalScore{
				Score:   s.OverallScore,
				Success: s.SprintOutcome == "merged",
			})
		}
	}
	return scores, nil
}

// findOptimalThreshold sweeps thresholds to maximize prediction accuracy.
func findOptimalThreshold(scores []historicalScore) (float64, float64) {
	sort.Slice(scores, func(i, j int) bool {
		return scores[i].Score < scores[j].Score
	})

	bestThreshold := defaultSatisfactionThreshold
	bestAccuracy := 0.0

	for t := 0.1; t <= 0.95; t += 0.01 {
		correct := 0
		for _, s := range scores {
			predicted := s.Score >= t
			if predicted == s.Success {
				correct++
			}
		}
		accuracy := float64(correct) / float64(len(scores))
		if accuracy > bestAccuracy {
			bestAccuracy = accuracy
			bestThreshold = math.Round(t*100) / 100
		}
	}

	return bestThreshold, bestAccuracy
}

// recordSatisfactionToCXDB records satisfaction scores as CXDB turns.
func recordSatisfactionToCXDB(beadID string, scores []SatisfactionScore) {
	client, err := cxdbConnect()
	if err != nil {
		return
	}
	ctxID, err := cxdbSprintContext(client, beadID)
	if err != nil {
		return
	}
	for _, s := range scores {
		payload, err := msgpack.Marshal(s)
		if err != nil {
			continue
		}
		_ = cxdbAppendTyped(client, ctxID, "clavain.satisfaction.v1", payload)
	}
}

// satisfactionGateCheck checks if the sprint meets the satisfaction threshold.
// Returns nil if passed, error if failed.
func satisfactionGateCheck(beadID string) error {
	threshold, source := loadSatisfactionThreshold()

	// Find latest satisfaction result for this bead
	resultsDir := filepath.Join(scenarioDir(), "satisfaction")
	entries, err := os.ReadDir(resultsDir)
	if err != nil {
		// No results directory — gate passes (no scenarios configured)
		return nil
	}

	var latestResult *SatisfactionResult
	for _, entry := range entries {
		if !strings.HasPrefix(entry.Name(), "satisfaction-") || !strings.HasSuffix(entry.Name(), ".json") {
			continue
		}
		data, err := os.ReadFile(filepath.Join(resultsDir, entry.Name()))
		if err != nil {
			continue
		}
		var result SatisfactionResult
		if json.Unmarshal(data, &result) != nil {
			continue
		}
		// Check if any scores belong to this bead
		for _, s := range result.Scores {
			if s.BeadID == beadID && s.Holdout {
				latestResult = &result
				break
			}
		}
	}

	if latestResult == nil {
		// No holdout scores for this bead — gate passes
		return nil
	}

	// Check for holdout access violations
	// (would need integration with policy violation tracking)

	if latestResult.AggregateScore < threshold {
		return fmt.Errorf("satisfaction gate failed: %.2f < %.2f (source: %s)",
			latestResult.AggregateScore, threshold, source)
	}

	return nil
}
