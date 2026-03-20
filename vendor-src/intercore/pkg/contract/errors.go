package contract

// ErrorCode is a machine-readable error code for intent failures.
type ErrorCode string

const (
	ErrGateBlocked    ErrorCode = "GATE_BLOCKED"
	ErrClaimConflict  ErrorCode = "CLAIM_CONFLICT"
	ErrBudgetExceeded ErrorCode = "BUDGET_EXCEEDED"
	ErrInvalidIntent  ErrorCode = "INVALID_INTENT"
	ErrPhaseConflict  ErrorCode = "PHASE_CONFLICT"
	ErrNotFound       ErrorCode = "NOT_FOUND"
	ErrInternal       ErrorCode = "INTERNAL"
)
