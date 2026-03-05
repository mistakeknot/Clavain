package main

import (
	"encoding/json"
	"fmt"
	"os"
)

// phaseToStage is defined in budget.go — maps sprint phases to macro-stage names.

// phaseTierFromPlans finds the model tier and budget for a phase from compose plans.
// Uses phaseToStage to map phase → stage, then looks up the matching ComposePlan.
// Returns the dominant model (from the first required agent) and the stage budget.
func phaseTierFromPlans(plans []ComposePlan, phase string) (model string, budget int64, found bool) {
	stage := phaseToStage(phase)
	if stage == "" || stage == "unknown" || stage == "done" {
		return "", 0, false
	}

	for _, p := range plans {
		if p.Stage == stage {
			// Find the dominant model: first required agent, or first agent
			m := ""
			for _, a := range p.Agents {
				if a.Required {
					m = a.Model
					break
				}
			}
			if m == "" && len(p.Agents) > 0 {
				m = p.Agents[0].Model
			}
			if m == "" {
				m = "sonnet" // safe default
			}
			return m, p.Budget, true
		}
	}
	return "", 0, false
}

// cmdSprintPlanPhase reads the stored ComposePlan and returns model + budget for a phase.
// Usage: sprint-plan-phase <bead_id> <phase>
// Output: JSON {"model": "opus", "budget": 400000, "stage": "build"} or error.
func cmdSprintPlanPhase(args []string) error {
	if len(args) < 2 || args[0] == "" || args[1] == "" {
		return fmt.Errorf("usage: sprint-plan-phase <bead_id> <phase>")
	}
	beadID := args[0]
	phase := args[1]

	// Try to load compose plan from ic artifact
	plans, err := loadComposePlans(beadID)
	if err != nil {
		// Fallback: compute from agency spec directly
		spec, specErr := loadAgencySpec()
		if specErr != nil {
			return fmt.Errorf("sprint-plan-phase: no compose plan and no agency spec: %w", specErr)
		}
		stage := phaseToStage(phase)
		if stage == "" {
			return fmt.Errorf("sprint-plan-phase: unknown phase %q", phase)
		}
		stageSpec, ok := spec.Stages[stage]
		if !ok {
			return fmt.Errorf("sprint-plan-phase: unknown stage %q for phase %q", stage, phase)
		}
		model := stageSpec.Budget.ModelTierHint
		if model == "" {
			model = "sonnet"
		}
		result := map[string]interface{}{
			"model":    model,
			"budget":   stageSpec.Budget.MinTokens,
			"stage":    stage,
			"fallback": true,
		}
		data, err := json.Marshal(result)
		if err != nil {
			return fmt.Errorf("sprint-plan-phase: marshal: %w", err)
		}
		fmt.Println(string(data))
		return nil
	}

	model, budget, found := phaseTierFromPlans(plans, phase)
	if !found {
		return fmt.Errorf("sprint-plan-phase: phase %q not mapped to any stage", phase)
	}

	result := map[string]interface{}{
		"model":  model,
		"budget": budget,
		"stage":  phaseToStage(phase),
	}
	data, err := json.Marshal(result)
	if err != nil {
		return fmt.Errorf("sprint-plan-phase: marshal: %w", err)
	}
	fmt.Println(string(data))
	return nil
}

// loadComposePlans loads stored compose plans from ic artifact.
func loadComposePlans(beadID string) ([]ComposePlan, error) {
	runID, err := resolveRunID(beadID)
	if err != nil {
		return nil, err
	}

	var artifacts []Artifact
	if err := runICJSON(&artifacts, "run", "artifact", "list", runID); err != nil {
		return nil, err
	}

	// Find compose_plan artifact
	for _, a := range artifacts {
		if a.Type == "compose_plan" {
			data, err := os.ReadFile(a.Path)
			if err != nil {
				continue
			}
			var plans []ComposePlan
			if err := json.Unmarshal(data, &plans); err != nil {
				// Try single plan (backward compat)
				var single ComposePlan
				if err2 := json.Unmarshal(data, &single); err2 == nil {
					return []ComposePlan{single}, nil
				}
				continue
			}
			return plans, nil
		}
	}
	return nil, fmt.Errorf("no compose_plan artifact found for %s", beadID)
}

// cmdSprintEnvVars outputs export statements for CLAVAIN_MODEL and CLAVAIN_PHASE_BUDGET.
// Intended to be eval'd by the sprint executor: eval $(clavain-cli sprint-env-vars <bead_id> <phase>)
// Usage: sprint-env-vars <bead_id> <phase>
func cmdSprintEnvVars(args []string) error {
	if len(args) < 2 || args[0] == "" || args[1] == "" {
		return fmt.Errorf("usage: sprint-env-vars <bead_id> <phase>")
	}
	beadID := args[0]
	phase := args[1]

	// Try compose plans first
	plans, err := loadComposePlans(beadID)
	if err == nil {
		model, budget, found := phaseTierFromPlans(plans, phase)
		if found {
			fmt.Printf("export CLAVAIN_MODEL=%s\n", model)
			fmt.Printf("export CLAVAIN_PHASE_BUDGET=%d\n", budget)
			fmt.Printf("export CLAVAIN_STAGE=%s\n", phaseToStage(phase))
			return nil
		}
	}

	// Fallback: agency spec model_tier_hint
	spec, specErr := loadAgencySpec()
	if specErr != nil {
		// No compose plan and no spec — emit empty exports (fail-soft)
		fmt.Fprintf(os.Stderr, "sprint-env-vars: no compose plan or agency spec for %s\n", beadID)
		return nil
	}
	stage := phaseToStage(phase)
	if stage == "" || stage == "unknown" || stage == "done" {
		fmt.Fprintf(os.Stderr, "sprint-env-vars: unknown phase %q — no env vars emitted\n", phase)
		return nil
	}
	stageSpec, ok := spec.Stages[stage]
	if !ok {
		fmt.Fprintf(os.Stderr, "sprint-env-vars: stage %q not in agency spec — no env vars emitted\n", stage)
		return nil
	}
	model := stageSpec.Budget.ModelTierHint
	if model == "" {
		model = "sonnet"
	}
	// Use proportional budget (share % of default 1M) with MinTokens as floor
	budget := int64(1000000) * int64(stageSpec.Budget.Share) / 100
	if budget < int64(stageSpec.Budget.MinTokens) {
		budget = int64(stageSpec.Budget.MinTokens)
	}
	fmt.Printf("export CLAVAIN_MODEL=%s\n", model)
	fmt.Printf("export CLAVAIN_PHASE_BUDGET=%d\n", budget)
	fmt.Printf("export CLAVAIN_STAGE=%s\n", stage)
	return nil
}
