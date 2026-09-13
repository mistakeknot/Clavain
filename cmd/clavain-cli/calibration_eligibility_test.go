package main

import (
	"math"
	"os"
	"path/filepath"
	"testing"
)

func TestCalibrationModernEligibility(t *testing.T) {
	agent := matchedAgent{id: "fd-quality", agent: FleetAgent{Models: AgentModels{Preferred: "sonnet"}}}
	for _, version := range []int{2, 3} {
		for _, eligible := range []bool{false, true} {
			cal := &InterspectCalibration{SchemaVersion: version, Agents: map[string]AgentCalibration{
				"fd-quality": {RecommendedModel: "haiku", Confidence: .9, EvidenceSessions: 5, PropagationEligible: eligible},
			}}
			got, _ := resolveModel(agent, AgentRole{}, cal, nil)
			want := "sonnet"
			if eligible {
				want = "haiku"
			}
			if got != want {
				t.Errorf("schema %d eligible %v: got %s, want %s", version, eligible, got, want)
			}
		}
	}
}

func TestCalibrationLegacyInMemoryAndSchemaOneRemainUsable(t *testing.T) {
	agent := matchedAgent{id: "fd-quality", agent: FleetAgent{Models: AgentModels{Preferred: "sonnet"}}}
	for _, version := range []int{0, 1} {
		cal := &InterspectCalibration{SchemaVersion: version, Agents: map[string]AgentCalibration{
			"fd-quality": {RecommendedModel: "haiku", Confidence: 0.9, EvidenceSessions: 5},
		}}
		got, _ := resolveModel(agent, AgentRole{}, cal, nil)
		if got != "haiku" {
			t.Errorf("legacy schema %d: got %s, want haiku", version, got)
		}
	}
}

func TestCalibrationIneligiblePhaseFallsBackToEligibleGlobal(t *testing.T) {
	agent := matchedAgent{id: "fd-quality", agent: FleetAgent{Models: AgentModels{Preferred: "sonnet"}}}
	cal := &InterspectCalibration{SchemaVersion: 2, Agents: map[string]AgentCalibration{
		"fd-quality": {RecommendedModel: "opus", Confidence: .9, EvidenceSessions: 30, PropagationEligible: true,
			Phases: map[string]AgentCalibration{"plan": {RecommendedModel: "haiku", Confidence: .9, EvidenceSessions: 5, PropagationEligible: false}}},
	}}
	got, _ := resolveModelForStage("plan", agent, AgentRole{}, cal, nil)
	if got != "opus" {
		t.Fatalf("ineligible phase selected: got %s, want eligible global opus", got)
	}
}

func TestCalibrationSchemaThreePreservesAgentSection(t *testing.T) {
	root := t.TempDir()
	t.Setenv("SPRINT_LIB_PROJECT_DIR", root)
	dir := filepath.Join(root, ".clavain", "interspect")
	if err := os.MkdirAll(dir, 0o755); err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(filepath.Join(dir, "routing-calibration.json"), []byte(`{"schema_version":3,"skills":{},"agents":{"fd-quality":{"recommended_model":"haiku","confidence":0.9,"evidence_sessions":30,"propagation_eligible":true}}}`), 0o600); err != nil {
		t.Fatal(err)
	}
	cal := loadInterspectCalibration()
	if cal == nil || cal.Agents["fd-quality"].RecommendedModel != "haiku" {
		t.Fatal("schema v3 discarded valid agent recommendations")
	}
}

func TestCalibrationLoaderRejectsUnknownSchemaAndWrongNumericTypes(t *testing.T) {
	for name, body := range map[string]string{
		"unknown schema":      `{"schema_version":4,"agents":{}}`,
		"string confidence":   `{"schema_version":2,"agents":{"fd-quality":{"recommended_model":"haiku","confidence":"high","evidence_sessions":30,"propagation_eligible":true}}}`,
		"fractional sessions": `{"schema_version":2,"agents":{"fd-quality":{"recommended_model":"haiku","confidence":0.9,"evidence_sessions":3.5,"propagation_eligible":true}}}`,
		"string eligibility":  `{"schema_version":2,"agents":{"fd-quality":{"recommended_model":"haiku","confidence":0.9,"evidence_sessions":30,"propagation_eligible":"true"}}}`,
	} {
		t.Run(name, func(t *testing.T) {
			root := t.TempDir()
			t.Setenv("SPRINT_LIB_PROJECT_DIR", root)
			dir := filepath.Join(root, ".clavain", "interspect")
			if err := os.MkdirAll(dir, 0o755); err != nil {
				t.Fatal(err)
			}
			if err := os.WriteFile(filepath.Join(dir, "routing-calibration.json"), []byte(body), 0o600); err != nil {
				t.Fatal(err)
			}
			if cal := loadInterspectCalibration(); cal != nil {
				t.Fatalf("invalid calibration loaded: %#v", cal)
			}
		})
	}
}

func TestCalibrationThresholdUsesMaximumOfModernFloorAndCalibratedValue(t *testing.T) {
	agent := matchedAgent{id: "fd-quality", agent: FleetAgent{Models: AgentModels{Preferred: "sonnet"}}}
	for _, tc := range []struct {
		name       string
		confidence float64
		threshold  float64
	}{
		{name: "modern floor", confidence: 0.69, threshold: 0.3},
		{name: "higher calibrated threshold", confidence: 0.75, threshold: 0.8},
	} {
		t.Run(tc.name, func(t *testing.T) {
			cal := &InterspectCalibration{SchemaVersion: 2, Agents: map[string]AgentCalibration{
				"fd-quality": {RecommendedModel: "haiku", Confidence: tc.confidence, EvidenceSessions: 30, PropagationEligible: true},
			}}
			thresholds := &CalibratedThresholds{Agents: map[string]AgentThreshold{
				"fd-quality": {ConfidenceThreshold: tc.threshold},
			}}
			got, _ := resolveModel(agent, AgentRole{}, cal, thresholds)
			if got != "sonnet" {
				t.Fatalf("confidence %v passed effective threshold max(0.7, %v): got %s", tc.confidence, tc.threshold, got)
			}
		})
	}
}

func TestCalibrationRejectsOutOfRangeConfidence(t *testing.T) {
	agent := matchedAgent{id: "fd-quality", agent: FleetAgent{Models: AgentModels{Preferred: "sonnet"}}}
	cal := &InterspectCalibration{SchemaVersion: 2, Agents: map[string]AgentCalibration{
		"fd-quality": {RecommendedModel: "haiku", Confidence: 1.1, EvidenceSessions: 30, PropagationEligible: true},
	}}
	got, _ := resolveModel(agent, AgentRole{}, cal, nil)
	if got != "sonnet" {
		t.Fatalf("out-of-range confidence authorized calibration: got %s", got)
	}
}

func TestCalibrationRejectsNonFiniteConfidence(t *testing.T) {
	agent := matchedAgent{id: "fd-quality", agent: FleetAgent{Models: AgentModels{Preferred: "sonnet"}}}
	cal := &InterspectCalibration{SchemaVersion: 2, Agents: map[string]AgentCalibration{
		"fd-quality": {RecommendedModel: "haiku", Confidence: math.NaN(), EvidenceSessions: 30, PropagationEligible: true},
	}}
	got, _ := resolveModel(agent, AgentRole{}, cal, nil)
	if got != "sonnet" {
		t.Fatalf("non-finite confidence authorized calibration: got %s", got)
	}
}

func TestCalibrationPhaseAliasesAreSymmetricAndExactFirst(t *testing.T) {
	agent := matchedAgent{id: "fd-quality", agent: FleetAgent{Models: AgentModels{Preferred: "sonnet"}}}
	entry := func(model string) AgentCalibration {
		return AgentCalibration{RecommendedModel: model, Confidence: 0.9, EvidenceSessions: 30, PropagationEligible: true}
	}
	cal := &InterspectCalibration{SchemaVersion: 2, Agents: map[string]AgentCalibration{
		"fd-quality": {
			RecommendedModel: "sonnet", Confidence: 0.9, EvidenceSessions: 30, PropagationEligible: true,
			Phases: map[string]AgentCalibration{
				"ship":          entry("haiku"),
				"quality-gates": entry("opus"),
				"plan":          entry("haiku"),
				"build":         entry("opus"),
			},
		},
	}}
	for phase, want := range map[string]string{
		"quality-gates":  "opus",
		"quality_gates":  "haiku",
		"shipping":       "haiku",
		"planning":       "haiku",
		"implementation": "opus",
		"implement":      "opus",
	} {
		got, _ := resolveModelForStage(phase, agent, AgentRole{}, cal, nil)
		if got != want {
			t.Errorf("phase %s: got %s, want %s", phase, got, want)
		}
	}
}
