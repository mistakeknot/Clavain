package main

import (
	"fmt"
	"os"
	"path/filepath"
	"strconv"

	"gopkg.in/yaml.v3"
)

// review-phase-calibration.yaml is written by interspect's
// _interspect_calibrate_reviews from review_phase_outcome evidence. It maps a
// "<phase>_C<complexity>" key to an action the sprint flow uses to decide
// whether to run, lighten, or skip a ceremonial review (brainstorm/strategy/
// plan) when the historical P0/P1 rate for that phase+complexity is low.
//
// Until this reader landed, the file was written but never read — sprint.md
// claimed it was consulted, but no code did, so every review always ran.

// reviewCalibrationFile is the YAML document interspect writes.
type reviewCalibrationFile struct {
	Calibration map[string]reviewCalibrationEntry `yaml:"calibration"`
}

type reviewCalibrationEntry struct {
	Action       string  `yaml:"action"`
	P0P1Rate     float64 `yaml:"p0p1_rate"`
	TotalReviews int     `yaml:"total_reviews"`
	AvgAgents    float64 `yaml:"avg_agents"`
}

// reviewCalibrationFilePath returns the path to the review calibration file,
// resolved relative to SPRINT_LIB_PROJECT_DIR (same convention as the phase
// cost calibration reader).
func reviewCalibrationFilePath() string {
	projectDir := os.Getenv("SPRINT_LIB_PROJECT_DIR")
	if projectDir == "" {
		projectDir = "."
	}
	return filepath.Join(projectDir, "os", "Clavain", "config", "review-phase-calibration.yaml")
}

// readReviewCalibration loads the calibration file. Returns nil if it is
// absent or invalid — callers treat that as "no calibration, run the review".
func readReviewCalibration() *reviewCalibrationFile {
	data, err := os.ReadFile(reviewCalibrationFilePath())
	if err != nil {
		return nil
	}
	var f reviewCalibrationFile
	if err := yaml.Unmarshal(data, &f); err != nil {
		return nil
	}
	if f.Calibration == nil {
		return nil
	}
	return &f
}

// reviewAction returns the calibrated action for a (phase, complexity) pair.
// It defaults to "full" when there is no calibration entry — the safe choice
// is always to run the review rather than silently skip one. The boolean
// reports whether a real calibration entry was found.
func reviewAction(phase string, complexity int) (string, bool) {
	f := readReviewCalibration()
	if f == nil {
		return "full", false
	}
	key := fmt.Sprintf("%s_C%d", phase, complexity)
	entry, ok := f.Calibration[key]
	if !ok || entry.Action == "" {
		return "full", false
	}
	switch entry.Action {
	case "skip", "lighten", "full":
		return entry.Action, true
	default:
		// Unknown action in the file — fail safe to running the review.
		return "full", false
	}
}

// cmdReviewCalibration prints the calibrated action for a phase+complexity:
//
//	clavain-cli review-calibration <phase> <complexity>
//
// Output is one of: skip | lighten | full. Exit 0 always (absence/parse
// errors yield "full" so the sprint never skips a review on a read failure).
func cmdReviewCalibration(args []string) error {
	if len(args) < 2 {
		return fmt.Errorf("usage: review-calibration <phase> <complexity>")
	}
	phase := args[0]
	complexity, err := strconv.Atoi(args[1])
	if err != nil {
		// A non-numeric complexity is a caller bug, but fail safe to full.
		fmt.Println("full")
		return nil
	}
	action, _ := reviewAction(phase, complexity)
	fmt.Println(action)
	return nil
}
