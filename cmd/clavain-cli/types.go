package main

// Run represents an Intercore sprint run.
type Run struct {
	ID            string   `json:"id"`
	Goal          string   `json:"goal"`
	Phase         string   `json:"phase"`
	Status        string   `json:"status"`
	ProjectDir    string   `json:"project_dir"`
	ScopeID       string   `json:"scope_id,omitempty"`
	Complexity    int      `json:"complexity"`
	AutoAdvance   bool     `json:"auto_advance"`
	ForceFull     bool     `json:"force_full"`
	TokenBudget   int64    `json:"token_budget,omitempty"`
	BudgetWarnPct int      `json:"budget_warn_pct,omitempty"`
	Phases        []string `json:"phases,omitempty"`
	CreatedAt     int64    `json:"created_at"`
	UpdatedAt     int64    `json:"updated_at"`
}

// BudgetResult from ic run budget.
type BudgetResult struct {
	RunID       string `json:"run_id"`
	TokenBudget int64  `json:"token_budget"`
	TokensUsed  int64  `json:"tokens_used"`
	Exceeded    bool   `json:"exceeded"`
	WarnPct     int    `json:"warn_pct,omitempty"`
}

// GateResult from ic gate check.
type GateResult struct {
	RunID     string        `json:"run_id"`
	FromPhase string        `json:"from_phase"`
	ToPhase   string        `json:"to_phase,omitempty"`
	Result    string        `json:"result"`
	Tier      string        `json:"tier"`
	Evidence  *GateEvidence `json:"evidence,omitempty"`
}

// Passed returns true if the gate check passed.
func (g GateResult) Passed() bool { return g.Result == "pass" }

// GateEvidence contains the individual condition checks.
type GateEvidence struct {
	Conditions []GateCondition `json:"conditions"`
}

// GateCondition is a single gate condition check result.
type GateCondition struct {
	Check  string `json:"check"`
	Phase  string `json:"phase,omitempty"`
	Result string `json:"result"`
	Count  int    `json:"count,omitempty"`
	Detail string `json:"detail,omitempty"`
}

// AdvanceResult from ic run advance.
type AdvanceResult struct {
	Advanced             bool     `json:"advanced"`
	FromPhase            string   `json:"from_phase"`
	ToPhase              string   `json:"to_phase"`
	GateResult           string   `json:"gate_result"`
	GateTier             string   `json:"gate_tier"`
	Reason               string   `json:"reason,omitempty"`
	EventType            string   `json:"event_type"`
	ActiveAgentCount     int      `json:"active_agent_count,omitempty"`
	NextGateRequirements []string `json:"next_gate_requirements,omitempty"`
}

// Artifact from ic run artifact list.
type Artifact struct {
	ID    string `json:"id,omitempty"`
	RunID string `json:"run_id"`
	Phase string `json:"phase"`
	Path  string `json:"path"`
	Type  string `json:"type,omitempty"`
}

// TokenAgg from ic run tokens.
type TokenAgg struct {
	InputTokens  int64 `json:"input_tokens"`
	OutputTokens int64 `json:"output_tokens"`
}

// RunAction from ic run action list.
type RunAction struct {
	Command  string `json:"command"`
	Phase    string `json:"phase"`
	Mode     string `json:"mode,omitempty"`
	Priority int    `json:"priority,omitempty"`
	Args     string `json:"args,omitempty"`
}

// RunAgent from ic run agent list.
type RunAgent struct {
	ID        string `json:"id"`
	RunID     string `json:"run_id"`
	AgentType string `json:"agent_type"`
	Name      string `json:"name,omitempty"`
	Status    string `json:"status"`
	CreatedAt string `json:"created_at,omitempty"`
}

// SprintState is the JSON output of sprint-read-state.
type SprintState struct {
	ID            string            `json:"id"`
	Phase         string            `json:"phase"`
	Artifacts     map[string]string `json:"artifacts"`
	History       map[string]string `json:"history"`
	Complexity    string            `json:"complexity"`
	AutoAdvance   string            `json:"auto_advance"`
	ActiveSession string            `json:"active_session"`
	TokenBudget   int64             `json:"token_budget"`
	TokensSpent   int64             `json:"tokens_spent"`
}

// ActiveSprint is one entry in the sprint-find-active result.
type ActiveSprint struct {
	ID    string `json:"id"`
	Title string `json:"title"`
	Phase string `json:"phase"`
	RunID string `json:"run_id"`
}

// Checkpoint is the JSON checkpoint format stored in ic state.
type Checkpoint struct {
	Bead           string   `json:"bead,omitempty"`
	Phase          string   `json:"phase,omitempty"`
	PlanPath       string   `json:"plan_path,omitempty"`
	GitSHA         string   `json:"git_sha,omitempty"`
	UpdatedAt      string   `json:"updated_at,omitempty"`
	CompletedSteps []string `json:"completed_steps,omitempty"`
	KeyDecisions   []string `json:"key_decisions,omitempty"`
}
