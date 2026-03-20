package contract

import (
	"testing"
	"time"
)

func TestIntentValidation(t *testing.T) {
	tests := []struct {
		name    string
		intent  Intent
		wantErr string
	}{
		{
			name: "valid sprint.advance",
			intent: Intent{
				Type:           IntentSprintAdvance,
				BeadID:         "iv-abc123",
				IdempotencyKey: "session-x-step-5",
				SessionID:      "sess-123",
				Timestamp:      time.Now().Unix(),
				Params:         map[string]any{"phase": "executing"},
			},
			wantErr: "",
		},
		{
			name: "missing type",
			intent: Intent{
				BeadID:         "iv-abc123",
				IdempotencyKey: "key-1",
				SessionID:      "sess-123",
				Timestamp:      time.Now().Unix(),
			},
			wantErr: "intent type is required",
		},
		{
			name: "missing idempotency key",
			intent: Intent{
				Type:      IntentSprintAdvance,
				BeadID:    "iv-abc123",
				SessionID: "sess-123",
				Timestamp: time.Now().Unix(),
			},
			wantErr: "idempotency key is required",
		},
		{
			name: "invalid intent type",
			intent: Intent{
				Type:           "invalid.type",
				BeadID:         "iv-abc123",
				IdempotencyKey: "key-1",
				SessionID:      "sess-123",
				Timestamp:      time.Now().Unix(),
			},
			wantErr: "unknown intent type",
		},
		{
			name: "invalid bead ID format",
			intent: Intent{
				Type:           IntentSprintAdvance,
				BeadID:         "../../etc/passwd",
				IdempotencyKey: "key-1",
				SessionID:      "sess-123",
				Timestamp:      time.Now().Unix(),
			},
			wantErr: "invalid bead ID format",
		},
		{
			name: "invalid session ID format",
			intent: Intent{
				Type:           IntentSprintAdvance,
				BeadID:         "iv-abc123",
				IdempotencyKey: "key-1",
				SessionID:      "sess;rm -rf /",
				Timestamp:      time.Now().Unix(),
			},
			wantErr: "invalid session ID format",
		},
		{
			name: "empty bead ID is allowed",
			intent: Intent{
				Type:           IntentSprintAdvance,
				IdempotencyKey: "key-1",
				SessionID:      "sess-123",
				Timestamp:      time.Now().Unix(),
			},
			wantErr: "",
		},
	}
	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			err := tt.intent.Validate()
			if tt.wantErr == "" {
				if err != nil {
					t.Errorf("unexpected error: %v", err)
				}
			} else {
				if err == nil {
					t.Fatalf("expected error containing %q, got nil", tt.wantErr)
				}
				if !contains(err.Error(), tt.wantErr) {
					t.Errorf("error %q does not contain %q", err.Error(), tt.wantErr)
				}
			}
		})
	}
}

func TestIntentResultJSON(t *testing.T) {
	r := IntentResult{
		OK:         false,
		IntentType: IntentGateEnforce,
		BeadID:     "iv-abc123",
		Error: &IntentError{
			Code:        ErrGateBlocked,
			Detail:      "plan must be reviewed first",
			Remediation: "Run /interflux:flux-drive on the plan",
		},
	}
	if r.OK {
		t.Error("expected OK to be false")
	}
	if r.Error.Code != ErrGateBlocked {
		t.Errorf("expected error code %s, got %s", ErrGateBlocked, r.Error.Code)
	}
}

func contains(s, substr string) bool {
	for i := 0; i <= len(s)-len(substr); i++ {
		if s[i:i+len(substr)] == substr {
			return true
		}
	}
	return false
}
