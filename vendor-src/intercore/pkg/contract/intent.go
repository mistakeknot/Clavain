package contract

import (
	"fmt"
	"regexp"
)

// Intent type constants — all policy-governing mutations apps can submit.
const (
	// Sprint lifecycle
	IntentSprintCreate  = "sprint.create"
	IntentSprintAdvance = "sprint.advance"
	IntentSprintClaim   = "sprint.claim"
	IntentSprintRelease = "sprint.release"

	// Gate & policy
	IntentGateEnforce = "gate.enforce"
	IntentGateSkip    = "gate.skip"
	IntentBudgetCheck = "budget.check"
	IntentModelRoute  = "model.route"

	// Agent dispatch
	IntentAgentDispatch = "agent.dispatch"
	IntentAgentApprove  = "agent.approve"
	IntentAgentCancel   = "agent.cancel"
)

// beadIDPattern validates bead IDs (e.g., "iv-abc123").
var beadIDPattern = regexp.MustCompile(`^[A-Za-z]+-[a-z0-9]+$`)

// sessionIDPattern validates session IDs (hex, UUID, or short alphanumeric).
var sessionIDPattern = regexp.MustCompile(`^[a-zA-Z0-9_-]{1,128}$`)

// validIntentTypes is the set of known intent types.
var validIntentTypes = map[string]bool{
	IntentSprintCreate:  true,
	IntentSprintAdvance: true,
	IntentSprintClaim:   true,
	IntentSprintRelease: true,
	IntentGateEnforce:   true,
	IntentGateSkip:      true,
	IntentBudgetCheck:   true,
	IntentModelRoute:    true,
	IntentAgentDispatch: true,
	IntentAgentApprove:  true,
	IntentAgentCancel:   true,
}

// Intent represents a typed, policy-governing mutation submitted by an app.
type Intent struct {
	Type           string         `json:"type"`
	BeadID         string         `json:"bead_id,omitempty"`
	IdempotencyKey string         `json:"idempotency_key"`
	SessionID      string         `json:"session_id"`
	Timestamp      int64          `json:"timestamp"`
	Params         map[string]any `json:"params,omitempty"`
}

// Validate checks required fields and type validity.
func (i *Intent) Validate() error {
	if i.Type == "" {
		return fmt.Errorf("intent type is required")
	}
	if !validIntentTypes[i.Type] {
		return fmt.Errorf("unknown intent type: %s", i.Type)
	}
	if i.IdempotencyKey == "" {
		return fmt.Errorf("idempotency key is required")
	}
	if i.SessionID == "" {
		return fmt.Errorf("session ID is required")
	}
	if i.Timestamp == 0 {
		return fmt.Errorf("timestamp is required")
	}
	if i.BeadID != "" && !beadIDPattern.MatchString(i.BeadID) {
		return fmt.Errorf("invalid bead ID format: %s", i.BeadID)
	}
	if !sessionIDPattern.MatchString(i.SessionID) {
		return fmt.Errorf("invalid session ID format")
	}
	return nil
}

// IntentResult is the structured response from the OS intent router.
type IntentResult struct {
	OK         bool           `json:"ok"`
	IntentType string         `json:"intent_type"`
	BeadID     string         `json:"bead_id,omitempty"`
	Data       map[string]any `json:"data,omitempty"`
	Error      *IntentError   `json:"error,omitempty"`
}

// IntentError is a structured, machine-readable error.
type IntentError struct {
	Code        ErrorCode `json:"code"`
	Detail      string    `json:"detail"`
	Remediation string    `json:"remediation,omitempty"`
}
