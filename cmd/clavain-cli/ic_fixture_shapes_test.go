package main

import (
	"encoding/json"
	"os"
	"path/filepath"
	"testing"
)

// The fixtures under tests/fixtures/ic are captured output of the real ic
// binary (ic --json run ...), not hand-written stubs. They pin the shapes the
// readers must accept; ic's emitter is the contract.

func readICFixture(t *testing.T, name string) []byte {
	t.Helper()
	data, err := os.ReadFile(filepath.Join("..", "..", "tests", "fixtures", "ic", name))
	if err != nil {
		t.Fatal(err)
	}
	return data
}

func TestBudgetResultReadsICShape(t *testing.T) {
	var br BudgetResult
	if err := json.Unmarshal(readICFixture(t, "run-budget.json"), &br); err != nil {
		t.Fatal(err)
	}
	if br.RunID == "" || br.TokenBudget != 1000 || br.TokensUsed != 0 || br.Exceeded || br.WarnPct != 80 {
		t.Fatalf("unexpected budget result: %+v", br)
	}
}

func TestBudgetResultUnsetBudgetIsZero(t *testing.T) {
	var br BudgetResult
	if err := json.Unmarshal(readICFixture(t, "run-budget-unset.json"), &br); err != nil {
		t.Fatal(err)
	}
	if br.TokenBudget != 0 || br.RunID == "" {
		t.Fatalf("unexpected budget result: %+v", br)
	}
}

func TestRunStatusFixture(t *testing.T) {
	var run Run
	if err := json.Unmarshal(readICFixture(t, "run-status.json"), &run); err != nil {
		t.Fatal(err)
	}
	if run.TokenBudget != 1000 || run.CreatedAt == 0 || run.ScopeID != "bead-fx" {
		t.Fatalf("unexpected run: %+v", run)
	}
}

func TestRunAgentListEpochCreatedAt(t *testing.T) {
	var agents []RunAgent
	if err := json.Unmarshal(readICFixture(t, "run-agent-list.json"), &agents); err != nil {
		t.Fatal(err)
	}
	if len(agents) != 1 || agents[0].CreatedAt == 0 || agents[0].Status != "active" {
		t.Fatalf("unexpected agents: %+v", agents)
	}
}

func TestRunEventsIntegerIDAndPhases(t *testing.T) {
	var events []RunEvent
	if err := json.Unmarshal(readICFixture(t, "run-events.json"), &events); err != nil {
		t.Fatal(err)
	}
	if len(events) != 1 || events[0].EventType != "advance" || events[0].ToPhase != "brainstorm-reviewed" || events[0].CreatedAt == 0 {
		t.Fatalf("unexpected events: %+v", events)
	}
	var cx []struct {
		ID    int64  `json:"id"`
		Type  string `json:"event_type"`
		Phase string `json:"to_phase,omitempty"`
	}
	if err := json.Unmarshal(readICFixture(t, "run-events.json"), &cx); err != nil || len(cx) != 1 || cx[0].ID != 1 {
		t.Fatalf("cxdb event shape: %v %+v", err, cx)
	}
}

func TestRunActionArgsIsJSONValue(t *testing.T) {
	var actions []RunAction
	if err := json.Unmarshal(readICFixture(t, "run-action-list.json"), &actions); err != nil {
		t.Fatal(err)
	}
	if len(actions) != 1 || actions[0].Command != "/clavain:x" || string(actions[0].Args) != `{"a":1}` {
		t.Fatalf("unexpected actions: %+v", actions)
	}
}
