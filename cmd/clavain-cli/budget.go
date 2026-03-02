package main

import (
	"encoding/json"
	"fmt"
	"math"
	"os"
	"path/filepath"
	"strconv"
	"strings"
	"time"
)

// ─── Pure Functions (no subprocess calls — unit testable) ───────────

// phaseCostEstimate returns the estimated billing tokens for a phase.
// Matches _sprint_phase_cost_estimate() in lib-sprint.sh.
func phaseCostEstimate(phase string) int64 {
	switch phase {
	case "brainstorm":
		return 30000
	case "brainstorm-reviewed":
		return 15000
	case "strategized":
		return 25000
	case "planned":
		return 35000
	case "plan-reviewed":
		return 50000
	case "executing":
		return 150000
	case "shipping":
		return 100000
	case "reflect":
		return 10000
	case "done":
		return 5000
	default:
		return 30000
	}
}

// phaseToStage maps sprint phases to macro-stage names.
// Matches _sprint_phase_to_stage() in lib-sprint.sh.
func phaseToStage(phase string) string {
	switch phase {
	case "brainstorm":
		return "discover"
	case "brainstorm-reviewed", "strategized", "planned", "plan-reviewed":
		return "design"
	case "executing":
		return "build"
	case "shipping":
		return "ship"
	case "reflect":
		return "reflect"
	case "done":
		return "done"
	default:
		return "unknown"
	}
}

// budgetRemaining computes remaining tokens, clamped to >= 0.
func budgetRemaining(budget, spent int64) int64 {
	rem := budget - spent
	if rem < 0 {
		return 0
	}
	return rem
}

// stageAllocation computes the allocated budget for a stage.
// Returns max(totalBudget * sharePct / 100, minTokens).
func stageAllocation(totalBudget int64, sharePct int, minTokens int64) int64 {
	alloc := totalBudget * int64(sharePct) / 100
	if alloc < minTokens {
		return minTokens
	}
	return alloc
}

// allStages is the ordered list of macro-stages for budget allocation.
var allStages = []string{"discover", "design", "build", "ship", "reflect"}

// allPhases is the canonical ordered phase sequence for a sprint.
var allPhases = []string{
	"brainstorm", "brainstorm-reviewed", "strategized", "planned",
	"plan-reviewed", "executing", "shipping", "reflect", "done",
}

// phasesAfter returns the phases remaining after currentPhase (exclusive).
// Unknown phase returns all phases (conservative — assumes nothing done).
func phasesAfter(currentPhase string) []string {
	for i, p := range allPhases {
		if p == currentPhase {
			if i+1 >= len(allPhases) {
				return nil
			}
			return allPhases[i+1:]
		}
	}
	return allPhases // unknown phase → return all (conservative)
}

// tokensToUSD converts token counts to USD using API pricing.
// Matches cost-query.sh pricing: opus $15/$75, sonnet $3/$15, haiku $1/$5 per million.
func tokensToUSD(model string, inputTokens, outputTokens int64) float64 {
	var inputRate, outputRate float64
	switch {
	case strings.Contains(model, "opus-4"):
		inputRate, outputRate = 15.0, 75.0
	case strings.Contains(model, "sonnet-4"):
		inputRate, outputRate = 3.0, 15.0
	case strings.Contains(model, "haiku-4"):
		inputRate, outputRate = 1.0, 5.0
	default:
		inputRate, outputRate = 3.0, 15.0 // default to sonnet pricing
	}
	cost := float64(inputTokens)*inputRate/1_000_000 + float64(outputTokens)*outputRate/1_000_000
	return math.Round(cost*10000) / 10000
}

// remainingEstimateUSD sums phaseCostEstimate for each phase and converts to USD.
// Uses the given model for pricing (typically "claude-sonnet-4-6").
func remainingEstimateUSD(phases []string, model string) float64 {
	if len(phases) == 0 {
		return 0
	}
	var totalInput, totalOutput int64
	for _, phase := range phases {
		est := phaseCostEstimate(phase)
		totalInput += est * 60 / 100
		totalOutput += est - (est * 60 / 100)
	}
	return tokensToUSD(model, totalInput, totalOutput)
}

// CostSnapshot mirrors cost-query.sh cost-snapshot output.
type CostSnapshot struct {
	BeadID       string           `json:"bead_id"`
	CapturedAt   string           `json:"captured_at"`
	TotalCostUSD float64          `json:"total_cost_usd"`
	ByModel      []CostModelEntry `json:"by_model"`
	PhasesSeen   []string         `json:"phases_seen"`
}

// CostModelEntry is one row of per-model cost data.
type CostModelEntry struct {
	Model        string  `json:"model"`
	Runs         int64   `json:"runs"`
	InputTokens  int64   `json:"input_tokens"`
	OutputTokens int64   `json:"output_tokens"`
	CostUSD      float64 `json:"cost_usd"`
}

// CostEstimateEntry records a point-in-time cost estimate for tracking accuracy.
type CostEstimateEntry struct {
	Phase             string  `json:"phase"`
	Timestamp         string  `json:"timestamp"`
	EstimatedTotalUSD float64 `json:"estimated_total_usd"`
	ActualSoFarUSD    float64 `json:"actual_so_far_usd"`
	RemainingEstUSD   float64 `json:"remaining_estimate_usd"`
	EstimationSource  string  `json:"estimation_source"`
}

// ─── Subprocess Helpers ─────────────────────────────────────────────

// resolveRunID is defined in sprint.go (cached version).

// readBudgetResult gets the budget result for a run, which includes tokens_used.
func readBudgetResult(runID string) (BudgetResult, error) {
	var br BudgetResult
	if err := runICJSON(&br, "run", "budget", runID); err != nil {
		return BudgetResult{}, err
	}
	return br, nil
}

// PhaseTokens stores per-phase token usage.
type PhaseTokens map[string]TokenAgg

// readPhaseTokens reads the phase_tokens state for a run.
func readPhaseTokens(runID string) (PhaseTokens, error) {
	out, err := runIC("state", "get", "phase_tokens", runID)
	if err != nil {
		return PhaseTokens{}, nil // no state yet
	}
	s := string(out)
	if s == "" || s == "null" {
		return PhaseTokens{}, nil
	}
	var pt PhaseTokens
	if err := json.Unmarshal(out, &pt); err != nil {
		return PhaseTokens{}, nil
	}
	return pt, nil
}

// StageBudgetSpec holds per-stage budget config from the agency spec.
type StageBudgetSpec struct {
	Share     int   `json:"share"`
	MinTokens int64 `json:"min_tokens"`
}

// specGetBudget attempts to read the budget config for a given stage
// from the agency spec via ic. Returns ok=false if spec unavailable.
func specGetBudget(stage string) (StageBudgetSpec, bool) {
	if !specAvailable() {
		return StageBudgetSpec{}, false
	}

	// Use ic spec get-budget (handles YAML parsing on the ic side)
	out, err := runIC("spec", "get-budget", stage)
	if err != nil || len(out) == 0 {
		return StageBudgetSpec{}, false
	}

	var sb StageBudgetSpec
	if err := json.Unmarshal(out, &sb); err != nil {
		return StageBudgetSpec{}, false
	}
	if sb.Share == 0 {
		sb.Share = 20
	}
	if sb.MinTokens == 0 {
		sb.MinTokens = 1000
	}
	return sb, true
}

// specAvailable returns true if an agency spec file exists.
func specAvailable() bool {
	return findSpecPath() != ""
}

// findSpecPath resolves the agency spec YAML path.
// Resolution order:
//  1. ${PROJECT_DIR}/.clavain/agency-spec.yaml
//  2. Plugin default config/agency-spec.yaml (not available from Go CLI)
func findSpecPath() string {
	// Check project override first
	projectDir := os.Getenv("SPRINT_LIB_PROJECT_DIR")
	if projectDir == "" {
		projectDir = "."
	}
	override := projectDir + "/.clavain/agency-spec.yaml"
	if _, err := os.Stat(override); err == nil {
		return override
	}

	// Check CLAVAIN_DIR config default
	clavainDir := os.Getenv("CLAVAIN_DIR")
	if clavainDir != "" {
		dflt := clavainDir + "/config/agency-spec.yaml"
		if _, err := os.Stat(dflt); err == nil {
			return dflt
		}
	}

	return ""
}

// sumAllStageAllocations computes the uncapped sum of all stage allocations.
// Used for the overallocation cap.
func sumAllStageAllocations(totalBudget int64) int64 {
	if totalBudget == 0 {
		return 0
	}
	var sum int64
	for _, stage := range allStages {
		sb, ok := specGetBudget(stage)
		if !ok {
			continue
		}
		share := sb.Share
		minTok := sb.MinTokens
		if share <= 0 {
			share = 20
		}
		if minTok <= 0 {
			minTok = 1000
		}
		alloc := stageAllocation(totalBudget, share, minTok)
		sum += alloc
	}
	return sum
}

// ─── Command Functions ──────────────────────────────────────────────

// cmdBudgetRemaining outputs the remaining token budget for a sprint.
// Output: integer on stdout. "0" for unknown beads.
func cmdBudgetRemaining(args []string) error {
	if len(args) < 1 || args[0] == "" {
		fmt.Println("0")
		return nil
	}
	beadID := args[0]

	runID, err := resolveRunID(beadID)
	if err != nil {
		fmt.Println("0")
		return nil
	}

	br, err := readBudgetResult(runID)
	if err != nil {
		fmt.Println("0")
		return nil
	}

	if br.TokenBudget == 0 {
		fmt.Println("0")
		return nil
	}

	rem := budgetRemaining(br.TokenBudget, br.TokensUsed)
	fmt.Println(rem)
	return nil
}

// cmdBudgetTotal outputs the total token budget for a sprint.
// Output: integer on stdout. "0" for unknown beads.
func cmdBudgetTotal(args []string) error {
	if len(args) < 1 || args[0] == "" {
		fmt.Println("0")
		return nil
	}
	beadID := args[0]

	runID, err := resolveRunID(beadID)
	if err != nil {
		fmt.Println("0")
		return nil
	}

	var run Run
	if err := runICJSON(&run, "run", "status", runID); err != nil {
		fmt.Println("0")
		return nil
	}

	fmt.Println(run.TokenBudget)
	return nil
}

// cmdBudgetStage outputs the allocated budget for a stage.
// Without spec, returns total budget (no per-stage breakdown).
func cmdBudgetStage(args []string) error {
	if len(args) < 2 || args[0] == "" || args[1] == "" {
		fmt.Println("0")
		return nil
	}
	beadID := args[0]
	stage := args[1]

	// Get total budget
	runID, err := resolveRunID(beadID)
	if err != nil {
		fmt.Println("0")
		return nil
	}

	var run Run
	if err := runICJSON(&run, "run", "status", runID); err != nil {
		fmt.Println("0")
		return nil
	}

	totalBudget := run.TokenBudget
	if totalBudget == 0 {
		fmt.Println("0")
		return nil
	}

	// Without spec, return total budget
	if !specAvailable() {
		fmt.Println(totalBudget)
		return nil
	}

	sb, ok := specGetBudget(stage)
	if !ok {
		fmt.Println(totalBudget)
		return nil
	}

	share := sb.Share
	minTok := sb.MinTokens
	if share <= 0 {
		share = 20
	}
	if minTok <= 0 {
		minTok = 1000
	}

	allocated := stageAllocation(totalBudget, share, minTok)

	// Cap: if all stages' min_tokens push total above budget, scale down
	uncappedSum := sumAllStageAllocations(totalBudget)
	if uncappedSum > totalBudget && uncappedSum > 0 {
		allocated = allocated * totalBudget / uncappedSum
	}

	fmt.Println(allocated)
	return nil
}

// cmdBudgetStageRemaining outputs remaining budget for a stage (allocated - spent).
func cmdBudgetStageRemaining(args []string) error {
	if len(args) < 2 || args[0] == "" || args[1] == "" {
		fmt.Println("0")
		return nil
	}
	beadID := args[0]
	stage := args[1]

	// Get allocated by capturing cmdBudgetStage output
	allocated := getBudgetStage(beadID, stage)
	spent := getStageTokensSpent(beadID, stage)

	rem := budgetRemaining(allocated, spent)
	fmt.Println(rem)
	return nil
}

// cmdBudgetStageCheck checks if stage budget is exceeded.
// Exits 0 if within budget, returns error (exit 1) with stderr message if exceeded.
func cmdBudgetStageCheck(args []string) error {
	if len(args) < 2 || args[0] == "" || args[1] == "" {
		return nil // no budget to check
	}
	beadID := args[0]
	stage := args[1]

	allocated := getBudgetStage(beadID, stage)
	spent := getStageTokensSpent(beadID, stage)

	rem := budgetRemaining(allocated, spent)
	if rem <= 0 {
		fmt.Fprintf(os.Stderr, "budget_exceeded|%s|stage budget depleted\n", stage)
		os.Exit(1)
	}
	return nil
}

// cmdStageTokensSpent outputs the sum of tokens spent across all phases
// belonging to a given stage.
func cmdStageTokensSpent(args []string) error {
	if len(args) < 2 || args[0] == "" || args[1] == "" {
		fmt.Println("0")
		return nil
	}
	beadID := args[0]
	stage := args[1]

	spent := getStageTokensSpent(beadID, stage)
	fmt.Println(spent)
	return nil
}

// cmdRecordPhaseTokens records phase token usage to ic state.
// Tries interstat for actual data first, falls back to estimates.
func cmdRecordPhaseTokens(args []string) error {
	if len(args) < 2 || args[0] == "" || args[1] == "" {
		return nil
	}
	beadID := args[0]
	phase := args[1]

	runID, err := resolveRunID(beadID)
	if err != nil {
		return nil // silently skip if no run
	}

	// Try actual data from interstat (session-scoped billing tokens)
	var actualTokens int64
	sessionID := os.Getenv("CLAUDE_SESSION_ID")
	if sessionID != "" {
		dbPath := os.Getenv("HOME") + "/.claude/interstat/metrics.db"
		if _, err := os.Stat(dbPath); err == nil {
			// Query interstat via sqlite3 CLI (no Go sqlite dependency)
			query := fmt.Sprintf(
				"SELECT COALESCE(SUM(COALESCE(input_tokens,0) + COALESCE(output_tokens,0)), 0) FROM agent_runs WHERE session_id='%s'",
				sessionID,
			)
			out, err := runCommand("sqlite3", dbPath, query)
			if err == nil {
				if v, err := strconv.ParseInt(strings.TrimSpace(string(out)), 10, 64); err == nil {
					actualTokens = v
				}
			}
		}
	}

	var inTokens, outTokens int64
	if actualTokens > 0 {
		inTokens = actualTokens * 60 / 100
		outTokens = actualTokens - inTokens
	} else {
		estimate := phaseCostEstimate(phase)
		inTokens = estimate * 60 / 100
		outTokens = estimate - inTokens
	}

	// Read existing phase tokens
	pt, _ := readPhaseTokens(runID)
	if pt == nil {
		pt = PhaseTokens{}
	}

	// Update
	pt[phase] = TokenAgg{
		InputTokens:  inTokens,
		OutputTokens: outTokens,
	}

	// Write back via ic state set
	data, err := json.Marshal(pt)
	if err != nil {
		return nil
	}

	// ic state set reads JSON from stdin
	writeICState("phase_tokens", runID, string(data))
	return nil
}

// ─── Cost Recording Commands ────────────────────────────────────────

// findInterstatScript locates cost-query.sh across environments.
// Resolution: plugin cache → CLAVAIN_SOURCE_DIR → empty (skip).
func findInterstatScript() string {
	// Plugin cache (Claude Code sessions)
	pluginRoot := os.Getenv("CLAUDE_PLUGIN_ROOT")
	if pluginRoot != "" {
		// interstat lives alongside clavain in the plugin cache
		candidate := filepath.Join(filepath.Dir(pluginRoot), "interstat", "scripts", "cost-query.sh")
		if _, err := os.Stat(candidate); err == nil {
			return candidate
		}
	}

	// CLAVAIN_SOURCE_DIR (development / monorepo)
	sourceDir := os.Getenv("CLAVAIN_SOURCE_DIR")
	if sourceDir != "" {
		candidate := filepath.Join(sourceDir, "..", "..", "interverse", "interstat", "scripts", "cost-query.sh")
		if _, err := os.Stat(candidate); err == nil {
			return candidate
		}
	}

	return ""
}

// cmdRecordCostActuals persists a full cost snapshot for a bead.
// Best-effort: silent on failure.
func cmdRecordCostActuals(args []string) error {
	if len(args) < 1 || args[0] == "" {
		return nil
	}
	beadID := args[0]

	script := findInterstatScript()
	if script == "" {
		return nil
	}

	// Run cost-snapshot query
	out, err := runCommand("bash", script, "cost-snapshot", "--bead="+beadID)
	if err != nil {
		return nil
	}

	// Validate JSON
	var snapshot CostSnapshot
	if err := json.Unmarshal(out, &snapshot); err != nil {
		return nil
	}

	runID, err := resolveRunID(beadID)
	if err != nil {
		return nil
	}

	// Persist full snapshot to ic state
	writeICState("cost_actuals", runID, string(out))

	// Set scalar on bead for quick lookup
	totalStr := strconv.FormatFloat(snapshot.TotalCostUSD, 'f', 4, 64)
	_, _ = runBD("set-state", beadID, "cost_usd="+totalStr)

	return nil
}

// cmdRecordCostEstimate records a point-in-time cost estimate for a phase.
// Appends to the cost_estimates array (read-append-write).
// Best-effort: silent on failure.
func cmdRecordCostEstimate(args []string) error {
	if len(args) < 2 || args[0] == "" || args[1] == "" {
		return nil
	}
	beadID := args[0]
	phase := args[1]

	runID, err := resolveRunID(beadID)
	if err != nil {
		return nil
	}

	// Get actual spend so far via cost-snapshot
	var actualUSD float64
	script := findInterstatScript()
	if script != "" {
		out, err := runCommand("bash", script, "cost-snapshot", "--bead="+beadID)
		if err == nil {
			var snapshot CostSnapshot
			if json.Unmarshal(out, &snapshot) == nil {
				actualUSD = snapshot.TotalCostUSD
			}
		}
	}

	// Compute remaining estimate
	remaining := phasesAfter(phase)
	remainingUSD := remainingEstimateUSD(remaining, "claude-sonnet-4-6")

	entry := CostEstimateEntry{
		Phase:             phase,
		Timestamp:         time.Now().UTC().Format(time.RFC3339),
		EstimatedTotalUSD: math.Round((actualUSD+remainingUSD)*10000) / 10000,
		ActualSoFarUSD:    actualUSD,
		RemainingEstUSD:   remainingUSD,
		EstimationSource:  "phase-estimate+interstat",
	}

	// Read existing estimates array
	var estimates []CostEstimateEntry
	existingOut, err := runIC("state", "get", "cost_estimates", runID)
	if err == nil {
		s := strings.TrimSpace(string(existingOut))
		if s != "" && s != "null" {
			_ = json.Unmarshal(existingOut, &estimates)
		}
	}

	estimates = append(estimates, entry)

	data, err := json.Marshal(estimates)
	if err != nil {
		return nil
	}

	writeICState("cost_estimates", runID, string(data))
	return nil
}

// ─── Internal Helpers ───────────────────────────────────────────────

// getBudgetStage returns the allocated budget for a stage (internal helper).
func getBudgetStage(beadID, stage string) int64 {
	runID, err := resolveRunID(beadID)
	if err != nil {
		return 0
	}

	var run Run
	if err := runICJSON(&run, "run", "status", runID); err != nil {
		return 0
	}

	totalBudget := run.TokenBudget
	if totalBudget == 0 {
		return 0
	}

	if !specAvailable() {
		return totalBudget
	}

	sb, ok := specGetBudget(stage)
	if !ok {
		return totalBudget
	}

	share := sb.Share
	minTok := sb.MinTokens
	if share <= 0 {
		share = 20
	}
	if minTok <= 0 {
		minTok = 1000
	}

	allocated := stageAllocation(totalBudget, share, minTok)

	uncappedSum := sumAllStageAllocations(totalBudget)
	if uncappedSum > totalBudget && uncappedSum > 0 {
		allocated = allocated * totalBudget / uncappedSum
	}

	return allocated
}

// getStageTokensSpent returns the sum of tokens spent for all phases
// belonging to a given stage (internal helper).
func getStageTokensSpent(beadID, stage string) int64 {
	runID, err := resolveRunID(beadID)
	if err != nil {
		return 0
	}

	pt, _ := readPhaseTokens(runID)
	if pt == nil {
		return 0
	}

	var total int64
	for phase, agg := range pt {
		if phaseToStage(phase) == stage {
			total += agg.InputTokens + agg.OutputTokens
		}
	}
	return total
}

// runCommand runs an arbitrary command and returns stdout.
func runCommand(name string, args ...string) ([]byte, error) {
	return runCommandExec(name, args...)
}

// writeICState writes JSON to ic state set via stdin pipe.
func writeICState(key, scopeID, jsonData string) {
	bin, err := findIC()
	if err != nil {
		return
	}
	cmd := execCommand(bin, "state", "set", key, scopeID)
	cmd.Stdin = strings.NewReader(jsonData + "\n")
	cmd.Stderr = os.Stderr
	_ = cmd.Run()
}
