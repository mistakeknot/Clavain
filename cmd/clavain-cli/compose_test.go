package main

import (
	"encoding/json"
	"os"
	"path/filepath"
	"testing"

	"gopkg.in/yaml.v3"
)

// ─── Test Helpers ─────────────────────────────────────────────────

func loadTestFleet(t *testing.T) *FleetRegistry {
	t.Helper()
	data, err := os.ReadFile(filepath.Join("testdata", "fleet-registry.yaml"))
	if err != nil {
		t.Fatalf("load fleet-registry.yaml: %v", err)
	}
	var reg FleetRegistry
	if err := yaml.Unmarshal(data, &reg); err != nil {
		t.Fatalf("parse fleet-registry.yaml: %v", err)
	}
	return &reg
}

func loadTestSpec(t *testing.T) *AgencySpec {
	t.Helper()
	data, err := os.ReadFile(filepath.Join("testdata", "agency-spec.yaml"))
	if err != nil {
		t.Fatalf("load agency-spec.yaml: %v", err)
	}
	var spec AgencySpec
	if err := yaml.Unmarshal(data, &spec); err != nil {
		t.Fatalf("parse agency-spec.yaml: %v", err)
	}
	return &spec
}

func loadTestCalibration(t *testing.T) *InterspectCalibration {
	t.Helper()
	data, err := os.ReadFile(filepath.Join("testdata", "routing-calibration.json"))
	if err != nil {
		t.Fatalf("load routing-calibration.json: %v", err)
	}
	var cal InterspectCalibration
	if err := json.Unmarshal(data, &cal); err != nil {
		t.Fatalf("parse routing-calibration.json: %v", err)
	}
	return &cal
}

func loadTestOverrides(t *testing.T) *RoutingOverrides {
	t.Helper()
	data, err := os.ReadFile(filepath.Join("testdata", "routing-overrides.json"))
	if err != nil {
		t.Fatalf("load routing-overrides.json: %v", err)
	}
	var ov RoutingOverrides
	if err := json.Unmarshal(data, &ov); err != nil {
		t.Fatalf("parse routing-overrides.json: %v", err)
	}
	return &ov
}

// ─── Tests ────────────────────────────────────────────────────────

func TestLoadFleetRegistry(t *testing.T) {
	fleet := loadTestFleet(t)
	if len(fleet.Agents) != 6 {
		t.Fatalf("expected 6 agents, got %d", len(fleet.Agents))
	}
	safety, ok := fleet.Agents["fd-safety"]
	if !ok {
		t.Fatal("fd-safety not found in fleet")
	}
	if safety.Runtime.SubagentType != "interflux:fd-safety" {
		t.Errorf("fd-safety subagent_type = %q, want %q", safety.Runtime.SubagentType, "interflux:fd-safety")
	}
}

func TestLoadAgencySpec(t *testing.T) {
	spec := loadTestSpec(t)
	if len(spec.Stages) != 4 {
		t.Fatalf("expected 4 stages, got %d", len(spec.Stages))
	}
	ship, ok := spec.Stages["ship"]
	if !ok {
		t.Fatal("ship stage not found")
	}
	if len(ship.Agents.Required) != 3 {
		t.Errorf("ship required agents = %d, want 3", len(ship.Agents.Required))
	}
}

func TestMatchRole(t *testing.T) {
	fleet := loadTestFleet(t)

	// Build active fleet: exclude orphaned agents (like composePlan does)
	activeFleet := map[string]FleetAgent{}
	for id, agent := range fleet.Agents {
		if agent.OrphanedAt == "" {
			activeFleet[id] = agent
		}
	}

	tests := []struct {
		name   string
		role   AgentRole
		fleet  map[string]FleetAgent
		wantID string
		wantOK bool
	}{
		{
			name:   "existing role matches",
			role:   AgentRole{Role: "fd-safety"},
			fleet:  activeFleet,
			wantID: "fd-safety",
			wantOK: true,
		},
		{
			name:   "cheapest candidate wins",
			role:   AgentRole{Role: "fd-quality"},
			fleet:  activeFleet,
			wantID: "fd-quality",
			wantOK: true,
		},
		{
			name:   "orphaned excluded from active fleet",
			role:   AgentRole{Role: "fd-architecture"},
			fleet:  activeFleet,
			wantID: "fd-architecture",
			wantOK: true,
		},
		{
			name:   "missing role returns false",
			role:   AgentRole{Role: "nonexistent"},
			fleet:  activeFleet,
			wantID: "",
			wantOK: false,
		},
		{
			name:   "synthesis role matches",
			role:   AgentRole{Role: "synthesis"},
			fleet:  activeFleet,
			wantID: "synthesis-agent",
			wantOK: true,
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			agent, ok := matchRole(tt.role, tt.fleet)
			if ok != tt.wantOK {
				t.Fatalf("matchRole(%q) ok = %v, want %v", tt.role.Role, ok, tt.wantOK)
			}
			if ok && agent.id != tt.wantID {
				t.Errorf("matchRole(%q) id = %q, want %q", tt.role.Role, agent.id, tt.wantID)
			}
		})
	}
}

func TestResolveModel(t *testing.T) {
	cal := loadTestCalibration(t)

	tests := []struct {
		name       string
		agent      matchedAgent
		role       AgentRole
		cal        *InterspectCalibration
		wantModel  string
		wantSource string
	}{
		{
			name:       "safety floor fd-safety no calibration",
			agent:      matchedAgent{id: "fd-safety", agent: FleetAgent{Models: AgentModels{Preferred: "sonnet"}}},
			role:       AgentRole{ModelTier: "sonnet"},
			cal:        cal,
			wantModel:  "sonnet",
			wantSource: "fleet_preferred",
		},
		{
			name:       "safety floor fd-correctness no calibration",
			agent:      matchedAgent{id: "fd-correctness", agent: FleetAgent{Models: AgentModels{Preferred: "sonnet"}}},
			role:       AgentRole{ModelTier: "sonnet"},
			cal:        cal,
			wantModel:  "sonnet",
			wantSource: "fleet_preferred",
		},
		{
			name:       "calibration applied fd-architecture to haiku",
			agent:      matchedAgent{id: "fd-architecture", agent: FleetAgent{Models: AgentModels{Preferred: "sonnet"}}},
			role:       AgentRole{ModelTier: "sonnet"},
			cal:        cal,
			wantModel:  "haiku",
			wantSource: "interspect_calibration",
		},
		{
			name:       "calibration upgrades fd-quality to opus",
			agent:      matchedAgent{id: "fd-quality", agent: FleetAgent{Models: AgentModels{Preferred: "sonnet"}}},
			role:       AgentRole{ModelTier: "sonnet"},
			cal:        cal,
			wantModel:  "opus",
			wantSource: "interspect_calibration",
		},
		{
			name:       "fleet preferred synthesis-agent haiku",
			agent:      matchedAgent{id: "synthesis-agent", agent: FleetAgent{Models: AgentModels{Preferred: "haiku"}}},
			role:       AgentRole{ModelTier: "haiku"},
			cal:        cal,
			wantModel:  "haiku",
			wantSource: "fleet_preferred",
		},
		{
			name:  "calibration upgrades fd-safety to opus",
			agent: matchedAgent{id: "fd-safety", agent: FleetAgent{}},
			role:  AgentRole{},
			cal: &InterspectCalibration{Agents: map[string]AgentCalibration{
				"fd-safety": {RecommendedModel: "opus", Confidence: 0.95, EvidenceSessions: 10},
			}},
			wantModel:  "opus",
			wantSource: "interspect_calibration",
		},
		{
			name:  "calibration haiku for fd-safety clamped to sonnet",
			agent: matchedAgent{id: "fd-safety", agent: FleetAgent{}},
			role:  AgentRole{},
			cal: &InterspectCalibration{Agents: map[string]AgentCalibration{
				"fd-safety": {RecommendedModel: "haiku", Confidence: 0.95, EvidenceSessions: 10},
			}},
			wantModel:  "sonnet",
			wantSource: "safety_floor",
		},
		{
			name:  "unrecognized calibration model for fd-safety falls to floor",
			agent: matchedAgent{id: "fd-safety", agent: FleetAgent{}},
			role:  AgentRole{},
			cal: &InterspectCalibration{Agents: map[string]AgentCalibration{
				"fd-safety": {RecommendedModel: "claude-3-5-sonnet", Confidence: 0.95, EvidenceSessions: 10},
			}},
			wantModel:  "sonnet",
			wantSource: "routing_fallback", // unrecognized model filtered by calibration, fallback produces sonnet which matches floor
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			model, source := resolveModel(tt.agent, tt.role, tt.cal, nil)
			if model != tt.wantModel || source != tt.wantSource {
				t.Errorf("resolveModel(%q) = (%q, %q), want (%q, %q)",
					tt.agent.id, model, source, tt.wantModel, tt.wantSource)
			}
		})
	}
}

func TestResolveModelNoCalibration(t *testing.T) {
	agent := matchedAgent{
		id:    "fd-architecture",
		agent: FleetAgent{Models: AgentModels{Preferred: "sonnet"}},
	}
	role := AgentRole{ModelTier: "sonnet"}
	model, source := resolveModel(agent, role, nil, nil)
	if model != "sonnet" || source != "fleet_preferred" {
		t.Errorf("no calibration: model=%q source=%q, want sonnet/fleet_preferred", model, source)
	}
}

func TestComposePlanShipStage(t *testing.T) {
	fleet := loadTestFleet(t)
	spec := loadTestSpec(t)
	cal := loadTestCalibration(t)
	overrides := loadTestOverrides(t)

	stageSpec := spec.Stages["ship"]
	budget := int64(stageSpec.Budget.MinTokens)
	plan := composePlan("ship", "", budget, stageSpec, fleet, cal, overrides, nil)

	// 5 agents: 3 required + 2 optional
	if len(plan.Agents) != 5 {
		t.Fatalf("ship stage agents = %d, want 5", len(plan.Agents))
	}

	// Deterministic order: sorted by AgentID
	wantOrder := []string{"fd-architecture", "fd-correctness", "fd-quality", "fd-safety", "synthesis-agent"}
	for i, a := range plan.Agents {
		if a.AgentID != wantOrder[i] {
			t.Errorf("agent[%d] = %q, want %q", i, a.AgentID, wantOrder[i])
		}
	}

	// Safety floor agents with no calibration data resolve via fleet_preferred
	// (sonnet matches floor, so clamp does not fire — source is fleet_preferred)
	for _, a := range plan.Agents {
		if a.AgentID == "fd-safety" {
			if a.Model != "sonnet" || a.ModelSource != "fleet_preferred" {
				t.Errorf("fd-safety: model=%q source=%q, want sonnet/fleet_preferred", a.Model, a.ModelSource)
			}
		}
		if a.AgentID == "fd-correctness" {
			if a.Model != "sonnet" || a.ModelSource != "fleet_preferred" {
				t.Errorf("fd-correctness: model=%q source=%q, want sonnet/fleet_preferred", a.Model, a.ModelSource)
			}
		}
	}

	// Calibration applied to fd-architecture
	for _, a := range plan.Agents {
		if a.AgentID == "fd-architecture" {
			if a.Model != "haiku" || a.ModelSource != "interspect_calibration" {
				t.Errorf("fd-architecture: model=%q source=%q, want haiku/interspect_calibration", a.Model, a.ModelSource)
			}
		}
	}

	// No warnings expected (all capabilities covered, budget sufficient)
	// Overrides exclude fd-game-design which is not in the plan anyway
	wantWarnings := 1 // excluded:fd-game-design:...
	if len(plan.Warnings) != wantWarnings {
		t.Errorf("warnings = %v, want %d warning(s)", plan.Warnings, wantWarnings)
	}
}

func TestComposePlanBudgetWarning(t *testing.T) {
	fleet := loadTestFleet(t)
	spec := loadTestSpec(t)
	cal := loadTestCalibration(t)

	stageSpec := spec.Stages["ship"]
	// Tiny budget that will be exceeded by agent token estimates
	plan := composePlan("ship", "", 100, stageSpec, fleet, nil, nil, nil)

	found := false
	for _, w := range plan.Warnings {
		if w == "budget_exceeded" {
			found = true
			break
		}
	}
	if !found {
		t.Errorf("expected budget_exceeded warning with budget=100, got %v", plan.Warnings)
	}
	_ = cal // loaded for consistency but not used in this test
}

func TestComposePlanUnmatchedRole(t *testing.T) {
	fleet := loadTestFleet(t)
	spec := loadTestSpec(t)

	stageSpec := spec.Stages["build"]
	budget := int64(stageSpec.Budget.MinTokens)
	plan := composePlan("build", "", budget, stageSpec, fleet, nil, nil, nil)

	found := false
	for _, w := range plan.Warnings {
		if w == "unmatched_role:implementer" {
			found = true
			break
		}
	}
	if !found {
		t.Errorf("expected unmatched_role:implementer warning, got %v", plan.Warnings)
	}
}

func TestComposePlanExcludedAgent(t *testing.T) {
	fleet := loadTestFleet(t)
	spec := loadTestSpec(t)
	cal := loadTestCalibration(t)

	// Create overrides that exclude fd-architecture
	overrides := &RoutingOverrides{
		Version: 1,
		Overrides: []RoutingOverride{
			{Agent: "fd-architecture", Action: "exclude", Reason: "test exclusion", Confidence: 0.9},
		},
	}

	stageSpec := spec.Stages["ship"]
	budget := int64(stageSpec.Budget.MinTokens)
	plan := composePlan("ship", "", budget, stageSpec, fleet, cal, overrides, nil)

	// fd-architecture should not be in plan
	for _, a := range plan.Agents {
		if a.AgentID == "fd-architecture" {
			t.Error("fd-architecture should be excluded from plan")
		}
	}

	// Exclusion warning should be present
	foundExclusion := false
	for _, w := range plan.Warnings {
		if w == "excluded:fd-architecture:test exclusion" {
			foundExclusion = true
			break
		}
	}
	if !foundExclusion {
		t.Errorf("expected exclusion warning for fd-architecture, got %v", plan.Warnings)
	}
}

func TestComposePlanOrphanedAgentExcluded(t *testing.T) {
	fleet := loadTestFleet(t)
	spec := loadTestSpec(t)

	stageSpec := spec.Stages["ship"]
	budget := int64(stageSpec.Budget.MinTokens)
	plan := composePlan("ship", "", budget, stageSpec, fleet, nil, nil, nil)

	for _, a := range plan.Agents {
		if a.AgentID == "orphaned-agent" {
			t.Error("orphaned-agent should never appear in plan")
		}
	}
}

func TestMergeSpec(t *testing.T) {
	spec := loadTestSpec(t)

	override := &AgencySpec{
		Stages: map[string]StageSpec{
			"ship": {
				Budget: StageBudget{Share: 30},
			},
		},
	}

	mergeSpec(spec, override)

	ship := spec.Stages["ship"]
	if ship.Budget.Share != 30 {
		t.Errorf("merged share = %d, want 30", ship.Budget.Share)
	}
	// MinTokens should be preserved from base
	if ship.Budget.MinTokens != 5000 {
		t.Errorf("merged min_tokens = %d, want 5000 (preserved from base)", ship.Budget.MinTokens)
	}
	// Agents should be preserved from base (override has none)
	if len(ship.Agents.Required) != 3 {
		t.Errorf("merged required agents = %d, want 3 (preserved from base)", len(ship.Agents.Required))
	}
}

func TestMergeSpecNilBaseStages(t *testing.T) {
	base := &AgencySpec{} // Stages is nil
	override := &AgencySpec{
		Stages: map[string]StageSpec{
			"ship": {Budget: StageBudget{Share: 50}},
		},
	}
	mergeSpec(base, override) // Must not panic
	if base.Stages["ship"].Budget.Share != 50 {
		t.Errorf("merged share = %d, want 50", base.Stages["ship"].Budget.Share)
	}
}

func TestSafetyFloorExclusionWarning(t *testing.T) {
	fleet := loadTestFleet(t)
	spec := loadTestSpec(t)
	overrides := &RoutingOverrides{
		Version: 1,
		Overrides: []RoutingOverride{
			{Agent: "fd-safety", Action: "exclude", Reason: "test"},
		},
	}
	plan := composePlan("ship", "", 100000, spec.Stages["ship"], fleet, nil, overrides, nil)
	var foundWarning bool
	for _, w := range plan.Warnings {
		if w == "WARNING:safety_floor_excluded:fd-safety:test" {
			foundWarning = true
		}
	}
	if !foundWarning {
		t.Errorf("expected WARNING:safety_floor_excluded warning, got %v", plan.Warnings)
	}
}

func TestComposePlanDeterministic(t *testing.T) {
	fleet := loadTestFleet(t)
	spec := loadTestSpec(t)
	cal := loadTestCalibration(t)
	overrides := loadTestOverrides(t)

	stageSpec := spec.Stages["ship"]
	budget := int64(stageSpec.Budget.MinTokens)

	// Generate plan once as reference
	ref := composePlan("ship", "", budget, stageSpec, fleet, cal, overrides, nil)
	refJSON, err := json.Marshal(ref)
	if err != nil {
		t.Fatalf("marshal reference plan: %v", err)
	}

	// Run 20 times and compare
	for i := 0; i < 20; i++ {
		plan := composePlan("ship", "", budget, stageSpec, fleet, cal, overrides, nil)
		planJSON, err := json.Marshal(plan)
		if err != nil {
			t.Fatalf("marshal plan iteration %d: %v", i, err)
		}
		if string(planJSON) != string(refJSON) {
			t.Fatalf("plan iteration %d differs from reference:\ngot:  %s\nwant: %s", i, planJSON, refJSON)
		}
	}
}

func TestCapabilityCoverage(t *testing.T) {
	fleet := loadTestFleet(t)

	// Two agents that cover domain_review, multi_perspective, and verdict_aggregation
	agents := []PlanAgent{
		{AgentID: "fd-architecture"}, // domain_review, multi_perspective
		{AgentID: "synthesis-agent"}, // verdict_aggregation
	}

	required := []string{"domain_review", "multi_perspective", "verdict_aggregation"}
	missing := checkCapabilityCoverage(required, agents, fleet)
	if len(missing) != 0 {
		t.Errorf("expected no missing capabilities, got %v", missing)
	}

	// Add a nonexistent capability
	required = append(required, "nonexistent")
	missing = checkCapabilityCoverage(required, agents, fleet)
	if len(missing) != 1 || missing[0] != "nonexistent" {
		t.Errorf("expected [nonexistent] missing, got %v", missing)
	}
}

func TestSprintComposeStoresAllStages(t *testing.T) {
	fleet := loadTestFleet(t)
	spec := loadTestSpec(t)
	cal := loadTestCalibration(t)

	plans := composeSprint(spec, fleet, cal, nil, nil, "test-sprint", 100000)

	// Should have plans for all stages in test spec (discover, design, ship, build)
	if len(plans) != 4 {
		t.Fatalf("composeSprint returned %d stage plans, want 4", len(plans))
	}

	// Verify ship stage has agents
	var shipPlan *ComposePlan
	for i := range plans {
		if plans[i].Stage == "ship" {
			shipPlan = &plans[i]
			break
		}
	}
	if shipPlan == nil {
		t.Fatal("no ship stage in composeSprint output")
	}
	if len(shipPlan.Agents) == 0 {
		t.Error("ship stage has no agents")
	}

	// Verify sprint ID is set on all plans
	for _, p := range plans {
		if p.Sprint != "test-sprint" {
			t.Errorf("stage %s: sprint = %q, want test-sprint", p.Stage, p.Sprint)
		}
	}
}

func TestMergeProjectOverride(t *testing.T) {
	spec := loadTestSpec(t)

	// Load project override
	data, err := os.ReadFile(filepath.Join("testdata", "project-agency-spec.yaml"))
	if err != nil {
		t.Fatalf("load project override: %v", err)
	}
	var override AgencySpec
	if err := yaml.Unmarshal(data, &override); err != nil {
		t.Fatalf("parse project override: %v", err)
	}

	mergeSpec(spec, &override)

	ship := spec.Stages["ship"]
	// Should now have 4 required agents (3 original + fd-self-modification)
	if len(ship.Agents.Required) != 4 {
		t.Errorf("merged ship required agents = %d, want 4", len(ship.Agents.Required))
	}

	// Verify fd-self-modification is present
	found := false
	for _, a := range ship.Agents.Required {
		if a.Role == "fd-self-modification" {
			found = true
			break
		}
	}
	if !found {
		t.Error("fd-self-modification not found in merged spec")
	}
}

func TestResolveModelRoutingFallback(t *testing.T) {
	agent := matchedAgent{
		id:    "some-agent",
		agent: FleetAgent{Models: AgentModels{Preferred: ""}},
	}
	role := AgentRole{ModelTier: "opus"}
	model, source := resolveModel(agent, role, nil, nil)
	if model != "opus" || source != "routing_fallback" {
		t.Errorf("routing fallback: model=%q source=%q, want opus/routing_fallback", model, source)
	}
}
