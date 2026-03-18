package main

import (
	"fmt"
	"testing"
)

func makeFleet(n int) *FleetRegistry {
	agents := make(map[string]FleetAgent, n)
	roles := []string{"reviewer", "architect", "tester", "implementer", "documenter"}
	caps := []string{"code-review", "testing", "architecture", "documentation", "debugging"}

	for i := 0; i < n; i++ {
		id := fmt.Sprintf("agent-%d", i)
		agents[id] = FleetAgent{
			Source:      "plugin",
			Category:    "review",
			Description: fmt.Sprintf("Agent %d for benchmarking", i),
			Capabilities: []string{
				caps[i%len(caps)],
				caps[(i+1)%len(caps)],
			},
			Roles: []string{roles[i%len(roles)]},
			Runtime: AgentRuntime{
				Mode:         "subagent",
				SubagentType: id,
			},
			Models: AgentModels{
				Preferred: []string{"sonnet", "haiku", "opus"}[i%3],
				Supported: []string{"sonnet", "haiku", "opus"},
			},
			ColdStartTokens: 5000 + i*1000,
			Tags:            []string{"go", "review"},
		}
	}
	return &FleetRegistry{
		Version:              "1.0",
		CapabilityVocabulary: caps,
		Agents:               agents,
	}
}

func makeStageSpec(requiredRoles, optionalRoles int) StageSpec {
	roles := []string{"reviewer", "architect", "tester", "implementer", "documenter"}
	var required []AgentRole
	for i := 0; i < requiredRoles && i < len(roles); i++ {
		required = append(required, AgentRole{
			Role:      roles[i],
			ModelTier: "sonnet",
		})
	}
	var optional []AgentRole
	for i := 0; i < optionalRoles && i < len(roles); i++ {
		optional = append(optional, AgentRole{
			Role:      roles[(i+requiredRoles)%len(roles)],
			ModelTier: "haiku",
		})
	}
	return StageSpec{
		Description: "benchmark stage",
		Requires: StageRequirements{
			Capabilities: []string{"code-review", "testing"},
		},
		Budget: StageBudget{
			Share:     25,
			MinTokens: 50000,
		},
		Agents: StageAgents{
			Required: required,
			Optional: optional,
		},
	}
}

func BenchmarkComposePlan10Agents(b *testing.B) {
	fleet := makeFleet(10)
	spec := makeStageSpec(3, 2)

	b.ResetTimer()
	for i := 0; i < b.N; i++ {
		_ = composePlan("review", "sprint-1", 500000, spec, fleet, nil, nil)
	}
}

func BenchmarkComposePlan30Agents(b *testing.B) {
	fleet := makeFleet(30)
	spec := makeStageSpec(4, 3)

	b.ResetTimer()
	for i := 0; i < b.N; i++ {
		_ = composePlan("review", "sprint-1", 500000, spec, fleet, nil, nil)
	}
}

func BenchmarkComposePlanWithCalibration(b *testing.B) {
	fleet := makeFleet(20)
	spec := makeStageSpec(3, 2)
	cal := &InterspectCalibration{
		SchemaVersion: 1,
		MinSessions:   3,
		Agents: map[string]AgentCalibration{
			"agent-0": {RecommendedModel: "haiku", Confidence: 0.9, EvidenceSessions: 10},
			"agent-1": {RecommendedModel: "sonnet", Confidence: 0.8, EvidenceSessions: 5},
			"agent-2": {RecommendedModel: "opus", Confidence: 0.75, EvidenceSessions: 4},
		},
	}

	b.ResetTimer()
	for i := 0; i < b.N; i++ {
		_ = composePlan("review", "sprint-1", 500000, spec, fleet, cal, nil)
	}
}

func BenchmarkMatchRole(b *testing.B) {
	fleet := makeFleet(30)
	role := AgentRole{Role: "reviewer", ModelTier: "sonnet"}

	b.ResetTimer()
	for i := 0; i < b.N; i++ {
		_, _ = matchRole(role, fleet.Agents)
	}
}

func BenchmarkMergeSpec(b *testing.B) {
	base := &AgencySpec{
		Stages: map[string]StageSpec{
			"brainstorm": makeStageSpec(2, 1),
			"plan":       makeStageSpec(3, 2),
			"execute":    makeStageSpec(4, 3),
			"review":     makeStageSpec(3, 2),
			"ship":       makeStageSpec(1, 1),
		},
	}
	override := &AgencySpec{
		Stages: map[string]StageSpec{
			"review": {
				Budget: StageBudget{Share: 30, MinTokens: 100000},
				Agents: StageAgents{
					Required: []AgentRole{{Role: "reviewer", ModelTier: "opus"}},
				},
			},
		},
	}

	b.ResetTimer()
	for i := 0; i < b.N; i++ {
		baseCopy := *base
		baseCopy.Stages = make(map[string]StageSpec, len(base.Stages))
		for k, v := range base.Stages {
			baseCopy.Stages[k] = v
		}
		mergeSpec(&baseCopy, override)
	}
}

func BenchmarkCheckCapabilityCoverage(b *testing.B) {
	fleet := makeFleet(20)
	agents := make([]PlanAgent, 10)
	for i := range agents {
		agents[i] = PlanAgent{AgentID: fmt.Sprintf("agent-%d", i)}
	}
	required := []string{"code-review", "testing", "architecture", "documentation", "debugging"}

	b.ResetTimer()
	for i := 0; i < b.N; i++ {
		_ = checkCapabilityCoverage(required, agents, fleet)
	}
}
