package main

import (
	"encoding/json"
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

func TestCalibrationSchemaZeroInMemoryCompatibilityOnly(t *testing.T) {
	agent := matchedAgent{id: "fd-quality", agent: FleetAgent{Models: AgentModels{Preferred: "sonnet"}}}
	cal := &InterspectCalibration{SchemaVersion: 0, Agents: map[string]AgentCalibration{
		"fd-quality": {RecommendedModel: "haiku", Confidence: 0.9, EvidenceSessions: 5},
	}}
	got, _ := resolveModel(agent, AgentRole{}, cal, nil)
	if got != "haiku" {
		t.Errorf("in-memory schema 0: got %s, want haiku", got)
	}
}

func TestCalibrationSchemaOneNeverAuthorizesSelection(t *testing.T) {
	agent := matchedAgent{id: "fd-quality", agent: FleetAgent{Models: AgentModels{Preferred: "sonnet"}}}
	cal := &InterspectCalibration{SchemaVersion: 1, Agents: map[string]AgentCalibration{
		"fd-quality": {RecommendedModel: "haiku", Confidence: 0.9, EvidenceSessions: 5},
	}}
	got, source := resolveModel(agent, AgentRole{}, cal, nil)
	if got != "sonnet" || source == "interspect_calibration" {
		t.Fatalf("schema 1 authorized selection: got %s/%s, want static sonnet", got, source)
	}
}

type calibrationConsumerCase struct {
	Name          string `json:"name"`
	Mode          string `json:"mode"`
	Phase         string `json:"phase"`
	Body          string `json:"body"`
	ExpectedModel string `json:"expected_model"`
}

func loadCalibrationConsumerCases(t *testing.T) []calibrationConsumerCase {
	t.Helper()
	data, err := os.ReadFile(filepath.Join("..", "..", "tests", "fixtures", "routing-calibration-consumer-cases.json"))
	if err != nil {
		t.Fatal(err)
	}
	var cases []calibrationConsumerCase
	if err := json.Unmarshal(data, &cases); err != nil {
		t.Fatal(err)
	}
	return cases
}

func TestCalibrationConsumerGoldenCases(t *testing.T) {
	for _, tc := range loadCalibrationConsumerCases(t) {
		t.Run(tc.Name, func(t *testing.T) {
			root := t.TempDir()
			t.Setenv("SPRINT_LIB_PROJECT_DIR", root)
			t.Setenv("INTERSPECT_ROUTING_MODE", tc.Mode)
			dir := filepath.Join(root, ".clavain", "interspect")
			if err := os.MkdirAll(dir, 0o755); err != nil {
				t.Fatal(err)
			}
			if err := os.WriteFile(filepath.Join(dir, "routing-calibration.json"), []byte(tc.Body), 0o600); err != nil {
				t.Fatal(err)
			}
			cal := loadInterspectCalibration()
			agent := matchedAgent{id: "fd-quality", agent: FleetAgent{Models: AgentModels{Preferred: "sonnet"}}}
			got, _ := resolveModelForStage(tc.Phase, agent, AgentRole{}, cal, nil)
			if got != tc.ExpectedModel {
				t.Fatalf("model = %q, want %q", got, tc.ExpectedModel)
			}
		})
	}
}

func TestComposeCalibrationModesAndEnvironmentPrecedence(t *testing.T) {
	for _, tc := range []struct {
		name        string
		policyMode  string
		envMode     *string
		wantModel   string
		wantWarning string
	}{
		{name: "off", policyMode: "off", wantModel: "sonnet"},
		{name: "shadow", policyMode: "shadow", wantModel: "sonnet", wantWarning: "calibration_shadow:fd-quality:sonnet->haiku"},
		{name: "enforce", policyMode: "enforce", wantModel: "haiku"},
		{name: "invalid", policyMode: "invalid", wantModel: "sonnet", wantWarning: "invalid_calibration_mode:invalid"},
		{name: "environment override", policyMode: "off", envMode: stringTestPointer("enforce"), wantModel: "haiku"},
	} {
		t.Run(tc.name, func(t *testing.T) {
			root := t.TempDir()
			t.Setenv("SPRINT_LIB_PROJECT_DIR", root)
			if tc.envMode == nil {
				previous, existed := os.LookupEnv("INTERSPECT_ROUTING_MODE")
				if err := os.Unsetenv("INTERSPECT_ROUTING_MODE"); err != nil {
					t.Fatal(err)
				}
				t.Cleanup(func() {
					if existed {
						_ = os.Setenv("INTERSPECT_ROUTING_MODE", previous)
					} else {
						_ = os.Unsetenv("INTERSPECT_ROUTING_MODE")
					}
				})
			} else {
				t.Setenv("INTERSPECT_ROUTING_MODE", *tc.envMode)
			}
			dir := filepath.Join(root, ".clavain", "interspect")
			if err := os.MkdirAll(dir, 0o755); err != nil {
				t.Fatal(err)
			}
			body := `{"schema_version":2,"agents":{"fd-quality":{"recommended_model":"haiku","confidence":0.9,"evidence_sessions":30,"propagation_eligible":true}}}`
			if err := os.WriteFile(filepath.Join(dir, "routing-calibration.json"), []byte(body), 0o600); err != nil {
				t.Fatal(err)
			}
			configPath := filepath.Join(root, "routing.yaml")
			if err := os.WriteFile(configPath, []byte("calibration:\n  mode: "+tc.policyMode+"\n"), 0o600); err != nil {
				t.Fatal(err)
			}
			t.Setenv("CLAVAIN_ROUTING_CONFIG", configPath)
			cal := loadInterspectCalibration()
			routing := loadRoutingConfig()
			fleet := &FleetRegistry{Agents: map[string]FleetAgent{
				"fd-quality": {Roles: []string{"fd-quality"}, Models: AgentModels{Preferred: "sonnet"}},
			}}
			stage := StageSpec{Agents: StageAgents{Required: []AgentRole{{Role: "fd-quality"}}}}
			plan := composePlanWithRouting("plan", "", 0, "", stage, fleet, cal, nil, nil, routing)
			if got := plan.Agents[0].Model; got != tc.wantModel {
				t.Fatalf("model = %q, want %q", got, tc.wantModel)
			}
			if tc.wantWarning != "" && !containsCalibrationWarning(plan.Warnings, tc.wantWarning) {
				t.Fatalf("warnings = %v, want %q", plan.Warnings, tc.wantWarning)
			}
		})
	}
}

func TestComposeSchemaOneEmitsDiagnosticWithoutAuthority(t *testing.T) {
	cal := &InterspectCalibration{SchemaVersion: 1, Agents: map[string]AgentCalibration{
		"fd-quality": {RecommendedModel: "haiku", Confidence: 0.9, EvidenceSessions: 30},
	}}
	fleet := &FleetRegistry{Agents: map[string]FleetAgent{
		"fd-quality": {Roles: []string{"fd-quality"}, Models: AgentModels{Preferred: "sonnet"}},
	}}
	stage := StageSpec{Agents: StageAgents{Required: []AgentRole{{Role: "fd-quality"}}}}
	plan := composePlan("plan", "", 0, stage, fleet, cal, nil, nil)
	if got := plan.Agents[0]; got.Model != "sonnet" || got.ModelSource == "interspect_calibration" {
		t.Fatalf("schema 1 model/source = %s/%s, want static sonnet", got.Model, got.ModelSource)
	}
	want := "calibration_diagnostic:schema1:fd-quality:sonnet->haiku"
	if !containsCalibrationWarning(plan.Warnings, want) {
		t.Fatalf("warnings = %v, want %q", plan.Warnings, want)
	}
}

func stringTestPointer(value string) *string { return &value }

func containsCalibrationWarning(values []string, want string) bool {
	for _, value := range values {
		if value == want {
			return true
		}
	}
	return false
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

func TestCalibrationLoaderRejectsUnknownSchemaAndWrongFieldTypes(t *testing.T) {
	for name, body := range map[string]string{
		"unknown schema":     `{"schema_version":4,"agents":{}}`,
		"string confidence":  `{"schema_version":2,"agents":{"fd-quality":{"recommended_model":"haiku","confidence":"high","evidence_sessions":30,"propagation_eligible":true}}}`,
		"string eligibility": `{"schema_version":2,"agents":{"fd-quality":{"recommended_model":"haiku","confidence":0.9,"evidence_sessions":30,"propagation_eligible":"true"}}}`,
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

func TestExactCalibrationRejectsInvalidThresholdAndAnonymousAgent(t *testing.T) {
	cal, err := parseInterspectCalibration([]byte(`{"schema_version":2,"agents":{"":{"recommended_model":"haiku","confidence":0.9,"evidence_sessions":30,"propagation_eligible":true},"fd-quality":{"recommended_model":"haiku","confidence":0.9,"evidence_sessions":30,"propagation_eligible":true}}}`))
	if err != nil {
		t.Fatal(err)
	}
	for _, agent := range []string{"", "plugin:"} {
		if _, ok := exactCalibrationCandidate(cal, agent, "", 0.7); ok {
			t.Errorf("anonymous agent %q authorized calibration", agent)
		}
	}
	for _, threshold := range []float64{math.NaN(), math.Inf(1), math.Inf(-1)} {
		if _, ok := exactCalibrationCandidate(cal, "fd-quality", "", threshold); ok {
			t.Errorf("invalid threshold %v authorized calibration", threshold)
		}
	}
}

func TestCalibrationNamespacedSafetyFloor(t *testing.T) {
	t.Setenv("INTERSPECT_ROUTING_MODE", "enforce")
	cal, err := parseInterspectCalibration([]byte(`{"schema_version":2,"agents":{"fd-safety":{"recommended_model":"haiku","confidence":0.9,"evidence_sessions":30,"propagation_eligible":true}}}`))
	if err != nil {
		t.Fatal(err)
	}
	agent := matchedAgent{id: "interflux:fd-safety", agent: FleetAgent{Models: AgentModels{Preferred: "sonnet"}}}
	model, _ := resolveModelForStage("ship", agent, AgentRole{}, cal, nil)
	if model != "sonnet" {
		t.Fatalf("namespaced safety floor bypassed: %s", model)
	}
	model, _ = applySafetyFloor(agent.id, "haiku", "complexity")
	if model != "sonnet" {
		t.Fatalf("complexity safety floor bypassed: %s", model)
	}
}
