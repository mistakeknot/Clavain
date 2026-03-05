package main

import (
	"encoding/json"
	"testing"

	"github.com/mistakeknot/intercore/pkg/contract"
)

func TestParseIntentJSON(t *testing.T) {
	raw := `{
		"type": "sprint.advance",
		"bead_id": "iv-abc123",
		"idempotency_key": "sess-x-step-5",
		"session_id": "sess-123",
		"timestamp": 1772749697,
		"params": {"phase": "executing"}
	}`

	var intent contract.Intent
	if err := json.Unmarshal([]byte(raw), &intent); err != nil {
		t.Fatalf("unmarshal: %v", err)
	}
	if err := intent.Validate(); err != nil {
		t.Fatalf("validate: %v", err)
	}
	if intent.Type != contract.IntentSprintAdvance {
		t.Errorf("type = %s, want %s", intent.Type, contract.IntentSprintAdvance)
	}
	if intent.BeadID != "iv-abc123" {
		t.Errorf("bead_id = %s, want iv-abc123", intent.BeadID)
	}
}

func TestIntentResultMarshal(t *testing.T) {
	r := contract.IntentResult{
		OK:         true,
		IntentType: contract.IntentSprintAdvance,
		BeadID:     "iv-abc123",
		Data:       map[string]any{"from_phase": "planned", "to_phase": "executing"},
	}
	b, err := json.Marshal(r)
	if err != nil {
		t.Fatalf("marshal: %v", err)
	}
	var decoded map[string]any
	if err := json.Unmarshal(b, &decoded); err != nil {
		t.Fatalf("unmarshal: %v", err)
	}
	if decoded["ok"] != true {
		t.Error("expected ok=true")
	}
}
