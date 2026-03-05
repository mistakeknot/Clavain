package main

import (
	"os"
	"path/filepath"
	"testing"

	"gopkg.in/yaml.v3"
)

func TestPhaseTierFromComposePlans(t *testing.T) {
	plans := []ComposePlan{
		{
			Stage:  "discover",
			Budget: 100000,
			Agents: []PlanAgent{
				{AgentID: "brainstorm-facilitator", Model: "sonnet", Role: "brainstorm-facilitator", Required: true},
			},
		},
		{
			Stage:  "build",
			Budget: 400000,
			Agents: []PlanAgent{
				{AgentID: "implementer", Model: "opus", Role: "implementer", Required: true},
			},
		},
	}

	tests := []struct {
		phase      string
		wantModel  string
		wantBudget int64
		wantFound  bool
	}{
		{"brainstorm", "sonnet", 100000, true},
		{"executing", "opus", 400000, true},
		{"nonexistent", "", 0, false},
		{"done", "", 0, false},
	}

	for _, tt := range tests {
		t.Run(tt.phase, func(t *testing.T) {
			model, budget, found := phaseTierFromPlans(plans, tt.phase)
			if found != tt.wantFound {
				t.Fatalf("phaseTierFromPlans(%q) found=%v, want %v", tt.phase, found, tt.wantFound)
			}
			if found {
				if model != tt.wantModel {
					t.Errorf("model = %q, want %q", model, tt.wantModel)
				}
				if budget != tt.wantBudget {
					t.Errorf("budget = %d, want %d", budget, tt.wantBudget)
				}
			}
		})
	}
}

func TestPhaseTierFallbackModel(t *testing.T) {
	// Stage exists but has no agents — should return "sonnet" default
	plans := []ComposePlan{
		{Stage: "discover", Budget: 50000, Agents: []PlanAgent{}},
	}
	model, budget, found := phaseTierFromPlans(plans, "brainstorm")
	if !found {
		t.Fatal("expected found=true for discover stage")
	}
	if model != "sonnet" {
		t.Errorf("model = %q, want sonnet (default)", model)
	}
	if budget != 50000 {
		t.Errorf("budget = %d, want 50000", budget)
	}
}

func TestPhaseToStageMapping(t *testing.T) {
	tests := []struct {
		phase string
		stage string
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
	}

	for _, tt := range tests {
		t.Run(tt.phase, func(t *testing.T) {
			got := phaseToStage(tt.phase)
			if got != tt.stage {
				t.Errorf("phaseToStage(%q) = %q, want %q", tt.phase, got, tt.stage)
			}
		})
	}
}

// ─── Integration Tests ──────────────────────────────────────────

func TestSelfBuildLoopComposeMerge(t *testing.T) {
	// Simulates: load base spec + project override → compose all stages → extract phase tier
	// This is the core self-building loop path without ic/bd dependencies.

	spec := loadTestSpec(t)

	// Load project override and merge
	data, err := os.ReadFile(filepath.Join("testdata", "project-agency-spec.yaml"))
	if err != nil {
		t.Fatalf("load project override: %v", err)
	}
	var override AgencySpec
	if err := yaml.Unmarshal(data, &override); err != nil {
		t.Fatalf("parse override: %v", err)
	}
	mergeSpec(spec, &override)

	fleet := loadTestFleet(t)
	cal := loadTestCalibration(t)

	// Compose all stages
	plans := composeSprint(spec, fleet, cal, nil, "self-build-test", 1000000)
	if len(plans) == 0 {
		t.Fatal("composeSprint returned no plans")
	}

	// Verify self-targeting: fd-self-modification should produce unmatched warning
	var shipPlan *ComposePlan
	for i := range plans {
		if plans[i].Stage == "ship" {
			shipPlan = &plans[i]
			break
		}
	}
	if shipPlan == nil {
		t.Fatal("no ship stage plan")
	}

	hasUnmatchedWarning := false
	for _, w := range shipPlan.Warnings {
		if w == "unmatched_role:fd-self-modification" {
			hasUnmatchedWarning = true
			break
		}
	}
	if !hasUnmatchedWarning {
		t.Error("expected unmatched_role:fd-self-modification warning (agent not in test fleet)")
	}

	// Verify phase tier extraction works for each known phase
	phaseTests := []struct {
		phase     string
		wantStage string
	}{
		{"brainstorm", "discover"},
		{"strategized", "design"},
		{"executing", "build"},
		{"shipping", "ship"},
		{"reflect", "reflect"},
	}

	for _, tt := range phaseTests {
		model, budget, found := phaseTierFromPlans(plans, tt.phase)
		if tt.wantStage == "reflect" {
			continue // test spec doesn't have reflect
		}
		if !found {
			t.Errorf("phaseTierFromPlans(%q) not found, want stage %q", tt.phase, tt.wantStage)
			continue
		}
		if model == "" {
			t.Errorf("phaseTierFromPlans(%q) model is empty", tt.phase)
		}
		if budget <= 0 {
			t.Errorf("phaseTierFromPlans(%q) budget=%d, want > 0", tt.phase, budget)
		}
	}
}

func TestGateModeGraduationIntegration(t *testing.T) {
	spec := loadTestSpec(t)

	// discover should have gate_mode: enforce
	discoverGates := spec.Stages["discover"].Gates
	if discoverGates == nil {
		t.Fatal("discover stage has no gates")
	}
	mode, ok := discoverGates["gate_mode"]
	if !ok || mode != "enforce" {
		t.Errorf("discover gate_mode = %v, want enforce", mode)
	}

	// design should have gate_mode: enforce
	designGates := spec.Stages["design"].Gates
	if designGates == nil {
		t.Fatal("design stage has no gates")
	}
	mode, ok = designGates["gate_mode"]
	if !ok || mode != "enforce" {
		t.Errorf("design gate_mode = %v, want enforce", mode)
	}

	// ship should NOT have gate_mode (inherits shadow)
	shipGates := spec.Stages["ship"].Gates
	if shipGates != nil {
		if _, hasGateMode := shipGates["gate_mode"]; hasGateMode {
			t.Error("ship stage should not have explicit gate_mode (should inherit shadow)")
		}
	}
}
