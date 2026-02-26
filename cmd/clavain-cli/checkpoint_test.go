package main

import (
	"encoding/json"
	"testing"
)

func TestCheckpointMarshalRoundTrip(t *testing.T) {
	ckpt := Checkpoint{
		Bead:           "iv-abc",
		Phase:          "planned",
		PlanPath:       "docs/plans/test.md",
		GitSHA:         "abc123",
		UpdatedAt:      "2026-02-25T00:00:00Z",
		CompletedSteps: []string{"brainstorm", "plan", "strategy"},
	}
	data, err := json.Marshal(ckpt)
	if err != nil {
		t.Fatal(err)
	}
	var got Checkpoint
	if err := json.Unmarshal(data, &got); err != nil {
		t.Fatal(err)
	}
	if got.Bead != ckpt.Bead {
		t.Errorf("Bead = %q, want %q", got.Bead, ckpt.Bead)
	}
	if got.Phase != ckpt.Phase {
		t.Errorf("Phase = %q, want %q", got.Phase, ckpt.Phase)
	}
	if got.PlanPath != ckpt.PlanPath {
		t.Errorf("PlanPath = %q, want %q", got.PlanPath, ckpt.PlanPath)
	}
	if got.GitSHA != ckpt.GitSHA {
		t.Errorf("GitSHA = %q, want %q", got.GitSHA, ckpt.GitSHA)
	}
	if got.UpdatedAt != ckpt.UpdatedAt {
		t.Errorf("UpdatedAt = %q, want %q", got.UpdatedAt, ckpt.UpdatedAt)
	}
	if len(got.CompletedSteps) != 3 {
		t.Errorf("CompletedSteps len = %d, want 3", len(got.CompletedSteps))
	}
}

func TestCheckpointAddStep_Dedup(t *testing.T) {
	ckpt := Checkpoint{CompletedSteps: []string{"brainstorm"}}
	ckpt = addCompletedStep(ckpt, "brainstorm") // duplicate — should not add
	ckpt = addCompletedStep(ckpt, "strategy")
	if len(ckpt.CompletedSteps) != 2 {
		t.Errorf("expected 2 steps after dedup, got %d: %v", len(ckpt.CompletedSteps), ckpt.CompletedSteps)
	}
}

func TestCheckpointAddStep_SortsResults(t *testing.T) {
	ckpt := Checkpoint{}
	ckpt = addCompletedStep(ckpt, "strategy")
	ckpt = addCompletedStep(ckpt, "brainstorm")
	ckpt = addCompletedStep(ckpt, "plan")
	if len(ckpt.CompletedSteps) != 3 {
		t.Fatalf("expected 3 steps, got %d", len(ckpt.CompletedSteps))
	}
	// Should be sorted
	expected := []string{"brainstorm", "plan", "strategy"}
	for i, want := range expected {
		if ckpt.CompletedSteps[i] != want {
			t.Errorf("CompletedSteps[%d] = %q, want %q", i, ckpt.CompletedSteps[i], want)
		}
	}
}

func TestCheckpointAddStep_Empty(t *testing.T) {
	ckpt := Checkpoint{}
	ckpt = addCompletedStep(ckpt, "brainstorm")
	if len(ckpt.CompletedSteps) != 1 {
		t.Errorf("expected 1 step, got %d", len(ckpt.CompletedSteps))
	}
	if ckpt.CompletedSteps[0] != "brainstorm" {
		t.Errorf("step = %q, want %q", ckpt.CompletedSteps[0], "brainstorm")
	}
}

func TestCheckpointAddKeyDecision_Dedup(t *testing.T) {
	ckpt := Checkpoint{KeyDecisions: []string{"decision-a"}}
	ckpt = addKeyDecision(ckpt, "decision-a") // duplicate
	ckpt = addKeyDecision(ckpt, "decision-b")
	if len(ckpt.KeyDecisions) != 2 {
		t.Errorf("expected 2 decisions, got %d: %v", len(ckpt.KeyDecisions), ckpt.KeyDecisions)
	}
}

func TestCheckpointAddKeyDecision_MaxFive(t *testing.T) {
	ckpt := Checkpoint{}
	for i := 0; i < 7; i++ {
		ckpt = addKeyDecision(ckpt, "decision-"+string(rune('a'+i)))
	}
	if len(ckpt.KeyDecisions) != 5 {
		t.Errorf("expected max 5 decisions, got %d: %v", len(ckpt.KeyDecisions), ckpt.KeyDecisions)
	}
}

func TestCheckpointEmptyJSON(t *testing.T) {
	var ckpt Checkpoint
	data, err := json.Marshal(ckpt)
	if err != nil {
		t.Fatal(err)
	}
	// Empty checkpoint should produce minimal JSON (no nil slice fields)
	var got map[string]interface{}
	if err := json.Unmarshal(data, &got); err != nil {
		t.Fatal(err)
	}
	// With omitempty, empty strings and nil slices are excluded
	if _, ok := got["bead"]; ok {
		t.Error("empty bead should be omitted")
	}
}
