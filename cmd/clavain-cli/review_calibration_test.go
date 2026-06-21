package main

import (
	"os"
	"path/filepath"
	"testing"
)

// writeReviewCalibration creates os/Clavain/config/review-phase-calibration.yaml
// under a temp project dir and points SPRINT_LIB_PROJECT_DIR at it.
func writeReviewCalibration(t *testing.T, yaml string) {
	t.Helper()
	dir := t.TempDir()
	cfgDir := filepath.Join(dir, "os", "Clavain", "config")
	if err := os.MkdirAll(cfgDir, 0o755); err != nil {
		t.Fatalf("mkdir: %v", err)
	}
	if err := os.WriteFile(filepath.Join(cfgDir, "review-phase-calibration.yaml"), []byte(yaml), 0o644); err != nil {
		t.Fatalf("write: %v", err)
	}
	t.Setenv("SPRINT_LIB_PROJECT_DIR", dir)
}

const sampleReviewCalibration = `calibration:
  brainstorm_C2:
    action: skip
    p0p1_rate: 0.02
    total_reviews: 25
    avg_agents: 4.0
  strategy_C2:
    action: lighten
    p0p1_rate: 0.10
    total_reviews: 22
    avg_agents: 5.0
  plan_C4:
    action: full
    p0p1_rate: 0.30
    total_reviews: 18
    avg_agents: 6.0
`

func TestReviewAction_CalibratedEntries(t *testing.T) {
	writeReviewCalibration(t, sampleReviewCalibration)

	cases := []struct {
		phase      string
		complexity int
		want       string
		wantOK     bool
	}{
		{"brainstorm", 2, "skip", true},
		{"strategy", 2, "lighten", true},
		{"plan", 4, "full", true},
	}
	for _, c := range cases {
		got, ok := reviewAction(c.phase, c.complexity)
		if got != c.want || ok != c.wantOK {
			t.Errorf("reviewAction(%q, %d) = (%q, %v), want (%q, %v)", c.phase, c.complexity, got, ok, c.want, c.wantOK)
		}
	}
}

// A phase+complexity with no entry must fail SAFE to "full" (run the review),
// reporting ok=false so the caller knows it wasn't a real calibration verdict.
func TestReviewAction_NoEntryFailsToFull(t *testing.T) {
	writeReviewCalibration(t, sampleReviewCalibration)

	if got, ok := reviewAction("brainstorm", 5); got != "full" || ok {
		t.Errorf("uncalibrated (brainstorm, C5) = (%q, %v), want (full, false)", got, ok)
	}
	if got, ok := reviewAction("nonsense", 2); got != "full" || ok {
		t.Errorf("unknown phase = (%q, %v), want (full, false)", got, ok)
	}
}

// A missing calibration file must also fail safe to "full" — the common case
// before enough evidence has accrued to generate the file at all.
func TestReviewAction_MissingFileFailsToFull(t *testing.T) {
	t.Setenv("SPRINT_LIB_PROJECT_DIR", t.TempDir()) // no config file written
	if got, ok := reviewAction("brainstorm", 2); got != "full" || ok {
		t.Errorf("missing file = (%q, %v), want (full, false)", got, ok)
	}
}

// An unknown/garbage action value in the file must not be trusted — fail safe.
func TestReviewAction_UnknownActionFailsToFull(t *testing.T) {
	writeReviewCalibration(t, `calibration:
  brainstorm_C2:
    action: explode
    p0p1_rate: 0.01
    total_reviews: 30
    avg_agents: 3.0
`)
	if got, ok := reviewAction("brainstorm", 2); got != "full" || ok {
		t.Errorf("garbage action = (%q, %v), want (full, false)", got, ok)
	}
}

// Malformed YAML must not crash — treated as no calibration.
func TestReviewAction_MalformedYAMLFailsToFull(t *testing.T) {
	writeReviewCalibration(t, "calibration: [this is: not valid: mapping")
	if got, ok := reviewAction("brainstorm", 2); got != "full" || ok {
		t.Errorf("malformed yaml = (%q, %v), want (full, false)", got, ok)
	}
}
